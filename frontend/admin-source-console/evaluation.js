(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const root = "/api/admin/evaluation-review";
  const state = { token: "", session: 0, operation: 0, busy: false, actor: null, review: false, records: [], selected: null };
  const pendingRequests = new Set();
  const REQUEST_TIMEOUT_MS = 30000;
  function assertSession(session) {
    if (session !== state.session) {
      const error = new Error("The operator session changed."); error.stale = true;
      throw error;
    }
  }
  const facts = ["nationality", "document", "city", "facility", "department", "contract", "basis", "activity", "on_date"];
  const scenarios = ["tourism", "study", "work", "business", "medical", "documents", "housing", "payments", "transport", "translation", "emergency", "community_experience", "unclear"];
  const risks = ["normal", "medium", "legal_sensitive", "work_status_sensitive", "medical_sensitive", "emergency", "unsafe", "prompt_injection"];
  for (const [id, values] of [["scenario", scenarios], ["risk", risks]]) {
    for (const value of values) {
      const option = document.createElement("option");
      option.textContent = value; option.value = value; $(id).append(option);
    }
  }
  for (const name of facts) {
    const label = document.createElement("label"); label.textContent = name.replaceAll("_", " ");
    const input = document.createElement("input"); input.id = `fact-${name}`;
    input.type = name === "on_date" ? "date" : "text"; input.maxLength = 100;
    label.append(input); $("applicability").append(label);
  }
  const message = (text, error = false) => { $("message").textContent = text; $("message").className = error ? "error" : ""; };
  function controls() {
    $("connect").disabled = state.busy;
    $("disconnect").disabled = !state.token;
    $("refresh").disabled = state.busy || !state.token;
    $("approve").disabled = state.busy || !state.review || !state.selected?.evidence_hash;
    $("revoke").disabled = state.busy || !state.review || !state.selected?.review_id || state.selected?.review_status === "revoked";
    document.querySelectorAll("#queue button").forEach((button) => { button.disabled = state.busy; });
    document.querySelectorAll("#reviewForm input, #reviewForm select, #reviewForm textarea").forEach((input) => { input.disabled = state.busy || !state.review; });
  }
  async function api(path = "", body, read = "json") {
    const session = state.session;
    if (state.token && window.location.protocol !== "https:" &&
        !["localhost", "127.0.0.1", "::1", "[::1]"].includes(window.location.hostname)) {
      throw new Error("Operator access requires HTTPS or a loopback server.");
    }
    const controller = new AbortController();
    let rejectRequest;
    const interruption = new Promise((_, reject) => { rejectRequest = reject; });
    const pending = { cancel() {
      const error = new Error("The operator session changed."); error.stale = true;
      rejectRequest(error); controller.abort();
    } };
    pendingRequests.add(pending);
    const timer = setTimeout(() => {
      rejectRequest(new Error("The request timed out. You can retry.")); controller.abort();
    }, REQUEST_TIMEOUT_MS);
    try {
      return await Promise.race([interruption, (async () => {
        const response = await fetch(root + path, {
          signal: controller.signal,
          method: body === undefined ? "GET" : "POST", cache: "no-store", credentials: "omit",
          headers: { Authorization: `Bearer ${state.token}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
          ...(body === undefined ? {} : { body: JSON.stringify(body) })
        });
        assertSession(session);
        if (!response.ok) {
          const error = new Error(({ 401: "Operator access expired. Connect again.", 403: "Your account cannot perform this review.", 409: "The case, originals or review changed. Refresh before deciding.", 422: "Check required fields and label limits.", 503: "Evaluation review storage is unavailable." })[response.status] || "The request could not be completed.");
          if (response.status === 401) { disconnect(); message(error.message, true); }
          throw error;
        }
        const result = await response[read]();
        assertSession(session);
        return result;
      })()]);
    } finally {
      clearTimeout(timer);
      pendingRequests.delete(pending);
    }
  }
  async function work(action) {
    if (state.busy) return;
    const session = state.session;
    const operation = ++state.operation;
    const active = () => session === state.session && operation === state.operation;
    state.busy = true; controls();
    try { await action(); } catch (error) { if (active() && !error.stale) message(error.message, true); }
    finally { if (active()) { state.busy = false; controls(); } }
  }
  function disconnect() {
    state.session += 1; state.token = ""; state.actor = null; state.review = false;
    state.operation++; state.busy = false;
    pendingRequests.forEach((pending) => pending.cancel());
    state.records = []; state.selected = null; $("token").value = "";
    $("identity").textContent = "Disconnected"; $("queue").replaceChildren(); $("detail").hidden = true;
    $("materials").replaceChildren(); $("history").replaceChildren(); $("empty").hidden = false;
    $("reviewForm").reset();
    ["title", "question", "status", "publication", "hashes", "message"].forEach((id) => $(id).replaceChildren());
    $("revokeReason").value = "";
    $("counts").textContent = ""; controls();
  }
  function queue() {
    $("queue").replaceChildren();
    const filter = $("filter").value.toLowerCase();
    for (const record of state.records) {
      if (!`${record.case.case_id} ${record.case.question} ${record.case.language} ${record.review_status}`.toLowerCase().includes(filter)) continue;
      const button = document.createElement("button"); button.type = "button";
      button.textContent = `${record.case.case_id} · ${record.case.language}`;
      const detail = document.createElement("small"); detail.textContent = record.review_status;
      button.append(detail); button.classList.toggle("selected", record.case.case_id === state.selected?.case.case_id);
      button.addEventListener("click", () => work(() => select(record.case.case_id))); $("queue").append(button);
    }
    const approved = state.records.filter((record) => record.review_status === "approved").length;
    $("counts").textContent = `${state.records.length} cases · ${approved} current reviewed annotations`;
    controls();
  }
  async function refresh() {
    const session = state.session;
    const result = await api();
    assertSession(session);
    state.records = result.cases;
    queue();
    if (state.selected) await select(state.selected.case.case_id);
  }
  function localDate(value) {
    const date = new Date(value);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  }
  async function select(caseId) {
    const session = state.session;
    const record = (await api(`/${encodeURIComponent(caseId)}`)).case;
    const events = (await api(`/${encodeURIComponent(caseId)}/history`)).events;
    if (session !== state.session) return;
    state.selected = record; const labels = record.labels;
    $("title").textContent = `${record.case.case_id} · ${record.case.language}`;
    $("question").textContent = record.case.question; $("status").textContent = record.review_status;
    $("publication").textContent = `Source publication: ${record.published_evidence_count}/${record.required_evidence_count} evidence sources currently published. Annotation approval is separate.`;
    $("hashes").textContent = `Case: ${record.case_hash}\nEvidence: ${record.evidence_hash || "unavailable"}\nReview: ${record.review_id || "pending"}`;
    $("behavior").value = labels.expected_behavior; $("scenario").value = labels.scenario; $("risk").value = labels.risk_level;
    $("conflict").value = labels.expected_conflict === null ? "" : String(labels.expected_conflict);
    $("conditions").value = labels.required_conditions.join("\n"); $("forbidden").value = labels.forbidden_claims.join("\n");
    for (const name of facts) $(`fact-${name}`).value = labels.applicability?.[name] || "";
    $("expiry").value = localDate(new Date(Date.now() + 30 * 86400000));
    for (const id of ["originalsChecked", "questionChecked", "conditionsChecked"]) $(id).checked = false;
    $("note").value = ""; $("revokeReason").value = ""; $("materials").replaceChildren();
    for (const evidence of record.case.evidence) {
      const container = document.createElement("details"); const summary = document.createElement("summary"); summary.textContent = evidence.source_id;
      const quote = document.createElement("pre"); quote.textContent = evidence.quote;
      const full = document.createElement("pre"); full.className = "source-text"; full.hidden = true;
      const show = document.createElement("button"); show.type = "button"; show.className = "secondary"; show.textContent = "Read complete captured text";
      const download = document.createElement("button"); download.type = "button"; download.className = "secondary"; download.textContent = "Download preserved original";
      const path = `/${encodeURIComponent(caseId)}/material/${encodeURIComponent(evidence.source_id)}`;
      show.addEventListener("click", () => work(async () => {
        const activeSession = state.session;
        const material = await api(path); assertSession(activeSession);
        full.textContent = material.text; full.hidden = false;
      }));
      download.addEventListener("click", () => work(async () => {
        const activeSession = state.session;
        const blob = await api(path + "/original", undefined, "blob");
        assertSession(activeSession);
        const url = URL.createObjectURL(blob); const link = document.createElement("a");
        link.href = url; link.download = `${evidence.source_id}.original`; link.click(); URL.revokeObjectURL(url);
      }));
      const buttons = document.createElement("div"); buttons.className = "actions"; buttons.append(show, download);
      container.append(summary, quote, buttons, full); $("materials").append(container);
    }
    $("history").replaceChildren();
    for (const event of events) {
      const row = document.createElement("li");
      row.textContent = `${event.at} · ${event.actor_id} · ${event.action}: ${event.approval?.note || event.reason || ""}`;
      $("history").append(row);
    }
    $("detail").hidden = false; $("empty").hidden = true; queue(); controls();
  }
  $("accessForm").addEventListener("submit", (event) => {
    event.preventDefault(); const token = $("token").value.trim(); disconnect();
    work(async () => {
      const session = state.session;
      state.token = token;
      try {
        const access = await api("/access"); assertSession(session);
        state.actor = access.actor; state.review = access.review_enabled;
        $("identity").textContent = `${state.actor.actor_id} · ${state.review ? "Reviewer" : "Read only"}. Token stays in this tab's memory.`;
        await refresh(); assertSession(session); message("Review workspace loaded.");
      } catch (error) {
        if (session === state.session) { disconnect(); message(error.message, true); }
        throw error;
      }
    });
  });
  $("disconnect").addEventListener("click", () => { disconnect(); message("Disconnected."); });
  $("refresh").addEventListener("click", () => work(refresh)); $("filter").addEventListener("input", queue);
  $("reviewForm").addEventListener("submit", (event) => { event.preventDefault(); work(async () => {
    const record = state.selected; if (!record || !state.review) return;
    const applicability = {};
    for (const name of facts) { const value = $(`fact-${name}`).value.trim(); if (value) applicability[name] = value; }
    const lines = (id) => $(id).value.split("\n").map((line) => line.trim()).filter(Boolean);
    await api(`/${encodeURIComponent(record.case.case_id)}/approve`, {
      expected_case_hash: record.case_hash, expected_evidence_hash: record.evidence_hash, expected_review_id: record.review_id,
      labels: { expected_behavior: $("behavior").value, scenario: $("scenario").value, risk_level: $("risk").value,
        required_conditions: lines("conditions"), forbidden_claims: lines("forbidden"),
        expected_conflict: $("conflict").value === "" ? null : $("conflict").value === "true", applicability: Object.keys(applicability).length ? applicability : null },
      expires_at: new Date($("expiry").value).toISOString(), note: $("note").value,
      originals_checked: $("originalsChecked").checked, question_checked: $("questionChecked").checked, conditions_checked: $("conditionsChecked").checked
    });
    await refresh(); message("Annotation recorded. Source publication remains a separate review.");
  }); });
  $("revoke").addEventListener("click", () => work(async () => {
    if (!state.selected || !state.review) return;
    await api(`/${encodeURIComponent(state.selected.case.case_id)}/revoke`, { expected_review_id: state.selected.review_id, reason: $("revokeReason").value });
    await refresh(); message("Annotation withdrawn; its history is preserved.");
  }));
  window.addEventListener("pagehide", disconnect);
  controls();
})();
