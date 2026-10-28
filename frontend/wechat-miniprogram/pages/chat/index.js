const api = require("../../utils/api");
const workspace = require("../../utils/workspace");
const answerSections = require("../../utils/answerSections");
const format = require("../../utils/format");
const clientContext = require("../../utils/clientContext");
const i18n = require("../../utils/i18n");
const chatInput = require("../../utils/chatInput");
const u = require("../../utils/workspaceUi");
const scenarioCopy = require("../../utils/scenarioCopy");
const { approvedProfileContext } = require("../../utils/profileContext");
const {
  utf8Bytes,
  boundedWindow
} = require("../../utils/renderBudget");
const TURN_LIMIT = 20,
  TURN_BYTES = 240 * 1024,
  SINGLE_TURN_BYTES = 32 * 1024;

function excerpt(value, limit = 2000) {
  const characters = Array.from(String(value || ""));
  return characters.length > limit ? characters.slice(0, limit).join("") + "…" : characters.join("");
}

function projectTurn(turn) {
  if (!turn.answerView) return {
    id: turn.id,
    kind: turn.kind,
    text: excerpt(turn.text, 8000),
    failed: Boolean(turn.failed),
    savedCopy: Boolean(turn.savedCopy),
    historical: Boolean(turn.historical),
    fullTextAvailable: Array.from(String(turn.text || "")).length > 8000
  };
  const view = Object.assign({}, turn.answerView, {
    userQuestion: excerpt(turn.answerView.userQuestion, 1200),
    rawAnswer: "",
    traceSummary: []
  });
  const projected = {
    id: turn.id,
    kind: turn.kind,
    historical: Boolean(turn.historical),
    answerView: view,
    warnings: turn.warnings || [],
    sourcesExpanded: Boolean(turn.sourcesExpanded),
    detailsExpanded: Boolean(turn.detailsExpanded),
    fullTextAvailable: true
  };
  if (utf8Bytes(projected) <= SINGLE_TURN_BYTES) return projected;
  return {
    id: turn.id,
    kind: turn.kind,
    compactAnswer: true,
    historical: Boolean(turn.historical),
    fullTextAvailable: true,
    text: excerpt(view.directAnswer),
    scenarioLabel: view.scenarioLabel,
    riskBadgeLabel: view.riskBadgeLabel,
    highRisk: Boolean(view.highRisk),
    escalationRecommended: Boolean(view.escalationRecommended),
    warnings: (turn.warnings || []).slice(0, 6).map((value) => excerpt(value, 400))
  };
}

function activeResponse(response, view) {
  return {
    response: response ? {
      trace_id: response.trace_id,
      case_id: response.case_id,
      scenario: response.scenario,
      risk_level: response.risk_level
    } : null,
    answerView: view ? {
      historical: Boolean(view.historical),
      userQuestion: excerpt(view.userQuestion, 8000),
      scenario: view.scenario,
      riskLevel: view.riskLevel,
      directAnswer: excerpt(view.directAnswer)
    } : null
  };
}

function fullTurnText(turn, ui) {
  const history = turn.historical ? ui.historicalAnswer + "\n" + ui.historicalNotice : "";
  if (!turn.answerView) return [history, String(turn.text || "")].filter(Boolean).join("\n\n");
  const view = turn.answerView,
    rows = (values) => values.map((item) => typeof item === "string" ? item : [item.title, item.body, (item.sourceIds ||
      []).map((id) => "[" + id + "]").join(" ")].filter(Boolean).join("\n")).join("\n\n");
  return [history, view.userQuestion ? ui.question + "\n" + view.userQuestion : "", ui.scenario + ": " + view.scenarioLabel,
    ui.risk + ": " + view.riskBadgeLabel, ui.direct + "\n" + view.directAnswer,
    view.reviewedNotes && view.reviewedNotes.length ? ui.reviewedInterpretation + "\n" + rows(view.reviewedNotes) : "",
    view.highRisk ? ui.highRisk : "", rows(turn.warnings || []), ui.steps + "\n" + rows(view.recommendedSteps ||
      []), rows(view.safetyPolicyNextSteps || []), ui.checklist + "\n" + rows(view.checklistItems || []),
    (turn.historical ? ui.historicalFacts : ui.groundedFacts) + "\n" + rows(view.groundedFacts || []), ui.escalation + "\n" + rows(view.escalationItems ||
      []) + (view.escalationRecommended ? "\n" + ui.human : ""),
    (turn.historical ? ui.historicalSources : ui.sources) + "\n" + (view.sourceNotes || []).map((source) => [source.sourceId ? "[" + source.sourceId +
      "]" : "", source.title, source.trustLabel, source.warning, source.publisher, source.reviewedAt,
      source.accessedAt, source.url
    ].filter(Boolean).join("\n")).join("\n\n")
  ].filter(Boolean).join("\n\n");
}

function unique(values) {
  return Array.from(new Set(values.filter(Boolean).map(String)));
}

function generationFailed(response) {
  const metadata = response && response.metadata || {};
  const expected = ["generated", "skipped_safety", "awaiting_official_sources",
    "source_conflict_requires_review", "source_conflict_withheld", "source_publication_withheld",
    "source_constraints_applied"];
  return [metadata.ollama_status, metadata.cloud_status].some((status) => status && expected.indexOf(status) < 0);
}

function warnings(view, response) {
  const ui = i18n.labels();
  return unique([view.containsSyntheticSources ? ui.demoEvidence : "", generationFailed(response) ? ui.cloudChatFallback : "",
      view.sourceReviewWarning.show ? view.sourceReviewWarning.message : "", view.noTrustedSourceLabel ? ui
      .noTrustedSources : "",
      view.safetyPolicyDecision.requires_official_source ? ui.officialRequired : "", view.safetyPolicyDecision
      .not_emergency_dispatch ? ui.emergencyNotice : ""
    ]
    .concat(view.safetyPolicyWarnings, view.verifierWarnings, view.freshnessWarnings, view.uncertaintyItems,
      view.sourceReviewWarning.guidance || []));
}

function answerTurn(response, question, historical = false) {
  const view = answerSections.normalizeChatResponse(response, {
    userQuestion: question,
    historical
  });
  view.scenarioLabel = scenarioCopy.categoryLabel(view.scenario);
  view.riskBadgeLabel = scenarioCopy.riskLabel(view.riskLevel);
  return {
    id: response.trace_id || "answer-" + Date.now(),
    kind: "assistant",
    historical,
    response,
    answerView: view,
    warnings: warnings(view, response),
    sourcesExpanded: false,
    detailsExpanded: false
  };
}

// Historical presentation is a new view; the recorded response and citations stay intact.
function archiveTurn(turn) {
  if (turn.kind !== "assistant") return turn;
  if (turn.response) return Object.assign({}, turn, answerTurn(turn.response,
    turn.answerView && turn.answerView.userQuestion || "", true), { id: turn.id });
  const view = turn.answerView && Object.assign({}, turn.answerView, {
    historical: true,
    hasTrustedSources: false,
    sourceNotes: (turn.answerView.sourceNotes || []).map((source) => Object.assign({}, source, {
      trusted: false,
      trustLabel: i18n.labels().historicalReference
    }))
  });
  return Object.assign({}, turn, { historical: true, answerView: view });
}
Page({
  data: Object.assign({}, i18n.pageState(), {
    submittedMessage: "",
    resetContext: false,
    message: "",
    loading: false,
    caseLoading: false,
    saving: false,
    caseSavePending: false,
    error: "",
    response: null,
    cloudChatEnabled: null,
    cloudFallback: false,
    answerView: null,
    safetyFlags: [],
    sourcesExpanded: false,
    detailsExpanded: false,
    photoDraftContext: null,
    photoDraftWarnings: [],
    turns: [],
    turnOffset: 0,
    turnEnd: 0,
    turnTotal: 0,
    hasPreviousTurns: false,
    hasNextTurns: false,
    fullTurnOpen: false,
    fullTurnText: "",
    fullTurnPart: 0,
    fullTurnParts: 0,
    caseId: "",
    caseTitle: "",
    caseStatus: "open",
    context: {},
    useSavedContext: false,
    explicitCity: "",
    editContext: false,
    saveStatus: "",
    scrollTarget: "",
    accessNeeded: false,
    samples: [{
      label: "Lost passport",
      labelKey: "samplePassport",
      message: "I lost my passport in Beijing and need urgent help."
    }, {
      label: "Tourist visa work",
      labelKey: "sampleVisa",
      message: "Can I work on a tourist visa and fix documents later?"
    }, {
      label: "Study registration",
      labelKey: "sampleStudy",
      message: "I am a student preparing university registration documents in Shanghai."
    }, {
      label: "Travel to Kazakhstan",
      labelKey: "sampleKazakhstanEntry",
      message: "I am planning a trip to Kazakhstan. Please help me check visa and entry rules."
    }]
  }),
  onLoad(options = {}) {
    this._ownerEpoch = clientContext.getOwnerEpoch();
    this._turnOwnerReady = true;
    this.clearTurnCache();
    this.setData({
      caseId: options.case_id || "",
      useSavedContext: Boolean(options.case_id)
    });
  },
  clearTurnCache() {
    this._turns = [];
    this._response = null;
    this._answerView = null;
    this._fullTurnChunks = [];
    this._pendingCaseSave = null;
  },
  ownsTurns() {
    if (this._turnOwnerReady === false) return false;
    if (this._ownerEpoch === clientContext.getOwnerEpoch()) return true;
    this._turnOwnerReady = false;
    this.clearTurnCache();
    u.resetOnOwnerChange(this, {
      turns: [],
      turnTotal: 0,
      turnOffset: 0,
      turnEnd: 0,
      hasPreviousTurns: false,
      hasNextTurns: false,
      fullTurnOpen: false,
      fullTurnText: "",
      fullTurnParts: 0,
      response: null,
      answerView: null,
      message: "",
      submittedMessage: "",
      caseId: "",
      caseTitle: "",
      caseStatus: "open",
      context: {},
      useSavedContext: false,
      explicitCity: "",
      photoDraftContext: null,
      photoDraftWarnings: [],
      loading: false,
      caseLoading: false,
      saving: false,
      caseSavePending: false,
      error: "",
      saveStatus: ""
    });
    return false;
  },
  setTurns(turns) {
    if (!this.ownsTurns()) return;
    this._turns = turns;
    this.latestTurns();
  },
  renderTurns(offset = 0, limit = TURN_LIMIT) {
    if (!this.ownsTurns()) return;
    const projected = this._turns.map(projectTurn),
      window = boundedWindow(projected, {
        offset,
        limit,
        maxBytes: TURN_BYTES
      });
    this.setData({
      turns: window.items,
      turnOffset: window.offset,
      turnEnd: window.end,
      turnTotal: window.total,
      hasPreviousTurns: window.hasPrevious,
      hasNextTurns: window.hasNext
    });
  },
  previousTurns() {
    if (!this.ownsTurns() || !this.data.hasPreviousTurns) return;
    let offset = this.data.turnOffset,
      bytes = 2,
      count = 0;
    while (offset > 0 && count < TURN_LIMIT) {
      const size = utf8Bytes(projectTurn(this._turns[offset - 1])) + 1;
      if (bytes + size > TURN_BYTES) break;
      offset -= 1;
      bytes += size;
      count += 1;
    }
    this.renderTurns(offset, count);
  },
  nextTurns() {
    if (this.data.hasNextTurns) this.renderTurns(this.data.turnEnd);
  },
  latestTurns() {
    if (!this.ownsTurns()) return;
    let offset = this._turns.length,
      bytes = 2,
      count = 0;
    while (offset > 0 && count < TURN_LIMIT) {
      const size = utf8Bytes(projectTurn(this._turns[offset - 1])) + 1;
      if (bytes + size > TURN_BYTES) break;
      offset -= 1;
      bytes += size;
      count += 1;
    }
    this.renderTurns(offset, count || TURN_LIMIT);
  },
  viewTurn(event) {
    if (!this.ownsTurns()) return;
    const turn = this._turns.find((item) => item.id === event.currentTarget.dataset.id);
    if (!turn) return;
    const characters = Array.from(fullTurnText(turn, this.data.ui));
    const history = turn.historical ? this.data.ui.historicalAnswer + "\n" + this.data.ui.historicalNotice + "\n\n" : "";
    this._fullTurnChunks = [];
    for (let start = 0; start < characters.length; start += 6000) this._fullTurnChunks.push((start ? history : "") + characters.slice(
      start, start + 6000).join(""));
    if (!this._fullTurnChunks.length) this._fullTurnChunks = [""];
    this.setData({
      fullTurnOpen: true,
      fullTurnText: this._fullTurnChunks[0],
      fullTurnPart: 0,
      fullTurnParts: this._fullTurnChunks.length
    });
  },
  previousFullTurn() {
    if (this.ownsTurns() && this.data.fullTurnPart > 0) {
      const part = this.data.fullTurnPart - 1;
      this.setData({
        fullTurnPart: part,
        fullTurnText: this._fullTurnChunks[part]
      });
    }
  },
  nextFullTurn() {
    if (this.ownsTurns() && this.data.fullTurnPart + 1 < this._fullTurnChunks.length) {
      const part = this.data.fullTurnPart + 1;
      this.setData({
        fullTurnPart: part,
        fullTurnText: this._fullTurnChunks[part]
      });
    }
  },
  closeFullTurn() {
    this._fullTurnChunks = [];
    this.setData({
      fullTurnOpen: false,
      fullTurnText: "",
      fullTurnPart: 0,
      fullTurnParts: 0
    });
  },
  onShow() {
    i18n.refresh(this);
    if (this._ownerEpoch !== clientContext.getOwnerEpoch()) {
      this._caseLoaded = false;
      this.ownsTurns();
    }
    u.resetOnOwnerChange(this, {
      turns: [],
      response: null,
      answerView: null,
      message: "",
      photoDraftContext: null,
      photoDraftWarnings: [],
      caseId: "",
      caseTitle: "",
      caseStatus: "open",
      context: {},
      useSavedContext: false,
      explicitCity: "",
      loading: false,
      caseLoading: false,
      saving: false,
      caseSavePending: false,
      submittedMessage: "",
      saveStatus: "",
      resetContext: true
    });
    this._turnOwnerReady = true;
    const app = getApp();
    const global = app && app.globalData || {};
    if (this._pendingCaseSave && this._pendingCaseSave.complete) {
      this._pendingCaseSave = null;
      this.setData({ caseSavePending: false });
    }
    const draft = global.chatDraft;
    const pendingDraft = draft && draft.pendingCaseSave;
    const restorePending = !this._pendingCaseSave && pendingDraft && !pendingDraft.complete &&
      pendingDraft.ownerEpoch === clientContext.getOwnerEpoch() &&
      (!this.data.caseId || this.data.caseId === pendingDraft.caseId);
    if ((!this.data.caseId && !this._turns.length && draft) || restorePending) {
      const saved = draft.pendingCaseSave;
      this._response = draft.response || null;
      const turns = (draft.turns || []).map(archiveTurn);
      const latest = turns.slice().reverse().find((turn) => turn.answerView);
      this._answerView = latest ? latest.answerView : null;
      this._pendingCaseSave = saved && !saved.complete ? saved : null;
      this.setData(Object.assign({
        message: draft.message || "",
        caseId: saved && saved.caseId || draft.caseId || "",
        caseTitle: saved && saved.caseTitle || draft.caseTitle || "",
        caseStatus: draft.caseStatus || "open",
        context: draft.context || {},
        useSavedContext: draft.useSavedContext === undefined ? Boolean(draft.caseId) : Boolean(draft.useSavedContext),
        explicitCity: draft.explicitCity || "",
        submittedMessage: draft.submittedMessage || "",
        caseSavePending: Boolean(this._pendingCaseSave)
      }, activeResponse(this._response, this._answerView)));
      this.setTurns(turns);
      if (saved && saved.complete && this.data.caseId) this.loadCase();
    } else if (this.data.caseId && !this._pendingCaseSave && !this.data.loading && !this.data.saving && !this.data.editContext) {
      this.loadCase();
    } else if (this._turns.length) {
      this.setTurns(this._turns.map(archiveTurn));
      const latest = this._turns.slice().reverse().find((turn) => turn.answerView);
      this._answerView = latest ? latest.answerView : null;
      this.setData(activeResponse(this._response, this._answerView));
    }
    const currentCapabilities = u.latestRequest(this, "capabilities");
    api.getCapabilities().then((capabilities) => {
      if (currentCapabilities()) this.setData({
        cloudChatEnabled: Boolean((capabilities.feature_flags || {}).cloud_chat)
      });
    }).catch(() => {
      if (currentCapabilities()) this.setData({
        cloudChatEnabled: null
      });
    });
    if (!this.data.caseId && this.data.useSavedContext) this.loadProfileContext().catch(() => {});
    const photo = global.photoDraftContext,
      prefill = global.pendingChatPrefill || "";
    if (photo) {
      global.photoDraftContext = null;
      global.pendingChatPrefill = "";
      this.setData({
        message: photo.chat_prompt || chatInput.buildPhotoChatPrompt(
          photo.extracted_text,
          photo.part_number,
          photo.part_count,
          this.data.preferredLanguage
        ),
        photoDraftContext: photo,
        photoDraftWarnings: buildPhotoDraftWarnings(photo),
        error: ""
      });
    } else if (prefill) {
      global.pendingChatPrefill = "";
      this.setData({
        message: prefill,
        photoDraftContext: null,
        photoDraftWarnings: [],
        error: ""
      });
    }
  },
  loadCase() {
    const caseId = this.data.caseId;
    if (!caseId) return Promise.resolve();
    const current = u.latestRequest(this, "caseLoad");
    this.setData({
      caseLoading: true,
      error: ""
    });
    return workspace.getCase(caseId).then((r) => {
      if (!current() || this.data.caseId !== caseId) return;
      let question = "",
        latest = null;
      const item = r.case,
        turns = (item.messages || []).map((message) => {
          if (message.kind === "user") question = message.text;
          if (message.kind === "assistant" && message.response) {
            const turn = answerTurn(message.response, question, true);
            latest = turn;
            return turn;
          }
          return {
            id: message.message_id,
            kind: message.kind,
            text: message.text,
            historical: message.kind === "assistant",
            savedCopy: message.kind === "assistant"
          };
        });
      this._caseLoaded = true;
      this._response = latest ? latest.response : null;
      this._answerView = latest ? latest.answerView : null;
      this.setData(Object.assign({
        caseTitle: item.title,
        caseStatus: item.status || "open",
        context: this.data.useSavedContext ? item.context || {} : { city: this.data.explicitCity },
        caseLoading: false,
        submittedMessage: latest ? latest.answerView.userQuestion : question,
        safetyFlags: latest ? format.formatSafetyFlags(latest.response.safety_flags) : [],
        cloudFallback: generationFailed(latest && latest.response)
      }, activeResponse(this._response, this._answerView)));
      this.setTurns(turns);
      this.keepDraft();
      this.scrollToEnd();
    }).catch((e) => {
      if (current()) {
        this.setData({
          caseLoading: false
        });
        u.error(this, e);
      }
    });
  },
  onUnload() {
    this.keepDraft();
    u.invalidateRequests(this);
    this.clearTurnCache();
    this._turnOwnerReady = false;
  },
  keepDraft() {
    if (this._ownerEpoch !== undefined && this._ownerEpoch !== clientContext.getOwnerEpoch()) return;
    const app = getApp();
    if (app && app.globalData) app.globalData.chatDraft = {
      turns: this._turns.slice(),
      message: this.data.message,
      caseId: this.data.caseId,
      caseTitle: this.data.caseTitle,
      caseStatus: this.data.caseStatus,
      context: this.data.context,
      useSavedContext: this.data.useSavedContext,
      explicitCity: this.data.explicitCity,
      response: this._response,
      answerView: this._answerView,
      submittedMessage: this.data.submittedMessage,
      pendingCaseSave: this._pendingCaseSave
    };
  },
  onMessageInput(event) {
    if (!this.data.loading) this.setData({
      message: event.detail.value
    });
  },
  useSample(event) {
    if (this.data.loading) return;
    const sample = this.data.samples[event.currentTarget.dataset.index];
    if (sample) this.setData({
      message: sample.labelKey === "sampleKazakhstanEntry"
        ? this.data.ui.kazakhstanTripMessage
        : this.data.ui[sample.labelKey + "Message"] || sample.message,
      error: ""
    });
  },
  sendMessage(event) {
    if (!this.ownsTurns()) return;
    if (this.data.loading || this.data.saving || this.data.caseLoading) return;
    if (this.data.caseId && this.data.caseStatus !== "open") {
      this.setData({
        error: this.data.ui.closedCaseHint
      });
      return;
    }
    const message = u.form(event, "message", this.data.message);
    this.setData({
      message
    });
    if (!message) {
      this.setData({
        error: i18n.labels().enterMessage
      });
      return;
    }
    if (chatInput.characterCount(message) > chatInput.CHAT_MAX_CHARS) {
      this.setData({
        error: i18n.labels().chatTextTooLong
      });
      return;
    }
    u.invalidateRequests(this, "caseLoad");
    const current = u.latestRequest(this, "send");
    const turnId = "user-" + Date.now() + "-" + Math.random().toString(36).slice(2, 7);
    const previous = this._turns.filter((turn) => !turn.failed);
    this.setData({
      loading: true,
      error: "",
      saveStatus: "",
      submittedMessage: message,
      message: ""
    });
    this.setTurns(previous.concat([{
      id: turnId,
      kind: "user",
      text: message
    }]));
    this.scrollToEnd();
    const options = {
      reset_context: this.data.resetContext,
        use_saved_context: this.data.useSavedContext,
        use_conversation_context: true
    };
    if (this.data.caseId) options.case_id = this.data.caseId;
    const prepare = this.data.useSavedContext && !this.data.caseId
      ? this.loadProfileContext() : Promise.resolve();
    return prepare.then(() => workspace.ensure()).then(() => {
      if (!current()) {
        const error = new Error("Session changed");
        error.stale = true;
        throw error;
      }
      if (this.data.context.city) options.city = this.data.context.city;
      return api.sendChatMessage(message, options);
    }).then((response) => {
      if (!current()) return;
      const turn = answerTurn(response, message);
      this._response = response;
      this._answerView = turn.answerView;
      this.setData(Object.assign({
        loading: false,
        resetContext: false,
        safetyFlags: format.formatSafetyFlags(response.safety_flags),
        cloudFallback: generationFailed(response),
        photoDraftContext: null,
        photoDraftWarnings: []
      }, activeResponse(response, turn.answerView)));
      this.setTurns(this._turns.concat([turn]));
      this.keepDraft();
      this.scrollToEnd();
    }).catch((error) => {
      if (!current() || error.stale) return;
      this.setData({
        loading: false,
        message,
        accessNeeded: error.status === 401 || error.status === 403,
        error: error.status === 401 || error.status === 403 ? this.data.ui.accessNeeded : this.data
          .ui.requestFailed
      });
      this.setTurns(this._turns.map((turn) => turn.id === turnId ? Object.assign({}, turn, {
        failed: true
      }) : turn));
    });
  },
  scrollToEnd() {
    this.setData({
      scrollTarget: "conversation-end"
    });
    if (typeof wx.pageScrollTo === "function") wx.pageScrollTo({
      selector: "#conversation-end",
      duration: 200
    });
  },
  reopenCase() {
    if (this.data.saving || this.data.loading || this.data.caseLoading || !this.data.caseId) return;
    const current = u.latestRequest(this, "reopen"),
      caseId = this.data.caseId;
    this.setData({
      saving: true,
      error: ""
    });
    return workspace.updateCase(caseId, {
      status: "open"
    }).then(() => {
      if (current() && this.data.caseId === caseId) {
        this.setData({
          saving: false
        });
        return this.loadCase();
      }
    }).catch((error) => {
      if (current()) u.error(this, error);
    });
  },
  toggleContext() {
    if (this.data.caseLoading) return;
    this.setData({
      editContext: !this.data.editContext
    });
  },
  loadProfileContext() {
    const current = u.latestRequest(this, "profile");
    return workspace.getProfile().then((r) => {
      if (!current() || this.data.caseId || !this.data.useSavedContext) return;
      const context = approvedProfileContext(r.profile);
      if (this.data.explicitCity) context.city = this.data.explicitCity;
      this.setData({ context });
    });
  },
  changeSavedContext(event) {
    if (this.data.loading || this.data.saving || this.data.caseLoading) return;
    u.invalidateRequests(this, "profile");
    u.invalidateRequests(this, "caseLoad");
    const enabled = Boolean(event.detail.value);
    this.setData({ useSavedContext: enabled, context: { city: this.data.explicitCity }, resetContext: true });
    this.keepDraft();
    if (enabled) return this.data.caseId ? this.loadCase()
      : this.loadProfileContext().catch((error) => u.error(this, error));
  },
  saveContext(event) {
    if (this.data.caseLoading) return;
    const city = u.form(event, "city"),
      caseId = this.data.caseId,
      current = u.latestRequest(this, "contextSave");
    this.setData({
      explicitCity: city,
      context: Object.assign({}, this.data.context, {
        city
      }),
      editContext: false
    });
    if (caseId) return workspace.updateCase(caseId, {
      context: this.data.context
    }).catch((e) => {
      if (current() && this.data.caseId === caseId) u.error(this, e);
    });
  },
  saveCase() {
    if (!this.ownsTurns() || this.data.saving || this.data.loading || this.data.caseLoading || !this._turns
      .length) return;
    if (this.data.caseId && !this._pendingCaseSave) {
      wx.navigateTo({
        url: "/pages/case-detail/index?id=" + encodeURIComponent(this.data.caseId)
      });
      return;
    }
    const current = u.latestRequest(this, "caseSave"),
      ownerEpoch = clientContext.getOwnerEpoch();
    const turns = this._pendingCaseSave ? this._pendingCaseSave.turns : JSON.parse(JSON.stringify(this._turns));
    const sameOwner = () => {
      if (ownerEpoch !== clientContext.getOwnerEpoch()) {
        const error = new Error("Session changed");
        error.stale = true;
        throw error;
      }
    };
    this.setData({
      saving: true,
      caseSavePending: true,
      error: "",
      saveStatus: ""
    });
    const title = (turns.find((t) => t.kind === "user") || {}).text || this.data.ui.createCase;
    const payload = this._pendingCaseSave ? this._pendingCaseSave.payload : u.retryableCreate(this, "caseSave", {
      title: title.slice(0, 150),
      scenario: this.data.response ? this.data.response.scenario : "unclear",
      use_profile_context: this.data.useSavedContext,
      context: Object.assign({}, this.data.context, {
        preferred_language: this.data.preferredLanguage
      })
    }, workspace.requestId);
    const save = this._pendingCaseSave || {
      ownerEpoch, turns, payload, caseId: "", caseTitle: "", nextTurn: 0, nextChunk: 0, notes: {}, partial: false
    };
    this._pendingCaseSave = save;
    this.keepDraft();
    let session;
    return workspace.ensure().then((value) => {
      session = value;
      sameOwner();
      return save.caseId ? { case: { case_id: save.caseId, title: save.caseTitle } } : workspace.createCase(payload);
    }).then(async(result) => {
      sameOwner();
      u.finishCreate(this, "caseSave");
      save.caseId = result.case.case_id;
      save.caseTitle = result.case.title;
      if (current()) this.setData({
        caseId: result.case.case_id,
        caseTitle: result.case.title
      });
      // A trace attachment includes its question. Keep every other question as
      // a labeled note, including a first attempt that never received an answer.
      for (let index = save.nextTurn; index < turns.length; index += 1) {
        const turn = turns[index];
        if (turn.kind !== "user") continue;
        const answer = turns[index + 1];
        const traceId = answer && answer.kind === "assistant" && answer.response && answer.response.trace_id;
        sameOwner();
        if (traceId && !save.notes[index]) {
          try {
            await workspace.attachTurn(result.case.case_id, traceId);
            save.nextTurn = index + 1;
            continue;
          } catch (error) {
            if (error.stale) throw error;
            sameOwner();
          }
        }
        save.partial = true;
        const label = this.data.ui.savedQuestionNote + "\n\n";
        const characters = Array.from(turn.text || "");
        const chunkSize = 8000 - Array.from(label).length;
        if (!save.notes[index]) {
          save.notes[index] = [];
          for (let offset = 0; offset < characters.length; offset += chunkSize) {
            save.notes[index].push({
              client_request_id: workspace.requestId(),
              text: label + characters.slice(offset, offset + chunkSize).join(""),
              kind: "note"
            });
          }
        }
        for (; save.nextChunk < save.notes[index].length; save.nextChunk += 1) {
          sameOwner();
          await workspace.addMessage(result.case.case_id, save.notes[index][save.nextChunk]);
        }
        save.nextTurn = index + 1;
        save.nextChunk = 0;
      }
      save.complete = true;
      if (current()) {
        this._pendingCaseSave = null;
        this.setData({
          saving: false,
          caseSavePending: false,
          saveStatus: (save.partial ? this.data.ui.historyPartial : this.data.ui.caseSaved) + (session
            .persistent ? "" : " " + this.data.ui.sessionOnly)
        });
        this.keepDraft();
      }
    }).catch((e) => {
      if (current()) {
        u.error(this, e);
        if (save.caseId && !(e.status === 401 || e.status === 403)) this.setData({ error: this.data.ui.caseSaveRetryHint });
        this.keepDraft();
      }
    });
  },
  goSupport(event) {
    if (!this.ownsTurns()) return;
    const id = event && event.currentTarget && event.currentTarget.dataset.id;
    const selected = this._turns.find((turn) => turn.id === id);
    const response = selected ? selected.response : this._response;
    const selectedView = selected ? selected.answerView : this._answerView;
    const app = getApp(),
      prefill = response ? response.escalation_prefill : null;
    if (app && app.globalData) app.globalData.supportDraftContext = {
      session_id: clientContext.getSessionId(),
      case_id: this.data.caseId || null,
      related_turn_id: response ? response.trace_id : null,
      source: prefill ? "chat_safety_policy" : "chat",
      draft_message: prefill ? prefill.summary : format.safeText(selectedView ? selectedView.userQuestion :
        this.data.submittedMessage || this.data.message),
      scenario: prefill ? prefill.scenario : selectedView ? selectedView.scenario : "",
      risk_level: prefill ? prefill.risk_level : selectedView ? selectedView.riskLevel : "",
      escalation_reason: prefill ? prefill.reason : "needs_human_help",
      urgency: prefill ? prefill.urgency : "normal",
      not_emergency_dispatch: prefill ? Boolean(prefill.not_emergency_dispatch) : false,
      safety_warning: prefill ? prefill.safety_warning : "",
      created_at: new Date().toISOString()
    };
    wx.navigateTo({
      url: "/pages/support/index"
    });
  },
  requestHumanHelpFromSafety(event) {
    this.goSupport(event);
  },
  newConversation() {
    if (this.data.loading || this.data.saving) return;
    u.finishCreate(this, "caseSave");
    u.invalidateRequests(this, "caseLoad");
    u.invalidateRequests(this, "profile");
    u.invalidateRequests(this, "contextSave");
    this._caseLoaded = false;
    this.clearTurnCache();
    this.setData({
      message: "",
      submittedMessage: "",
      response: null,
      answerView: null,
      turns: [],
      turnOffset: 0,
      turnEnd: 0,
      turnTotal: 0,
      hasPreviousTurns: false,
      hasNextTurns: false,
      fullTurnOpen: false,
      fullTurnText: "",
      fullTurnParts: 0,
      caseId: "",
      caseTitle: "",
      caseStatus: "open",
      context: {},
      useSavedContext: false,
      explicitCity: "",
      caseLoading: false,
      cloudFallback: false,
      sourcesExpanded: false,
      detailsExpanded: false,
      photoDraftContext: null,
      photoDraftWarnings: [],
      safetyFlags: [],
      error: "",
      saveStatus: "",
      caseSavePending: false,
      resetContext: true
    });
    const app = getApp();
    if (app && app.globalData) {
      app.globalData.photoDraftContext = null;
      app.globalData.pendingChatPrefill = "";
      app.globalData.supportDraftContext = null;
      app.globalData.chatDraft = null;
      app.globalData.activeCase = null;
    }
  },
  toggleSources(event) {
    this.toggleTurn(event, "sourcesExpanded");
  },
  toggleDetails(event) {
    this.toggleTurn(event, "detailsExpanded");
  },
  toggleTurn(event, key) {
    if (!this.ownsTurns()) return;
    const id = event && event.currentTarget && event.currentTarget.dataset.id;
    if (!id) {
      const patch = {};
      patch[key] = !this.data[key];
      this.setData(patch);
      return;
    }
    this._turns = this._turns.map((turn) => {
      if (turn.id !== id) return turn;
      const patch = {};
      patch[key] = !turn[key];
      return Object.assign({}, turn, patch);
    });
    this.renderTurns(this.data.turnOffset);
  },
  copySourceLink(event) {
    if (!this.ownsTurns()) return;
    const data = event.currentTarget.dataset;
    const turn = this._turns.find((t) => t.id === data.turn);
    const view = turn ? turn.answerView : this._answerView;
    const source = view && view.sourceNotes[data.index];
    if (source && source.url) wx.setClipboardData({
      data: source.url
    });
  },
  goPhoto() {
    wx.navigateTo({
      url: "/pages/photo-intake/index"
    });
  },
  goProfile: u.goProfile
});

function buildPhotoDraftWarnings(context) {
  const ui = i18n.labels();
  return unique([].concat(context.privacy_warnings || [], context.safety_warnings || [], [ui.reviewImported,
    ui.personalDataNotice, ui.untrustedText
  ]));
}
