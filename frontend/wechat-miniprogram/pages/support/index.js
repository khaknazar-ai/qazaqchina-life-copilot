const api = require("../../utils/api");
const format = require("../../utils/format");
const clientContext = require("../../utils/clientContext");
const i18n = require("../../utils/i18n");
const workspace = require("../../utils/workspace");
const u = require("../../utils/workspaceUi");
const {
  boundedWindow
} = require("../../utils/renderBudget");
const TICKET_PAGE_SIZE = 30;
const REPLY_PAGE_SIZE = 10;

function preview(value, length = 240) {
  const text = String(value || "");
  return text.length > length ? text.slice(0, length) + "…" : text;
}

const FEEDBACK_LABELS = {
  answer_wrong: "Report wrong answer",
  outdated_info: "Report outdated information",
  unsafe_advice: "Unsafe advice",
  source_problem: "Source problem"
};

const ESCALATION_LABELS = {
  needs_human_help: "Request human help",
  scam_or_payment_risk: "Scam/payment risk",
  medical_risk: "Medical risk",
  legal_or_visa_risk: "Legal/visa risk",
  emergency: "Urgent/high-risk case"
};

const FEEDBACK_KEYS = {
  answer_wrong: "wrongAnswer",
  outdated_info: "outdatedInfo",
  unsafe_advice: "unsafeAdvice",
  source_problem: "sourceProblem"
};
const ESCALATION_KEYS = {
  needs_human_help: "human",
  scam_or_payment_risk: "paymentRisk",
  medical_risk: "medicalRisk",
  legal_or_visa_risk: "legalVisaRisk",
  emergency: "urgentCase"
};
const FEEDBACK_CATEGORIES = Object.keys(FEEDBACK_LABELS);
const ESCALATION_REASONS = Object.keys(ESCALATION_LABELS);

function pickerState(value, ui) {
  const feedbackCategory = FEEDBACK_CATEGORIES.includes(value.feedbackCategory) ? value.feedbackCategory : "answer_wrong";
  const escalationReason = ESCALATION_REASONS.includes(value.escalationReason) ? value.escalationReason : "needs_human_help";
  return {
    feedbackCategory,
    feedbackCategoryIndex: FEEDBACK_CATEGORIES.indexOf(feedbackCategory),
    feedbackCategoryLabel: ui[FEEDBACK_KEYS[feedbackCategory]] || FEEDBACK_LABELS[feedbackCategory],
    escalationReason,
    escalationReasonIndex: ESCALATION_REASONS.indexOf(escalationReason),
    escalationReasonLabel: ui[ESCALATION_KEYS[escalationReason]] || ESCALATION_LABELS[escalationReason]
  };
}

Page({
  data: Object.assign({}, i18n.pageState(), {
    mode: "help",
    tickets: [],
    ticketId: "",
    openedTicket: null,
    ticketOffset: 0,
    ticketTotal: 0,
    ticketPage: 1,
    ticketPageCount: 1,
    hasPreviousTickets: false,
    hasNextTickets: false,
    replyOffset: 0,
    replyDraft: "",
    replyPage: 1,
    replyPageCount: 1,
    hasPreviousReplies: false,
    hasNextReplies: false,
    caseId: "",
    requestLoading: false,
    ticketLoading: false,
    requestStatus: "",
    sessionId: "",
    relatedTurnId: null,
    escalationUrgency: "normal",
    feedbackCategory: "answer_wrong",
    feedbackCategoryIndex: 0,
    feedbackCategoryLabel: FEEDBACK_LABELS.answer_wrong,
    escalationReason: "needs_human_help",
    escalationReasonIndex: 0,
    escalationReasonLabel: ESCALATION_LABELS.needs_human_help,
    message: "",
    summary: "",
    scenario: "",
    riskLevel: "",
    feedbackLoading: false,
    escalationLoading: false,
    feedbackStatus: "",
    escalationStatus: "",
    prefillNotice: "",
    safetyWarning: "",
    feedbackError: "",
    escalationError: "",
    error: ""
  }),

  onLoad() {
    this._ownerEpoch = clientContext.getOwnerEpoch();
    this._cacheEpoch = this._ownerEpoch;
    this._tickets = [];
    this.setData(Object.assign({}, pickerState(this.data, this.data.ui), {
      sessionId: clientContext.getSessionId()
    }));
    const app = getApp();
    const context = app && app.globalData ? app.globalData.supportDraftContext : null;
    if (!context) {
      return;
    }
    app.globalData.supportDraftContext = null;
    const reason = context.escalation_reason || context.reason || "needs_human_help";
    this.setData(Object.assign({}, pickerState(Object.assign({}, this.data, { escalationReason: reason }), this.data.ui), {
      caseId: context.case_id || "",
      sessionId: clientContext.getSessionId(),
      relatedTurnId: context.related_turn_id || null,
      escalationUrgency: ["normal", "high", "urgent"].indexOf(context.urgency) >= 0 ? context.urgency :
        "normal",
      message: context.draft_message || "",
      summary: context.draft_message || "",
      scenario: context.scenario || "",
      riskLevel: context.risk_level || "",
      prefillNotice: context.source === "chat_safety_policy" ?
        this.data.ui.reviewPrefill || "Safety policy prefill. Review/edit before submitting." :
        "",
      safetyWarning: context.safety_warning || ""
    }));
  },

  selectFeedbackCategory(event) {
    if (this.data.feedbackLoading) return;
    const category = event.currentTarget.dataset.category || "answer_wrong";
    if (!FEEDBACK_CATEGORIES.includes(category)) return;
    this.setData(pickerState(Object.assign({}, this.data, { feedbackCategory: category }), this.data.ui));
  },

  selectEscalationReason(event) {
    if (this.data.escalationLoading) return;
    const reason = event.currentTarget.dataset.reason || "needs_human_help";
    if (!ESCALATION_REASONS.includes(reason)) return;
    this.setData(pickerState(Object.assign({}, this.data, { escalationReason: reason }), this.data.ui));
  },

  onMessageInput(event) {
    this.setData({
      message: event.detail.value
    });
  },

  onSummaryInput(event) {
    this.setData({
      summary: event.detail.value,
      message: event.detail.value
    });
  },

  submitFeedback(event) {
    if (!this.checkOwner() || this.data.feedbackLoading) return;
    const message = format.safeText(formValue(event, "message", this.data.message));
    if (!message) {
      this.setData({
        error: this.data.ui.enterMessage,
        feedbackError: this.data.ui.enterMessage
      });
      return;
    }
    this.setData({
      message,
      feedbackLoading: true,
      error: "",
      feedbackError: "",
      feedbackStatus: ""
    });
    const current = u.latestRequest(this, "feedbackMutation");
    return api
      .createFeedback({
        session_id: this.data.sessionId || clientContext.getSessionId(),
        related_turn_id: this.data.relatedTurnId,
        category: this.data.feedbackCategory,
        message,
        severity: this.data.feedbackCategory === "unsafe_advice" ? "high" : "normal",
        scenario: this.data.scenario,
        risk_level: this.data.riskLevel,
        metadata: {
          source: "miniprogram_support_page",
          not_trusted_source_evidence: true
        }
      })
      .then((response) => {
        if (!current()) return;
        this.setData({
          feedbackLoading: false,
          feedbackStatus: `${this.data.ui.feedbackSent || "Feedback submitted"}: ${response.feedback_id}`
        });
      })
      .catch(() => {
        if (!current()) return;
        this.setData({
          feedbackLoading: false,
          error: this.data.ui.requestFailed,
          feedbackError: this.data.ui.requestFailed
        });
      });
  },

  submitEscalation(event) {
    if (!this.checkOwner() || this.data.escalationLoading) return;
    const summary = format.safeText(formValue(event, "summary", this.data.summary || this.data.message));
    if (!summary) {
      this.setData({
        error: this.data.ui.enterMessage,
        escalationError: this.data.ui.enterMessage
      });
      return;
    }
    this.setData({
      summary,
      escalationLoading: true,
      error: "",
      escalationError: "",
      escalationStatus: ""
    });
    const current = u.latestRequest(this, "escalationMutation");
    return api
      .createEscalation({
        session_id: this.data.sessionId || clientContext.getSessionId(),
        related_turn_id: this.data.relatedTurnId,
        scenario: this.data.scenario,
        risk_level: this.data.riskLevel,
        summary,
        reason: this.data.escalationReason,
        urgency: this.data.escalationReason === "emergency" || this.data.escalationUrgency === "urgent" ?
          "urgent" :
          this.data.escalationUrgency === "high" || ["medical_risk", "legal_or_visa_risk",
            "scam_or_payment_risk"
          ].indexOf(this.data.escalationReason) >= 0 ?
          "high" : "normal",
        metadata: {
          source: "miniprogram_support_page",
          not_trusted_source_evidence: true
        }
      })
      .then((response) => {
        if (!current()) return;
        this.setData({
          escalationLoading: false,
          escalationStatus: `${this.data.ui.helpSent || "Escalation request submitted"}: ${response.escalation_id}. ${response.safety_message}`
        });
      })
      .catch(() => {
        if (!current()) return;
        this.setData({
          escalationLoading: false,
          error: this.data.ui.requestFailed,
          escalationError: this.data.ui.requestFailed
        });
      });
  },

  goPrivacy() {
    wx.navigateTo({
      url: "/pages/privacy/index"
    });
  },

  onShow() {
    i18n.refresh(this);
    this._active = true;
    this.checkOwner();
    u.resetOnOwnerChange(this, Object.assign({}, pickerState({}, this.data.ui), {
      sessionId: clientContext.getSessionId(),
      escalationUrgency: "normal",
      scenario: "",
      riskLevel: "",
      tickets: [],
      ticketId: "",
      openedTicket: null,
      caseId: "",
      message: "",
      summary: "",
      error: "",
      requestStatus: "",
      requestLoading: false,
      ticketLoading: false,
      feedbackLoading: false,
      escalationLoading: false,
      relatedTurnId: null,
      prefillNotice: "",
      safetyWarning: "",
      ticketOffset: 0,
      ticketTotal: 0,
      ticketPage: 1,
      ticketPageCount: 1,
      hasPreviousTickets: false,
      hasNextTickets: false,
      replyOffset: 0,
      replyPage: 1,
      replyPageCount: 1,
      hasPreviousReplies: false,
      hasNextReplies: false
    }));
    this.loadTickets();
    this.setData(pickerState(this.data, this.data.ui));
  },

  selectMode(event) {
    if (!this.data.requestLoading) this.setData({
      mode: event.currentTarget.dataset.mode,
      error: "",
      requestStatus: ""
    });
  },
  selectReason(event) {
    this.selectEscalationReason({
      currentTarget: {
        dataset: {
          reason: ESCALATION_REASONS[Number(event.detail.value)]
        }
      }
    });
  },
  selectCategory(event) {
    this.selectFeedbackCategory({
      currentTarget: {
        dataset: {
          category: FEEDBACK_CATEGORIES[Number(event.detail.value)]
        }
      }
    });
  },
  checkOwner() {
    if (this._active === false) return false;
    const epoch = clientContext.getOwnerEpoch();
    if (this._cacheEpoch !== undefined && this._cacheEpoch !== epoch) {
      this._tickets = [];
      this._creates = {};
      u.invalidateRequests(this);
      this.setData(Object.assign({}, pickerState({}, this.data.ui), {
        sessionId: clientContext.getSessionId(),
        escalationUrgency: "normal",
        scenario: "",
        riskLevel: "",
        tickets: [],
        ticketId: "",
        openedTicket: null,
        replyDraft: "",
        caseId: "",
        message: "",
        summary: "",
        requestLoading: false,
        ticketLoading: false,
        feedbackLoading: false,
        escalationLoading: false,
        relatedTurnId: null,
        prefillNotice: "",
        safetyWarning: "",
        requestStatus: "",
        feedbackStatus: "",
        escalationStatus: "",
        feedbackError: "",
        escalationError: "",
        error: "",
        ticketOffset: 0,
        ticketTotal: 0,
        ticketPage: 1,
        ticketPageCount: 1,
        hasPreviousTickets: false,
        hasNextTickets: false,
        replyOffset: 0,
        replyPage: 1,
        replyPageCount: 1,
        hasPreviousReplies: false,
        hasNextReplies: false
      }));
      this._cacheEpoch = epoch;
      return false;
    }
    this._cacheEpoch = epoch;
    return true;
  },
  ticketSummary(ticket) {
    return {
      ticket_id: ticket.ticket_id,
      summary: preview(ticket.summary),
      status: ticket.status,
      created_at: preview(ticket.created_at, 80),
      replyCount: (ticket.replies || []).length,
      staffed: ticket.staffed,
      not_emergency_dispatch: ticket.not_emergency_dispatch,
      queue_status_available: ticket.queue_status_available,
      queue_sync_pending: ticket.queue_sync_pending,
      statusLabel: ticket.queue_status_available === false || ticket.queue_sync_pending ? this.data.ui.queueStatusUnknown :
        this.data.ui[ticket.status] || ticket.status,
      queueNotice: ticket.queue_sync_pending ? this.data.ui.queueSyncPending : ticket.queue_status_available ===
        false ? this.data.ui.queueStatusUnavailable : ""
    };
  },
  renderTicket(offset = 0) {
    if (!this.checkOwner()) return;
    const ticket = (this._tickets || []).find((item) => item.ticket_id === this.data.ticketId);
    if (!ticket) {
      this.setData({
        ticketId: "",
        openedTicket: null,
        replyOffset: 0,
        replyPage: 1,
        replyPageCount: 1,
        hasPreviousReplies: false,
        hasNextReplies: false
      });
      return;
    }
    const replies = ticket.replies || [];
    const start = Math.max(0, Math.min(offset, Math.floor(Math.max(0, replies.length - 1) /
      REPLY_PAGE_SIZE) * REPLY_PAGE_SIZE));
    const view = boundedWindow(replies.map((reply) => ({
      reply_id: reply.reply_id,
      role: reply.role,
      text: reply.text,
      created_at: preview(reply.created_at, 80)
    })), {
      offset: start,
      limit: REPLY_PAGE_SIZE,
      maxBytes: 256 * 1024
    });
    this.setData({
      openedTicket: Object.assign(this.ticketSummary(ticket), {
        summary: ticket.summary,
        replies: view.items
      }),
      replyOffset: view.offset,
      replyPage: Math.floor(view.offset / REPLY_PAGE_SIZE) + 1,
      replyPageCount: Math.max(1, Math.ceil(replies.length / REPLY_PAGE_SIZE)),
      hasPreviousReplies: view.hasPrevious,
      hasNextReplies: view.hasNext
    });
  },
  loadTickets() {
    if (!this.checkOwner() || this.data.requestLoading) return Promise.resolve();
    const current = u.latestRequest(this, "tickets");
    const offset = this.data.ticketOffset;
    this.setData({
      ticketLoading: true
    });
    return workspace.call(`/support?limit=${TICKET_PAGE_SIZE}&offset=${offset}`).then((r) => {
      if (!current()) return;
      const raw = r.tickets || [],
        total = Math.max(0, Number(r.total) || raw.length);
      if (total && offset >= total) {
        this.setData({
          ticketOffset: Math.floor((total - 1) / TICKET_PAGE_SIZE) * TICKET_PAGE_SIZE
        });
        return this.loadTickets();
      }
      this._tickets = raw;
      const rows = boundedWindow(raw.map((ticket) => this.ticketSummary(ticket)), {
        limit: TICKET_PAGE_SIZE,
        maxBytes: 128 * 1024
      }).items;
      this.setData({
        tickets: rows,
        ticketLoading: false,
        ticketTotal: total,
        ticketPage: Math.floor(offset / TICKET_PAGE_SIZE) + 1,
        ticketPageCount: Math.max(1, Math.ceil(total / TICKET_PAGE_SIZE)),
        hasPreviousTickets: offset > 0,
        hasNextTickets: offset + TICKET_PAGE_SIZE < total
      });
      this.renderTicket(this.data.replyOffset);
    }).catch((e) => {
      if (current()) {
        this.setData({
          ticketLoading: false
        });
        u.error(this, e);
      }
    });
  },
  previousTickets() {
    if (!this.checkOwner() || this.data.ticketLoading || this.data.requestLoading || !this.data.hasPreviousTickets)
      return;
    this.setData({
      ticketOffset: Math.max(0, this.data.ticketOffset - TICKET_PAGE_SIZE),
      ticketId: "",
      openedTicket: null,
      replyDraft: ""
    });
    return this.loadTickets();
  },
  nextTickets() {
    if (!this.checkOwner() || this.data.ticketLoading || this.data.requestLoading || !this.data.hasNextTickets)
      return;
    this.setData({
      ticketOffset: this.data.ticketOffset + TICKET_PAGE_SIZE,
      ticketId: "",
      openedTicket: null,
      replyDraft: ""
    });
    return this.loadTickets();
  },
  previousReplies() {
    if (!this.checkOwner() || !this.data.hasPreviousReplies) return;
    this.renderTicket(Math.max(0, this.data.replyOffset - REPLY_PAGE_SIZE));
  },
  nextReplies() {
    if (!this.checkOwner() || !this.data.hasNextReplies) return;
    this.renderTicket(this.data.replyOffset + REPLY_PAGE_SIZE);
  },
  onUnload() {
    this._active = false;
    this._tickets = [];
    this._creates = {};
    u.invalidateRequests(this);
  },
  submitRequest(event) {
    if (!this.checkOwner() || this.data.requestLoading || this.data.feedbackLoading) return;
    const message = formValue(event, "message", this.data.summary || this.data.message).trim();
    if (!message) {
      this.setData({
        error: this.data.ui.enterMessage
      });
      return;
    }
    this.setData({
      message,
      summary: message,
      error: "",
      requestStatus: ""
    });
    if (this.data.mode === "feedback") return this.submitFeedback({
      detail: {
        value: {
          message
        }
      }
    });
    u.invalidateRequests(this, "tickets");
    const current = u.latestRequest(this, "ticketMutation");
    this.setData({
      requestLoading: true,
      ticketLoading: false
    });
    const urgency = this.data.escalationReason === "emergency" || this.data.escalationUrgency ===
      "urgent" ? "urgent" :
      this.data.escalationUrgency === "high" || ["medical_risk", "legal_or_visa_risk",
        "scam_or_payment_risk"
      ].includes(this.data.escalationReason) ? "high" : "normal";
    const payload = u.retryableCreate(this, "supportRequest", {
      summary: message,
      reason: this.data.escalationReason,
      urgency,
      case_id: this.data.caseId || null
    }, workspace.requestId);
    return workspace.createSupport(payload)
      .then((r) => {
        if (!current()) return;
        u.finishCreate(this, "supportRequest");
        this.setData({
          requestLoading: false,
          requestStatus: this.data.ui.helpSent,
          ticketId: r.ticket.ticket_id,
          ticketOffset: 0,
          replyOffset: 0,
          summary: "",
          message: ""
        });
        return this.loadTickets();
      })
      .catch((e) => {
        if (current()) {
          this.setData({
            requestLoading: false
          });
          u.error(this, e);
        }
      });
  },
  openTicket(event) {
    if (!this.checkOwner() || this.data.requestLoading) return;
    const id = event.currentTarget.dataset.id;
    if (!(this._tickets || []).some((ticket) => ticket.ticket_id === id)) return;
    this.setData({
      ticketId: this.data.ticketId === id ? "" : id,
      replyDraft: ""
    });
    this.renderTicket(0);
  },
  onReplyInput(event) {
    if (this.checkOwner() && !this.data.requestLoading) this.setData({
      replyDraft: event.detail.value
    });
  },
  reply(event) {
    if (!this.checkOwner() || this.data.requestLoading) return;
    const text = formValue(event, "reply", this.data.replyDraft).trim();
    if (!text) return;
    const ticketId = event.currentTarget.dataset.id;
    const ticket = (this._tickets || []).find((item) => item.ticket_id === ticketId);
    this.setData({ replyDraft: text });
    if (!ticket || ["closed", "resolved"].includes(ticket.status)) {
      this.setData({ error: this.data.ui.reopenTicketHint });
      return;
    }
    u.invalidateRequests(this, "tickets");
    const current = u.latestRequest(this, "ticketMutation");
    this.setData({
      requestLoading: true,
      ticketLoading: false,
      error: ""
    });
    return workspace.reply(ticketId, text).then((r) => {
        if (!current()) return;
        const count = r.ticket && Array.isArray(r.ticket.replies) ? r.ticket.replies.length : 0;
        this.setData({
          requestLoading: false,
          replyDraft: "",
          replyOffset: Math.floor(Math.max(0, count - 1) / REPLY_PAGE_SIZE) * REPLY_PAGE_SIZE
        });
        return this.loadTickets();
      })
      .catch((e) => {
        if (current()) {
          this.setData({
            requestLoading: false
          });
          if (e.status === 409 && e.message === "reopen_ticket_before_replying") {
            this.setData({ error: this.data.ui.reopenTicketHint });
            return this.loadTickets();
          }
          u.error(this, e);
        }
      });
  },
  ticketStatus(event) {
    if (!this.checkOwner() || this.data.requestLoading) return;
    u.invalidateRequests(this, "tickets");
    const current = u.latestRequest(this, "ticketMutation");
    this.setData({
      requestLoading: true,
      ticketLoading: false,
      error: ""
    });
    return workspace.updateSupport(event.currentTarget.dataset.id, event.currentTarget.dataset.status)
      .then(() => {
        if (!current()) return;
        this.setData({
          requestLoading: false
        });
        return this.loadTickets();
      })
      .catch((e) => {
        if (current()) {
          this.setData({
            requestLoading: false
          });
          u.error(this, e);
        }
      });
  },
  goProfile: u.goProfile
});

function formValue(event, name, fallback) {
  const values = event && event.detail && event.detail.value;
  return values && typeof values === "object" && name in values ? values[name] : fallback;
}
