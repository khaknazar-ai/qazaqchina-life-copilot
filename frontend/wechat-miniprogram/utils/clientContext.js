// Anonymous continuity only. This identifier is not authentication or proof of ownership.
const SESSION_KEY = "qazaqchina_anonymous_session";
const LANGUAGE_KEY = "qazaqchina_preferred_language";
const LANGUAGES = ["ru", "kk", "zh", "en"];
let sessionId = "";
let language = "";
// Pilot credentials live only in this process, never in persistent device storage.
let pilotAccessToken = "";
let workspaceSessionToken = "";
let ownerEpoch = 0;
let account = null;
let localDemoAccountType = "citizen";
let localDemoAutoSigninSuppressed = false;

function setPilotAccessToken(value) {
  const next = typeof value === "string" ? value.trim() : "";
  if (next !== pilotAccessToken) clearPrivateContext();
  pilotAccessToken = next;
}

function replaceLocalPilotAccessToken(value) {
  pilotAccessToken = typeof value === "string" ? value.trim() : "";
  workspaceSessionToken = "";
}

function getPilotAccessToken() { return pilotAccessToken; }
function getOwnerEpoch() { return ownerEpoch; }
function getWorkspaceSessionToken() { return workspaceSessionToken; }
function setWorkspaceSessionToken(value) { workspaceSessionToken = value || ""; }
function clearPrivateContext() {
  account = null;
  ownerEpoch += 1;
  workspaceSessionToken = "";
  sessionId = "";
  try { wx.removeStorageSync(SESSION_KEY); } catch (_) { writeStorage(SESSION_KEY, ""); }
  const app = typeof getApp === "function" ? getApp() : null;
  if (app && app.globalData) {
    ["photoDraftContext", "supportDraftContext", "activeCase", "chatDraft", "pendingExplanation"].forEach((key) => { app.globalData[key] = null; });
    app.globalData.pendingChatPrefill = "";
  }
}

function readStorage(key) {
  try { return wx.getStorageSync(key); } catch (_) { return ""; }
}

function writeStorage(key, value) {
  try { wx.setStorageSync(key, value); } catch (_) { /* Keep in-memory continuity. */ }
}

function getSessionId() {
  if (!sessionId) {
    const saved = readStorage(SESSION_KEY);
    sessionId = typeof saved === "string" && /^anon-[a-z0-9-]{12,100}$/.test(saved)
      ? saved
      : `anon-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
    writeStorage(SESSION_KEY, sessionId);
  }
  return sessionId;
}

function getPreferredLanguage() {
  if (!language) {
    const saved = readStorage(LANGUAGE_KEY);
    language = LANGUAGES.indexOf(saved) >= 0 ? saved : "ru";
  }
  return language;
}

function setPreferredLanguage(value) {
  language = LANGUAGES.indexOf(value) >= 0 ? value : "ru";
  writeStorage(LANGUAGE_KEY, language);
  return language;
}

module.exports = {
  getAccount: () => account,
  setAccount: (value) => { account = value || null; },
  LANGUAGES, getSessionId, getPreferredLanguage, setPreferredLanguage,
  getPilotAccessToken, setPilotAccessToken, replaceLocalPilotAccessToken, getOwnerEpoch,
  getWorkspaceSessionToken, setWorkspaceSessionToken, clearPrivateContext,
  getLocalDemoAccountType: () => localDemoAccountType,
  setLocalDemoAccountType: (value) => {
    localDemoAccountType = value === "consul" ? "consul" : "citizen";
    return localDemoAccountType;
  },
  isLocalDemoAutoSigninSuppressed: () => localDemoAutoSigninSuppressed,
  setLocalDemoAutoSigninSuppressed: (value) => { localDemoAutoSigninSuppressed = Boolean(value); }
};
