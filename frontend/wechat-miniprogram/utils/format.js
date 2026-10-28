function formatScenarioTitle(scenario) {
  if (!scenario) {
    return "Demo scenario";
  }
  return safeText(scenario.title, scenario.scenario_id || "Demo scenario");
}

function formatFeatureList(features) {
  if (!Array.isArray(features)) {
    return [];
  }
  return features.filter(Boolean).map((feature) => String(feature));
}

function formatSafetyFlags(flags) {
  if (!Array.isArray(flags)) {
    return [];
  }
  return flags.filter(Boolean).map((flag) => String(flag).replace(/_/g, " "));
}

function safeText(value, fallback = "") {
  if (value === null || value === undefined) {
    return fallback;
  }
  const text = String(value).trim();
  return text || fallback;
}

function compactJson(value) {
  if (value === null || value === undefined) {
    return "";
  }
  const text = JSON.stringify(value, null, 2);
  if (text.length > 1800) {
    return `${text.slice(0, 1800)}...`;
  }
  return text;
}

module.exports = {
  formatScenarioTitle,
  formatFeatureList,
  formatSafetyFlags,
  safeText,
  compactJson
};
