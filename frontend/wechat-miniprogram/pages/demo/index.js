const api = require("../../utils/api");
const format = require("../../utils/format");
const i18n = require("../../utils/i18n");
const scenarioCopy = require("../../utils/scenarioCopy");

const FALLBACK_SCENARIOS = [
  {
    scenario_id: "lost-passport-emergency",
    title: "Lost passport emergency",
    description: "Emergency escalation, checklist, and official-source priority.",
    expected_features: ["emergency", "retrieval", "escalation", "checklist"]
  },
  {
    scenario_id: "study-registration",
    title: "Study registration checklist",
    description: "University registration and residence-permit document preparation.",
    expected_features: ["study checklist", "official source priority", "multilingual"]
  },
  {
    scenario_id: "unsafe-work-status",
    title: "Unsafe work-status advice",
    description: "Cautious handling for tourist visa and unclear work authorization.",
    expected_features: ["work-status safety", "refusal/caution", "escalation"]
  },
  {
    scenario_id: "payment-scam-warning",
    title: "Payment scam warning",
    description: "Scam signals and moderation around payment or visa agents.",
    expected_features: ["scam warning", "moderation", "payments checklist"]
  },
  {
    scenario_id: "chinese-notice-explanation",
    title: "Chinese notice explanation",
    description: "Chinese notice key terms and non-certified explanation.",
    expected_features: ["Chinese explanation", "key terms", "disclaimer"]
  },
  {
    scenario_id: "housing-registration",
    title: "Housing registration",
    description: "Apartment rental address and accommodation registration checklist.",
    expected_features: ["housing checklist", "official source priority"]
  },
  {
    scenario_id: "hospital-registration",
    title: "Hospital registration and payment",
    description: "Hospital registration, documents, payment, and medical caution.",
    expected_features: ["medical caution", "checklist", "official source priority"]
  },
  {
    scenario_id: "police-station-registration",
    title: "Police station residence registration",
    description: "Apartment rental residence registration at the local police station.",
    expected_features: ["residence registration", "official source priority", "checklist"]
  },
  {
    scenario_id: "visa-extension-warning",
    title: "Visa extension and overstay warning",
    description: "Cautious handling for overstay and visa-extension questions.",
    expected_features: ["overstay warning", "escalation", "no unsafe advice"]
  },
  {
    scenario_id: "bank-card-payment-setup",
    title: "Bank card and payment setup",
    description: "Bank card, WeChat Pay, and Alipay preparation.",
    expected_features: ["payments checklist", "document checklist", "practical caveat"]
  },
  {
    scenario_id: "sim-card-registration",
    title: "SIM card registration and scam risk",
    description: "SIM card passport registration and scam-risk preparation.",
    expected_features: ["registration checklist", "scam warning", "source priority"]
  },
  {
    scenario_id: "work-contract-risk",
    title: "Work contract and permit risk",
    description: "Cautious handling when work starts before contract or permit clarity.",
    expected_features: ["work-status safety", "caution/refusal", "escalation"]
  },
  {
    scenario_id: "university-dormitory-issue",
    title: "University dormitory registration delay",
    description: "Student dormitory registration delay and closed office fallback path.",
    expected_features: ["study checklist", "escalation path", "multilingual handling"]
  },
  {
    scenario_id: "lost-phone-and-documents",
    title: "Lost phone and document copies",
    description: "Emergency steps for phone, document-copy, and bank-access loss.",
    expected_features: ["emergency checklist", "escalation", "account/payment safety"]
  },
  {
    scenario_id: "consulate-appointment-flow",
    title: "Consulate appointment flow",
    description: "Kazakhstan consulate contact flow after document loss.",
    expected_features: ["consular escalation", "official source priority", "checklist"]
  },
  {
    scenario_id: "community-misinformation-conflict",
    title: "Community misinformation conflict",
    description: "Source-governance case for unsafe community work-status advice.",
    expected_features: [
      "conflict handling",
      "official sources outrank community",
      "unsafe advice rejection"
    ]
  }
];

Page({
  data: Object.assign({}, i18n.pageState(), {
    loading: false,
    error: "",
    scenarios: [],
    openingScenarioId: ""
  }),

  onLoad() {
    this.loadScenarios();
  },

  loadScenarios() {
    if (this.data.loading) return;
    this.setData({ loading: true, error: "" });
    return api
      .listDemoScenarios()
      .then((data) => {
        this.setData({
          loading: false,
          scenarios: decorateScenarios(data.scenarios || [])
        });
      })
      .catch(() => {
        this.setData({
          loading: false,
          error: this.data.ui.demoLoadFallback || "Using local fallback list. Backend unavailable.",
          scenarios: decorateScenarios(FALLBACK_SCENARIOS)
        });
      });
  },

  openDetail(event) {
    if (this.data.openingScenarioId) return;
    const scenarioId = event.currentTarget.dataset.id;
    if (!scenarioId) return;
    this.setData({ openingScenarioId: scenarioId });
    wx.navigateTo({
      url: `/pages/demo-detail/index?scenario_id=${encodeURIComponent(scenarioId)}`,
      fail: () => this.setData({ openingScenarioId: "", error: this.data.ui.requestFailed })
    });
  },

  onShow() {
    i18n.refresh(this);
    this.setData({ openingScenarioId: "", scenarios: decorateScenarios(this.data.scenarios) });
  }
});

function decorateScenarios(scenarios) {
  return scenarios.map((scenario) =>
    Object.assign(scenarioCopy.decorateScenario(scenario), {
      featureTags: format.formatFeatureList(scenario.expected_features)
    })
  );
}
