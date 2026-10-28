const workspace = require("../../utils/workspace");
const i18n = require("../../utils/i18n");
const context = require("../../utils/clientContext");
const u = require("../../utils/workspaceUi");
const examples = require("../../utils/guideExamples");
const config = require("../../utils/config");
const {
  boundedWindow
} = require("../../utils/renderBudget");
const PAGE_SIZE = 30;
const TEXT_PART_SIZE = 4000;

function preview(value, length = 240) {
  const text = String(value || "");
  return text.length > length ? text.slice(0, length) + "…" : text;
}

function parts(text) {
  const result = [];
  for (let start = 0; start < text.length;) {
    let end = Math.min(text.length, start + TEXT_PART_SIZE);
    if (end < text.length && /[\uD800-\uDBFF]/.test(text[end - 1])) end -= 1;
    result.push(text.slice(start, end));
    start = end;
  }
  return result.length ? result : [""];
}

function summary(item, official) {
  return official ? {
    source_id: item.source_id,
    title: preview(item.title),
    city: preview(item.city, 100),
    source_type: item.source_type,
    reviewed_at: String(item.reviewed_at || "").slice(0, 10)
  } : {
    post_id: item.post_id,
    title: preview(item.title),
    city: preview(item.city, 100),
    moderation_status: item.moderation_status,
    created_at: preview(item.created_at, 80)
  };
}

Page({
  data: Object.assign({}, i18n.pageState(), {
    pool: "experience",
    examples: [],
    expandedExampleId: "",
    sources: [],
    posts: [],
    loading: false,
    saving: false,
    error: "",
    accessNeeded: false,
    query: "",
    city: "",
    scenarioIndex: 0,
    scenarioOptions: [],
    showAdd: false,
    mine: false,
    allowRetrieval: false,
    expandedId: "",
    expandedText: "",
    expandedHasUrl: false,
    partIndex: 0,
    partCount: 0,
    status: "",
    total: 0,
    offset: 0,
    pageNumber: 1,
    pageCount: 1,
    hasPrevious: false,
    hasNext: false
  }),
  clearPrivate() {
    this._sources = [];
    this._posts = [];
    this._parts = [];
  },
  checkOwner() {
    if (this._active === false) return false;
    const epoch = context.getOwnerEpoch();
    if (this._cacheEpoch !== undefined && this._cacheEpoch !== epoch) {
      this.clearPrivate();
      u.invalidateRequests(this);
      this.setData({
        sources: [],
        posts: [],
        expandedId: "",
        expandedText: "",
        expandedHasUrl: false,
        partIndex: 0,
        partCount: 0,
        total: 0,
        offset: 0,
        pageNumber: 1,
        pageCount: 1,
        hasPrevious: false,
        hasNext: false,
        loading: false,
        saving: false,
        showAdd: false,
        error: "",
        status: "",
        query: "",
        city: "",
        scenarioIndex: 0,
        mine: false,
        allowRetrieval: false
      });
      this._cacheEpoch = epoch;
      return false;
    }
    this._cacheEpoch = epoch;
    return true;
  },
  onShow() {
    this._active = true;
    i18n.refresh(this);
    this.checkOwner();
    u.resetOnOwnerChange(this, {
      sources: [],
      posts: [],
      showAdd: false,
      error: "",
      status: "",
      saving: false,
      loading: false,
      query: "",
      city: "",
      mine: false,
      allowRetrieval: false,
      expandedId: "",
      expandedText: "",
      expandedHasUrl: false,
      partIndex: 0,
      partCount: 0,
      total: 0,
      offset: 0,
      pageNumber: 1,
      pageCount: 1,
      hasPrevious: false,
      hasNext: false,
      accessNeeded: false
    });
    this.setData({
      scenarioOptions: [{
        value: "",
        label: this.data.ui.allTopics
      }].concat(u.scenarios())
    });
    return this.load();
  },
  filters() {
    return {
      query: this.data.query,
      city: this.data.city,
      scenario: (this.data.scenarioOptions[this.data.scenarioIndex] || {}).value,
      language: this.data.pool === "experience" ? context.getPreferredLanguage() : undefined,
      limit: PAGE_SIZE,
      offset: this.data.offset
    };
  },
  load() {
    if (!this.checkOwner()) return Promise.resolve();
    const current = u.latestRequest(this, "listing"),
      pool = this.data.pool,
      mine = this.data.mine,
      filters = this.filters();
    this.setData({
      examples: pool === "experience" && !mine && config.DEMO_MODE
        ? examples.list(context.getPreferredLanguage(), filters) : [],
      expandedExampleId: ""
    });
    this.clearPrivate();
    this.setData({
      loading: true,
      error: "",
      sources: [],
      posts: [],
      expandedId: "",
      expandedText: "",
      expandedHasUrl: false,
      partIndex: 0,
      partCount: 0
    });
    const query = pool === "official" ? workspace.library(filters) : workspace.community(Object.assign(
      filters, {
        mine
      }));
    return query.then((r) => {
      if (!current()) return;
      const raw = pool === "official" ? (r.sources || []).filter((s) => !s.is_synthetic) :
        (r.posts || []).filter((s) => mine ? s.is_own : s.moderation_status === "approved" && !s.is_synthetic);
      const total = Math.max(0, Number(r.total) || raw.length),
        offset = filters.offset;
      if (total && offset >= total) {
        this.setData({
          offset: Math.floor((total - 1) / PAGE_SIZE) * PAGE_SIZE
        });
        return this.load();
      }
      if (pool === "official") this._sources = raw;
      else this._posts = raw;
      const rows = boundedWindow(raw.map((item) => summary(item, pool === "official")), {
        limit: PAGE_SIZE,
        maxBytes: 128 * 1024
      }).items;
      this.setData({
        loading: false,
        accessNeeded: false,
        sources: pool === "official" ? rows : [],
        posts: pool === "experience" ? rows : [],
        total,
        pageNumber: Math.floor(offset / PAGE_SIZE) + 1,
        pageCount: Math.max(1, Math.ceil(total / PAGE_SIZE)),
        hasPrevious: offset > 0,
        hasNext: offset + PAGE_SIZE < total
      });
    }).catch((e) => {
      if (current()) u.error(this, e);
    });
  },
  search(event) {
    if (!this.checkOwner()) return;
    const query = u.form(event, "query");
    if (Array.from(query).length > 100) {
      this.setData({ error: this.data.ui.searchQueryTooLong });
      return;
    }
    this.setData({
      query,
      city: u.form(event, "city"),
      offset: 0
    });
    return this.load();
  },
  scenarioChange(event) {
    if (!this.checkOwner()) return;
    this.setData({
      scenarioIndex: Number(event.detail.value),
      offset: 0
    });
    return this.load();
  },
  changePool(event) {
    if (!this.checkOwner()) return;
    this.setData({
      pool: event.currentTarget.dataset.pool,
      offset: 0,
      total: 0
    });
    return this.load();
  },
  toggleMine() {
    if (!this.checkOwner()) return;
    this.setData({
      mine: !this.data.mine,
      offset: 0,
      total: 0
    });
    return this.load();
  },
  expandExample(event) {
    const id = event.currentTarget.dataset.id;
    if (!this.data.examples.some((item) => item.id === id)) return;
    this.setData({ expandedExampleId: this.data.expandedExampleId === id ? "" : id });
  },
  previousPage() {
    if (!this.checkOwner() || this.data.loading || !this.data.hasPrevious) return;
    this.setData({
      offset: Math.max(0, this.data.offset - PAGE_SIZE)
    });
    return this.load();
  },
  nextPage() {
    if (!this.checkOwner() || this.data.loading || !this.data.hasNext) return;
    this.setData({
      offset: this.data.offset + PAGE_SIZE
    });
    return this.load();
  },
  onUnload() {
    this._active = false;
    this.clearPrivate();
    u.invalidateRequests(this);
  },
  toggleAdd() {
    if (this.checkOwner()) this.setData({
      showAdd: !this.data.showAdd,
      status: "",
      allowRetrieval: false
    });
  },
  expand(event) {
    if (!this.checkOwner()) return;
    const id = event.currentTarget.dataset.id;
    if (this.data.expandedId === id) {
      this._parts = [];
      this.setData({
        expandedId: "",
        expandedText: "",
        expandedHasUrl: false,
        partIndex: 0,
        partCount: 0
      });
      return;
    }
    const official = this.data.pool === "official";
    const item = (official ? this._sources || [] : this._posts || []).find((entry) => (official ? entry.source_id :
      entry.post_id) === id);
    if (!item) return;
    const fields = official ? [
        [this.data.ui.entryTitle, item.title],
        [this.data.ui.original, item.content],
        [this.data.ui.officialSources, item.url]
      ] :
      [
        [this.data.ui.entryTitle, item.title],
        [this.data.ui.situation, item.situation],
        [this.data.ui.happened, item.what_happened],
        [this.data.ui.helped, item.what_helped],
        [this.data.ui.experience, item.advice_for_others]
      ];
    this._parts = parts(fields.filter((field) => field[1]).map((field) =>
      `${field[0] || ""}\n${field[1]}`).join("\n\n"));
    this.setData({
      expandedId: id,
      expandedText: this._parts[0],
      expandedHasUrl: official && /^https?:\/\//i.test(item.url || ""),
      partIndex: 0,
      partCount: this._parts.length
    });
  },
  changePart(event) {
    if (!this.checkOwner() || !this.data.expandedId) return;
    const index = this.data.partIndex + Number(event.currentTarget.dataset.direction);
    if (index < 0 || index >= (this._parts || []).length) return;
    this.setData({
      partIndex: index,
      expandedText: this._parts[index]
    });
  },
  consent(event) {
    if (this.checkOwner()) this.setData({
      allowRetrieval: (event.detail.value || []).includes("allow")
    });
  },
  submit(event) {
    if (!this.checkOwner() || this.data.saving) return;
    const title = u.form(event, "title"),
      situation = u.form(event, "situation"),
      what_happened = u.form(event, "what_happened");
    if (!title || !situation || !what_happened) {
      this.setData({
        error: this.data.ui.inputRequired
      });
      return;
    }
    const current = u.latestRequest(this, "postMutation");
    this.setData({
      saving: true,
      error: ""
    });
    return workspace.addExperience({
        title,
        situation,
        what_happened,
        what_helped: u.form(event, "what_helped"),
        city: u.form(event, "experienceCity", this.data.city),
        scenario: (this.data.scenarioOptions[this.data.scenarioIndex] || {}).value ||
          "community_experience",
        language: context.getPreferredLanguage(),
        allow_ai_retrieval: this.data.allowRetrieval
      })
      .then(() => {
        if (!current()) return;
        this.setData({
          saving: false,
          showAdd: false,
          mine: true,
          pool: "experience",
          offset: 0,
          status: this.data.ui.pendingNotice
        });
        return this.load();
      })
      .catch((e) => {
        if (current()) u.error(this, e);
      });
  },
  copySource(event) {
    if (!this.checkOwner()) return;
    const source = (this._sources || []).find((s) => s.source_id === event.currentTarget.dataset.id);
    if (source && /^https?:\/\//i.test(source.url || "")) wx.setClipboardData({
      data: source.url
    });
  },
  goProfile: u.goProfile
});
