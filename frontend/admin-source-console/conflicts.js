(() => {
  "use strict";

  const apiRoot = "/api/admin/source-conflicts";
  const byId = (id) => document.getElementById(id);
  const state = {
    token: "",
    actor: null,
    sources: [],
    cases: [],
    selected: null,
    busy: false,
    session: 0,
    operation: 0,
    semanticReviewEnabled: false
  };
  const pendingRequests = new Set();
  const REQUEST_TIMEOUT_MS = 30000;

  function assertSession(session) {
    if (session !== state.session) {
      const error = new Error("The operator session changed.");
      error.stale = true;
      throw error;
    }
  }

  function element(tag, value, className) {
    const node = document.createElement(tag);
    if (value != null) node.textContent = String(value);
    if (className) node.className = className;
    return node;
  }

  function message(text, error = false) {
    byId("message").textContent = text;
    byId("message").className = error ? "error" : "";
  }

  function can(permission) {
    return Boolean(state.actor?.permissions.includes(`source_conflicts:${permission}`));
  }

  function updateControls() {
    document.querySelectorAll("[data-permission]").forEach((button) => {
      const permission = button.dataset.permission;
      let permitted = can(permission);
      if (button.id === "semanticDetectButton") permitted = permitted && state.semanticReviewEnabled;
      if (permission === "note") permitted = permitted && Boolean(state.selected);
      if (button.id === "approveButton" || button.id === "rejectButton") {
        permitted = permitted && state.selected?.status === "proposed";
      }
      if (button.id === "approveButton") {
        permitted = permitted && state.selected?.proposal_actor_id !== state.actor?.actor_id;
        permitted = permitted && (state.selected?.proposal?.outcome === "prefer_source" ||
          (state.selected?.proposal?.outcome === "different_conditions" && state.selected.proposal
            .conditions?.length >= 2));
      }
      if (button.id === "revokeButton") permitted = permitted && state.selected?.status ===
        "approved";
      if (button.id === "refreshSourcesButton") {
        permitted = permitted && Boolean(state.selected) && state.selected.sources.every((snapshot) =>
          state.sources.some((source) => source.source_id === snapshot.source.source_id));
      }
      button.disabled = state.busy || !permitted;
    });
    byId("connectButton").disabled = state.busy;
    byId("disconnectButton").disabled = !state.token;
  }

  async function request(path = "", body) {
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
    }, path === "/semantic-detect" ? 140000 : REQUEST_TIMEOUT_MS);
    try {
      return await Promise.race([interruption, (async () => {
        const response = await fetch(apiRoot + path, {
          signal: controller.signal,
          method: body === undefined ? "GET" : "POST",
          headers: {
            Authorization: `Bearer ${state.token}`,
            ...(body === undefined ? {} : {
              "Content-Type": "application/json"
            })
          },
          cache: "no-store",
          credentials: "omit",
          ...(body === undefined ? {} : {
            body: JSON.stringify(body)
          }),
        });
        assertSession(session);
        if (!response.ok) {
          const messages = {
            400: "Check exact quotations, evidence, scope, expiry and permitted review state.",
            401: "The token was not accepted. Connect with an active operator account.",
            403: "This action requires an enabled authenticated account with the appropriate review permission.",
            404: "This case is no longer available.",
            409: "Another reviewer changed this case. The latest revision has been loaded; review it before submitting again.",
            422: "Check the required fields and use a valid date and time.",
            503: "Source review is unavailable or its history could not be verified.",
          };
          const error = new Error(messages[response.status] || "The request could not be completed.");
          error.status = response.status;
          throw error;
        }
        const result = await response.json();
        assertSession(session);
        return result;
      })()]);
    } finally {
      clearTimeout(timer);
      pendingRequests.delete(pending);
    }
  }

  async function run(action) {
    if (state.busy) return;
    const session = state.session;
    const operation = ++state.operation;
    const active = () => session === state.session && operation === state.operation;
    state.busy = true;
    updateControls();
    message("");
    try {
      await action();
    } catch (error) {
      if (!active() || error.stale) return;
      if (error.status === 409 && state.selected) {
        try {
          await loadCase(state.selected.conflict_id);
        } catch (_) { /* Keep the original failure visible. */ }
      }
      if (active()) message(error.message || "The request could not be completed.", true);
    } finally {
      if (active()) { state.busy = false; updateControls(); }
    }
  }

  function renderQueue() {
    const list = byId("caseList");
    list.replaceChildren();
    if (!state.cases.length) list.append(element("p", "No conflict cases yet.", "empty"));
    state.cases.forEach((item) => {
      const button = element("button", item.topic, "case-button");
      button.type = "button";
      button.dataset.permission = "read";
      if (state.selected?.conflict_id === item.conflict_id) button.classList.add("selected");
      button.append(element("small", `${item.status} · revision ${item.revision}`));
      button.addEventListener("click", () => run(() => loadCase(item.conflict_id)));
      list.append(button);
    });
    updateControls();
  }

  async function loadQueue() {
    const session = state.session;
    const result = await request();
    assertSession(session);
    state.cases = result.cases;
    renderQueue();
  }

  function renderSourcePicker(preserve = false) {
    ["A", "B"].forEach((side) => {
      const picker = byId(`source${side}`);
      const previous = preserve ? picker.value : "";
      picker.replaceChildren(element("option", "Select a source"));
      picker.firstChild.value = "";
      state.sources.forEach((source) => {
        const option = element("option", `${source.title} · ${source.source_id}`);
        option.value = source.source_id;
        picker.append(option);
      });
      picker.value = previous;
      const selected = state.sources.find((source) => source.source_id === picker.value);
      byId(`body${side}`).textContent = selected?.content ||
        "Select a source to read its available text.";
    });
  }

  function sourceLink(source) {
    try {
      const url = new URL(source.url);
      if (!["https:", "http:"].includes(url.protocol)) return null;
      const link = element("a", "Open official/source page");
      link.href = url.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      return link;
    } catch (_) {
      return null;
    }
  }

  const scopeFields = ["nationality", "document", "activity", "city", "basis", "facility", "department",
    "contract"
  ];

  function addCondition(card, key = "basis", evidence = {}) {
    const row = element("fieldset", null, "condition-row");
    row.append(element("legend", "Applicability condition"));
    const dimension = element("select");
    dimension.dataset.conditionField = "dimension";
    dimension.setAttribute("aria-label", "Condition type");
    scopeFields.forEach((name) => {
      const option = element("option", name.charAt(0).toUpperCase() + name.slice(1));
      option.value = name;
      dimension.append(option);
    });
    dimension.value = key;
    const value = element("input");
    value.dataset.conditionField = "value";
    value.maxLength = 120;
    value.placeholder = "Exact applicability term, for example X1 or Shanghai";
    value.setAttribute("aria-label", "Applicability value from the original");
    value.value = evidence.value || "";
    row.append(dimension, value);
    JSON.parse(card.dataset.sourceIds).forEach((sid) => {
      const source = state.selected.sources.find((snapshot) => snapshot.source.source_id === sid).source;
      const quote = element("textarea");
      quote.rows = 3;
      quote.dataset.conditionSource = sid;
      quote.value = evidence.quotes?.[sid] || state.selected.quotes[sid] || "";
      quote.setAttribute("aria-label", `Exact condition evidence from ${source.title}`);
      row.append(element("p", `Exact passage from ${source.title}`, "muted"), quote);
    });
    const remove = element("button", "Remove condition", "secondary");
    remove.type = "button";
    remove.addEventListener("click", () => row.remove());
    row.append(remove);
    card.querySelector(".branch-conditions").append(row);
  }

  function renderConditions(item) {
    const target = byId("conditionBranches");
    target.replaceChildren();
    const branches = item.proposal?.conditions?.length ? item.proposal.conditions :
      item.sources.map((snapshot) => ({
        source_ids: [snapshot.source.source_id],
        conditions: {}
      }));
    branches.forEach((branch, index) => {
      const card = element("section", null, "source-card condition-branch");
      card.dataset.sourceIds = JSON.stringify(branch.source_ids);
      card.append(element("h4", `Conditions ${index + 1}`));
      branch.source_ids.forEach((sid) => {
        const source = item.sources.find((snapshot) => snapshot.source.source_id === sid).source;
        card.append(element("p", source.title, "muted"));
      });
      card.append(element("div", null, "branch-conditions"));
      const add = element("button", "Add a condition", "secondary");
      add.type = "button";
      add.addEventListener("click", () => addCondition(card));
      card.append(add);
      const dates = element("div", null, "form-grid");
      [
        ["valid_from", "Effective from"],
        ["valid_until", "Effective through"]
      ].forEach(([key, label]) => {
        const field = element("label", label);
        const input = element("input");
        input.type = "date";
        input.dataset.branchDate = key;
        input.value = branch[key] || "";
        field.append(input);
        dates.append(field);
      });
      card.append(dates, element("p",
        "If dates are used, quote the original effective dates in YYYY-MM-DD form. Publication dates alone do not establish applicability.",
        "muted"));
      branch.source_ids.forEach((sid) => {
        const input = element("textarea");
        input.rows = 2;
        input.dataset.dateSource = sid;
        input.value = branch.date_quotes?.[sid] || "";
        input.setAttribute("aria-label", `Exact effective date evidence from ${sid}`);
        card.append(input);
      });
      target.append(card);
      const entries = Object.entries(branch.conditions || {});
      if (!entries.length && !branch.valid_from && !branch.valid_until) addCondition(card);
      entries.forEach(([key, evidence]) => addCondition(card, key, evidence));
    });
  }

  function readConditions() {
    return Array.from(byId("conditionBranches").querySelectorAll(".condition-branch"), (card) => {
      const conditions = {};
      card.querySelectorAll(".condition-row").forEach((row) => {
        const key = row.querySelector('[data-condition-field="dimension"]').value;
        const value = row.querySelector('[data-condition-field="value"]').value.trim();
        if (!value || conditions[key]) throw new Error(
          "Give every condition a distinct type and an explicit value.");
        conditions[key] = {
          value,
          quotes: Object.fromEntries(Array.from(row.querySelectorAll("[data-condition-source]"),
            (input) => [input.dataset.conditionSource, input.value]))
        };
      });
      const dates = Object.fromEntries(Array.from(card.querySelectorAll("[data-branch-date]"),
        (input) => [input.dataset.branchDate, input.value || null]));
      return {
        source_ids: JSON.parse(card.dataset.sourceIds),
        conditions,
        ...dates,
        date_quotes: dates.valid_from || dates.valid_until ? Object.fromEntries(Array.from(card.querySelectorAll(
            "[data-date-source]"),
          (input) => [input.dataset.dateSource, input.value])) : {}
      };
    });
  }

  function updateOutcome() {
    const conditional = byId("outcome").value === "different_conditions";
    byId("conditionsPanel").hidden = !conditional;
    byId("preferredSources").hidden = byId("outcome").value !== "prefer_source";
  }
  byId("outcome").addEventListener("change", updateOutcome);

  function renderCase(item, events) {
    state.selected = item;
    state.cases = state.cases.map((entry) => entry.conflict_id === item.conflict_id ? item : entry);
    byId("casePanel").hidden = false;
    byId("historyPanel").hidden = false;
    byId("caseHeading").textContent = item.topic;
    byId("caseMeta").textContent = `${item.conflict_id} · revision ${item.revision}`;
    byId("caseStatus").textContent = item.status;
    byId("scope").textContent = `${item.scenario} · ${item.risk_level} · ${item.city || "National scope"}`;
    const evidence = byId("evidence");
    evidence.replaceChildren();
    const preferred = byId("preferredSources");
    preferred.replaceChildren(element("legend", "Supporting source to prefer"));
    item.sources.forEach((snapshot) => {
      const source = snapshot.source;
      const card = element("div", null, "source-card");
      card.append(element("small", `${source.source_type} · ${source.trust_level}`), element("h3",
        source.title));
      const link = sourceLink(source);
      if (link) card.append(link);
      card.append(element("blockquote", item.quotes[source.source_id]));
      const original = element("details");
      original.append(element("summary", "Read preserved original"), element("pre", source.content,
        "source-body"));
      card.append(original);
      card.append(element("small", `Snapshot ${snapshot.snapshot_id} · ${snapshot.snapshot_hash}`));
      evidence.append(card);
      const label = element("label");
      const checkbox = element("input");
      checkbox.type = "checkbox";
      checkbox.value = source.source_id;
      checkbox.checked = item.proposal?.preferred_source_ids.includes(source.source_id) || false;
      const bestTrust = Math.min(...item.sources.map((entry) => Number(entry.source.trust_level.split(
        "_")[1])));
      checkbox.disabled = !["official", "curated_guide"].includes(source.source_type) ||
        Number(source.trust_level.split("_")[1]) > bestTrust;
      label.append(checkbox, element("span", source.title));
      preferred.append(label);
    });
    const refreshEvidence = byId("refreshEvidence");
    refreshEvidence.replaceChildren();
    item.sources.forEach((snapshot) => {
      const source = state.sources.find((entry) => entry.source_id === snapshot.source.source_id);
      const card = element("div", null, "source-card");
      card.append(element("h3", snapshot.source.title));
      if (source) {
        const original = element("details");
        original.append(element("summary", "Read current registry text"), element("pre", source.content,
          "source-body"));
        card.append(original);
        const quote = element("textarea");
        quote.dataset.sourceId = source.source_id;
        quote.rows = 4;
        quote.required = true;
        quote.setAttribute("aria-label", `New exact passage from ${source.title}`);
        quote.value = source.content.includes(item.quotes[source.source_id]) ? item.quotes[source.source_id] :
          "";
        card.append(element("p", "Exact passage to preserve", "muted"), quote);
      } else card.append(element("p", "This source is no longer eligible in the current registry.",
        "muted"));
      refreshEvidence.append(card);
    });
    const proposal = item.proposal;
    const preview = byId("currentProposal");
    preview.hidden = !proposal;
    preview.replaceChildren();
    if (proposal) {
      preview.append(element("strong", `${proposal.outcome} · submitted by ${item.proposal_actor_id}`));
      preview.append(element("p", proposal.note), element("p", proposal.reason, "muted"));
      preview.append(element("small",
        `Valid until ${new Date(proposal.valid_until).toLocaleString()}${item.approval_actor_id ? ` · approved by ${item.approval_actor_id}` : ""}`
      ));
    }
    byId("note").value = proposal?.note || "";
    byId("proposalReason").value = proposal?.reason || "";
    byId("outcome").value = proposal?.outcome || "prefer_source";
    renderConditions(item);
    updateOutcome();
    const expiry = proposal ? new Date(proposal.valid_until) : new Date(Date.now() + 30 * 86400000);
    byId("validUntil").value = new Date(expiry.getTime() - expiry.getTimezoneOffset() * 60000).toISOString()
      .slice(0, 16);
    byId("decisionReason").value = "";
    const history = byId("history");
    history.replaceChildren();
    events.forEach((event) => {
      const row = element("li");
      row.append(element("strong", `${event.event_type} · ${event.actor_id || "system"}`));
      row.append(element("p",
        `${new Date(event.created_at).toLocaleString()} · revision ${event.revision || "—"} · ${event.actor_roles.join(", ")}`,
        "muted"));
      row.append(element("p", event.reason));
      if (event.event_type === "answer_usage" && event.payload?.trace_id) {
        row.append(element("p", `Answer trace: ${event.payload.trace_id}`, "muted"));
      }
      const archived = event.payload?.case?.proposal || event.payload?.proposal;
      if (archived?.note) row.append(element("p", archived.note));
      if (Array.isArray(event.payload?.sources)) {
        const originals = element("details");
        originals.append(element("summary", "Evidence preserved in this revision"));
        event.payload.sources.forEach((snapshot) => {
          originals.append(element("strong", snapshot.source.title));
          originals.append(element("p", event.payload.quotes?.[snapshot.source.source_id]));
          originals.append(element("pre", snapshot.source.content, "source-body"));
        });
        row.append(originals);
      }
      const verification = element("details");
      verification.append(element("summary", "Audit reference"), element("pre",
        `${event.event_id}\n${event.event_hash}`, "source-body"));
      row.append(verification);
      history.append(row);
    });
    renderQueue();
  }

  async function loadCase(id) {
    const session = state.session;
    const [item, history, sources] = await Promise.all([request(`/${encodeURIComponent(id)}`), request(
      `/${encodeURIComponent(id)}/history`), request("/sources")]);
    assertSession(session);
    state.sources = sources.sources;
    state.semanticReviewEnabled = Boolean(sources.semantic_review_enabled);
    renderSourcePicker(true);
    renderCase(item, history.events);
  }

  function disconnect() {
    state.session += 1;
    state.operation++;
    state.busy = false;
    pendingRequests.forEach((pending) => pending.cancel());
    state.token = "";
    state.actor = null;
    state.sources = [];
    state.semanticReviewEnabled = false;
    state.cases = [];
    state.selected = null;
    byId("operatorToken").value = "";
    byId("createForm").reset();
    byId("createDetails").open = false;
    byId("identity").textContent = "Not connected.";
    byId("casePanel").hidden = true;
    byId("historyPanel").hidden = true;
    byId("casePanel").querySelectorAll("input, textarea").forEach((input) => {
      input.value = "";
    });
    ["evidence", "history", "currentProposal", "suggestions", "refreshEvidence", "conditionBranches"].forEach
      ((id) => byId(id).replaceChildren());
    ["caseHeading", "caseMeta", "caseStatus", "scope"].forEach((id) => {
      byId(id).textContent = "";
    });
    byId("preferredSources").replaceChildren(element("legend", "Supporting source to prefer"));
    renderQueue();
    renderSourcePicker();
    message("Disconnected.");
    updateControls();
  }

  byId("accessForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const token = byId("operatorToken").value.trim();
    byId("operatorToken").value = "";
    disconnect();
    run(async () => {
      const session = state.session;
      state.token = token;
      try {
        const actor = await request("/access");
        assertSession(session);
        state.actor = actor;
        const available = await request("/sources");
        assertSession(session);
        state.sources = available.sources;
        state.semanticReviewEnabled = Boolean(available.semantic_review_enabled);
        byId("identity").textContent = `${state.actor.actor_id} · ${state.actor.roles.join(", ")}`;
        renderSourcePicker();
        await loadQueue();
        assertSession(session);
        message(
          "Connected. Source snapshots and decisions are visible only to authorized operators.");
      } catch (error) {
        if (session === state.session) {
          disconnect();
          message(error.message, true);
        }
        throw error;
      }
    });
  });
  byId("disconnectButton").addEventListener("click", disconnect);
  byId("refreshButton").addEventListener("click", () => run(async () => {
    await loadQueue();
    if (state.selected) await loadCase(state.selected.conflict_id);
    message("Review queue refreshed.");
  }));
  ["A", "B"].forEach((side) => byId(`source${side}`).addEventListener("change", () => {
    const source = state.sources.find((item) => item.source_id === byId(`source${side}`).value);
    byId(`body${side}`).textContent = source?.content ||
      "Select a source to read its available text.";
    byId(`quote${side}`).value = "";
  }));

  function showSuggestions(result) {
    const list = byId("suggestions");
    list.replaceChildren();
    result.suggestions.forEach((suggestion) => {
      const button = element("button", suggestion.topic, "secondary");
      button.type = "button";
      button.dataset.permission = "create";
      button.append(element("small", suggestion.reason));
      if (suggestion.scope && Object.keys(suggestion.scope).length) {
        button.append(element("small", Object.entries(suggestion.scope)
          .map(([key, value]) => `${key}: ${value}`).join(" · ")));
      }
      button.addEventListener("click", () => {
        byId("createDetails").open = true;
        byId("topic").value = suggestion.topic;
        byId("scenario").value = suggestion.scenario;
        byId("risk").value = suggestion.risk_level;
        byId("city").value = suggestion.city || "";
        ["A", "B"].forEach((side, index) => {
          byId(`source${side}`).value = suggestion.source_ids[index];
          byId(`body${side}`).textContent = state.sources.find((item) => item.source_id ===
            suggestion.source_ids[index])?.content || "";
          byId(`quote${side}`).value = suggestion.quotes[index];
        });
        byId("topic").focus();
        message(
          "Suggestion copied to the form. Check applicability and original passages before creating a case."
        );
      });
      list.append(button);
    });
    const outcome = result.total ? `${result.total} possible conflicts found. Select one to inspect it.` :
      "No supported automatic matches. You can still open a case manually.";
    const coverage = result.coverage_status === "partial" ?
      ` The automatic check reached its limits (${result.scanned_source_count} of ${result.input_source_count} sources checked). Review skipped materials manually; the result may be incomplete.` :
      " This checks supported rule patterns and does not establish that all sources agree.";
    message(outcome + coverage);
  }
  byId("detectButton").addEventListener("click", () => run(async () => {
    showSuggestions(await request("/detect", {}));
  }));
  byId("semanticDetectButton").addEventListener("click", () => run(async () => {
    const result = await request("/semantic-detect", {});
    showSuggestions(result);
    if (result.warnings?.includes("semantic_review_unavailable")) {
      message(
        "Cloud comparison could not complete. The rule comparison and manual review remain available.",
        true);
    } else if (result.warnings?.length) {
      message(
        "Cloud suggestions are ready. Some materials or unsupported suggestions were excluded; compare those originals manually."
      );
    }
  }));
  byId("createForm").addEventListener("submit", (event) => {
    event.preventDefault();
    run(async () => {
      const ids = [byId("sourceA").value, byId("sourceB").value];
      if (!ids.every(Boolean) || ids[0] === ids[1]) throw new Error("Select two different sources.");
      const item = await request("", {
        source_ids: ids,
        quotes: {
          [ids[0]]: byId("quoteA").value,
          [ids[1]]: byId("quoteB").value
        },
        topic: byId("topic").value,
        scenario: byId("scenario").value,
        risk_level: byId("risk").value,
        city: byId("city").value.trim() || null,
        scope_partitioned: byId("scopePartitioned").checked,
      });
      await loadQueue();
      await loadCase(item.conflict_id);
      byId("createDetails").open = false;
      message("Case created. Both original passages have been preserved.");
    });
  });
  byId("proposalForm").addEventListener("submit", (event) => {
    event.preventDefault();
    run(async () => {
      if (!state.selected) throw new Error("Select a case first.");
      const expiry = new Date(byId("validUntil").value);
      if (!Number.isFinite(expiry.getTime()) || expiry <= new Date()) throw new Error(
        "Choose a future review date.");
      const preferred = Array.from(byId("preferredSources").querySelectorAll("input:checked"), (
        input) => input.value);
      if (byId("outcome").value === "prefer_source" && (!preferred.length || preferred.length ===
          state.selected.sources.length)) {
        throw new Error(
          "Select supported evidence to prefer; choosing every conflicting source does not resolve the disagreement."
        );
      }
      await request(`/${encodeURIComponent(state.selected.conflict_id)}/proposals`, {
        expected_revision: state.selected.revision,
        proposal: {
          note: byId("note").value,
          reason: byId("proposalReason").value,
          outcome: byId("outcome").value,
          valid_until: expiry.toISOString(),
          conditions: byId("outcome").value === "different_conditions" ? readConditions() : [],
          preferred_source_ids: byId("outcome").value === "prefer_source" ?
            preferred : []
        },
      });
      await loadQueue();
      await loadCase(state.selected.conflict_id);
      message("Interpretation submitted. A separate authorized operator must approve it.");
    });
  });
  byId("refreshSourcesForm").addEventListener("submit", (event) => {
    event.preventDefault();
    run(async () => {
      if (!state.selected) throw new Error("Select a case first.");
      const quotes = Object.fromEntries(Array.from(byId("refreshEvidence").querySelectorAll(
          "textarea"),
        (input) => [input.dataset.sourceId, input.value]));
      await request(`/${encodeURIComponent(state.selected.conflict_id)}/sources`, {
        expected_revision: state.selected.revision,
        quotes,
      });
      await loadQueue();
      await loadCase(state.selected.conflict_id);
      message("New evidence preserved. Submit a fresh interpretation for independent review.");
    });
  });
  [
    ["approveButton", "approve"],
    ["rejectButton", "reject"],
    ["revokeButton", "revoke"]
  ].forEach(([id, action]) => {
    byId(id).addEventListener("click", () => run(async () => {
      if (!state.selected) throw new Error("Select a case first.");
      if (byId("decisionReason").value.trim().length < 3) throw new Error(
        "Give a reason for the decision.");
      await request(`/${encodeURIComponent(state.selected.conflict_id)}/decisions`, {
        expected_revision: state.selected.revision,
        action,
        reason: byId("decisionReason").value,
      });
      await loadQueue();
      await loadCase(state.selected.conflict_id);
      message("Decision recorded in the case history.");
    }));
  });
  window.addEventListener("pagehide", disconnect);
  renderSourcePicker();
  updateControls();
})();
