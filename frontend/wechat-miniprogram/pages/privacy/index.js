const api = require("../../utils/api");
const format = require("../../utils/format");
const i18n = require("../../utils/i18n");
const context = require("../../utils/clientContext");
const u = require("../../utils/workspaceUi");

Page({
  data: Object.assign({}, i18n.pageState(), {
    redactionText: "",
    redactedText: "",
    redactionWarning: "",
    deleteMessage: "",
    contact: "",
    targetScope: "session",
    policies: [],
    redactionLoading: false,
    deleteLoading: false,
    policyLoading: false,
    redactionError: "",
    deleteError: "",
    policyError: "",
    deleteStatus: "",
    error: ""
  }),

  onLoad() {
    this._unloaded = false;
    this.syncOwner();
    this.loadPolicies();
  },

  syncOwner() {
    if (this._unloaded) return false;
    const epoch = context.getOwnerEpoch();
    if (this._ownerEpoch === undefined) this._ownerEpoch = epoch;
    else if (this._ownerEpoch !== epoch) {
      this._ownerEpoch = epoch;
      this.clearPrivateState();
      return false;
    }
    return true;
  },

  clearPrivateState(render = true) {
    u.invalidateRequests(this);
    const empty = {
      redactionText: "", redactedText: "", redactionWarning: "", deleteMessage: "", contact: "",
      targetScope: "session", policies: [], redactionLoading: false, deleteLoading: false,
      policyLoading: false, redactionError: "", deleteError: "", policyError: "", deleteStatus: "", error: ""
    };
    if (render) this.setData(empty);
    else Object.assign(this.data, empty);
  },

  onRedactionInput(event) {
    if (!this.syncOwner()) return;
    this.setData({ redactionText: event.detail.value });
  },

  onDeleteMessageInput(event) {
    if (!this.syncOwner()) return;
    this.setData({ deleteMessage: event.detail.value });
  },

  onContactInput(event) {
    if (!this.syncOwner()) return;
    this.setData({ contact: event.detail.value });
  },

  selectScope(event) {
    if (!this.syncOwner() || this.data.deleteLoading) return;
    const scope = event.currentTarget.dataset.scope;
    if (["session", "feedback", "escalation", "all_known_data"].indexOf(scope) < 0) return;
    this.setData({ targetScope: scope });
  },

  previewRedaction(event) {
    if (!this.syncOwner() || this.data.redactionLoading) return;
    const text = format.safeText(formValue(event, "redactionText", this.data.redactionText));
    if (!text) {
      this.setData({ error: this.data.ui.enterMessage, redactionError: this.data.ui.enterMessage });
      return;
    }
    this.setData({ redactionText: text, redactionLoading: true, error: "", redactionError: "", redactedText: "", redactionWarning: "" });
    const current = u.latestRequest(this, "redaction");
    return api
      .redactPreview({ text })
      .then((response) => {
        if (!this.syncOwner() || !current()) return;
        this.setData({
          redactionLoading: false,
          redactedText: response.redacted_text || "",
          redactionWarning: (response.warnings || []).join(" ")
        });
      })
      .catch((error) => {
        if (!this.syncOwner() || !current() || error.stale) return;
        this.setData({
          redactionLoading: false,
          error: this.data.ui.requestFailed,
          redactionError: this.data.ui.requestFailed
        });
      });
  },

  submitDeleteRequest(event) {
    if (!this.syncOwner() || this.data.deleteLoading) return;
    const message = format.safeText(formValue(event, "deleteMessage", this.data.deleteMessage));
    const contact = format.safeText(formValue(event, "contact", this.data.contact));
    if (!message) {
      this.setData({ error: this.data.ui.enterMessage, deleteError: this.data.ui.enterMessage });
      return;
    }
    this.setData({ deleteMessage: message, contact, deleteLoading: true, error: "", deleteError: "", deleteStatus: "" });
    const current = u.latestRequest(this, "deletion");
    return api
      .createDeleteRequest({
        message,
        contact,
        target_scope: this.data.targetScope,
        metadata: {
          source: "miniprogram_privacy_page",
          workflow_only: true
        }
      })
      .then((response) => {
        if (!this.syncOwner() || !current()) return;
        this.setData({
          deleteLoading: false,
          deleteStatus: `${this.data.ui.deletionSent || "Delete request submitted for review"}: ${response.request_id}. ${response.safety_message}`
        });
      })
      .catch((error) => {
        if (!this.syncOwner() || !current() || error.stale) return;
        this.setData({
          deleteLoading: false,
          error: this.data.ui.requestFailed,
          deleteError: this.data.ui.requestFailed
        });
      });
  },

  loadPolicies() {
    if (!this.syncOwner() || this.data.policyLoading) return;
    const current = u.latestRequest(this, "policies");
    this.setData({ policyLoading: true, error: "", policyError: "" });
    return api
      .getPrivacyPolicies()
      .then((policies) => {
        if (!this.syncOwner() || !current()) return;
        this.setData({ policyLoading: false, policies: policies || [] });
      })
      .catch((error) => {
        if (!this.syncOwner() || !current() || error.stale) return;
        this.setData({
          policyLoading: false,
          error: this.data.ui.loadError || this.data.ui.requestFailed,
          policyError: this.data.ui.loadError || this.data.ui.requestFailed
        });
      });
  },

  onShow() {
    if (this._unloaded) return;
    const sameOwner = this.syncOwner();
    i18n.refresh(this);
    if (!sameOwner) this.loadPolicies();
  },

  onUnload() {
    this._unloaded = true;
    this.clearPrivateState(false);
  }
});

function formValue(event, name, fallback) {
  const values = event && event.detail && event.detail.value;
  return values && typeof values === "object" && name in values ? values[name] : fallback;
}
