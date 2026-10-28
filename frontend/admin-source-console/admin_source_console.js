const state = {
  candidates: [],
  selectedCandidateId: "",
  operatorToken: "",
  authEpoch: 0,
  operations: {},
  busy: new Set(),
};
const pendingRequests = new Set();
const REQUEST_TIMEOUT_MS = 30000;
const operationButtons = {
  connect: ["connectOperatorButton"],
  create: ["createCandidateButton"],
  candidates: ["refreshCandidatesButton"],
  review: ["approveButton", "rejectButton", "needsReviewButton"],
  registry: ["registryReadyButton"],
  dryRun: ["dryRunButton"],
};

const els = {
  operatorTokenInput: document.getElementById("operatorTokenInput"),
  authStatus: document.getElementById("authStatus"),
  urlInput: document.getElementById("urlInput"),
  scenarioInput: document.getElementById("scenarioInput"),
  riskLevelInput: document.getElementById("riskLevelInput"),
  languageInput: document.getElementById("languageInput"),
  cityInput: document.getElementById("cityInput"),
  allowNetworkInput: document.getElementById("allowNetworkInput"),
  confirmNetworkInput: document.getElementById("confirmNetworkInput"),
  previewOutput: document.getElementById("previewOutput"),
  candidateList: document.getElementById("candidateList"),
  candidateCount: document.getElementById("candidateCount"),
  registryReadyCount: document.getElementById("registryReadyCount"),
  candidateIdInput: document.getElementById("candidateIdInput"),
  reviewerIdInput: document.getElementById("reviewerIdInput"),
  sourceTypeInput: document.getElementById("sourceTypeInput"),
  trustLevelInput: document.getElementById("trustLevelInput"),
  freshnessNoteInput: document.getElementById("freshnessNoteInput"),
  reasonInput: document.getElementById("reasonInput"),
  allowRetrievalInput: document.getElementById("allowRetrievalInput"),
  reviewOutput: document.getElementById("reviewOutput"),
  registryOutput: document.getElementById("registryOutput"),
  dryRunOutput: document.getElementById("dryRunOutput"),
};

document.getElementById("createCandidateButton").addEventListener("click", createCandidate);
document.getElementById("refreshCandidatesButton").addEventListener("click", loadCandidates);
document.getElementById("approveButton").addEventListener("click", () => reviewCandidate("approve"));
document.getElementById("rejectButton").addEventListener("click", () => reviewCandidate("reject"));
document.getElementById("needsReviewButton").addEventListener("click", () => reviewCandidate("needs_review"));
document.getElementById("registryReadyButton").addEventListener("click", loadRegistryReady);
document.getElementById("dryRunButton").addEventListener("click", prepareDryRun);
document.getElementById("connectOperatorButton").addEventListener("click", connectOperator);
document.getElementById("disconnectOperatorButton").addEventListener("click", disconnectOperator);
window.addEventListener("pagehide", disconnectOperator);

loadCandidates();

async function connectOperator() {
  if (state.busy.has("connect")) return;
  const token = els.operatorTokenInput.value.trim();
  disconnectOperator();
  els.operatorTokenInput.value = "";
  const localHost = ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
  if (token && window.location.protocol !== "https:" && !localHost) {
    els.authStatus.textContent = "A token requires HTTPS or localhost.";
    return;
  }
  state.operatorToken = token;
  return runOperation("connect", els.authStatus, async (current) => {
    const result = await getJson("/api/admin/auth/check");
    if (!current()) return;
    if (!result.authenticated) {
      state.operatorToken = "";
      els.authStatus.textContent = result.error ? result.detail : "Access denied. Check the operator token and permissions.";
      return;
    }
    els.authStatus.textContent = result.reason === "auth_disabled_local_dev"
      ? "Local/demo access: authentication is disabled."
      : "Operator connected. Token is held in memory only.";
    await loadCandidates();
  });
}

function disconnectOperator() {
  state.authEpoch += 1;
  state.operations = {};
  state.busy.clear();
  pendingRequests.forEach((pending) => pending.cancel());
  updateControls();
  state.operatorToken = "";
  els.operatorTokenInput.value = "";
  state.candidates = [];
  state.selectedCandidateId = "";
  els.candidateList.textContent = "";
  els.candidateIdInput.value = "";
  els.candidateCount.textContent = "0";
  els.registryReadyCount.textContent = "0";
  [els.previewOutput, els.reviewOutput, els.registryOutput, els.dryRunOutput].forEach((element) => render(element, "Disconnected."));
  els.authStatus.textContent = "Disconnected. Token cleared.";
}

async function createCandidate() {
  if (state.busy.has("create")) return;
  const payload = {
    url: els.urlInput.value.trim(),
    scenario: valueOrNull(els.scenarioInput.value),
    risk_level: valueOrNull(els.riskLevelInput.value),
    language: valueOrNull(els.languageInput.value),
    city: valueOrNull(els.cityInput.value),
    allow_network: els.allowNetworkInput.checked,
    confirm_network: els.confirmNetworkInput.checked,
  };
  if (!payload.url) {
    render(els.previewOutput, { error: "URL is required." });
    return;
  }
  return runOperation("create", els.previewOutput, async (current) => {
    render(els.previewOutput, "Creating pending candidate...");
    const result = await postJson("/api/admin/source-url/preview", payload);
    if (!current()) return;
    render(els.previewOutput, result);
    if (result.error) return;
    if (result.candidate && result.candidate.candidate_id) selectCandidate(result.candidate.candidate_id);
    await loadCandidates();
  });
}

async function loadCandidates() {
  return runOperation("candidates", els.previewOutput, async (current) => {
    const result = await getJson("/api/admin/source-candidates");
    if (!current()) return;
    if (result.error) {
      render(els.previewOutput, result);
      return;
    }
    state.candidates = result.candidates || [];
    els.candidateCount.textContent = String(state.candidates.length);
    els.candidateList.innerHTML = "";
    if (!state.candidates.length) {
      els.candidateList.textContent = "No candidates yet.";
      return;
    }
    state.candidates.forEach((candidate) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "candidate-row";
      row.innerHTML = `
      <strong>${escapeHtml(candidate.title || candidate.candidate_id)}</strong>
      <span>${escapeHtml(candidate.candidate_id)}</span>
      <span>status=${escapeHtml(candidate.status)}</span>
      <span>requires_review=${candidate.requires_review}</span>
      <span>allow_retrieval=${candidate.allow_retrieval}</span>
    `;
      row.addEventListener("click", () => selectCandidate(candidate.candidate_id));
      els.candidateList.appendChild(row);
    });
  }, true);
}

function selectCandidate(candidateId) {
  state.selectedCandidateId = candidateId;
  els.candidateIdInput.value = candidateId;
}

async function reviewCandidate(action) {
  if (state.busy.has("review")) return;
  const candidateId = els.candidateIdInput.value.trim();
  if (!candidateId) {
    render(els.reviewOutput, { error: "Candidate ID is required." });
    return;
  }
  const payload = {
    action,
    reviewer_id: els.reviewerIdInput.value.trim() || "local-demo-reviewer",
    reason: els.reasonInput.value.trim() || "Reviewed in local demo console.",
    assigned_source_type: action === "approve" ? els.sourceTypeInput.value : null,
    assigned_trust_level: action === "approve" ? els.trustLevelInput.value : null,
    allow_retrieval: action === "approve" ? els.allowRetrievalInput.checked : false,
    freshness_note: action === "approve" ? els.freshnessNoteInput.value.trim() : null,
    notes: "No automatic trusted registry write.",
  };
  return runOperation("review", els.reviewOutput, async (current) => {
    render(els.reviewOutput, "Submitting review...");
    const result = await postJson(`/api/admin/source-candidates/${encodeURIComponent(candidateId)}/review`, payload);
    if (!current()) return;
    render(els.reviewOutput, result);
    if (!result.error) await loadCandidates();
  });
}

async function loadRegistryReady() {
  return runOperation("registry", els.registryOutput, async (current) => {
    const result = await getJson("/api/admin/source-candidates/registry-ready/list");
    if (!current()) return;
    if (result.error) { render(els.registryOutput, result); return; }
    els.registryReadyCount.textContent = String(result.total || 0);
    render(els.registryOutput, {
      registry_modified: false,
      total: result.total,
      sources: result.sources,
      warnings: result.warnings,
    });
  }, true);
}

async function prepareDryRun() {
  return runOperation("dryRun", els.dryRunOutput, async (current) => {
    const result = await postJson("/api/admin/source-ingestion/prepare-dry-run", {
      target_registry_file: "data/sources/official_sources.jsonl",
    });
    if (current()) render(els.dryRunOutput, result);
  });
}

function updateControls() {
  Object.keys(operationButtons).forEach((key) => {
    operationButtons[key].forEach((id) => { document.getElementById(id).disabled = state.busy.has(key); });
  });
}

async function runOperation(key, output, action, refresh = false) {
  if (state.busy.has(key) && !refresh) return;
  const operations = state.operations;
  const generation = (operations[key] || 0) + 1;
  const epoch = state.authEpoch;
  operations[key] = generation;
  const current = () => epoch === state.authEpoch && operations === state.operations && operations[key] === generation;
  state.busy.add(key);
  updateControls();
  try {
    await action(current);
  } catch (error) {
    if (current() && !error.stale) render(output, { error: "network", detail: error.message });
  } finally {
    if (current()) { state.busy.delete(key); updateControls(); }
  }
}

function assertSession(epoch) {
  if (epoch !== state.authEpoch) {
    const error = new Error("The operator session changed.");
    error.stale = true;
    throw error;
  }
}

async function getJson(url) {
  return apiRequest(url, { method: "GET" });
}

async function postJson(url, payload) {
  return apiRequest(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function apiRequest(url, options) {
  const epoch = state.authEpoch;
  const headers = Object.assign({}, options.headers || {});
  if (state.operatorToken) headers.Authorization = `Bearer ${state.operatorToken}`;
  const controller = new AbortController();
  let rejectRequest;
  const interruption = new Promise((_, reject) => { rejectRequest = reject; });
  const pending = { cancel() {
    const error = new Error("The operator session changed."); error.stale = true;
    rejectRequest(error); controller.abort();
  } };
  pendingRequests.add(pending);
  const timer = setTimeout(() => {
    rejectRequest(new Error("The request timed out. Check the connection and retry."));
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  try {
    return await Promise.race([interruption, (async () => {
      const response = await fetch(url, Object.assign({}, options, {
        headers, signal: controller.signal, cache: "no-store", credentials: "omit"
      }));
      assertSession(epoch);
      if (!pendingRequests.has(pending)) throw new Error("The request is no longer active.");
      const result = await handleResponse(response);
      assertSession(epoch);
      if (!pendingRequests.has(pending)) throw new Error("The request is no longer active.");
      if (response.status === 401) {
        disconnectOperator();
        els.authStatus.textContent = "Operator token required or expired. Connect again.";
      }
      return result;
    })()]);
  } finally {
    clearTimeout(timer);
    pendingRequests.delete(pending);
  }
}

async function handleResponse(response) {
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text };
  }
  if (!response.ok) {
    return { error: response.status, detail: payload.detail || payload };
  }
  return payload;
}

function render(element, value) {
  element.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function valueOrNull(value) {
  const trimmed = String(value || "").trim();
  return trimmed || null;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
