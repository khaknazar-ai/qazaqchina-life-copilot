const assert = require("node:assert/strict");
const answers = require("../frontend/wechat-miniprogram/utils/answerSections");
const i18n = require("../frontend/wechat-miniprogram/utils/i18n");
for (const mode of ["dialogue", "translation", "document_qa"]) {
  const view = answers.normalizeChatResponse({
    answer: "Hello", metadata: { assistant_mode: mode },
    grounded_answer: { direct_answer: "Hello", source_notes: [] }
  });
  assert.equal(view.directAnswer, "Hello");
  assert.equal(view.showSourcePanel, false);
}
assert.equal(answers.normalizeChatResponse({ answer: "Guidance" }).showSourcePanel, true);

const privateReply = answers.normalizeChatResponse({
  answer: "Hello",
  metadata: { assistant_mode: "translation" },
  safety_flags: ["untrusted_translation_content", "answer_verification_warning"],
  answer_quality_report: {
    issues: [
      { severity: "warning", code: "no_trusted_sources", message: "No trusted source notes are attached to the answer." },
      { severity: "warning", code: "missing_recommended_steps", message: "No steps were attached." }
    ]
  },
  answer_verification_report: {
    issues: [{ severity: "warning", code: "answer_verification_warning", message: "No sources." }]
  },
  safety_policy_decision: {
    required_warnings: [
      "No official or curated source is available in this result, so the answer must state uncertainty and recommend official verification.",
      "Unreviewed sources cannot be used as trusted evidence.",
      "Нет проверенных сведений для конкретного ответа. Уточните условия в официальной службе.",
      "Для ответа не найдено подходящих проверенных источников; конкретные требования нужно уточнить."
    ],
    recommended_next_steps: [
      "Answer only within the available trusted evidence.",
      "Recommend official verification when sources are missing or uncertain.",
      "Используйте только сведения, подтверждённые доступными проверенными источниками.",
      "Перед действиями уточните актуальные требования в официальном источнике."
    ]
  }
});
assert.equal(privateReply.noTrustedSourceLabel, "");
assert.deepEqual(privateReply.uncertaintyItems, []);
assert.deepEqual(privateReply.verifierWarnings, []);
assert.deepEqual(privateReply.freshnessWarnings, []);
assert.deepEqual(privateReply.safetyPolicyWarnings, []);
assert.deepEqual(privateReply.safetyPolicyNextSteps, []);

const highRiskReply = answers.normalizeChatResponse({
  answer: "Please verify this before acting.",
  risk_level: "legal_sensitive",
  metadata: { assistant_mode: "document_qa" },
  safety_policy_decision: {
    requires_official_source: true,
    required_warnings: ["Official source required before acting on high-risk guidance."]
  }
});
assert.equal(highRiskReply.safetyPolicyWarnings.length, 1);

const ungroundedPublicReply = answers.normalizeChatResponse({
  answer: "Use general steps and verify details before acting.",
  answer_verification_report: { issues: [
    { severity: "warning", code: "coverage_warning", message: "Hybrid RAG evidence lacks required official source coverage." },
    { severity: "warning", code: "answer_verification_warning", message: "Internal verifier warning." }
  ] },
  safety_flags: ["answer_verification_warning"]
});
assert.ok(ungroundedPublicReply.verifierWarnings.includes(i18n.labels().noVerifiedAnswer));
assert.ok(!JSON.stringify(ungroundedPublicReply).match(/coverage_warning|answer_verification_warning|Hybrid RAG|Internal verifier/i),
  "internal verification diagnostics are not shown in a citizen answer");

const clientContext = require("../frontend/wechat-miniprogram/utils/clientContext");
clientContext.setPreferredLanguage("ru");
const localizedPolicyWarning = "Official or curated sources are required before making definitive legal, visa, work, police, medical, or emergency claims.";
const userFacingReply = answers.normalizeChatResponse({
  answer: "The table lists visa-free entry.",
  grounded_answer: { direct_answer: "The table lists visa-free entry." },
  answer_quality_report: { issues: [
    { severity: "warning", code: "missing_recommended_steps", message: "Answer draft has no recommended next steps." }
  ] },
  safety_policy_decision: { required_warnings: [localizedPolicyWarning] }
});
assert.ok(!userFacingReply.uncertaintyItems.some((item) => item.includes("missing_recommended_steps")));
assert.deepEqual(userFacingReply.safetyPolicyWarnings, [i18n.labels().officialRequired]);
assert.ok(!userFacingReply.safetyPolicyWarnings.some((item) => item === localizedPolicyWarning));
console.log("Dialogue frontend checks passed");
