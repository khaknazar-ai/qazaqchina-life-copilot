const assert = require("node:assert/strict");
const path = require("node:path");
const mini = path.resolve(__dirname, "../frontend/wechat-miniprogram");
const calls = [], storage = new Map();
const app = { globalData: { apiBaseUrl: "http://127.0.0.1:8000" } };
let selectedRole = "citizen", signins = 0;
global.getApp = () => app;
global.App = definition => { app.definition = definition; };
global.wx = {
  getStorageSync: key => storage.get(key),
  setStorageSync: (key, value) => storage.set(key, value),
  removeStorageSync: key => storage.delete(key),
  request(options) {
    calls.push(options);
    const path = new URL(options.url).pathname;
    const respond = (data, statusCode = 200) => queueMicrotask(() => options.success({ data, statusCode }));
    if (path === "/api/capabilities") return respond({ feature_flags: {
      pilot_access_required: true,
      local_device_signin: true
    } });
    if (path === "/api/local-access/start") {
      assert.equal(options.header["X-Q-Local-Access"], "devtools");
      selectedRole = options.data.account_type;
      signins += 1;
      return respond({
        session_token: `local-demo-session-${selectedRole}-01234567890123456789`,
        account_type: selectedRole,
        local_preview: true
      });
    }
    if (path === "/api/workspace/session") {
      if (options.header.Authorization === "Bearer rejected-local-preview") {
        return respond({ detail: "pilot_access_required" }, 401);
      }
      assert.match(options.header.Authorization, /^Bearer local-demo-session-/);
      return respond({ demo_session_token: "workspace-session-memory-only-0000",
        account_type: selectedRole, persistent: true, local_preview: true });
    }
    if (path === "/api/chat") {
      assert.match(options.header.Authorization, /^Bearer local-demo-session-/);
      return respond({ trace_id: "demo-chat-turn", answer: "Grounded demo reply" });
    }
    throw new Error(`Unexpected route ${options.method} ${path}`);
  }
};

const context = require(path.join(mini, "utils/clientContext"));
const workspace = require(path.join(mini, "utils/workspace"));
const api = require(path.join(mini, "utils/api"));

(async () => {
  require(path.join(mini, "app.js"));
  app.definition.globalData = app.globalData;
  app.definition.onLaunch.call(app);
  await app.globalData.localDemoSigninPromise;
  assert.equal(context.getLocalDemoAccountType(), "citizen");
  assert.match(context.getPilotAccessToken(), /^local-demo-session-citizen-/);
  assert.ok(!JSON.stringify([...storage]).includes(context.getPilotAccessToken()),
    "demo bearer tokens stay in memory");

  const citizenSession = await workspace.ensure();
  assert.equal(citizenSession.account_type, "citizen");
  const reply = await api.sendChatMessage("Chinese citizen traveling to Kazakhstan for tourism");
  assert.equal(reply.answer, "Grounded demo reply");

  context.setPilotAccessToken("rejected-local-preview");
  const refreshedSession = await workspace.ensure();
  assert.equal(refreshedSession.account_type, "citizen");
  assert.match(context.getPilotAccessToken(), /^local-demo-session-citizen-/);
  assert.equal(signins, 2, "expired local access silently gets a new session");

  context.setLocalDemoAccountType("consul");
  context.setPilotAccessToken("");
  context.setLocalDemoAutoSigninSuppressed(false);
  const consulSession = await workspace.ensure();
  assert.equal(consulSession.account_type, "consul");
  assert.equal(signins, 3, "switching roles issues a separate local session");

  context.setLocalDemoAutoSigninSuppressed(true);
  context.setPilotAccessToken("");
  await assert.rejects(api.ensurePilotAccess(), error => error.code === "pilot_access_required");
  assert.equal(signins, 3, "explicit logout disables automatic sign-in for this app session");
  assert.ok(!JSON.stringify([...storage]).includes("local-demo-session-"));
  console.log("Local demo auth checks passed (automatic citizen session, chat, consul role, logout, memory-only tokens).");
})().catch(error => { console.error(error); process.exitCode = 1; });
