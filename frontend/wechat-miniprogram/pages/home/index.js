const api = require("../../utils/api");
const workspace = require("../../utils/workspace");
const context = require("../../utils/clientContext");
const uiTools = require("../../utils/workspaceUi");
const i18n = require("../../utils/i18n");
Page({
  data: Object.assign({}, i18n.pageState(), {
    message: "",
    recentCase: null,
    loading: false,
    error: "",
    accessNeeded: false,
    capabilities: null,
    isConsul: false
  }),
  onShow() {
    this._unloaded = false;
    i18n.refresh(this);
    uiTools.resetOnOwnerChange(this, {
      message: "",
      recentCase: null,
      error: "",
      isConsul: false
    });
    const app = typeof getApp === "function" ? getApp() : null;
    const startup = app && app.globalData && app.globalData.localDemoSigninPromise;
    if (startup) {
      this.setData({ loading: true, error: "" });
      return Promise.resolve(startup).then(() => {
        if (!this._unloaded) this.loadHomeState();
      });
    }
    return this.loadHomeState();
  },
  loadHomeState() {
    const accountCurrent = uiTools.latestRequest(this, "account");
    workspace.ensure().then(session => {
      if (!accountCurrent()) return;
      this.setData({ isConsul: session.account_type === "consul" });
      i18n.refresh(this);
      if (!this.data.isConsul) this.loadRecent();
    }).catch(error => { if (accountCurrent()) uiTools.error(this, error); });
    const current = uiTools.latestRequest(this, "capabilities");
    api.getCapabilities().then((capabilities) => {
      if (current()) this.setData({
        capabilities
      });
    }).catch(() => {});
  },
  onLoad() {},
  goConsul() { wx.navigateTo({ url: "/pages/consul/index" }); },
  onMessageInput(event) {
    this.setData({
      message: event.detail.value
    });
  },
  onLanguageChange(event) {
    context.setPreferredLanguage(context.LANGUAGES[Number(event.detail.value)]);
    i18n.refresh(this);
  },
  loadRecent() {
    const current = uiTools.latestRequest(this, "recent");
    this.setData({
      loading: true,
      error: ""
    });
    return workspace.listCases({
      limit: 1,
      status: "open"
    }).then((result) => {
      if (current()) this.setData({
        loading: false,
        recentCase: result.cases && result.cases[0] ? uiTools.compactCaseView(result.cases[0]) : null
      });
    }).catch((e) => {
      if (current()) uiTools.error(this, e);
    });
  },
  onUnload() {
    this._unloaded = true;
    uiTools.invalidateRequests(this);
  },
  goChat(event) {
    const message = uiTools.form(event, "message", this.data.message);
    const app = getApp();
    const navigate = () => {
      app.globalData.pendingChatPrefill = message;
      wx.navigateTo({ url: "/pages/chat/index" });
    };
    const startup = app && app.globalData && app.globalData.localDemoSigninPromise;
    return startup ? Promise.resolve(startup).then(navigate) : navigate();
  },
  startKazakhstanTrip() {
    const app = getApp();
    const navigate = () => {
      if (app && app.globalData) app.globalData.pendingChatPrefill = this.data.ui.kazakhstanTripMessage;
      wx.navigateTo({ url: "/pages/chat/index" });
    };
    const startup = app && app.globalData && app.globalData.localDemoSigninPromise;
    return startup ? Promise.resolve(startup).then(navigate) : navigate();
  },
  resume() {
    if (this.data.recentCase) wx.navigateTo({
      url: "/pages/case-detail/index?id=" + encodeURIComponent(this.data.recentCase.case_id)
    });
  },
  goCases() {
    wx.switchTab({
      url: "/pages/cases/index"
    });
  },
  goPhotoIntake() {
    wx.navigateTo({
      url: "/pages/photo-intake/index"
    });
  },
  goExplain() {
    wx.navigateTo({
      url: "/pages/explain/index"
    });
  },
  goEmergency() {
    wx.navigateTo({
      url: "/pages/emergency/index"
    });
  },
  goSupport() {
    wx.navigateTo({
      url: "/pages/support/index"
    });
  },
  goPrivacy() {
    wx.navigateTo({
      url: "/pages/privacy/index"
    });
  },
  goDemo() {
    wx.navigateTo({
      url: "/pages/demo/index"
    });
  },
  goChecklist() {
    wx.navigateTo({
      url: "/pages/checklist/index"
    });
  },
  goProfile: uiTools.goProfile
});
