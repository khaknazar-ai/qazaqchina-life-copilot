const config = require("./config");
const clientContext = require("./clientContext");

const DEFAULT_TIMEOUT = 15000;

function request(path, options = {}) {
  return sendRequest(path, options, false);
}

function sendRequest(path, options, retried) {
  const ownerEpoch = clientContext.getOwnerEpoch();
  const token = clientContext.getPilotAccessToken();
  const workspaceToken = clientContext.getWorkspaceSessionToken();
  const app = typeof getApp === "function" ? getApp() : null;
  const baseUrl = normalizeBaseUrl(app && app.globalData && app.globalData.apiBaseUrl
    || config.API_BASE_URL);
  const method = options.method || "GET";
  const data = options.data || {};
  const header = Object.assign(
    {
      "content-type": "application/json"
    },
    options.header || {}
  );
  if (token) header.Authorization = `Bearer ${token}`;
  if (workspaceToken) header["X-Workspace-Session"] = workspaceToken;
  const carriesCredential = Object.keys(header).some((name) =>
    /^(authorization|x-workspace-session)$/i.test(name) && Boolean(header[name]));
  if (carriesCredential && !/^https:\/\//i.test(baseUrl) && !/^http:\/\/(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$/i.test(baseUrl)) {
    return Promise.reject(new Error("Authenticated access requires HTTPS or a loopback server."));
  }

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${baseUrl}${path}`,
      method,
      data,
      header,
      timeout: options.timeout || DEFAULT_TIMEOUT,
      success(response) {
        if (ownerEpoch !== clientContext.getOwnerEpoch()) {
          const error = new Error("Session changed"); error.stale = true; reject(error); return;
        }
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data);
          return;
        }
        const error = new Error(readableApiError(response));
        error.status = response.statusCode;
        if (response.statusCode === 401 && !retried
          && /^\/api\/workspace(?:\/|$)/.test(path) && token) {
          recoverLocalDemoAccess(ownerEpoch, token).then((recovered) => {
            if (!recovered) { reject(error); return; }
            sendRequest(path, options, true).then(resolve, reject);
          }, reject);
          return;
        }
        reject(error);
      },
      fail(error) {
        if (ownerEpoch !== clientContext.getOwnerEpoch()) { const stale = new Error("Session changed"); stale.stale = true; reject(stale); return; }
        reject(new Error(error.errMsg || "Backend request failed."));
      }
    });
  });
}

let capabilitiesPending = null;
let localSigninPending = null;
let localRecoveryPending = null;

function startLocalSignin(accountType = "citizen") {
  return request("/api/local-access/start", {
    method: "POST", data: { account_type: accountType }, header: { "X-Q-Local-Access": "devtools" }
  });
}

function recoverLocalDemoAccess(ownerEpoch, rejectedToken) {
  if (!config.DEMO_MODE || !rejectedToken || clientContext.isLocalDemoAutoSigninSuppressed()) {
    return Promise.resolve(false);
  }
  if (localRecoveryPending) return localRecoveryPending;
  const pending = getCapabilities().then((capabilities) => {
    if (ownerEpoch !== clientContext.getOwnerEpoch()
      || rejectedToken !== clientContext.getPilotAccessToken()) return false;
    const flags = capabilities && capabilities.feature_flags || {};
    if (!flags.pilot_access_required || !flags.local_device_signin) return false;
    return startLocalSignin(clientContext.getLocalDemoAccountType()).then((signin) => {
      if (ownerEpoch !== clientContext.getOwnerEpoch()
        || rejectedToken !== clientContext.getPilotAccessToken()) return false;
      if (!/^[\x21-\x7e]{32,256}$/.test(signin.session_token || "")) {
        throw new Error("Invalid local demo session");
      }
      clientContext.replaceLocalPilotAccessToken(signin.session_token);
      clientContext.setLocalDemoAutoSigninSuppressed(false);
      return true;
    });
  }).catch(() => false).finally(() => {
    if (localRecoveryPending === pending) localRecoveryPending = null;
  });
  localRecoveryPending = pending;
  return pending;
}

function getCapabilities() {
  if (capabilitiesPending) return capabilitiesPending;
  capabilitiesPending = request("/api/capabilities").then((capabilities) => {
    const app = typeof getApp === "function" ? getApp() : null;
    if (app && app.globalData) app.globalData.lastCapabilities = capabilities;
    return capabilities;
  }).finally(() => { capabilitiesPending = null; });
  return capabilitiesPending;
}

function ensureFromCapabilities(result, ownerEpoch) {
  if (ownerEpoch !== clientContext.getOwnerEpoch()) {
    const error = new Error("Session changed"); error.stale = true; return Promise.reject(error);
  }
  if (clientContext.getPilotAccessToken()) return null;
  const flags = result && result.feature_flags || {};
  if (!flags.pilot_access_required) return null;
  if (!config.DEMO_MODE || !flags.local_device_signin
    || clientContext.isLocalDemoAutoSigninSuppressed()) {
    const error = new Error("pilot_access_required");
    error.status = 401;
    error.code = "pilot_access_required";
    return Promise.reject(error);
  }
  if (!localSigninPending) {
    const accountType = clientContext.getLocalDemoAccountType();
    const pending = startLocalSignin(accountType).then((signin) => {
      if (ownerEpoch !== clientContext.getOwnerEpoch()) {
        const error = new Error("Session changed"); error.stale = true; throw error;
      }
      if (!/^[\x21-\x7e]{32,256}$/.test(signin.session_token || "")) {
        throw new Error("Invalid local demo session");
      }
      clientContext.setPilotAccessToken(signin.session_token);
      clientContext.setLocalDemoAutoSigninSuppressed(false);
    }).finally(() => {
      if (localSigninPending === pending) localSigninPending = null;
    });
    localSigninPending = pending;
  }
  return localSigninPending;
}

function ensurePilotAccess() {
  if (clientContext.getPilotAccessToken()) return null;
  const app = typeof getApp === "function" ? getApp() : null;
  const cached = app && app.globalData && app.globalData.lastCapabilities;
  const ownerEpoch = clientContext.getOwnerEpoch();
  if (cached) return ensureFromCapabilities(cached, ownerEpoch);
  return getCapabilities().then((result) => ensureFromCapabilities(result, ownerEpoch));
}

function listDemoScenarios() {
  return request("/api/demo/scenarios");
}

function getDemoScenario(scenarioId) {
  return request(`/api/demo/scenarios/${encodeURIComponent(scenarioId)}`);
}

function runDemoScenario(scenarioId) {
  return request("/api/demo/run", {
    method: "POST",
    data: {
      scenario_id: scenarioId,
      use_agent_workflow: true
    }
  });
}

function sendChatMessage(message, options = {}) {
  const access = ensurePilotAccess();
  const send = () => request("/api/chat", {
    method: "POST",
    timeout: 140000,
    data: Object.assign(
      {
        user_message: message,
        session_id: clientContext.getSessionId(),
        preferred_language: clientContext.getPreferredLanguage()
      },
      options
    )
  });
  return access ? access.then(send) : send();
}

function createChecklist(payload) {
  return request("/api/checklists", {
    method: "POST",
    data: Object.assign({ language: clientContext.getPreferredLanguage() }, payload)
  });
}

function explainChineseText(text, options = {}) {
  const access = ensurePilotAccess();
  const send = () => request("/api/translate/explain", {
    method: "POST",
    timeout: 140000,
    data: Object.assign(
      {
        text,
        target_language: clientContext.getPreferredLanguage()
      },
      options
    )
  });
  return access ? access.then(send) : send();
}

function previewPhotoIntake(payload) {
  return request("/api/photo-intake/preview", {
    method: "POST",
    timeout: 140000,
    data: payload
  });
}

function getPhotoIntakeMode() {
  return request("/api/photo-intake/mode");
}

function createFeedback(payload) {
  return request("/api/human-support/feedback", {
    method: "POST",
    data: Object.assign({ session_id: clientContext.getSessionId() }, payload)
  });
}

function createEscalation(payload) {
  return request("/api/human-support/escalations", {
    method: "POST",
    data: Object.assign({ session_id: clientContext.getSessionId() }, payload)
  });
}

function createDeleteRequest(payload) {
  return request("/api/privacy/delete-request", {
    method: "POST",
    data: Object.assign({ session_id: clientContext.getSessionId() }, payload)
  });
}

function getPrivacyPolicies() {
  return request("/api/privacy/policies");
}

function redactPreview(payload) {
  return request("/api/privacy/redact-preview", {
    method: "POST",
    data: payload
  });
}

function createCommunityPost(payload) {
  return request("/api/community/posts", {
    method: "POST",
    data: payload
  });
}

function normalizeBaseUrl(value) {
  return String(value || "").replace(/\/+$/, "");
}

function readableApiError(response) {
  const data = response.data || {};
  if (data.detail && data.detail.error && data.detail.error.message) {
    return data.detail.error.message;
  }
  if (data.detail && typeof data.detail === "string") {
    return data.detail;
  }
  return `Backend request failed with status ${response.statusCode}.`;
}

module.exports = {
  startLocalSignin,
  ensurePilotAccess,
  endLocalSignin: () => request("/api/local-access/logout", { method: "POST" }),
  checkPilotAccess: () => request("/api/access/check"),
  request,
  getCapabilities,
  listDemoScenarios,
  getDemoScenario,
  runDemoScenario,
  sendChatMessage,
  createChecklist,
  explainChineseText,
  previewPhotoIntake,
  getPhotoIntakeMode,
  createFeedback,
  createEscalation,
  createDeleteRequest,
  getPrivacyPolicies,
  redactPreview,
  createCommunityPost
};
