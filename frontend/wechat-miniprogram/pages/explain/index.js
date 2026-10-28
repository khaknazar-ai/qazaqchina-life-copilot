const api = require("../../utils/api");
const workspace = require("../../utils/workspace");
const i18n = require("../../utils/i18n");
const u = require("../../utils/workspaceUi");
const documentInput = require("../../utils/documentInput");
const context = require("../../utils/clientContext");
const {
  documentPresentation
} = require("../../utils/documentPresentation");
const SAMPLE_TEXT = "请携带护照和签证到派出所办理登记。";
const NEUTRAL_PHRASE = "请确认这条信息的意思和需要我做的事。谢谢。";
Page({
  data: Object.assign({}, i18n.pageState(), {
    text: "",
    loading: false,
    error: "",
    response: null,
    explanationView: {
      summary: "",
      explanation: "",
      notices: []
    },
    phrase: "",
    phraseMeaning: "",
    showPhrase: false,
    noticesExpanded: false,
    originalExpanded: false,
    partContext: null,
    reviewedScope: null,
    documentPartIndex: 0,
    documentPartOptions: [],
    selectedDocumentText: ""
  }),
  onLoad() {
    this._unloaded = false;
    this.syncOwner();
  },
  syncOwner() {
    if (this._unloaded) return false;
    const epoch = context.getOwnerEpoch();
    if (this._ownerEpoch === undefined) this._ownerEpoch = epoch;
    else if (this._ownerEpoch !== epoch) {
      this._ownerEpoch = epoch;
      this.clearPrivateDocument();
      return false;
    }
    return true;
  },
  clearPrivateDocument(render = true) {
    u.invalidateRequests(this);
    const empty = {
      text: "", loading: false, error: "", response: null,
      explanationView: { summary: "", explanation: "", notices: [] },
      phrase: "", phraseMeaning: "", showPhrase: false, noticesExpanded: false, originalExpanded: false,
      partContext: null, reviewedScope: null, documentPartIndex: 0,
      documentPartOptions: [], selectedDocumentText: "", saved: false
    };
    if (render) this.setData(empty);
    else Object.assign(this.data, empty);
  },
  onShow() {
    if (this._unloaded) return;
    this.syncOwner();
    i18n.refresh(this);
    const global = getApp().globalData;
    if (global.pendingExplanation) {
      this.clearPrivateDocument();
      this.setData({
        text: global.pendingExplanation.text,
        partContext: global.pendingExplanation,
        reviewedScope: null,
        response: null,
        explanationView: {
          summary: "",
          explanation: "",
          notices: []
        }
      });
      global.pendingExplanation = null;
      this.updateDocumentParts();
    }
  },
  onTextInput(event) {
    if (!this.syncOwner()) return;
    if (!this.data.loading) {
      this.setData({
        text: event.detail.value,
        reviewedScope: null
      });
      this.updateDocumentParts();
    }
  },
  updateDocumentParts(index = 0) {
    const parts = documentInput.splitForReview(this.data.text);
    const selected = Math.max(0, Math.min(index, parts.length - 1));
    this.setData({
      documentPartIndex: selected,
      documentPartOptions: parts.map((_, i) => (i + 1) + " / " + parts.length),
      selectedDocumentText: parts[selected] || ""
    });
    return parts;
  },
  selectDocumentPart(event) {
    if (!this.syncOwner()) return;
    if (!this.data.loading) this.updateDocumentParts(Number(event.detail.value));
  },
  useSample() {
    if (!this.syncOwner()) return;
    if (!this.data.loading) {
      this.setData({
        text: SAMPLE_TEXT,
        partContext: null,
        reviewedScope: null,
        error: ""
      });
      this.updateDocumentParts();
    }
  },
  explainText(event) {
    if (!this.syncOwner()) return;
    if (this.data.loading) return;
    const original = u.form(event, "text", this.data.text);
    if (!original) {
      this.setData({
        error: this.data.ui.enterMessage
      });
      return;
    }
    const changed = original !== this.data.text;
    this.setData(Object.assign({ text: original }, changed ? { reviewedScope: null } : {}));
    const parts = this.updateDocumentParts(changed ? 0 : this.data.documentPartIndex);
    if (parts.length > 1 && changed) {
      this.setData({
        error: this.data.ui.documentLimit
      });
      return;
    }
    const text = this.data.selectedDocumentText;
    const origin = this.data.partContext;
    this.setData({
      loading: true,
      error: "",
      response: null,
      reviewedScope: {
        part_number: this.data.documentPartIndex + 1,
        part_count: parts.length,
        reviewed_character_count: Array.from(text).length,
        input_character_count: Array.from(original).length,
        origin_part_number: origin ? origin.part_number : 1,
        origin_part_count: origin ? origin.part_count : 1,
        original_character_count: origin && origin.original_character_count || Array.from(original).length
      },
      phrase: "",
      phraseMeaning: "",
      noticesExpanded: false
    });
    const current = u.latestRequest(this, "explain");
    return api.explainChineseText(text).then((response) => {
      if (this.syncOwner() && current()) this.presentResponse(response);
    }).catch((error) => {
      if (!this.syncOwner() || !current() || error.stale) return;
      const needsSignin = error.code === "pilot_access_required" || error.message === "pilot_access_required";
      this.setData({
        loading: false,
        error: needsSignin ? this.data.ui.translationAccessRequired : this.data.ui.requestFailed
      });
    });
  },
  presentResponse(response) {
    if (!this.syncOwner()) return;
    this.setData({
      loading: false,
      response,
      explanationView: documentPresentation(response),
      phrase: response.suggested_reply_zh || "",
      noticesExpanded: false,
      phraseMeaning: response.suggested_reply_zh === NEUTRAL_PHRASE ? this.data.ui.neutralPhraseMeaning :
        ""
    });
  },
  onPhraseInput(event) {
    if (!this.syncOwner()) return;
    this.setData({
      phrase: event.detail.value,
      phraseMeaning: event.detail.value === NEUTRAL_PHRASE ? this.data.ui.neutralPhraseMeaning : ""
    });
  },
  showPhrase() {
    if (!this.syncOwner()) return;
    if (this.data.phrase.trim()) this.setData({
      showPhrase: true
    });
  },
  closePhrase() {
    if (!this.syncOwner()) return;
    this.setData({
      showPhrase: false
    });
  },
  copyPhrase() {
    if (!this.syncOwner()) return;
    if (this.data.phrase.trim()) wx.setClipboardData({
      data: this.data.phrase.trim()
    });
  },
  toggleOriginal() {
    if (!this.syncOwner()) return;
    this.setData({
      originalExpanded: !this.data.originalExpanded
    });
  },
  toggleNotices() {
    if (!this.syncOwner()) return;
    this.setData({ noticesExpanded: !this.data.noticesExpanded });
  },
  changeText() {
    if (!this.syncOwner()) return;
    u.invalidateRequests(this, "explain");
    this.setData({
      loading: false,
      response: null,
      explanationView: {
        summary: "",
        explanation: "",
        notices: []
      },
      phrase: "", phraseMeaning: "", showPhrase: false,
      noticesExpanded: false,
      error: ""
    });
  },
  goChat() {
    if (!this.syncOwner()) return;
    getApp().globalData.pendingChatPrefill = this.data.selectedDocumentText || this.data.text;
    wx.navigateTo({
      url: "/pages/chat/index"
    });
  },
  saveDocument() {
    if (!this.syncOwner()) return;
    const item = getApp().globalData.activeCase;
    if (!item) return;
    const current = u.latestRequest(this, "saveDocument");
    return workspace.addDocument(item.case_id, {
      title: this.data.ui.photo,
      text: this.data.text,
      confirmed: true
    }).then(() => {
      if (this.syncOwner() && current()) this.setData({ error: "", saved: true });
    }).catch((e) => { if (this.syncOwner() && current()) u.error(this, e); });
  },
  onUnload() {
    this._unloaded = true;
    this.clearPrivateDocument(false);
  }
});
