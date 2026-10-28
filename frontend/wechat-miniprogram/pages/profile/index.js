const api = require("../../utils/api");
const workspace = require("../../utils/workspace");
const context = require("../../utils/clientContext");
const i18n = require("../../utils/i18n");
const u = require("../../utils/workspaceUi");
Page({
  data: Object.assign({}, i18n.pageState(), {
    profile: {},
    account: { account_type: "citizen", local_preview: false },
    selectedAccount: "citizen",
    accessReady: false,
    accessNeeded: false,
    accessCode: "",
    accessError: "",
    accessLoading: false,
    localSigninAvailable: false,
    accessModeLoaded: false,
    showTechnicalAccess: false,
    loading: false,
    saving: false,
    error: "",
    saved: false,
    session: null
  }),
  onShow() {
    this._visible = true;
    this._unloaded = false;
    const approved = this._pendingLocalSignin;
    this._pendingLocalSignin = null;
    if (approved && approved.epoch === context.getOwnerEpoch()
      && approved.attempt === this._localSigninAttempt) {
      this.completeLocalSignin(approved.token);
      return;
    }
    i18n.refresh(this);
    u.resetOnOwnerChange(this, {
      profile: {},
      account: { account_type: "citizen", local_preview: false },
      selectedAccount: context.getLocalDemoAccountType(),
      session: null,
      error: "",
      saved: false,
      loading: false,
      saving: false,
      accessLoading: false,
      accessCode: "",
      accessError: "",
      accessNeeded: false
    });
    this.setData({
      accessReady: Boolean(context.getPilotAccessToken()),
      selectedAccount: context.getLocalDemoAccountType()
    });
    const app = typeof getApp === "function" ? getApp() : null;
    const startup = app && app.globalData && app.globalData.localDemoSigninPromise;
    if (startup && startup !== this._waitedDemoSignin) {
      this._waitedDemoSignin = startup;
      return Promise.resolve(startup).then(() => {
        if (this._visible !== false && !this._unloaded) this.loadAccessAndProfile();
      });
    }
    return this.loadAccessAndProfile();
  },
  loadAccessAndProfile() {
    this.setData({
      accessReady: Boolean(context.getPilotAccessToken()),
      selectedAccount: context.getLocalDemoAccountType()
    });
    const currentMode = u.latestRequest(this, "signinMode");
    api.getCapabilities().then((result) => {
      if (currentMode()) this.setData({
        localSigninAvailable: Boolean((result.feature_flags || {}).local_device_signin),
        accessModeLoaded: true
      });
    }).catch(() => {
      if (currentMode()) this.setData({ accessModeLoaded: true, localSigninAvailable: false });
    });
    if (!this.data.saving) this.loadProfile();
  },
  loadProfile() {
    if (this.data.saving) return Promise.resolve();
    const app = typeof getApp === "function" ? getApp() : null;
    const startup = app && app.globalData && app.globalData.localDemoSigninPromise;
    if (startup && startup !== this._waitedDemoSignin) {
      this._waitedDemoSignin = startup;
      return Promise.resolve(startup).then(() => {
        if (this._visible !== false && !this._unloaded && !this.data.saving) return this.loadProfile();
        return null;
      });
    }
    const current = u.latestRequest(this, "profileState");
    this.setData({
      loading: true,
      error: ""
    });
    return workspace.ensure().then((session) => {
      if (!current()) return null;
      this.setData({
        session
      });
      return workspace.getProfile();
    }).then((result) => {
      if (current() && result) { this.setData({
        profile: result.profile || {},
        account: result.account || context.getAccount() || { account_type: "citizen", local_preview: false },
        accessReady: Boolean(context.getPilotAccessToken()),
        selectedAccount: (result.account || context.getAccount() || {}).account_type
          || context.getLocalDemoAccountType(),
        loading: false,
        error: "",
        accessNeeded: false
      }); i18n.refresh(this); }
    }).catch((e) => {
      if (current()) {
        if (e.status === 401) {
          context.setPilotAccessToken("");
          this.setData({ accessReady: false });
        }
        u.error(this, e);
      }
    });
  },
  onUnload() {
    this._unloaded = true;
    this._visible = false;
    this._pendingLocalSignin = null;
    this._localSigninAttempt = (this._localSigninAttempt || 0) + 1;
    u.invalidateRequests(this);
  },
  onHide() {
    this._visible = false;
    // Keep a late response private until this same owner returns to Profile.
    u.invalidateRequests(this, "signinMode");
  },
  completeLocalSignin(token) {
    context.setPilotAccessToken(token);
    this.setData({ accessLoading: false, accessReady: true, accessError: "" });
    wx.reLaunch({ url: "/pages/profile/index" });
  },
  toggleTechnicalAccess() {
    this.setData({ showTechnicalAccess: !this.data.showTechnicalAccess });
  },
  selectAccount(event) {
    if (this.data.accessLoading || !this.data.localSigninAvailable) return;
    const role = event.currentTarget.dataset.role;
    if (role !== "citizen" && role !== "consul") return;
    context.setLocalDemoAccountType(role);
    this.setData({ selectedAccount: role, accessError: "" });
    if (this.data.accessReady && this.data.account.account_type !== role) {
      return this.connectLocal(role);
    }
  },
  goConsul() {
    wx.navigateTo({ url: "/pages/consul/index" });
  },
  connectLocal(accountTypeOrEvent = this.data.selectedAccount) {
    const accountType = typeof accountTypeOrEvent === "string"
      ? accountTypeOrEvent
      : this.data.selectedAccount;
    if (this.data.accessLoading || !this.data.localSigninAvailable) return;
    if (accountType !== "citizen" && accountType !== "consul") return;
    context.setLocalDemoAccountType(accountType);
    context.setLocalDemoAutoSigninSuppressed(false);
    const attempt = this._localSigninAttempt = (this._localSigninAttempt || 0) + 1;
    const epoch = context.getOwnerEpoch();
    const current = () => !this._unloaded && this._localSigninAttempt === attempt
      && context.getOwnerEpoch() === epoch;
    this.setData({ accessLoading: true, accessError: "" });
    return api.startLocalSignin(accountType).then((result) => {
      if (!current()) return;
      if (!/^[\x21-\x7e]{32,256}$/.test(result.session_token || "")) throw new Error("Invalid session");
      if (this._visible === false) {
        this._pendingLocalSignin = { token: result.session_token, epoch, attempt };
        this.setData({ accessLoading: false });
      } else this.completeLocalSignin(result.session_token);
    }).catch((error) => {
      if (!current()) return;
      const message = error.status === 429 ? this.data.ui.localSigninRateLimit
        : error.status ? this.data.ui.localSigninUnavailable : this.data.ui.localSigninFailed;
      this.setData({ accessLoading: false, accessError: message });
    });
  },
  onLanguageChange(event) {
    context.setPreferredLanguage(context.LANGUAGES[Number(event.detail.value)]);
    i18n.refresh(this);
  },
  onAccessCodeInput(event) {
    this.setData({
      accessCode: event.detail.value,
      accessError: ""
    });
  },
  connectPilot(event) {
    if (this.data.accessLoading) return;
    const code = u.form(event, "accessCode", this.data.accessCode);
    if (!/^[\x21-\x7e]{32,256}$/.test(code)) {
      this.setData({
        accessError: this.data.ui.pilotCodeInvalid
      });
      return;
    }
    context.setPilotAccessToken(code);
    this.setData({
      accessCode: "",
      accessError: "",
      accessLoading: true
    });
    return api.checkPilotAccess().then((result) => {
        if (!result.authenticated) throw new Error("Access denied");
        context.clearPrivateContext();
        this.setData({
          accessLoading: false,
          accessReady: true,
          error: "",
          accessNeeded: false
        });
        wx.reLaunch({
          url: "/pages/profile/index"
        });
      })
      .catch((error) => {
        if (error.stale) return;
        context.setPilotAccessToken("");
        this.setData({
          accessReady: false,
          accessLoading: false,
          accessError: this.data.ui.pilotError
        });
      });
  },
  disconnectPilot() {
    context.setLocalDemoAutoSigninSuppressed(true);
    api.endLocalSignin().catch(() => {});
    context.setPilotAccessToken("");
    context.clearPrivateContext();
    wx.reLaunch({
      url: "/pages/profile/index"
    });
  },
  saveProfile(event) {
    if (this.data.saving) return;
    const current = u.latestRequest(this, "profileState");
    this.setData({
      saving: true,
      loading: false,
      saved: false,
      error: ""
    });
    return workspace.saveProfile({
        display_name: u.form(event, "display_name"),
        position: this.data.account.account_type === "consul" ? u.form(event, "position") : "",
        city: u.form(event, "city"),
        purpose: this.data.account.account_type === "citizen" ? u.form(event, "purpose") : "",
        institution: u.form(event, "institution"),
        preferred_language: context.getPreferredLanguage()
      })
      .then((result) => {
        if (current()) this.setData({
          profile: result.profile || {},
          saving: false,
          saved: true
        });
      }).catch((e) => {
        if (current()) u.error(this, e);
      });
  },
  clearProfile() {
    if (this.data.saving) return;
    return new Promise((resolve) => wx.showModal({
      title: this.data.ui.clearProfile,
      content: this.data.ui.confirmDelete,
      confirmText: this.data.ui.confirmShort,
      cancelText: this.data.ui.noShort,
      success: (r) => {
        if (!r.confirm) {
          resolve();
          return;
        }
        const current = u.latestRequest(this, "profileState");
        this.setData({
          saving: true,
          loading: false,
          error: ""
        });
        workspace.clearProfile().then((result) => {
          if (current()) this.setData({
            profile: result.profile || {},
            saved: false,
            saving: false
          });
          resolve();
        }).catch((e) => {
          if (current()) u.error(this, e);
          resolve();
        });
      },
      fail: () => resolve()
    }));
  },
  clearDevice() {
    wx.showModal({
      title: this.data.ui.clearDevice,
      content: this.data.ui.clearDeviceBody,
      confirmText: this.data.ui.confirmShort,
      cancelText: this.data.ui.noShort,
      success: (r) => {
        if (r.confirm) this.disconnectPilot();
      }
    });
  },
  goPrivacy() {
    wx.navigateTo({
      url: "/pages/privacy/index"
    });
  },
  goSupport() {
    wx.navigateTo({
      url: "/pages/support/index"
    });
  },
  goDemo() {
    wx.navigateTo({
      url: "/pages/demo/index"
    });
  }
});
