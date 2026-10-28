const api = require("../../utils/api");
const workspace = require("../../utils/workspace");
const context = require("../../utils/clientContext");
const i18n = require("../../utils/i18n");
const u = require("../../utils/workspaceUi");
const STATUSES = ["", "new", "in_review", "waiting_for_user", "resolved", "closed"];
function call(path, method = "GET", data = {}) {
  return api.request("/api/consul/requests" + path, { method, data });
}
Page({
  data: Object.assign({}, i18n.pageState(), {
    account: null, tickets: [], ticket: null, loading: false, saving: false,
    error: "", accessNeeded: false, filterIndex: 0, filters: [], offset: 0, total: 0,
    replyDraft: "", replyOffset: 0, replyTotal: 0
  }),
  onShow() {
    u.resetOnOwnerChange(this, { account: null, tickets: [], ticket: null, replyDraft: "",
      total: 0, offset: 0, filterIndex: 0, saving: false, loading: false, error: "" });
    this._ticket = null;
    this._creates = {};
    i18n.refresh(this);
    this.setData({ filters: STATUSES.map(value => this.data.ui[value] || this.data.ui.allRequests) });
    return this.load(0);
  },
  load(offset = 0) {
    u.invalidateRequests(this, "detail");
    const current = u.latestRequest(this, "queue");
    this.setData({ loading: true, error: "", ticket: null, replyDraft: "" });
    this._ticket = null;
    return workspace.ensure().then(session => {
      if (!current()) return null;
      if (session.account_type !== "consul") throw Object.assign(new Error("Consul required"), { status: 403 });
      this.setData({ account: context.getAccount() });
      i18n.refresh(this);
      const status = STATUSES[this.data.filterIndex];
      return call("?limit=20&offset=" + offset + (status ? "&status=" + encodeURIComponent(status) : ""));
    }).then(result => {
      if (current() && result) this.setData({
        tickets: (result.tickets || []).map(ticket => ({ ticket_id: ticket.ticket_id,
          summary: ticket.summary.slice(0, 180), status: ticket.status, urgency: ticket.urgency })),
        offset, total: result.total || 0, loading: false, accessNeeded: false
      });
    }).catch(error => { if (current()) this.fail(error); });
  },
  fail(error) {
    if (error.stale) return;
    u.error(this, error);
    if (error.status === 403) this.setData({ error: this.data.ui.consulOnly, tickets: [], ticket: null });
  },
  filter(event) {
    if (this.data.saving) return;
    this.setData({ filterIndex: Number(event.detail.value) });
    return this.load(0);
  },
  next() { if (!this.data.loading && !this.data.saving) return this.load(this.data.offset + 20); },
  previous() { if (!this.data.loading && !this.data.saving) return this.load(Math.max(0, this.data.offset - 20)); },
  open(event) {
    if (this.data.saving) return;
    const current = u.latestRequest(this, "detail");
    this.setData({ loading: true, error: "", ticket: null, replyDraft: "" });
    return call("/" + encodeURIComponent(event.currentTarget.dataset.id)).then(result => {
      if (current()) { this._ticket = result.ticket; this.showReplies(0); this.setData({ loading: false }); }
    }).catch(error => { if (current()) this.fail(error); });
  },
  showReplies(offset) {
    const ticket = this._ticket;
    if (!ticket) return;
    this.setData({ ticket: Object.assign({}, ticket, { replies: ticket.replies.slice(offset, offset + 10) }),
      replyOffset: offset, replyTotal: ticket.replies.length });
  },
  nextReplies() { this.showReplies(this.data.replyOffset + 10); },
  previousReplies() { this.showReplies(Math.max(0, this.data.replyOffset - 10)); },
  onReplyInput(event) { this.setData({ replyDraft: event.detail.value }); },
  reply(event) {
    if (this.data.saving || !this.data.ticket) return;
    const text = u.form(event, "reply", this.data.replyDraft);
    if (!text) return;
    const payload = u.retryableCreate(this, "reply:" + this.data.ticket.ticket_id,
      { text, status: "waiting_for_user" }, workspace.requestId);
    return this.mutate("/replies", "POST", payload);
  },
  changeStatus(event) {
    return this.mutate("", "PATCH", { status: event.currentTarget.dataset.status });
  },
  mutate(suffix, method, payload) {
    if (this.data.saving || !this.data.ticket) return;
    const current = u.latestRequest(this, "detail"), id = this.data.ticket.ticket_id;
    this.setData({ saving: true, error: "" });
    return call("/" + encodeURIComponent(id) + suffix, method, payload).then(result => {
      if (!current()) return;
      this._ticket = result.ticket;
      this.showReplies(Math.max(0, result.ticket.replies.length - 10));
      this.setData({ saving: false, replyDraft: suffix ? "" : this.data.replyDraft,
        tickets: this.data.tickets.map(ticket => ticket.ticket_id === id
          ? Object.assign({}, ticket, { status: result.ticket.status }) : ticket) });
      if (suffix) u.finishCreate(this, "reply:" + id);
    }).catch(error => { if (current()) this.fail(error); });
  },
  goProfile: u.goProfile,
  onHide() { u.invalidateRequests(this); this._ticket = null; this.setData({ ticket: null, replyDraft: "" }); },
  onUnload() { u.invalidateRequests(this); this._ticket = null; }
});
