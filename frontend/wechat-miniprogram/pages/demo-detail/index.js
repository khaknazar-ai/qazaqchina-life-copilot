const api = require("../../utils/api");
const i18n = require("../../utils/i18n");
const answerSections = require("../../utils/answerSections");
const format = require("../../utils/format");
const scenarioCopy = require("../../utils/scenarioCopy");

const FALLBACK_BY_ID = {
  "lost-passport-emergency": {
    scenario_id: "lost-passport-emergency",
    title: "Lost passport emergency",
    description: "Emergency escalation, checklist, and official-source priority.",
    user_message: "I lost my passport in Beijing and need urgent help.",
    expected_features: ["emergency", "retrieval", "escalation", "checklist"]
  },
  "study-registration": {
    scenario_id: "study-registration",
    title: "Study registration checklist",
    description: "University registration and residence-permit document preparation.",
    user_message: "I am a student preparing university registration documents.",
    expected_features: ["study checklist", "official source priority", "multilingual"]
  },
  "unsafe-work-status": {
    scenario_id: "unsafe-work-status",
    title: "Unsafe work-status advice",
    description: "Cautious handling for unclear work authorization.",
    user_message: "Can I work on a tourist visa and fix documents later?",
    expected_features: ["work-status safety", "refusal/caution", "escalation"]
  },
  "payment-scam-warning": {
    scenario_id: "payment-scam-warning",
    title: "Payment scam warning",
    description: "Scam signals and moderation around payment or visa agents.",
    user_message: "A stranger asks for money for guaranteed visa and payment help.",
    expected_features: ["scam warning", "moderation", "payments checklist"]
  },
  "chinese-notice-explanation": {
    scenario_id: "chinese-notice-explanation",
    title: "Chinese notice explanation",
    description: "Chinese notice key terms and non-certified explanation.",
    user_message: "\u8bf7\u643a\u5e26\u62a4\u7167\u548c\u7b7e\u8bc1\u5230\u6d3e\u51fa\u6240\u529e\u7406\u767b\u8bb0\u3002",
    expected_features: ["Chinese explanation", "key terms", "disclaimer"]
  },
  "housing-registration": {
    scenario_id: "housing-registration",
    title: "Housing registration",
    description: "Apartment rental address and accommodation registration checklist.",
    user_message: "I am renting an apartment and need housing registration guidance.",
    expected_features: ["housing checklist", "official source priority"]
  },
  "hospital-registration": {
    scenario_id: "hospital-registration",
    title: "Hospital registration and payment",
    description: "Hospital registration, documents, payment, and medical caution.",
    user_message: "I have fever and injury and need hospital registration guidance.",
    expected_features: ["medical caution", "checklist", "official source priority"]
  },
  "police-station-registration": {
    scenario_id: "police-station-registration",
    title: "Police station residence registration",
    description: "Apartment rental residence registration at the local police station.",
    user_message: "My landlord says I need police station registration.",
    expected_features: ["residence registration", "official source priority", "checklist"]
  },
  "visa-extension-warning": {
    scenario_id: "visa-extension-warning",
    title: "Visa extension and overstay warning",
    description: "Cautious handling for overstay and visa-extension questions.",
    user_message: "Can I overstay a few days and fix visa later?",
    expected_features: ["overstay warning", "escalation", "no unsafe advice"]
  },
  "bank-card-payment-setup": {
    scenario_id: "bank-card-payment-setup",
    title: "Bank card and payment setup",
    description: "Bank card, WeChat Pay, and Alipay preparation.",
    user_message: "I want to open a bank card and set up WeChat Pay and Alipay.",
    expected_features: ["payments checklist", "document checklist", "practical caveat"]
  },
  "sim-card-registration": {
    scenario_id: "sim-card-registration",
    title: "SIM card registration and scam risk",
    description: "SIM card passport registration and scam-risk preparation.",
    user_message: "I need a Chinese SIM card and want to avoid registration scams.",
    expected_features: ["registration checklist", "scam warning", "source priority"]
  },
  "work-contract-risk": {
    scenario_id: "work-contract-risk",
    title: "Work contract and permit risk",
    description: "Cautious handling when work starts before contract or permit clarity.",
    user_message: "Employer asks me to start work before contract and permit are ready.",
    expected_features: ["work-status safety", "caution/refusal", "escalation"]
  },
  "university-dormitory-issue": {
    scenario_id: "university-dormitory-issue",
    title: "University dormitory registration delay",
    description: "Student dormitory registration delay and closed office fallback path.",
    user_message: "Student university dormitory registration is delayed and office is closed.",
    expected_features: ["study checklist", "escalation path", "multilingual handling"]
  },
  "lost-phone-and-documents": {
    scenario_id: "lost-phone-and-documents",
    title: "Lost phone and document copies",
    description: "Emergency steps for phone, document-copy, and bank-access loss.",
    user_message: "I lost my phone, document copies, and bank access.",
    expected_features: ["emergency checklist", "escalation", "account/payment safety"]
  },
  "consulate-appointment-flow": {
    scenario_id: "consulate-appointment-flow",
    title: "Consulate appointment flow",
    description: "Kazakhstan consulate contact flow after document loss.",
    user_message: "I lost my passport and need Kazakhstan consulate appointment guidance.",
    expected_features: ["consular escalation", "official source priority", "checklist"]
  },
  "community-misinformation-conflict": {
    scenario_id: "community-misinformation-conflict",
    title: "Community misinformation conflict",
    description: "Source-governance case for unsafe community work-status advice.",
    user_message: "A community post says work on tourist visa for paid cash is fine.",
    expected_features: [
      "conflict handling",
      "official sources outrank community",
      "unsafe advice rejection"
    ]
  }
};

Page({
  data: Object.assign({}, i18n.pageState(), {
    scenarioId: "",
    scenario: {},
    featureTags: [],
    result: null,
    escalationNotice: "",
    answerView: null,
    resultScenarioLabel: "",
    resultRiskLabel: "",
    checklistItems: [],
    sourceIds: [],
    safetyFlags: [],
    rawResult: "",
    running: false,
    error: "",
    runError: ""
  }),

  onLoad(options) {
    const scenarioId = options.scenario_id || "";
    this.setData({ scenarioId });
    this.loadScenario(scenarioId);
  },

  loadScenario(scenarioId) {
    api
      .getDemoScenario(scenarioId)
      .then((data) => {
        this.setScenario(data.scenario, "");
      })
      .catch(() => {
        const fallback = FALLBACK_BY_ID[scenarioId] || {
          scenario_id: scenarioId,
          title: "Demo scenario",
          description: "Local fallback scenario.",
          user_message: "",
          expected_features: []
        };
        this.setScenario(
          fallback,
          this.data.ui.demoLoadFallback || "Using local scenario fallback. Backend unavailable."
        );
      });
  },

  setScenario(scenario, error) {
    this.setData({
      scenario: scenarioCopy.decorateScenario(scenario),
      featureTags: format.formatFeatureList(scenario.expected_features),
      error
    });
  },

  runDemo() {
    if (this.data.running) return;
    this.setData({ running: true, runError: "" });
    return api
      .runDemoScenario(this.data.scenarioId)
      .then((data) => {
        const result = data.result || {};
        const checklist = result.checklist && result.checklist.checklist;
        const answerView = answerSections.normalizeDemoRunResponse(result);
        this.setData({
          running: false,
          result,
          escalationNotice: i18n.escalationNotice(result.escalation_summary || ""),
          answerView,
          resultScenarioLabel: scenarioCopy.categoryLabel(answerView.scenario),
          resultRiskLabel: scenarioCopy.riskLabel(answerView.riskLevel),
          checklistItems: checklist && checklist.items ? checklist.items : [],
          sourceIds: result.source_ids || [],
          safetyFlags: format.formatSafetyFlags(result.safety_flags),
          rawResult: format.compactJson(result)
        });
      })
      .catch(() => {
        this.setData({
          running: false,
          runError: this.data.ui.requestFailed
        });
      });
  },

  onShow() {
    i18n.refresh(this);
    const result = this.data.result;
    const answer = result ? answerSections.normalizeDemoRunResponse(result) : this.data.answerView;
    this.setData({
      answerView: answer,
      escalationNotice: result ? i18n.escalationNotice(result.escalation_summary || "") : "",
      scenario: scenarioCopy.decorateScenario(this.data.scenario),
      resultScenarioLabel: answer ? scenarioCopy.categoryLabel(answer.scenario) : "",
      resultRiskLabel: answer ? scenarioCopy.riskLabel(answer.riskLevel) : ""
    });
  },

  copySourceLink(event) {
    const source = this.data.answerView && this.data.answerView.sourceNotes[event.currentTarget.dataset.index];
    if (source && source.url) wx.setClipboardData({ data: source.url });
  }
});
