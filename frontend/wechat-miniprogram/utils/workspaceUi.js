const i18n = require("./i18n");
const context = require("./clientContext");
const {
  compactCase
} = require("./renderBudget");
const SCENARIOS = ["tourism", "study", "work", "business", "medical", "documents", "housing", "payments",
  "transport", "translation", "emergency", "unclear"
];
const names = {
  business: ["Бизнес", "Бизнес", "商务", "Business"],
  documents: ["Документы", "Құжаттар", "证件", "Documents"],
  transport: ["Транспорт", "Көлік", "交通", "Transport"],
  translation: ["Перевод", "Аударма", "翻译", "Translation"],
  unclear: ["Другое", "Басқа", "其他", "Other"]
};

function scenarios() {
  const ui = i18n.labels();
  const lang = context.LANGUAGES.indexOf(context.getPreferredLanguage());
  return SCENARIOS.map((value) => ({
    value,
    label: names[value] ? names[value][lang] : ui[value] || value
  }));
}

function caseView(value) {
  const item = value || {};
  const tasks = (item.tasks || []).map((task) => Object.assign({}, task, {
    statusIndex: ["todo", "in_progress", "done", "skipped"].indexOf(task.status)
  }));
  const taskCount = Array.isArray(item.tasks) ? tasks.length : Number(item.taskCount || 0);
  const completed = Array.isArray(item.tasks) ? tasks.filter((task) => task.status === "done" || task.status ===
    "skipped").length : Number(item.completedTasks || 0);
  const next = tasks.find((task) => task.status !== "done" && task.status !== "skipped");
  return Object.assign({}, item, {
    tasks,
    taskCount,
    nextAction: next ? next.title : item.nextAction || "",
    completedTasks: completed,
    progress: taskCount ? Math.round(completed * 100 / taskCount) : 0,
    statusLabel: i18n.labels()[item.status] || item.status,
    timeline: (item.timeline || []).map((event) => Object.assign({}, event, {
      label: i18n.labels()[event.summary] || event.summary
    })),
    scenarioLabel: (scenarios().find((entry) => entry.value === item.scenario) || {}).label || item.scenario
  });
}

function compactCaseView(value) {
  const item = caseView(compactCase(value));
  delete item.tasks;
  delete item.timeline;
  item.context = {
    city: item.context && item.context.city || ""
  };
  return item;
}

function error(page, failure) {
  if (failure && failure.stale) return;
  page.setData({
    loading: false,
    saving: false,
    error: failure && (failure.status === 401 || failure.status === 403) ? page.data.ui.accessNeeded : page
      .data.ui.loadError,
    accessNeeded: Boolean(failure && (failure.status === 401 || failure.status === 403))
  });
}

function goProfile() {
  wx.switchTab({
    url: "/pages/profile/index"
  });
}

function form(event, name, fallback = "") {
  const values = event && event.detail && event.detail.value;
  return values && typeof values === "object" ? String(values[name] || "").trim() : String(fallback || "").trim();
}

function resetOnOwnerChange(page, empty) {
  const epoch = context.getOwnerEpoch();
  if (page._ownerEpoch !== epoch) {
    invalidateRequests(page);
    page._ownerEpoch = epoch;
    page.setData(empty);
  }
}
// An owner can make several requests in the same view. Only the newest request
// for a given view state may update it, even when responses arrive out of order.
function latestRequest(page, key) {
  const requests = page._requests || (page._requests = {});
  const generation = (requests[key] || 0) + 1;
  const ownerEpoch = context.getOwnerEpoch();
  requests[key] = generation;
  return () => page._requests === requests && requests[key] === generation && ownerEpoch === context.getOwnerEpoch();
}

function invalidateRequests(page, key) {
  if (key && page._requests) page._requests[key] = (page._requests[key] || 0) + 1;
  else page._requests = {};
}

function retryableCreate(page, name, payload, requestId) {
  const creates = page._creates || (page._creates = {});
  const fingerprint = JSON.stringify(payload),
    ownerEpoch = context.getOwnerEpoch();
  const previous = creates[name];
  if (!previous || previous.fingerprint !== fingerprint || previous.ownerEpoch !== ownerEpoch)
    creates[name] = {
      fingerprint,
      ownerEpoch,
      requestId: requestId()
    };
  return Object.assign({
    client_request_id: creates[name].requestId
  }, payload);
}

function finishCreate(page, name) {
  if (page._creates) delete page._creates[name];
}
module.exports = {
  scenarios,
  caseView,
  compactCaseView,
  error,
  goProfile,
  form,
  resetOnOwnerChange,
  latestRequest,
  invalidateRequests,
  retryableCreate,
  finishCreate
};
