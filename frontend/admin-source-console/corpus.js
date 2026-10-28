(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const root = "/api/admin/source-corpus";
  const state = {
    token: "",
    actor: null,
    enabled: false,
    packets: [],
    sources: [],
    selected: null,
    busy: false,
    session: 0,
    operation: 0,
    reviewExpiry: null,
    reviewPassages: null
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
  const scenarios = ["tourism", "study", "work", "business", "medical", "documents", "housing", "payments",
    "transport", "translation", "emergency", "community_experience", "unclear"
  ];
  for (const value of scenarios) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    $("scenario").append(option);
  }
  const message = (text, error = false) => {
    $("message").textContent = text;
    $("message").className = error ? "error" : "";
  };
  const current = () => state.sources.find((s) => s.revision.packet.candidate_id === state.selected?.candidate_id);
  const can = (action) => state.enabled && state.actor?.permissions?.includes(`source_corpus:${action}`);
  const riskValues = () => Array.from($("risk").selectedOptions).map((option) => option.value).filter(
    Boolean);
  const sensitiveTopics = new Set(["documents", "visa", "registration", "housing", "work", "study",
    "medical", "emergency", "business", "payments"
  ]);
  const sensitiveRisks = new Set(["legal_sensitive", "work_status_sensitive", "medical_sensitive",
    "emergency"
  ]);

  function requiredReviews(item) {
    const review = item?.approvals?.[0]?.review;
    const sensitive = item?.revision?.packet?.topics?.some((topic) => sensitiveTopics.has(topic)) ||
      sensitiveTopics.has(review?.scenario) || review?.risk_tags?.some((risk) => sensitiveRisks.has(
        risk));
    return sensitive ? 2 : 1;
  }

  function readAnswerPassages() {
    const text = $("answerPassages").value;
    if (state.reviewPassages && text === state.reviewPassages.display) {
      return state.reviewPassages.original.slice();
    }
    if (!text.trim()) return [];
    const passages = text.split(/\n---\n/);
    if (passages.length > 12 || passages.some((passage) => passage.length < 12 || passage.length > 2400)) {
      throw new Error("Use at most 12 complete passages of 12–2400 characters each.");
    }
    return passages;
  }

  function updatePassageAttestation() {
    $("answerPassagesComplete").required = Boolean($("answerPassages").value.trim());
  }

  function controls() {
    const item = current();
    $("connect").disabled = state.busy;
    $("disconnect").disabled = !state.token;
    $("refresh").disabled = state.busy || !state.token;
    $("stage").disabled = state.busy || !can("stage") || state.selected?.status !== "pending";
    $("review").disabled = state.busy || !can("review") || item?.status !== "pending" || item?.approvals?.some((a) => a.actor_id === state.actor?.actor_id);
    const reviewers = new Set(item?.approvals?.map((review) => review.actor_id) || []);
    $("publish").disabled = state.busy || !can("publish") || item?.status !== "pending" ||
      reviewers.size < requiredReviews(item);
    $("revoke").disabled = state.busy || !can("revoke") || item?.status !== "approved";
    $("resetReview").disabled = state.busy || !can("stage") || !item;
    document.querySelectorAll("#queue button").forEach((button) => {
      button.disabled = state.busy;
    });
  }
  async function api(path = "", body) {
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
          method: body === undefined ? "GET" : "POST",
          cache: "no-store",
          credentials: "omit",
          headers: {
            Authorization: `Bearer ${state.token}`,
            ...(body === undefined ? {} : {
              "Content-Type": "application/json"
            })
          },
          ...(body === undefined ? {} : {
            body: JSON.stringify(body)
          })
        });
        assertSession(session);
        if (!response.ok) {
          const error = new Error(({
            401: "Access was not accepted.",
            403: "An authenticated account with this permission is required.",
            404: "The prepared source or revision is unavailable.",
            409: "Evidence or review state changed. Reload and check the source and approvals.",
            422: "Check the review fields and expiry.",
            503: "The source library could not verify its evidence or history."
          })[response.status] || "The request failed.");
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
    controls();
    message("");
    try {
      await action();
    } catch (error) {
      if (!active() || error.stale) return;
      if (error.status === 409) {
        try {
          await load();
        } catch (_) {}
      }
      if (active()) message(error.message, true);
    } finally {
      if (active()) { state.busy = false; controls(); }
    }
  }

  function node(tag, text) {
    const value = document.createElement(tag);
    value.textContent = text;
    return value;
  }

  function queue() {
    const filter = $("filter").value.toLowerCase();
    $("queue").replaceChildren();
    for (const packet of state.packets) {
      if (!`${packet.title} ${packet.publisher} ${packet.candidate_id}`.toLowerCase().includes(filter))
        continue;
      const button = node("button", packet.title);
      button.type = "button";
      button.className = packet.candidate_id === state.selected?.candidate_id ? "selected" : "";
      const status = state.sources.find((s) => s.revision.packet.candidate_id === packet.candidate_id)?.status ||
        packet.status;
      button.append(node("small", `${packet.candidate_id} · ${status}`));
      button.addEventListener("click", () => run(async () => {
        state.selected = packet;
        await render();
        queue();
      }));
      $("queue").append(button);
    }
    controls();
  }
  async function load() {
    const session = state.session;
    const [packets, sources] = await Promise.all([api("/packets"), api()]);
    assertSession(session);
    state.packets = packets.packets;
    state.sources = sources.sources;
    $("counts").textContent =
      `${state.packets.length} captured candidates · ${packets.published_sources} published sources`;
    if (state.selected) state.selected = state.packets.find((p) => p.candidate_id === state.selected.candidate_id) ||
      null;
    queue();
    await render();
  }
  async function render() {
    const session = state.session;
    const packet = state.selected;
    $("detail").hidden = !packet;
    $("empty").hidden = Boolean(packet);
    if (!packet) return;
    const item = current();
    const original = item?.revision.packet || packet;
    $("title").textContent = original.title;
    $("status").textContent = item?.status || original.status;
    $("metadata").textContent =
      `${original.publisher} · ${original.jurisdiction_or_scope} · captured ${original.captured_at||"unavailable"}`;
    const url = original.final_url || original.requested_url;
    $("original").removeAttribute("href");
    try {
      const parsed = new URL(url);
      if (["https:", "http:"].includes(parsed.protocol) && !parsed.username && !parsed.password) $(
        "original").href = parsed.href;
    } catch (_) {}
    $("findings").textContent = original.findings.join(" · ");
    $("body").textContent = original.text ||
      "Complete readable text is unavailable. This source cannot be published.";
    $("hashes").textContent =
      `Original: ${original.raw_sha256||"missing"}\nExtracted: ${original.extracted_sha256||"missing"}\nReview text: ${original.text_sha256}\nRevision: ${item?.revision.revision_hash||"not staged"}`;
    $("reviewPanel").hidden = !item;
    $("reviewForm").reset();
    $("history").replaceChildren();
    if (!item) return;
    const prior = item.approvals?.[0]?.review;
    const passages = prior?.answer_passages || [];
    $("answerPassages").value = passages.join("\n---\n");
    state.reviewPassages = {
      original: passages.slice(),
      display: $("answerPassages").value
    };
    $("answerPassagesComplete").checked = false;
    updatePassageAttestation();
    $("scenario").value = prior?.scenario || "";
    $("city").value = prior?.city || "";
    for (const option of $("risk").options) option.selected = (prior?.risk_tags || []).includes(option.value) ||
      (!prior?.risk_tags?.length && !option.value);
    const date = new Date(prior?.expires_at || Date.now() + 30 * 86400000);
    $("expiry").value = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0,
      16);
    state.reviewExpiry = {
      original: prior?.expires_at,
      display: $("expiry").value
    };
    $("revokeReason").value = "";
    $("reviewContext").textContent =
      `${item.approvals?.length||0} recorded reviews. Sensitive material requires two independent reviewers. All reviews must agree on scope and expiry. Publication is a separate action.`;
    const history = await api(`/${encodeURIComponent(original.source_id)}/history`);
    assertSession(session);
    for (const event of history.events) {
      const value = event.value || {};
      const row = node("li",
        `${value.action||event.action} · ${value.actor_id||event.actor_id||"unknown"} · ${value.at||event.at||""}`
      );
      if (value.data?.review?.note) row.append(node("p", value.data.review.note));
      if (value.data?.review?.answer_passages?.length) {
        const passages = node("details", "");
        passages.append(node("summary", "Passages preserved in this review"));
        value.data.review.answer_passages.forEach((passage) => passages.append(node("pre", passage)));
        row.append(passages);
      }
      if (value.data?.reason) row.append(node("p", value.data.reason));
      $("history").append(row);
    }
  }

  function disconnect() {
    state.session++;
    state.operation++;
    state.busy = false;
    pendingRequests.forEach((pending) => pending.cancel());
    state.token = "";
    state.actor = null;
    state.enabled = false;
    state.selected = null;
    state.packets = [];
    state.sources = [];
    $("token").value = "";
    state.reviewExpiry = null;
    state.reviewPassages = null;
    $("reviewForm").reset();
    $("revokeReason").value = "";
    ["title", "status", "metadata", "findings", "hashes", "body", "reviewContext", "history", "message"].forEach
      ((id) => $(id).replaceChildren());
    $("original").removeAttribute("href");
    $("identity").textContent = "Disconnected";
    $("counts").textContent = "";
    $("queue").replaceChildren();
    $("detail").hidden = true;
    $("empty").hidden = false;
    controls();
  }
  $("accessForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const token = $("token").value.trim();
    disconnect();
    run(async () => {
      const session = state.session;
      state.token = token;
      try {
        const access = await api("/access");
        assertSession(session);
        state.actor = access.actor;
        state.enabled = access.publication_enabled;
        $("identity").textContent =
          `${state.actor.actor_id} · ${state.actor.roles.join(", ")}${state.enabled?"":" · publication disabled"}`;
        await load();
        assertSession(session);
        message("Connected.");
      } catch (error) {
        if (session === state.session) {
          disconnect();
          message(error.message, true);
        }
        throw error;
      }
    });
  });
  $("disconnect").addEventListener("click", disconnect);
  window.addEventListener("pagehide", disconnect);
  $("filter").addEventListener("input", queue);
  $("answerPassages").addEventListener("input", () => {
    $("answerPassagesComplete").checked = false;
    updatePassageAttestation();
  });
  $("refresh").addEventListener("click", () => run(load));
  $("stage").addEventListener("click", () => run(async () => {
    await api("/stage", {
      candidate_id: state.selected.candidate_id
    });
    await load();
    message("Revision staged. Read the evidence before recording a review.");
  }));
  $("reviewForm").addEventListener("submit", (event) => {
    event.preventDefault();
    run(async () => {
      const item = current();
      if (!item || !can("review")) return;
      const attestations = {};
      $("attestations").querySelectorAll("input").forEach((input) => {
        attestations[input.name] = input.checked;
      });
      await api(`/${encodeURIComponent(item.revision.revision_id)}/review`, {
        expected_revision_hash: item.revision.revision_hash,
        expected_text_sha256: item.revision.packet.text_sha256,
        expires_at: state.reviewExpiry?.original && $("expiry").value === state.reviewExpiry.display ?
          state.reviewExpiry.original : new Date($("expiry").value).toISOString(),
        scenario: $("scenario").value || null,
        city: $("city").value.trim() || null,
        risk_tags: riskValues(),
        answer_passages: readAnswerPassages(),
        answer_passages_complete: $("answerPassagesComplete").checked,
        note: $("note").value.trim(),
        ...attestations
      });
      await load();
      message("Review recorded. This action does not publish the source.");
    });
  });
  $("publish").addEventListener("click", () => run(async () => {
    const item = current();
    if (!item || !can("publish")) return;
    await api(`/${encodeURIComponent(item.revision.revision_id)}/publish`, {
      expected_revision_hash: item.revision.revision_hash
    });
    await load();
    message("Reviewed revision published.");
  }));
  $("revoke").addEventListener("click", () => run(async () => {
    const item = current();
    const reason = $("revokeReason").value.trim();
    if (!item || !can("revoke")) return;
    if (!reason) throw new Error("Record the reason for revocation.");
    await api(`/${encodeURIComponent(item.revision.packet.source_id)}/revoke`, {
      expected_revision_hash: item.revision.revision_hash,
      reason
    });
    await load();
    message("Publication revoked. The original and history are preserved.");
  }));
  $("resetReview").addEventListener("click", () => run(async () => {
    const item = current();
    const reason = $("revokeReason").value.trim();
    if (!item || !can("stage")) return;
    if (!reason) throw new Error("Record why a new review is required.");
    await api(`/${encodeURIComponent(item.revision.packet.source_id)}/reset-review`, {
      expected_revision_hash: item.revision.revision_hash,
      reason
    });
    await load();
    message("A new revision is pending review. Earlier decisions remain in history.");
  }));
  controls();
})();
