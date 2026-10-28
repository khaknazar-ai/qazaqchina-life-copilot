const workspace = require("../../utils/workspace");
const i18n = require("../../utils/i18n");
const u = require("../../utils/workspaceUi");
const context = require("../../utils/clientContext");
const render = require("../../utils/renderBudget");
const documentInput = require("../../utils/documentInput");
const CASE_BUSY_RETRY_LIMIT = 4;
const CASE_BUSY_RETRY_DELAY_MS = 300;
const PAGE_LIMITS = {
  tasks: 20,
  documents: 5,
  messages: 10,
  timeline: 20
};

function excerpt(value, limit = 600) {
  const text = String(value || "");
  const characters = Array.from(text);
  return {
    text: characters.slice(0, limit).join(""),
    truncated: characters.length > limit
  };
}

function pageState(window, limit) {
  return {
    offset: window.offset,
    end: window.end,
    total: window.total,
    hasPrevious: window.hasPrevious,
    hasNext: window.hasNext,
    page: Math.floor(window.offset / limit) + 1,
    pageCount: Math.max(1, Math.ceil(window.total / limit))
  };
}

function reopenCaseWhenReady(caseId, retriesLeft = CASE_BUSY_RETRY_LIMIT) {
  return workspace.updateCase(caseId, { status: "open" }).catch((error) => {
    if (error.status !== 409 || error.message !== "case_chat_in_progress") throw error;
    return workspace.getCase(caseId).then((result) => {
      if (result.case.status === "open") return result;
      if (retriesLeft <= 0) throw error;
      return new Promise((resolve) => setTimeout(resolve, CASE_BUSY_RETRY_DELAY_MS))
        .then(() => reopenCaseWhenReady(caseId, retriesLeft - 1));
    });
  });
}
Page({
  data: Object.assign({}, i18n.pageState(), {
    caseId: "",
    item: null,
    caseWritable: false,
    loading: false,
    saving: false,
    error: "",
    taskTitle: "",
    editContext: false,
    showDocument: false,
    editDocumentId: "",
    documentConfirmed: false,
    documentImporting: false,
    documentFileLoaded: false,
    documentFileError: "",
    documentType: "reviewed_text",
    statusKeys: ["todo", "in_progress", "done", "skipped"],
    statusLabels: [],
    due: "",
    documentText: "",
    documentTitle: "",
    sectionPages: {},
    fullTextOpen: false,
    fullText: "",
    fullTextTitle: "",
    fullTextIndex: 0,
    fullTextCount: 0
  }),
  onLoad(options = {}) {
    this._ownerEpoch = context.getOwnerEpoch();
    this.setData({
      caseId: options.id || ""
    });
  },
  onShow() {
    i18n.refresh(this);
    if (this._ownerEpoch !== context.getOwnerEpoch()) {
      this._case = null;
      this._sectionOffsets = {};
      this._fullTextParts = [];
    }
    u.resetOnOwnerChange(this, {
      item: null,
      caseId: "",
      caseWritable: false,
      error: "",
      loading: false,
      saving: false,
      taskTitle: "",
      editContext: false,
      showDocument: false,
      editDocumentId: "",
      documentImporting: false,
      documentFileLoaded: false,
      documentFileError: "",
      documentTitle: "",
      documentText: "",
      documentConfirmed: false,
      sectionPages: {},
      fullTextOpen: false,
      fullText: "",
      fullTextTitle: "",
      fullTextIndex: 0,
      fullTextCount: 0
    });
    this.setData({
      statusLabels: this.data.statusKeys.map((key) => this.data.ui[key])
    });
    if (this.data.caseId && !this.data.saving) return this.load();
  },
  currentOwner() {
    if (this._ownerEpoch === context.getOwnerEpoch()) return true;
    this._case = null;
    this._sectionOffsets = {};
    this._fullTextParts = [];
    u.invalidateRequests(this);
    this.setData({
      item: null,
      caseId: "",
      caseWritable: false,
      loading: false,
      saving: false,
      taskTitle: "",
      editContext: false,
      showDocument: false,
      editDocumentId: "",
      documentImporting: false,
      documentFileLoaded: false,
      documentFileError: "",
      documentTitle: "",
      documentText: "",
      documentConfirmed: false,
      sectionPages: {},
      fullTextOpen: false,
      fullText: "",
      fullTextTitle: "",
      fullTextIndex: 0,
      fullTextCount: 0
    });
    return false;
  },
  load() {
    if (!this.currentOwner() || this.data.saving || !this.data.caseId) return Promise.resolve(false);
    const current = u.latestRequest(this, "caseState"),
      caseId = this.data.caseId;
    this.setData({
      loading: true,
      error: ""
    });
    return workspace.getCase(caseId).then((result) => this.show(result, () => current() && this.data.caseId ===
      caseId)).catch((error) => {
      if (current()) u.error(this, error);
      return false;
    });
  },
  show(result, current = () => true) {
    if (!current() || !this.currentOwner()) return false;
    this._case = result.case;
    this.renderCase({
      caseWritable: result.case.status === "open",
      loading: false,
      saving: false,
      error: "",
      due: result.case.deadline || ""
    });
    return true;
  },
  renderCase(extra = {}) {
    if (!this.currentOwner() || !this._case) return;
    const summary = render.compactCase(this._case),
      offsets = this._sectionOffsets || (this._sectionOffsets = {}),
      pages = {};
    summary.context = Object.assign({}, this._case.context || {});
    summary.hasPlan = (this._case.tasks || []).some(task => Boolean(task.template_key));
    summary.statusLabel = this.data.ui[summary.status] || summary.status;
    summary.scenarioLabel = (u.scenarios().find((entry) => entry.value === summary.scenario) || {}).label ||
      summary.scenario;
    for (const section of Object.keys(PAGE_LIMITS)) {
      const source = this._case[section] || [],
        limit = PAGE_LIMITS[section];
      let offset = offsets[section] || 0;
      if (offset >= source.length) offset = Math.max(0, Math.floor((source.length - 1) / limit) * limit);
      const projected = source.map((entry) => {
        if (section === "tasks") return {
          task_id: entry.task_id,
          title: entry.title,
          description: entry.description || "",
          status: entry.status,
          due_at: entry.due_at || null,
          statusIndex: this.data.statusKeys.indexOf(entry.status)
        };
        if (section === "documents") {
          const preview = excerpt(entry.text);
          return {
            document_id: entry.document_id,
            title: entry.title,
            text: preview.text,
            truncated: preview.truncated,
            created_at: entry.created_at,
            confirmed: entry.confirmed
          };
        }
        if (section === "messages") {
          const preview = excerpt(entry.text);
          return {
            message_id: entry.message_id,
            kind: entry.kind,
            historical: entry.kind === "assistant",
            text: preview.text,
            truncated: preview.truncated,
            created_at: entry.created_at
          };
        }
        return {
          event_id: entry.event_id,
          created_at: entry.created_at,
          label: this.data.ui[entry.summary] || entry.summary || entry.event_type || entry.kind
        };
      });
      const window = render.boundedWindow(projected, {
        offset,
        limit,
        maxBytes: 160 * 1024
      });
      offsets[section] = window.offset;
      summary[section] = window.items;
      pages[section] = pageState(window, limit);
    }
    this.setData(Object.assign({
      item: summary,
      sectionPages: pages
    }, extra));
  },
  changePage(event) {
    if (!this.currentOwner()) return;
    const data = event.currentTarget.dataset,
      section = data.section,
      page = this.data.sectionPages[section];
    if (!page || this.data.loading || this.data.saving) return;
    const direction = Number(data.direction);
    if (direction > 0 && !page.hasNext || direction < 0 && !page.hasPrevious) return;
    this._sectionOffsets[section] = direction > 0 ? page.end : Math.max(0, page.offset - PAGE_LIMITS[
      section]);
    this.renderCase();
  },
  viewFullText(event) {
    if (!this.currentOwner()) return;
    const data = event.currentTarget.dataset,
      section = data.section;
    if (!this._case || !["documents", "messages"].includes(section)) return;
    const key = section === "documents" ? "document_id" : "message_id",
      entry = (this._case[section] || []).find((value) => value[key] === data.id);
    if (!entry) return;
    const history = section === "messages" && entry.kind === "assistant" ?
      this.data.ui.historicalAnswer + "\n" + this.data.ui.historicalNotice + "\n\n" : "";
    const text = Array.from(String(entry.text || ""));
    this._fullTextParts = [];
    for (let index = 0; index < text.length; index += 8000) this._fullTextParts.push(history + text.slice(index,
      index + 8000).join(""));
    if (!this._fullTextParts.length) this._fullTextParts = [history];
    this.setData({
      fullTextOpen: true,
      fullTextTitle: entry.title || this.data.ui.timeline,
      fullText: this._fullTextParts[0],
      fullTextIndex: 0,
      fullTextCount: this._fullTextParts.length
    });
  },
  changeFullTextPage(event) {
    if (!this.currentOwner()) return;
    const index = this.data.fullTextIndex + Number(event.currentTarget.dataset.direction);
    if (index < 0 || index >= this._fullTextParts.length) return;
    this.setData({
      fullText: this._fullTextParts[index],
      fullTextIndex: index
    });
  },
  closeFullText() {
    this._fullTextParts = [];
    this.setData({
      fullTextOpen: false,
      fullText: "",
      fullTextTitle: "",
      fullTextIndex: 0,
      fullTextCount: 0
    });
  },
  openPlan() {
    if (!this.currentOwner() || !this.data.caseId) return;
    wx.navigateTo({url: "/pages/checklist/index?case_id=" + encodeURIComponent(this.data.caseId)});
  },
  mutate(operation, allowClosed = false) {
    if (!this.currentOwner() || this.data.saving) return Promise.resolve(false);
    if (!allowClosed && !this.data.caseWritable) {
      this.setData({
        error: this.data.ui.closedCaseHint
      });
      return Promise.resolve(false);
    }
    const current = u.latestRequest(this, "caseState"),
      caseId = this.data.caseId;
    this.setData({
      saving: true,
      loading: false,
      error: ""
    });
    return operation().then((result) => this.show(result, () => current() && this.data.caseId === caseId))
      .catch((error) => {
        if (current() && error.status === 409 && error.message === "case_chat_in_progress") {
          this.setData({
            loading: false,
            saving: false,
            error: this.data.ui.caseChatInProgress
          });
        } else if (current()) u.error(this, error);
        return false;
      });
  },
  onUnload() {
    u.invalidateRequests(this);
    this._case = null;
    this._fullTextParts = [];
  },
  taskStatus(event) {
    const taskId = event.currentTarget.dataset.id;
    const status = this.data.statusKeys[Number(event.detail.value)];
    return this.mutate(() => workspace.updateTask(this.data.caseId, taskId, {
      status
    }));
  },
  taskDate(event) {
    return this.mutate(() => workspace.updateTask(this.data.caseId, event.currentTarget.dataset.id, {
      due_at: event.detail.value
    }));
  },
  clearTaskDate(event) {
    return this.mutate(() => workspace.updateTask(this.data.caseId, event.currentTarget.dataset.id, {
      due_at: null
    }));
  },
  onTaskTitleInput(event) {
    if (!this.data.saving && !this.data.loading) this.setData({
      taskTitle: event.detail.value
    });
  },
  addTask(event) {
    if (this.data.saving) return Promise.resolve(false);
    const title = u.form(event, "title", this.data.taskTitle);
    if (!title) return Promise.resolve(false);
    this.setData({
      taskTitle: title
    });
    return this.mutate(() => workspace.addTask(this.data.caseId, {
      title
    })).then((saved) => {
      if (saved && this.data.taskTitle === title) this.setData({
        taskTitle: ""
      });
      return saved;
    });
  },
  generateChecklist() {
    return this.mutate(() => workspace.checklist(this.data.caseId));
  },
  setStatus(event) {
    return this.mutate(() => workspace.updateCase(this.data.caseId, {
      status: event.currentTarget.dataset.status
    }), true);
  },
  toggleContext() {
    if (this.data.caseWritable && !this.data.saving && !this.data.loading) this.setData({
      editContext: !this.data.editContext
    });
  },
  onDate(event) {
    this.setData({
      due: event.detail.value
    });
  },
  clearDate() {
    this.setData({
      due: ""
    });
  },
  saveContext(event) {
    if (!this.currentOwner() || this.data.saving || !this.data.item) return;
    const payload = {
      title: u.form(event, "title", this.data.item.title),
      deadline: this.data.due || null,
      context: {
        city: u.form(event, "city"),
        purpose: u.form(event, "purpose"),
        institution: u.form(event, "institution"),
        deadline: this.data.due || null,
        preferred_language: this.data.preferredLanguage
      }
    };
    return this.mutate(() => workspace.updateCase(this.data.caseId, payload)).then((saved) => {
      if (saved) this.setData({
        editContext: false
      });
    });
  },
  resume() {
    if (!this.currentOwner() || this.data.loading || this.data.saving || !this.data.item) return;
    const caseId = this.data.caseId;
    const navigate = () => {
      getApp().globalData.activeCase = this._case || this.data.item;
      wx.navigateTo({
        url: "/pages/chat/index?case_id=" + encodeURIComponent(caseId)
      });
    };
    if (this.data.caseWritable) {
      navigate();
      return Promise.resolve();
    }
    return new Promise((resolve) => wx.showModal({
      title: this.data.ui.reopen,
      content: this.data.ui.closedCaseHint,
      confirmText: this.data.ui.confirmShort,
      cancelText: this.data.ui.noShort,
      success: (result) => {
        if (!result.confirm || this.data.caseId !== caseId || !this.currentOwner()) {
          resolve();
          return;
        }
        this.mutate(() => reopenCaseWhenReady(caseId), true).then((saved) => {
          if (saved && this.data.caseWritable) navigate();
          resolve();
        });
      },
      fail: () => resolve()
    }));
  },
  toggleDocument() {
    if (!this.currentOwner() || this.data.saving || this.data.loading || this.data.documentImporting ||
        !this.data.caseWritable) return;
    this.setData({
      showDocument: !this.data.showDocument,
      editDocumentId: "",
      documentTitle: "",
      documentText: "",
      documentConfirmed: false,
      documentType: "reviewed_text",
      documentImporting: false,
      documentFileLoaded: false,
      documentFileError: ""
    });
  },
  editDocument(event) {
    if (!this.currentOwner() || this.data.saving || this.data.loading || this.data.documentImporting ||
        !this.data.caseWritable) return;
    const document = ((this._case || {}).documents || []).find((entry) => entry.document_id === event.currentTarget
      .dataset.id);
    if (document) this.setData({
      showDocument: true,
      editDocumentId: document.document_id,
      documentTitle: document.title,
      documentText: document.text,
      documentConfirmed: false,
      documentFileLoaded: false,
      documentFileError: "",
      documentType: document.document_type || "reviewed_text",
      error: ""
    });
  },
  chooseDocumentFile() {
    if (!this.currentOwner() || this.data.saving || this.data.loading ||
        this.data.documentImporting || !this.data.caseWritable || !this.data.showDocument) return;
    if (typeof wx.chooseMessageFile !== "function" || typeof wx.getFileSystemManager !== "function") {
      this.setData({ error: this.data.ui.documentFileReadError });
      return;
    }
    const current = u.latestRequest(this, "documentImport");
    const caseId = this.data.caseId;
    const active = () => current() && this.currentOwner() && this.data.caseId === caseId;
    this.setData({ documentImporting: true, documentFileLoaded: false, documentFileError: "" });
    wx.chooseMessageFile({
      count: 1,
      type: "file",
      extension: documentInput.TEXT_FILE_EXTENSIONS,
      success: (selection) => {
        if (!active()) return;
        const file = selection && selection.tempFiles && selection.tempFiles[0];
        documentInput.readTextFile(file, wx.getFileSystemManager()).then((result) => {
          if (!active()) return;
          this.setData({
            documentImporting: false,
            documentTitle: result.title,
            documentText: result.text,
            documentType: "uploaded_text",
            documentConfirmed: false,
            documentFileLoaded: true,
            documentFileError: ""
          });
        }).catch((error) => {
          if (!active()) return;
          const key = error.code === "unsupported_file_type" ? "documentFileUnsupported" :
            error.code === "file_too_large" ? "documentFileTooLarge" :
            error.code === "file_too_long" ? "documentFileTooLong" :
            error.code === "empty_file" ? "documentFileEmpty" : "documentFileReadError";
          this.setData({ documentImporting: false, documentFileError: this.data.ui[key] });
        });
      },
      fail: (error) => {
        if (!active()) return;
        const cancelled = String((error && error.errMsg) || "").toLowerCase().includes("cancel");
        this.setData({ documentImporting: false, documentFileError: cancelled ? "" : this.data.ui.documentFileReadError });
      }
    });
  },
  onDocumentTitleInput(event) {
    if (!this.data.saving && !this.data.loading && !this.data.documentImporting) this.setData({
      documentTitle: event.detail.value,
      documentConfirmed: false,
      documentFileLoaded: false
    });
  },
  onDocumentTextInput(event) {
    if (!this.data.saving && !this.data.loading && !this.data.documentImporting) this.setData({
      documentText: event.detail.value,
      documentConfirmed: false,
      documentFileLoaded: false
    });
  },
  confirmDocument(event) {
    if (!this.data.saving && !this.data.loading) this.setData({
      documentConfirmed: (event.detail.value || []).includes("reviewed")
    });
  },
  saveDocument(event) {
    if (!this.currentOwner() || this.data.saving || this.data.documentImporting) return;
    const title = u.form(event, "title");
    const text = u.form(event, "text");
    if (!title || !text || !this.data.documentConfirmed) {
      this.setData({
        error: this.data.ui.inputRequired
      });
      return;
    }
    return this.mutate(() => this.data.editDocumentId ? workspace.updateDocument(this.data.caseId, this.data
      .editDocumentId, {
        title,
        text,
        confirmed: true
      }) : workspace.addDocument(this.data.caseId, {
      title,
      text,
      confirmed: true,
      document_type: this.data.documentType || "reviewed_text"
    })).then((saved) => {
      if (saved) this.setData({
        showDocument: false,
        editDocumentId: "",
        documentTitle: "",
        documentText: "",
        documentConfirmed: false,
        documentFileLoaded: false,
        documentFileError: ""
      });
    });
  },
  deleteDocument(event) {
    if (!this.currentOwner() || this.data.saving || !this.data.caseWritable) return;
    const documentId = event.currentTarget.dataset.id;
    return new Promise((resolve) => wx.showModal({
      title: this.data.ui.delete,
      content: this.data.ui.confirmDelete,
      confirmText: this.data.ui.confirmShort,
      cancelText: this.data.ui.noShort,
      success: (result) => {
        if (!result.confirm) {
          resolve();
          return;
        }
        this.mutate(() => workspace.deleteDocument(this.data.caseId, documentId)).then((saved) => {
          if (saved && this.data.editDocumentId === documentId) this.setData({
            showDocument: false,
            editDocumentId: "",
            documentConfirmed: false
          });
          resolve();
        });
      },
      fail: () => resolve()
    }));
  },
  remove() {
    if (!this.currentOwner() || this.data.loading || this.data.saving) return;
    const current = u.latestRequest(this, "caseState");
    wx.showModal({
      title: this.data.ui.delete,
      content: this.data.ui.confirmDelete,
      confirmText: this.data.ui.confirmShort,
      cancelText: this.data.ui.noShort,
      success: (r) => {
        if (r.confirm && current()) workspace.deleteCase(this.data.caseId).then(() => {
          if (current()) wx.navigateBack();
        }).catch((e) => {
          if (current()) u.error(this, e);
        });
      }
    });
  },
  goProfile: u.goProfile
});
