const config = require("./utils/config");
const api = require("./utils/api");

App({
  globalData: {
    apiBaseUrl: config.API_BASE_URL,
    appName: "QminiGuide",
    supportedLanguages: ["ru", "kk", "zh", "en"],
    lastCapabilities: null,
    localDemoSigninPromise: null,
    localDemoSigninError: null,
    pendingChatPrefill: "",
    photoDraftContext: null
  },

  onLaunch() {
    if (config.DEMO_MODE) {
      console.log("QminiGuide running in local demo mode.");
      this.globalData.localDemoSigninPromise = Promise.resolve()
        .then(() => api.ensurePilotAccess())
        .catch((error) => {
          this.globalData.localDemoSigninError = error;
        });
    }
  }
});
