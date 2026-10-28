// Keep complete records in ordinary page fields. Only bounded projections cross
// the Mini Program's setData bridge; paging replaces a window instead of appending.
function utf8Bytes(value) {
  const text = JSON.stringify(value);
  if (text === undefined) return 0;
  let bytes = 0;
  for (let index = 0; index < text.length; index += 1) {
    const code = text.charCodeAt(index);
    if (code < 0x80) bytes += 1;
    else if (code < 0x800) bytes += 2;
    else if (code >= 0xd800 && code <= 0xdbff && index + 1 < text.length &&
      text.charCodeAt(index + 1) >= 0xdc00 && text.charCodeAt(index + 1) <= 0xdfff) {
      bytes += 4;
      index += 1;
    } else bytes += 3;
  }
  return bytes;
}

// The caller must project each item before paging. An item that alone exceeds
// maxBytes raises instead of silently skipping it; provide a compact preview and
// a separate full-text view for large content. end is the exclusive next offset.
function boundedWindow(array, { offset = 0, limit = 20, maxBytes = 256 * 1024 } = {}) {
  const source = Array.isArray(array) ? array : [];
  const start = Math.max(0, Math.min(source.length, Math.floor(Number(offset) || 0)));
  const count = Math.max(1, Math.floor(Number(limit) || 20));
  const budget = Math.max(2, Math.floor(Number(maxBytes) || 256 * 1024));
  const items = [];
  let bytes = 2;
  for (let index = start; index < source.length && items.length < count; index += 1) {
    const itemBytes = utf8Bytes(source[index]) + (items.length ? 1 : 0);
    if (bytes + itemBytes > budget) {
      if (!items.length) throw new RangeError("Project large items before rendering a bounded window.");
      break;
    }
    items.push(source[index]);
    bytes += itemBytes;
  }
  const end = start + items.length;
  return { items, offset: start, end, total: source.length, hasPrevious: start > 0,
    hasNext: end < source.length, bytes };
}

function compactCase(value) {
  const item = value || {};
  const tasks = Array.isArray(item.tasks) ? item.tasks : [];
  const taskCount = Array.isArray(item.tasks) ? tasks.length : Number(item.taskCount) || 0;
  const completedTasks = Array.isArray(item.tasks)
    ? tasks.filter((task) => task.status === "done" || task.status === "skipped").length
    : Number(item.completedTasks) || 0;
  const next = tasks.find((task) => task.status !== "done" && task.status !== "skipped");
  return {
    case_id: item.case_id, title: item.title || "", scenario: item.scenario, status: item.status,
    context: { city: (item.context || {}).city || "" }, deadline: item.deadline || null,
    created_at: item.created_at, updated_at: item.updated_at, taskCount, completedTasks,
    progress: taskCount ? Math.round(completedTasks * 100 / taskCount) : 0,
    nextAction: next ? next.title : item.nextAction || "",
    documentCount: Array.isArray(item.documents) ? item.documents.length : Number(item.documentCount) || 0,
    messageCount: Array.isArray(item.messages) ? item.messages.length : Number(item.messageCount) || 0,
    timelineCount: Array.isArray(item.timeline) ? item.timeline.length : Number(item.timelineCount) || 0,
    scenarioLabel: item.scenarioLabel, statusLabel: item.statusLabel
  };
}

module.exports = { utf8Bytes, boundedWindow, compactCase };
