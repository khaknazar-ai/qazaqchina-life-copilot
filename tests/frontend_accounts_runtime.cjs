const assert = require("node:assert/strict");
const path = require("node:path");
const root = path.resolve(__dirname, "../frontend/wechat-miniprogram");
const requests = [], navigation = [], storage = new Map();
let accountType = "citizen", held = null, failReply = false;
const app = { globalData: {} };
global.getApp = () => app;
const fullTicket = { ticket_id: "request-1", summary: "Shared question", reason: "needs_human_help",
  status: "new", urgency: "normal", replies: [] };
global.wx = {
  getStorageSync: key => storage.get(key), setStorageSync: (key, value) => storage.set(key, value), removeStorageSync: key => storage.delete(key),
  setTabBarItem() {}, setNavigationBarTitle() {},
  navigateTo: value => navigation.push(value.url), reLaunch: value => navigation.push(value.url),
  switchTab: value => navigation.push(value.url),
  request(options) {
    requests.push(options);
    if (held && held(options)) return;
    const route = new URL(options.url).pathname;
    const send = (data, statusCode = 200) => queueMicrotask(() => options.success({ data: JSON.parse(JSON.stringify(data)), statusCode }));
    if (route === "/api/capabilities") return send({ feature_flags: { local_device_signin: true } });
    if (route === "/api/local-access/start") { accountType = options.data.account_type; return send({ session_token: "account-session-memory-only-" + accountType + "-000000", account_type: accountType }); }
    if (route === "/api/workspace/session") return send({ account_type: accountType, local_preview: true, persistent: true });
    if (route === "/api/workspace/profile") return send({ profile: { display_name: accountType }, account: { account_type: accountType, local_preview: true } });
    if (route === "/api/workspace/cases") return send({ cases: [], total: 0 });
    if (route === "/api/consul/requests") return send({ tickets: [fullTicket], total: 1 });
    if (route === "/api/consul/requests/request-1/replies") {
      if (failReply) return send({ detail: "retryable failure" }, 500);
      fullTicket.replies.push({ reply_id: "reply-" + fullTicket.replies.length, role: "consul", text: options.data.text });
      fullTicket.status = "waiting_for_user";
      return send({ ticket: fullTicket });
    }
    if (route === "/api/consul/requests/request-1") {
      if (options.method === "PATCH") fullTicket.status = options.data.status;
      return send({ ticket: fullTicket });
    }
    if (route === "/api/local-access/logout") return send({ signed_out: true });
    throw new Error("Unknown route " + route);
  }
};
const context = require(path.join(root, "utils/clientContext"));
const workspace = require(path.join(root, "utils/workspace"));
const i18n = require(path.join(root, "utils/i18n"));
function page(name) {
  let result; global.Page = value => { result = value; };
  const filename = path.join(root, "pages", name, "index.js");
  delete require.cache[require.resolve(filename)]; require(filename);
  result.data = JSON.parse(JSON.stringify(result.data));
  result.setData = patch => Object.assign(result.data, patch);
  return result;
}
const click = data => ({ currentTarget: { dataset: data } });
const form = value => ({ detail: { value } });
async function flush() { for (let n = 0; n < 30; n++) await Promise.resolve(); }
(async () => {
  context.setPilotAccessToken("citizen-fixture-memory-token-000000");
  const profile = page("profile"); profile.onShow(); await flush();
  profile.disconnectPilot();
  const login = page("profile"); login.onShow(); await flush();
  login.selectAccount(click({ role: "consul" }));
  // Mini Program bindtap passes an event object; the handler must use the
  // selected role instead of silently treating that event as an account type.
  await login.connectLocal(click({}));
  assert.equal(requests.findLast(r => r.url.endsWith("/api/local-access/start")).data.account_type, "consul");
  const staff = page("profile"); staff.onShow(); await flush();
  assert.equal(staff.data.account.account_type, "consul");
  assert.equal(staff.data.profile.display_name, "consul");
  assert.ok(!JSON.stringify(staff.data).includes("account-session-memory-only"));
  const cases = page("cases"); cases.onShow(); await flush(); assert.equal(cases.data.isConsul, true);
  const home = page("home"); home.onShow(); await flush(); assert.equal(home.data.isConsul, true);
  const queue = page("consul"); await queue.onShow(); await flush();
  assert.equal(queue.data.tickets.length, 1); assert.equal(queue.data.account.account_type, "consul");
  assert.ok(!new URL(requests.findLast(r => new URL(r.url).pathname === "/api/consul/requests").url).searchParams.has("status"));
  await queue.open(click({ id: "request-1" }));
  failReply = true; queue.onReplyInput({ detail: { value: "Reply draft" } });
  await queue.reply(form({ reply: "Reply draft" }));
  assert.equal(queue.data.replyDraft, "Reply draft");
  const first = requests.at(-1).data.client_request_id;
  failReply = false; await queue.reply(form({ reply: "Reply draft" }));
  assert.equal(requests.at(-1).data.client_request_id, first);
  assert.equal(queue.data.ticket.replies[0].text, "Reply draft"); assert.equal(queue.data.replyDraft, "");
  await queue.changeStatus(click({ status: "resolved" })); assert.equal(queue.data.ticket.status, "resolved");
  await queue.changeStatus(click({ status: "in_review" })); assert.equal(queue.data.ticket.status, "in_review");
  // A late detail response cannot repopulate a page after account switch.
  let late;
  held = options => { if (options.url.endsWith("/request-1")) { late = options; return true; } return false; };
  const opening = queue.open(click({ id: "request-1" }));
  context.setPilotAccessToken("new-citizen-fixture-token-00000000"); accountType = "citizen";
  late.success({ statusCode: 200, data: { ticket: fullTicket } }); await opening;
  held = null; await queue.onShow(); await flush();
  assert.equal(queue.data.tickets.length, 0); assert.equal(queue.data.ticket, null);
  assert.equal(queue.data.error, queue.data.ui.consulOnly);
  assert.equal(context.getAccount().account_type, "citizen");
  const oldRequests = requests.length;
  await queue.load(); assert.equal(requests.length, oldRequests, "citizen never sends a consul queue request");
  const citizen = page("profile"); citizen.onShow(); await flush();
  assert.equal(citizen.data.profile.display_name, "citizen");
  for (const language of context.LANGUAGES) {
    context.setPreferredLanguage(language); const labels = i18n.labels();
    for (const name of ["citizen", "consul", "consulRequests", "consulProfile"]) assert.ok(labels[name]);
  }
  assert.deepEqual(context.LANGUAGES.map(language => {
    context.setPreferredLanguage(language); return i18n.labels().accountType;
  }), ["Роль", "Рөл", "身份", "Role"]);
  context.setPilotAccessToken(""); assert.equal(context.getAccount(), null);
  assert.ok(!JSON.stringify([...storage]).includes("token"));
  console.log("Account frontend checks passed (selection, profiles, navigation, queue, replies, status, retries, owner isolation, languages).");
})().catch(error => { console.error(error); process.exitCode = 1; });
