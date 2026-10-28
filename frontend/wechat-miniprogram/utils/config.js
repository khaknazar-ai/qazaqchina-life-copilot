const env = require("../config/env");

module.exports = {
  API_BASE_URL: env.API_BASE_URL || "http://127.0.0.1:8000",
  DEMO_MODE: env.DEMO_MODE !== false,
  SAFETY_LABELS: {
    demoMode: "Demo mode",
    providerDefault: "mock/fake provider by default",
    offlineDefault: "no real provider/internet by default"
  }
};
