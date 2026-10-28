function text(value) { return typeof value === "string" ? value.trim() : ""; }
function key(value) { return text(value).replace(/\s+/g, " "); }

function documentPresentation(response) {
  const value = response || {};
  const seen = new Set();
  const notices = [];
  const candidates = [].concat(value.warnings || [], value.limitations || [], [value.disclaimer || ""]);
  for (const candidate of candidates) {
    const notice = text(candidate), normalized = key(notice);
    if (normalized && !seen.has(normalized)) { seen.add(normalized); notices.push(notice); }
  }
  // Only remove a repeated whole line. Distinct conditions and risk wording
  // remain visible; the API response and original document stay untouched.
  const withoutRepeatedNotice = (content) => text(content).split(/\r?\n/)
    .filter((line) => !seen.has(key(line))).join("\n").trim();
  const summary = withoutRepeatedNotice(value.translated_summary || value.explanation);
  const explanation = withoutRepeatedNotice(value.explanation);
  return { summary, explanation:key(explanation) === key(summary) ? "" : explanation, notices };
}

module.exports = { documentPresentation };
