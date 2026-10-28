const workspace = require("../../utils/workspace");
const i18n = require("../../utils/i18n");
const u = require("../../utils/workspaceUi");
Page({
  data: Object.assign({}, i18n.pageState(), {
    cases: [],
    isConsul: false,
    caseOffset: 0,
    caseEnd: 0,
    loading: false,
    saving: false,
    error: "",
    accessNeeded: false,
    filter: "open",
    showCreate: false,
    title: "",
    scenarioIndex: 0,
    scenarios: [],
    session: null,
    total: 0
  }),
  onShow() {
    this._visible = true;
    i18n.refresh(this);
    u.resetOnOwnerChange(this, {
      cases: [],
      isConsul: false,
      session: null,
      showCreate: false,
      error: "",
      saving: false,
      loading: false,
      title: "",
      total: 0,
      accessNeeded: false
    });
    this.setData({
      scenarios: u.scenarios()
    });
    this.load();
  },
  load(offset = 0) {
    const current = u.latestRequest(this, "listing"),
      status = this.data.filter;
    this.setData({
      loading: true,
      error: ""
    });
    return workspace.ensure().then((session) => {
        if (!current()) return null;
        this.setData({
          session, isConsul: session.account_type === "consul"
        });
        i18n.refresh(this);
        if (this.data.isConsul) { this.setData({ loading: false, cases: [], total: 0 }); return null; }
        return workspace.listCases({
          status,
          limit: 20,
          offset
        });
      })
      .then((r) => {
        if (current() && r) {
          const cases = (r.cases || []).map(u.compactCaseView);
          this.setData({
            cases,
            caseOffset: offset,
            caseEnd: offset + cases.length,
            total: r.total || 0,
            loading: false,
            accessNeeded: false
          });
        }
      })
      .catch((e) => {
        if (current()) u.error(this, e);
      });
  },
  more() {
    if (this.data.loading) return;
    return this.load(this.data.caseEnd);
  },
  goConsul() { wx.navigateTo({ url: "/pages/consul/index" }); },
  previousPage() {
    if (!this.data.loading && this.data.caseOffset > 0) return this.load(Math.max(0, this.data.caseOffset -
      20));
  },
  filter(event) {
    this.setData({
      filter: event.currentTarget.dataset.status,
      cases: [],
      total: 0
    });
    return this.load();
  },
  onUnload() {
    u.invalidateRequests(this);
  },
  onHide() {
    this._visible = false;
    u.invalidateRequests(this, "createNavigation");
  },
  open(event) {
    wx.navigateTo({
      url: "/pages/case-detail/index?id=" + encodeURIComponent(event.currentTarget.dataset.id)
    });
  },
  showCreate() {
    this.setData({
      showCreate: !this.data.showCreate,
      error: ""
    });
  },
  onScenarioChange(event) {
    this.setData({
      scenarioIndex: Number(event.detail.value)
    });
  },
  create(event) {
    if (this.data.saving) return;
    const title = u.form(event, "title");
    if (!title) {
      this.setData({
        error: this.data.ui.inputRequired
      });
      return;
    }
    const current = u.latestRequest(this, "caseCreate"),
      navigate = u.latestRequest(this, "createNavigation");
    this.setData({
      saving: true,
      error: ""
    });
    const payload = u.retryableCreate(this, "caseCreate", {
      title,
      scenario: this.data.scenarios[this.data.scenarioIndex].value
    }, workspace.requestId);
    return workspace.createCase(payload)
      .then((r) => {
        if (!current()) return;
        u.finishCreate(this, "caseCreate");
        this.setData({
          saving: false,
          showCreate: false
        });
        if (navigate() && this._visible !== false) wx.navigateTo({
          url: "/pages/case-detail/index?id=" + encodeURIComponent(r.case.case_id)
        });
      }).catch((e) => {
        if (current()) u.error(this, e);
      });
  },
  goAssistant() {
    wx.switchTab({
      url: "/pages/home/index"
    });
  },
  goProfile: u.goProfile
});
