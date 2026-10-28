const format = require("./format");
const i18n = require("./i18n");
const PRIVATE_ASSISTANT_MODES = new Set(["translation", "dialogue", "document_qa"]);

function normalizeChatResponse(response, options = {}) {
  const value = response || {};
  const grounded = value.grounded_answer || {};
  const traceSummary = extractTraceSummary(value);
  const sourceReviewConstraint = normalizeSourceReviewConstraint(value);
  const sourceReviewWarning = normalizeSourceReviewWarning(
    value,
    sourceReviewConstraint
  );
  const assistantMode = (value.metadata || {}).assistant_mode || "";
  const privateAssistantMode = PRIVATE_ASSISTANT_MODES.has(assistantMode);
  const directAnswer = sanitizeSourceReviewAnswerText(
    extractDirectAnswer(value),
    sourceReviewConstraint
  );
  const historical = Boolean(options.historical);
  const sourceNotes = extractSourceNotes(value).map((source) => historical ? Object.assign({}, source, {
    trusted: false,
    trustLabel: i18n.labels().historicalReference
  }) : source);
  return {
    historical,
    userQuestion: options.userQuestion || value.user_message || "",
    scenario: value.scenario || grounded.scenario || "",
    riskLevel: value.risk_level || grounded.risk_level || "",
    riskBadgeLabel: getRiskBadgeLabel(value.risk_level || grounded.risk_level),
    directAnswer,
    containsSyntheticSources: Boolean(value.metadata && value.metadata.contains_synthetic_sources) || extractSourceNotes(value).some((note) => note.isSynthetic),
    groundedFacts: extractGroundedFacts(value),
    reviewedNotes: normalizeReviewedNotes(grounded.reviewed_notes),
    recommendedSteps: extractRecommendedSteps(value),
    checklistItems: extractChecklistItems(value),
    escalationItems: extractEscalationItems(value),
    uncertaintyItems: extractUncertaintyItems(value, privateAssistantMode),
    sourceNotes,
    showSourcePanel: !["translation", "dialogue", "document_qa"].includes(
      (value.metadata || {}).assistant_mode
    ) || sourceNotes.length > 0,
    verifierWarnings: extractVerifierWarnings(value, privateAssistantMode),
    freshnessWarnings: privateAssistantMode ? [] : extractFreshnessWarnings(value),
    safetyPolicyDecision: value.safety_policy_decision || {},
    highRisk: Boolean(value.high_risk),
    safetyPolicyWarnings: extractSafetyPolicyWarnings(value, privateAssistantMode),
    safetyPolicyNextSteps: extractSafetyPolicyNextSteps(value, privateAssistantMode),
    escalationRecommended: Boolean(value.escalation_recommended),
    escalationPrefill: value.escalation_prefill || null,
    traceSummary,
    hasTrustedSources: !historical && hasTrustedSources(value),
    hasUnreviewedCandidates: hasUnreviewedCandidates(value),
    unreviewedCandidates: extractUnreviewedCandidates(value),
    has_source_review_constraints: Boolean(value.has_source_review_constraints),
    source_review_constraint: sourceReviewConstraint,
    required_official_verification_warning: format.safeText(
      value.required_official_verification_warning,
      ""
    ),
    prohibited_claim_types: normalizeStringList(value.prohibited_claim_types || []),
    citizen_visible_source_review_disclosure_allowed: Boolean(
      value.citizen_visible_source_review_disclosure_allowed
    ),
    sourceReviewConstraint,
    sourceReviewWarning,
    rawAnswer: format.safeText(value.answer, ""),
    emptyState: directAnswer ? "" : "Empty answer",
    noTrustedSourceLabel: privateAssistantMode || hasTrustedSources(value)
      ? ""
      : "No trusted source coverage",
    loadingLabel: "Loading answer",
    errorLabel: "Error",
    notTrustedLabel: "Not trusted evidence",
    highRiskBannerLabel: "High-risk safety notice",
    requestHumanHelpLabel: "Request human help",
    fallbackUsed: !value.grounded_answer
  };
}

function normalizeReviewedNotes(notes) {
  if (!Array.isArray(notes)) return [];
  return notes.slice(0, 8).filter((note) => note && note.note).map((note) => ({
    conflictId: format.safeText(note.conflict_id, ""),
    revision: Number.isSafeInteger(note.revision) ? note.revision : 0,
    body: format.safeText(note.note, ""),
    sourceIds: normalizeStringList(note.source_ids || []).slice(0, 20)
  }));
}

function normalizeSourceReviewConstraint(response) {
  const value = response || {};
  const constraint = value.source_review_constraint || null;
  if (!value.has_source_review_constraints || !constraint) {
    return null;
  }
  return {
    domain: format.safeText(constraint.domain, ""),
    allowed_mode: format.safeText(constraint.allowed_mode, ""),
    required_warning: format.safeText(constraint.required_warning, ""),
    safe_response_guidance: normalizeSafeSourceReviewGuidance(value),
    citizen_visible_source_review_disclosure_allowed: Boolean(
      constraint.citizen_visible_source_review_disclosure_allowed
    ),
    unpublished_candidates_must_not_be_cited: Boolean(
      constraint.unpublished_candidates_must_not_be_cited
    )
  };
}

function shouldShowSourceReviewWarning(message) {
  const value = message || {};
  return Boolean(
    value.has_source_review_constraints === true &&
      value.source_review_constraint &&
      value.required_official_verification_warning &&
      value.citizen_visible_source_review_disclosure_allowed === false
  );
}

function normalizeSourceReviewWarning(response, sourceReviewConstraint) {
  const message = {
    has_source_review_constraints: Boolean(response.has_source_review_constraints),
    source_review_constraint: sourceReviewConstraint,
    required_official_verification_warning: format.safeText(
      response.required_official_verification_warning,
      ""
    ),
    citizen_visible_source_review_disclosure_allowed: Boolean(
      response.citizen_visible_source_review_disclosure_allowed
    )
  };
  return {
    show: shouldShowSourceReviewWarning(message),
    title: "Official verification required",
    message: message.required_official_verification_warning,
    guidance: sourceReviewConstraint
      ? sourceReviewConstraint.safe_response_guidance
      : [],
    domain: sourceReviewConstraint ? sourceReviewConstraint.domain : ""
  };
}

function sanitizeSourceReviewAnswerText(answer, sourceReviewConstraint) {
  if (!sourceReviewConstraint) {
    return answer;
  }
  return String(answer || "")
    .split("\n")
    .filter((line) => line.indexOf("Unpublished source candidates") < 0)
    .join("\n")
    .trim();
}

function normalizeDemoRunResponse(response) {
  const result = response && response.result ? response.result : response || {};
  const chatResponse = result.chat_response || {};
  const normalized = normalizeChatResponse(chatResponse, {
    userQuestion: result.scenario ? result.scenario.user_message : ""
  });
  const checklist = result.checklist && result.checklist.checklist;
  const checklistItems = checklist && Array.isArray(checklist.items) ? checklist.items : [];
  return Object.assign({}, normalized, {
    scenarioTitle: result.scenario ? result.scenario.title : "",
    demoModeLabel: "Demo mode",
    providerModeLabel: "mock/fake provider by default",
    offlineModeLabel: "no real provider/internet by default",
    checklistItems: normalized.checklistItems.concat(
      checklistItems.map((item) => ({
        title: item.title || "Checklist",
        body: item.description || "",
        priority: item.priority || "",
        sourceIds: []
      }))
    ),
    escalationItems: uniqueStrings(normalized.escalationItems.concat(
      result.escalation_summary ? [result.escalation_summary] : []
    ).map(i18n.escalationNotice)),
    verifierWarnings: normalized.verifierWarnings.concat(
      format.formatSafetyFlags(result.safety_flags || [])
    ),
    traceSummary: normalized.traceSummary.concat([
      {
        label: "Demo trace summary",
        value: result.scenario ? result.scenario.scenario_id : "unknown"
      }
    ]),
    notes: Array.isArray(result.notes) ? result.notes : []
  });
}

function extractDirectAnswer(response) {
  const grounded = response.grounded_answer || {};
  return format.safeText(
    grounded.direct_answer || response.direct_answer || response.answer,
    ""
  );
}

function extractGroundedFacts(response) {
  const grounded = response.grounded_answer || {};
  return normalizeSections(grounded.grounded_facts || response.grounded_facts || []);
}

function extractRecommendedSteps(response) {
  const grounded = response.grounded_answer || {};
  return normalizeSections(grounded.recommended_steps || response.recommended_steps || []);
}

function extractChecklistItems(response) {
  const grounded = response.grounded_answer || {};
  const items = grounded.checklist_items || response.checklist_items || [];
  if (!Array.isArray(items)) {
    return [];
  }
  return items.map((item) => {
    if (typeof item === "string") {
      return { title: "Checklist", body: item, priority: "", sourceIds: [] };
    }
    return {
      title: item.title || "Checklist",
      body: item.body || item.description || "",
      priority: item.priority || "",
      sourceIds: item.source_ids || []
    };
  });
}

function extractEscalationItems(response) {
  const grounded = response.grounded_answer || {};
  const items = []
    .concat(grounded.escalation || [])
    .concat(response.escalation_summary ? [response.escalation_summary] : [])
    .concat(response.escalation_required ? ["Escalation / official verification required"] : []);
  return uniqueStrings(items.map(i18n.escalationNotice));
}

function extractUncertaintyItems(response, privateAssistantMode = false) {
  const grounded = response.grounded_answer || {};
  const issues = privateAssistantMode ? [] : issueMessages(response.answer_quality_report);
  return uniqueStrings([].concat(grounded.uncertainty || []).concat(issues));
}

function extractSourceNotes(response) {
  const grounded = response.grounded_answer || {};
  const notes = grounded.source_notes || response.source_notes || [];
  const citations = response.citations || [];
  const sourceNotes = [];
  if (Array.isArray(notes)) {
    notes.forEach((note) => {
      sourceNotes.push({
        sourceId: note.source_id || "unknown",
        title: note.title || note.source_id || "Trusted source",
        sourceType: note.source_type || "",
        trustLevel: note.trust_level || "",
        usedFor: note.used_for || "grounding",
        warning: note.warning || "",
        isSynthetic: note.is_synthetic === true,
        url: safeSourceUrl(note.url),
        publisher: format.safeText(note.publisher),
        reviewedAt: format.safeText(note.last_reviewed_at),
        accessedAt: format.safeText(note.date_accessed),
        trustLabel: getSourceTrustLabel(note),
        trusted: note.is_synthetic !== true && note.trust_level !== "level_6_untrusted" && ["official", "curated_guide"].indexOf(note.source_type) >= 0
      });
    });
  }
  if (!sourceNotes.length && Array.isArray(citations)) {
    citations.forEach((citation) => {
      sourceNotes.push({
        sourceId: citation.source_id || "unknown",
        title: citation.claim || citation.source_id || "Citation",
        sourceType: "citation",
        trustLevel: "",
        usedFor: "citation",
        warning: "",
        url: safeSourceUrl(citation.url),
        publisher: "",
        reviewedAt: "",
        accessedAt: "",
        trustLabel: i18n.labels().unverified,
        trusted: false
      });
    });
  }
  return sourceNotes;
}

function extractVerifierWarnings(response, privateAssistantMode = false) {
  const report = response.answer_verification_report || response.verifier_report || {};
  const issues = privateAssistantMode ? [] : issueMessages(report);
  const ui = i18n.labels();
  const internal = ["official_curated_priority", "approved_community_context_allowed", "safety_policy_evaluated"];
  const labels = {
    safety_policy_official_source_required: ui.officialRequired,
    human_escalation_required: ui.human,
    safety_policy_human_escalation_required: ui.human,
    safety_policy_emergency_authority_required: ui.emergencyNotice,
    not_emergency_dispatch: ui.emergencyNotice
  };
  const privateModeInternal = new Set([
    "answer_verification_warning",
    "answer_verification_failed",
    "unverified_answer_withheld",
    "untrusted_translation_content"
  ]);
  const verificationFlags = new Set([
    "answer_verification_warning",
    "answer_verification_failed",
    "unverified_answer_withheld"
  ]);
  const safetyFlags = (Array.isArray(response.safety_flags) ? response.safety_flags : [])
    .filter((flag) => flag && !internal.includes(flag) &&
      !(privateAssistantMode && privateModeInternal.has(flag)) &&
      !(privateAssistantMode && !Object.prototype.hasOwnProperty.call(labels, flag)))
    .map((flag) => Object.prototype.hasOwnProperty.call(labels, flag) ? labels[flag] :
      verificationFlags.has(flag) ? ui.noVerifiedAnswer : String(flag).replace(/_/g, " "));
  return uniqueStrings([].concat(issues).concat(safetyFlags));
}

function extractFreshnessWarnings(response) {
  const grounded = response.grounded_answer || {};
  const hybrid = response.hybrid_rag_result || {};
  const coverage = hybrid.coverage || {};
  return uniqueStrings(
    []
      .concat(response.freshness_warnings || [])
      .concat(grounded.freshness_warnings || [])
      .concat(hybrid.freshness_warnings || [])
      .concat(coverage.freshness_warnings || [])
  );
}

function normalizeSafeSourceReviewGuidance(response) {
  const constraint = (response || {}).source_review_constraint || {};
  const domain = format.safeText(constraint.domain, "");
  const guidance = normalizeStringList(constraint.safe_response_guidance || []).filter(
    isCitizenSafeSourceReviewGuidance
  );
  if (guidance.length) return guidance;
  const ui = i18n.labels();
  if (domain === "visa_extension") {
    return [ui.verifyVisaGuidance];
  }
  if (domain === "residence_registration") {
    return [ui.verifyRegistrationGuidance];
  }
  return [];
}

function isCitizenSafeSourceReviewGuidance(value) {
  const text = String(value || "").toLowerCase();
  const blockedTerms = [
    "candidate",
    "reviewer packet",
    "draft evidence",
    "review evidence",
    "publish preview",
    "local intake",
    "registry"
  ];
  return !/\badmin(?:s|istrators?)?\b/.test(text) && !blockedTerms.some((term) => text.indexOf(term) >= 0);
}

function extractSafetyPolicyWarnings(response, privateAssistantMode = false) {
  const decision = response.safety_policy_decision || {};
  const ui = i18n.labels();
  const fixed = {
    "Official or curated sources are required before making definitive legal, visa, work, police, medical, or emergency claims.": ui.officialRequired,
    "No official or curated source is available in this result, so the answer must state uncertainty and recommend official verification.": ui.noVerifiedAnswer,
    "Unreviewed sources cannot be used as trusted evidence.": ui.unreviewedMaterialNotice,
    "This is not emergency dispatch.": ui.emergencyNotice,
    "Official source required before acting on high-risk guidance.": ui.officialRequired
  };
  const sourceAvailabilityWarnings = new Set([
    "No official or curated source is available in this result, so the answer must state uncertainty and recommend official verification.",
    "Unreviewed sources cannot be used as trusted evidence.",
    "Source coverage is limited: no trusted registry source was selected for this answer.",
    "Для ответа не найдено подходящих проверенных источников; конкретные требования нужно уточнить.",
    "Жауапқа сай тексерілген дереккөз табылмады; нақты талаптарды анықтау керек.",
    "未找到适合此回答的可信来源；具体要求仍需核实。",
    ui.noVerifiedAnswer,
    ui.sourceCoverageLimited,
    ui.unreviewedMaterialNotice
  ]);
  return uniqueStrings(
    []
      .concat(response.required_warnings || [])
      .concat(decision.required_warnings || [])
      .concat(response.not_emergency_dispatch ? ["This is not emergency dispatch."] : [])
      .concat(
        response.requires_official_source
          ? ["Official source required before acting on high-risk guidance."]
          : []
      ).filter((message) => !(privateAssistantMode && sourceAvailabilityWarnings.has(message)))
      .map((message) => Object.prototype.hasOwnProperty.call(fixed, message) ? fixed[message] : message)
  );
}

function extractSafetyPolicyNextSteps(response, privateAssistantMode = false) {
  const decision = response.safety_policy_decision || {};
  const localized = normalizeStringList(response.recommended_next_steps || []);
  const raw = normalizeStringList(decision.recommended_next_steps || []);
  const privateModeSourceSteps = new Set([
    "Answer only within the available trusted evidence.",
    "Recommend official verification when sources are missing or uncertain.",
    "Use only information supported by trusted sources.",
    i18n.labels().safetyUseTrustedInformation,
    i18n.labels().safetyVerifyOfficial
  ]);
  // Localize only fixed application copy, then remove exact display duplicates.
  // A partial top-level list must not hide additional safety requirements.
  return uniqueStrings(localized.concat(raw)
    .filter((step) => !(privateAssistantMode && privateModeSourceSteps.has(step)))
    .map(i18n.policyStep));
}

function extractTraceSummary(response) {
  const items = [];
  if (response.trace_id) {
    items.push({ label: "Trace ID", value: response.trace_id });
  }
  if (response.scenario) {
    items.push({ label: "Scenario", value: response.scenario });
  }
  if (response.risk_level) {
    items.push({ label: "Risk level", value: response.risk_level });
  }
  if (response.answer_quality_report) {
    items.push({
      label: "Answer quality issues",
      value: String((response.answer_quality_report.issues || []).length)
    });
  }
  if (response.answer_verification_report) {
    items.push({
      label: "Verifier",
      value: response.answer_verification_report.max_severity || "none"
    });
  }
  return items;
}

function getRiskBadgeLabel(riskLevel) {
  const value = format.safeText(riskLevel, "normal");
  return `Risk level: ${value.replace(/_/g, " ")}`;
}

function getSourceTrustLabel(source) {
  const type = format.safeText(source.source_type || source.sourceType, "unknown");
  const ui = i18n.labels();
  if (source.is_synthetic === true) return ui.synthetic;
  if (source.trust_level === "level_6_untrusted") return ui.unverified;
  if (type === "official") return ui.official;
  if (type === "curated_guide") return ui.curated;
  if (type === "verified_institutional_contributor") return ui.institutional;
  if (type === "verified_experienced_contributor" || type === "ordinary_community") return ui.practical;
  return ui.unverified;
}

function safeSourceUrl(value) {
  const url = format.safeText(value);
  return /^https?:\/\/[^\s/@]+(?:[/:?#]|$)/i.test(url) && !/[\s<>]/.test(url) ? url : "";
}

function hasTrustedSources(response) {
  return extractSourceNotes(response).some((source) => source.trusted);
}

function hasUnreviewedCandidates(response) {
  const grounded = response.grounded_answer || {};
  return Boolean(
    grounded.unreviewed_candidate_count ||
      response.unreviewed_candidate_count ||
      response.unreviewed_source_candidate_count
  );
}

function extractUnreviewedCandidates(response) {
  if (!hasUnreviewedCandidates(response)) {
    return [];
  }
  const grounded = response.grounded_answer || {};
  const count =
    grounded.unreviewed_candidate_count ||
    response.unreviewed_candidate_count ||
    response.unreviewed_source_candidate_count ||
    0;
  return [
    {
      title: "Unreviewed source candidates",
      body: `${count} candidate(s) were detected but are Not trusted evidence.`,
      sourceIds: [],
      warnings: ["Unreviewed candidates must not appear as trusted citations."]
    }
  ];
}

function normalizeSections(sections) {
  if (!Array.isArray(sections)) {
    return [];
  }
  return sections.map((section) => ({
    title: section.heading || section.title || "",
    body: section.body || section.description || "",
    sourceIds: section.source_ids || section.sourceIds || [],
    warnings: section.warnings || []
  }));
}

function issueMessages(report) {
  if (!report || !Array.isArray(report.issues)) {
    return [];
  }
  return report.issues.map((issue) => {
    // This report is an internal quality diagnostic. Missing optional next-step
    // sections should not be exposed as a user-facing warning code.
    if (issue.code === "missing_recommended_steps") {
      return "";
    }
    if (issue.severity === "warning" && issue.code === "no_trusted_sources" &&
        issue.message === "No trusted source notes are attached to the answer.") {
      return i18n.labels().noTrustedSources;
    }
    if (issue.code === "coverage_warning" || issue.code === "answer_verification_warning" ||
        issue.code === "answer_verification_failed" || issue.code === "unverified_answer_withheld") {
      return i18n.labels().noVerifiedAnswer;
    }
    if (issue.severity === "info" && issue.code === "unreviewed_candidates_not_cited" &&
        issue.message === "Unreviewed source candidates are present but must not be cited as trusted evidence.") {
      return i18n.labels().unreviewedMaterialNotice;
    }
    return [issue.severity, issue.code, issue.message].filter(Boolean).join(": ");
  });
}

function uniqueStrings(values) {
  const seen = new Set();
  return (Array.isArray(values) ? values : [])
    .filter((value) => value !== null && value !== undefined && String(value).trim())
    .map((value) => String(value))
    .filter((value) => {
      if (seen.has(value)) {
        return false;
      }
      seen.add(value);
      return true;
    });
}

function normalizeStringList(values) {
  return uniqueStrings(Array.isArray(values) ? values : []);
}

module.exports = {
  normalizeChatResponse,
  normalizeDemoRunResponse,
  normalizeSourceReviewConstraint,
  shouldShowSourceReviewWarning,
  extractDirectAnswer,
  extractGroundedFacts,
  extractRecommendedSteps,
  extractChecklistItems,
  extractEscalationItems,
  extractUncertaintyItems,
  extractSourceNotes,
  extractVerifierWarnings,
  extractFreshnessWarnings,
  extractSafetyPolicyWarnings,
  extractSafetyPolicyNextSteps,
  extractTraceSummary,
  getRiskBadgeLabel,
  getSourceTrustLabel,
  hasTrustedSources,
  hasUnreviewedCandidates
};
