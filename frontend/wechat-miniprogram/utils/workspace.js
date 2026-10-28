const api = require("./api");
const context = require("./clientContext");
let session = null;
let pending = null;
let epoch = -1;

function accessRequiredError() {
  const error = new Error("pilot_access_required");
  error.status = 401;
  error.code = "pilot_access_required";
  return error;
}

function authorizeWorkspaceSession(ownerEpoch) {
  if (context.getPilotAccessToken()) return Promise.resolve(ownerEpoch);
  const app = typeof getApp === "function" ? getApp() : null;
  const cached = app && app.globalData && app.globalData.lastCapabilities;
  const capabilities = cached
    ? Promise.resolve(cached)
    : typeof api.getCapabilities === "function" ? api.getCapabilities() : Promise.resolve(null);
  return capabilities.then((result) => {
    if (ownerEpoch !== context.getOwnerEpoch()) throw staleError();
    if (app && app.globalData) app.globalData.lastCapabilities = result;
    if (typeof api.ensurePilotAccess === "function") {
      return Promise.resolve(api.ensurePilotAccess()).then(() => context.getOwnerEpoch());
    }
    const flags = result && result.feature_flags;
    if (flags && flags.pilot_access_required) throw accessRequiredError();
    return context.getOwnerEpoch();
  });
}

function ensure() {
  let current = context.getOwnerEpoch();
  if (epoch !== current) { session = null; pending = null; epoch = current; }
  if (session) return Promise.resolve(session);
  if (pending) return pending;
  pending = authorizeWorkspaceSession(current).then((authorizedEpoch) => {
    if (authorizedEpoch !== context.getOwnerEpoch()) throw staleError();
    current = authorizedEpoch;
    epoch = current;
    return api.request("/api/workspace/session", { method: "POST", data: {} });
  }).then((value) => {
    if (current !== context.getOwnerEpoch()) throw staleError();
    context.setWorkspaceSessionToken(value.demo_session_token);
    context.setAccount({ account_type: value.account_type || "citizen", local_preview: Boolean(value.local_preview) });
    session = value;
    return value;
  }).finally(() => { if (current === epoch) pending = null; });
  return pending;
}
function staleError() { const error = new Error("Session changed"); error.stale = true; return error; }
function call(path, method = "GET", data = {}) {
  const current = context.getOwnerEpoch();
  return ensure().then(() => {
    if (current !== context.getOwnerEpoch()) throw staleError();
    return api.request(`/api/workspace${path}`, { method, data });
  });
}
function id(value) { return encodeURIComponent(value); }
function query(values = {}) {
  return Object.keys(values).filter((key) => values[key] !== "" && values[key] !== undefined)
    .map((key) => `${id(key)}=${id(values[key])}`).join("&");
}
function requestId() { return `mini-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`; }
function create(path, data) { return call(path, "POST", Object.assign({ client_request_id: requestId() }, data)); }
module.exports = {
  ensure, call, requestId,
  getProfile: () => call("/profile"),
  saveProfile: (data) => call("/profile", "PATCH", data),
  clearProfile: () => call("/profile", "DELETE"),
  listCases: (options) => call(`/cases?${query(options)}`),
  createCase: (data) => create("/cases", data),
  createPlan: (data) => create("/plans", data),
  getCase: (caseId) => call(`/cases/${id(caseId)}`),
  updateCase: (caseId, data) => call(`/cases/${id(caseId)}`, "PATCH", data),
  deleteCase: (caseId) => call(`/cases/${id(caseId)}`, "DELETE"),
  addTask: (caseId, data) => create(`/cases/${id(caseId)}/tasks`, data),
  updateTask: (caseId, taskId, data) => call(`/cases/${id(caseId)}/tasks/${id(taskId)}`, "PATCH", data),
  checklist: (caseId) => call(`/cases/${id(caseId)}/checklist`, "POST", { language: context.getPreferredLanguage() }),
  addDocument: (caseId, data) => create(`/cases/${id(caseId)}/documents`, data),
  updateDocument: (caseId, documentId, data) => call(`/cases/${id(caseId)}/documents/${id(documentId)}`, "PATCH", data),
  deleteDocument: (caseId, documentId) => call(`/cases/${id(caseId)}/documents/${id(documentId)}`, "DELETE"),
  addMessage: (caseId, data) => create(`/cases/${id(caseId)}/messages`, data),
  attachTurn: (caseId, traceId) => call(`/cases/${id(caseId)}/chat-turns`, "POST", { trace_id: traceId }),
  library: (filters) => call(`/library?${query(filters)}`),
  community: (filters) => call(`/community?${query(filters)}`),
  addExperience: (data) => create("/community", data),
  support: () => call("/support"),
  createSupport: (data) => create("/support", data),
  reply: (ticketId, text) => create(`/support/${id(ticketId)}/replies`, { text }),
  updateSupport: (ticketId, status) => call(`/support/${id(ticketId)}`, "PATCH", { status })
};
