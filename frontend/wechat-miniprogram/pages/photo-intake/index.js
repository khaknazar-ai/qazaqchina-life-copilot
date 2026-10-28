const api = require("../../utils/api");
const format = require("../../utils/format");
const i18n = require("../../utils/i18n");
const chatInput = require("../../utils/chatInput");
const context = require("../../utils/clientContext");
const u = require("../../utils/workspaceUi");

const DEMO_PNG_BASE64 = "iVBORw0KGgo=";

Page({
  data: Object.assign({}, i18n.pageState(), {
    selectedImagePath: "",
    manualMode: false,
    demoImageSelected: false,
    choosingImage: false,
    cloudProcessing: false,
    localProcessing: false,
    localUnavailable: false,
    cloudConsent: false,
    modeKnown: false,
    filename: "demo-notice.png",
    contentType: "image/png",
    scenario: "chinese-notice-explanation",
    manualTranscription: "",
    loading: false,
    error: "",
    result: null,
    extractedText: "",
    editableExtractedText: "",
    photoPartIndex: 0,
    photoPartNumber: 1,
    photoPartOptions: [],
    detailsExpanded: false,
    selectedPhotoText: "",
    privacyWarnings: [],
    safetyWarnings: [],
    statusText:
      "Fake OCR/demo mode by default. Local OCR is not enabled by default. Manual transcription remains the safest fallback."
  }),

  onLoad() {
    this._unloaded = false;
    this.syncOwner();
  },

  syncOwner() {
    if (this._unloaded) return false;
    const epoch = context.getOwnerEpoch();
    if (this._ownerEpoch === undefined) {
      this._ownerEpoch = epoch;
      this._imageBase64 = DEMO_PNG_BASE64;
    } else if (this._ownerEpoch !== epoch) {
      this._ownerEpoch = epoch;
      this.clearPrivateInput();
      u.invalidateRequests(this);
      this.setData({ modeKnown: false, cloudProcessing: false, localProcessing: false, localUnavailable: false });
      return false;
    }
    return true;
  },

  clearPrivateInput(render = true) {
    this._imageBase64 = "";
    u.invalidateRequests(this, "photoSelection");
    u.invalidateRequests(this, "photoPreview");
    const empty = {
      selectedImagePath: "", manualMode: false, demoImageSelected: false,
      choosingImage: false, loading: false, cloudConsent: false,
      filename: "demo-notice.png", contentType: "image/png", manualTranscription: "",
      result: null, extractedText: "", editableExtractedText: "", selectedPhotoText: "",
      photoPartIndex: 0, photoPartNumber: 1, photoPartOptions: [],
      detailsExpanded: false, privacyWarnings: [], safetyWarnings: [], error: "", statusText: ""
    };
    if (render) this.setData(empty);
    else Object.assign(this.data, empty);
  },

  onManualInput(event) {
    if (!this.syncOwner()) return;
    if (this.data.loading || this.data.choosingImage) return;
    this.setData({ manualTranscription: event.detail.value, error: "" });
  },

  toggleManual() {
    if (!this.syncOwner()) return;
    if (this.data.loading || this.data.choosingImage) return;
    const manualMode = !this.data.manualMode;
    this.clearPrivateInput();
    this.setData({ manualMode });
  },

  restartInput() {
    if (!this.syncOwner() || this.data.loading || this.data.choosingImage) return;
    this.clearPrivateInput();
  },

  explainReviewedText(event) {
    if (!this.syncOwner() || this.data.loading || this.data.choosingImage) return;
    const values = event && event.detail && event.detail.value;
    if (values && typeof values.editableExtractedText === "string") this.setData({ editableExtractedText: values.editableExtractedText });
    const parts = this.updatePhotoParts();
    const text = parts[this.data.photoPartIndex] || "";
    if (!text.trim()) { this.setData({ error: this.data.ui.photoEmpty }); return; }
    getApp().globalData.pendingExplanation = { text, part_number: this.data.photoPartNumber, part_count: parts.length,
      original_character_count: chatInput.characterCount(this.data.editableExtractedText), not_trusted_evidence: true };
    wx.navigateTo({ url: "/pages/explain/index" });
  },

  onCloudConsent(event) {
    if (!this.syncOwner()) return;
    if (this.data.loading || this.data.choosingImage) return;
    this.setData({ cloudConsent: (event.detail.value || []).indexOf("allow") >= 0 });
  },

  onExtractedTextInput(event) {
    if (!this.syncOwner()) return;
    if (this.data.loading || this.data.choosingImage) return;
    this.setData({ editableExtractedText: event.detail.value, error: "" });
    this.updatePhotoParts(0);
  },

  updatePhotoParts(index = this.data.photoPartIndex) {
    const parts = chatInput.splitPhotoText(this.data.editableExtractedText);
    const selected = Math.max(0, Math.min(Number(index) || 0, parts.length - 1));
    this.setData({
      photoPartIndex: selected,
      photoPartNumber: selected + 1,
      photoPartOptions: parts.map((_, i) => `${i + 1} / ${parts.length}`),
      selectedPhotoText: parts[selected] || ""
    });
    return parts;
  },

  onPhotoPartChange(event) {
    if (!this.syncOwner()) return;
    if (this.data.loading || this.data.choosingImage) return;
    this.updatePhotoParts(Number(event.detail.value));
  },

  useDemoImage() {
    if (!this.syncOwner()) return;
    if (this.data.loading || this.data.choosingImage) return;
    u.invalidateRequests(this, "photoSelection");
    u.invalidateRequests(this, "photoPreview");
    this._imageBase64 = DEMO_PNG_BASE64;
    this.setData({
      demoImageSelected: true,
      filename: "demo-notice.png",
      contentType: "image/png",
      selectedImagePath: "",
      cloudConsent: false,
      result: null,
      extractedText: "",
      editableExtractedText: "",
      detailsExpanded: false,
      error: "",
      statusText: this.data.ui.photoDemoReturned || "Demo image selected. Fake OCR/demo mode by default."
    });
    this.updatePhotoParts(0);
  },

  chooseImage() {
    if (!this.syncOwner()) return;
    if (this.data.loading || this.data.choosingImage) return;
    this.clearPrivateInput();
    const current = u.latestRequest(this, "photoSelection");
    const active = () => this.syncOwner() && current();
    this.setData({ choosingImage: true, demoImageSelected: false, manualMode: false, manualTranscription: "", error: "" });
    const success = (selection) => {
      if (!active()) return;
      const file = selection.tempFiles && selection.tempFiles[0];
      const filePath = file && (file.tempFilePath || file.path);
      if (!filePath || !file.size || file.size > 5000000) {
        this.setData({ choosingImage: false, error: this.data.ui.photoSizeError || "Choose an image up to 5 MB." });
        return;
      }
      wx.getFileSystemManager().readFile({
        filePath, encoding: "base64",
        success: (result) => {
          if (!active()) return;
          const imageBase64 = String(result.data || "");
          const contentType = imageBase64.startsWith("iVBORw0KGgo") ? "image/png"
            : imageBase64.startsWith("/9j/") ? "image/jpeg" : "";
          if (!contentType || imageBase64.length > 6666668) {
            this.setData({ choosingImage: false, error: this.data.ui.photoFormatError || "Choose a valid PNG or JPEG up to 5 MB." });
            return;
          }
          // Image bytes never cross the rendering bridge; only preview metadata does.
          this._imageBase64 = imageBase64;
          this.setData({
            choosingImage: false, contentType,
            filename: contentType === "image/png" ? "notice.png" : "notice.jpg",
            selectedImagePath: filePath, result: null, extractedText: "", editableExtractedText: "",
            cloudConsent: false, detailsExpanded: false,
            statusText: this.data.ui.imageSelected || "Image selected locally. Review it before sending for OCR. No upload has occurred yet."
          });
          this.updatePhotoParts(0);
        },
        fail: () => { if (active()) this.setData({ choosingImage: false, error: this.data.ui.photoReadError || "Cannot read the selected image. Try another photo." }); }
      });
    };
    const fail = (error) => { if (active()) this.setData({
      choosingImage: false,
      error: String(error.errMsg || "").indexOf("cancel") >= 0 ? "" : this.data.ui.photoChooseError || "Could not select an image."
    }); };
    if (typeof wx.chooseMedia === "function") {
      wx.chooseMedia({ count: 1, mediaType: ["image"], sourceType: ["album", "camera"], sizeType: ["compressed"], success, fail });
    } else {
      wx.chooseImage({ count: 1, sourceType: ["album", "camera"], sizeType: ["compressed"], success, fail });
    }
  },

  previewPhoto(event) {
    if (!this.syncOwner()) return;
    if (this.data.loading || this.data.choosingImage) return;
    const submittedValues = event && event.detail && event.detail.value;
    const input = submittedValues && typeof submittedValues === "object"
      ? submittedValues.manualTranscription : this.data.manualTranscription;
    if (submittedValues && typeof submittedValues === "object") {
      this.setData({ manualTranscription: typeof input === "string" ? input : "" });
    }
    const manualText = format.safeText(input);
    if (this.data.manualMode && !manualText) {
      this.setData({ error: this.data.ui.manualTextRequired });
      return;
    }
    if (chatInput.characterCount(manualText) > chatInput.MANUAL_MAX_CHARS) {
      this.setData({ error: this.data.ui.manualTextTooLong });
      return;
    }
    if (!manualText && !this.data.modeKnown) {
      this.setData({ error: this.data.ui.photoModeUnavailable });
      return;
    }
    if (!manualText && this.data.localUnavailable) {
      this.setData({ error: this.data.ui.photoLocalUnavailable });
      return;
    }
    if (!manualText && this.data.cloudProcessing) {
      if (!this.data.selectedImagePath) {
        this.setData({ error: this.data.ui.chooseRealPhoto });
        return;
      }
      if (!this.data.cloudConsent) {
        this.setData({ error: this.data.ui.photoConsentRequired });
        return;
      }
    }
    this.setData({ loading: true, error: "", result: null, detailsExpanded: false,
      manualTranscription: manualText,
      statusText: this.data.ui.photoProcessing || "Sending the image to the configured backend for preview." });
    const current = u.latestRequest(this, "photoPreview");
    return api
      .previewPhotoIntake({
        filename: this.data.filename,
        content_type: this.data.contentType,
        image_base64: this._imageBase64 || DEMO_PNG_BASE64,
        scenario: this.data.scenario,
        manual_transcription: manualText || null,
        allow_cloud_processing: !manualText && this.data.cloudProcessing && this.data.cloudConsent
      })
      .then((result) => {
        if (!this.syncOwner() || !current()) return;
        this.setData({
          loading: false,
          result,
          error: result.accepted === false ? ((result.validation || {}).errors || [this.data.ui.photoRejected || "Image preview rejected."]).join(" ") : "",
          extractedText: result.extracted_text || "",
          editableExtractedText: result.extracted_text || "",
          statusText: result.manual_transcription_used
            ? this.data.ui.photoManualReturned || "Manual transcription returned. Review the text before using it in chat."
            : result.ocr && result.ocr.provider === "fake"
              ? this.data.ui.photoDemoReturned || "Demo OCR returned sample text. This is not recognition of your photo; replace it with the real text."
              : this.data.ui.photoFinished || "Preview finished. Check every extracted detail before using it in chat."
        });
        this.presentWarnings(result);
        this.updatePhotoParts(0);
      })
      .catch((error) => {
        if (!this.syncOwner() || !current() || error.stale) return;
        this.setData({
          loading: false,
          statusText: this.data.ui.photoFailed || "Preview failed. You can retry or use manual transcription.",
          error: `${this.data.ui.requestFailed} ${error.message}`
        });
      });
  },

  useExtractedTextInChat(event) {
    if (!this.syncOwner()) return;
    if (this.data.loading || this.data.choosingImage) return;
    const submittedValues = event && event.detail && event.detail.value;
    if (submittedValues && typeof submittedValues === "object") {
      this.setData({ editableExtractedText: typeof submittedValues.editableExtractedText === "string"
        ? submittedValues.editableExtractedText : "" });
    }
    const parts = this.updatePhotoParts();
    const text = parts[this.data.photoPartIndex] || "";
    if (!text.trim()) {
      this.setData({ error: this.data.ui.photoEmpty || "Extracted text preview is empty." });
      return;
    }
    const result = this.data.result || {};
    const ocr = result.ocr || {};
    const chatPrompt = chatInput.buildPhotoChatPrompt(
      text,
      this.data.photoPartNumber,
      parts.length,
      this.data.preferredLanguage
    );
    const photoDraftContext = {
      source: "photo_intake",
      extracted_text: text,
      chat_prompt: chatPrompt,
      part_number: this.data.photoPartNumber,
      part_count: parts.length,
      not_trusted_evidence: true,
      privacy_warnings: this.data.privacyWarnings || [],
      safety_warnings: this.data.safetyWarnings || [],
      ocr_provider: ocr.provider || "fake",
      ocr_model: ocr.model || "",
      manual_transcription_used: Boolean(result.manual_transcription_used),
      created_at: new Date().toISOString()
    };
    const app = getApp();
    if (app && app.globalData) {
      app.globalData.photoDraftContext = photoDraftContext;
      app.globalData.pendingChatPrefill = chatPrompt;
    }
    wx.navigateTo({ url: "/pages/chat/index" });
  },

  toggleDetails() {
    if (!this.syncOwner()) return;
    this.setData({ detailsExpanded: !this.data.detailsExpanded });
  },

  presentWarnings(result) {
    this.setData({
      privacyWarnings: (result.privacy_warnings || []).map(i18n.photoWarning),
      safetyWarnings: (result.safety_warnings || []).concat(result.ocr ? result.ocr.warnings || [] : [])
        .map(i18n.photoWarning)
    });
  },

  onShow() {
    if (this._unloaded) return;
    this.syncOwner();
    i18n.refresh(this);
    if (this.data.result) this.presentWarnings(this.data.result);
    this.updatePhotoParts();
    this.setData({ modeKnown: false, cloudProcessing: false, localProcessing: false,
      localUnavailable: false, cloudConsent: false });
    const current = u.latestRequest(this, "photoMode");
    api.getPhotoIntakeMode().then((mode) => {
      if (!this.syncOwner() || !current()) return;
      const cloudProcessing = Boolean(mode.cloud_processing);
      const localProcessing = Boolean(mode.local_processing);
      const localUnavailable = Boolean(mode.local_unavailable);
      this.setData({ modeKnown: true, cloudProcessing, localProcessing, localUnavailable,
        statusText: cloudProcessing ? this.data.ui.photoModeCloud
          : localProcessing ? this.data.ui.photoModeLocal
            : localUnavailable ? this.data.ui.photoLocalUnavailable : this.data.ui.photoModeDemo });
    }).catch((error) => { if (this.syncOwner() && current() && !error.stale) this.setData({ modeKnown: false, error: this.data.ui.photoModeUnavailable }); });
  },

  onUnload() {
    this._unloaded = true;
    this.clearPrivateInput(false);
    u.invalidateRequests(this);
  }
});
