const context = require("./clientContext");

// Display copy for the fixed demonstration catalog. Original records stay intact.
const catalog = {
  "lost-passport-emergency": {
    category: "emergency",
    risk: "emergency",
    titles: ["Потерялся паспорт", "Паспорт жоғалды", "护照遗失", "Lost passport"],
    descriptions: ["Как подготовить обращение и найти официальную помощь при потере паспорта.",
      "Паспорт жоғалғанда өтініш дайындау және ресми көмек табу.", "护照遗失后，准备求助信息并寻找官方帮助。",
      "Prepare a request and find official help after losing a passport."
    ]
  },
  "study-registration": {
    category: "study",
    risk: "normal",
    titles: ["Регистрация в университете", "Университетке тіркелу", "大学报到", "University registration"],
    descriptions: ["Подготовить документы для регистрации в университете и проживания во время учёбы.",
      "Университетке тіркелу және оқу кезінде тұру үшін құжаттарды дайындау.", "准备大学报到和学习期间居留所需的材料。",
      "Prepare documents for university registration and student residence."
    ]
  },
  "unsafe-work-status": {
    category: "work",
    risk: "work_status_sensitive",
    titles: ["Работа и визовый статус", "Жұмыс және виза мәртебесі", "工作与签证身份", "Work and visa status"],
    descriptions: ["Разобраться в рисках работы, когда право на трудоустройство не подтверждено.",
      "Жұмыс істеу құқығы расталмаған кездегі тәуекелдерді түсіну.", "了解尚未确认就业许可时开始工作的风险。",
      "Understand the risks of working without confirmed authorization."
    ]
  },
  "payment-scam-warning": {
    category: "payments",
    risk: "medium",
    titles: ["Подозрительный платёж", "Күмәнді төлем", "可疑付款", "Suspicious payment"],
    descriptions: ["На что обратить внимание, если посредник обещает помощь за предоплату.",
      "Делдал көмек үшін алдын ала ақша сұраса, неге назар аудару керек.", "中介承诺提供帮助并要求预付款时，应留意哪些信号。",
      "What to check when an intermediary promises help for an advance payment."
    ]
  },
  "chinese-notice-explanation": {
    category: "translation",
    risk: "medium",
    titles: ["Уведомление на китайском", "Қытай тіліндегі хабарлама", "中文通知", "Chinese notice"],
    descriptions: ["Понять основные слова и действия в уведомлении о регистрации.",
      "Тіркелу туралы хабарламадағы негізгі сөздер мен әрекеттерді түсіну.", "理解登记通知中的关键词和需要采取的行动。",
      "Understand key terms and actions in a registration notice."
    ]
  },
  "housing-registration": {
    category: "housing",
    risk: "normal",
    titles: ["Аренда и регистрация проживания", "Жалдау және тұратын жерге тіркелу", "租房与住宿登记",
      "Rental and residence registration"
    ],
    descriptions: ["Подготовить сведения об аренде и вопросы о регистрации по месту проживания.",
      "Жалдау мәліметтері мен тұратын жерге тіркелу сұрақтарын дайындау.", "整理租房信息，以及住宿登记需要核实的问题。",
      "Prepare rental information and questions about residence registration."
    ]
  },
  "hospital-registration": {
    category: "medical",
    risk: "medical_sensitive",
    titles: ["Обращение в больницу", "Ауруханаға жүгіну", "医院就诊", "Hospital visit"],
    descriptions: ["Подготовка к регистрации и оплате без медицинских диагнозов.",
      "Медициналық диагноз қоймай, тіркелу мен төлемге дайындалу.", "准备挂号和付款信息，不提供医疗诊断。",
      "Prepare for registration and payment without medical diagnosis."
    ]
  },
  "police-station-registration": {
    category: "housing",
    risk: "legal_sensitive",
    titles: ["Регистрация в полиции", "Полицияда тіркелу", "派出所住宿登记", "Police residence registration"],
    descriptions: ["Подготовить вопросы и документы для уточнения регистрации проживания.",
      "Тұратын жерге тіркелуді нақтылау үшін сұрақтар мен құжаттарды дайындау.", "准备核实住宿登记所需的问题和材料。",
      "Prepare questions and documents to verify residence registration."
    ]
  },
  "visa-extension-warning": {
    category: "documents",
    risk: "legal_sensitive",
    titles: ["Продление визы", "Визаны ұзарту", "签证延期", "Visa extension"],
    descriptions: ["Уточнить сроки и официальные действия, если срок визы подходит к концу.",
      "Виза мерзімі аяқталуға жақындағанда мерзімдер мен ресми әрекеттерді нақтылау.",
      "签证即将到期时，核实期限与官方办理方式。", "Verify deadlines and official options when a visa is nearing expiry."
    ]
  },
  "bank-card-payment-setup": {
    category: "payments",
    risk: "normal",
    titles: ["Банковская карта и платежи", "Банк картасы және төлемдер", "银行卡与支付", "Bank card and payments"],
    descriptions: ["Подготовить документы и вопросы для банка, WeChat Pay и Alipay.",
      "Банк, WeChat Pay және Alipay үшін құжаттар мен сұрақтарды дайындау.", "准备银行、微信支付和支付宝相关的材料与问题。",
      "Prepare documents and questions for a bank, WeChat Pay and Alipay."
    ]
  },
  "sim-card-registration": {
    category: "payments",
    risk: "medium",
    titles: ["Оформление SIM-карты", "SIM-картаны рәсімдеу", "办理电话卡", "Getting a SIM card"],
    descriptions: ["Подготовка к оформлению номера и проверка подозрительных предложений.",
      "Нөмірді рәсімдеуге дайындалу және күмәнді ұсыныстарды тексеру.", "准备办理电话号码，并检查可疑的代办服务。",
      "Prepare to register a phone number and check suspicious offers."
    ]
  },
  "work-contract-risk": {
    category: "work",
    risk: "work_status_sensitive",
    titles: ["Работа до оформления документов", "Құжаттарды рәсімдеуге дейін жұмыс істеу", "手续完成前开始工作",
      "Work before paperwork is ready"
    ],
    descriptions: ["Что нужно уточнить, если просят выйти на работу до договора и разрешения.",
      "Шарт пен рұқсат дайын болмай тұрып жұмысқа шақырса, нені нақтылау керек.",
      "被要求在合同和许可完成前上班时，应核实哪些事项。",
      "What to verify when asked to start work before a contract and permit are ready."
    ]
  },
  "university-dormitory-issue": {
    category: "study",
    risk: "medium",
    titles: ["Задержка регистрации в общежитии", "Жатақханаға тіркелудің кешігуі", "宿舍登记延迟",
      "Delayed dormitory registration"
    ],
    descriptions: ["Подготовить обращение, если регистрация задерживается, а офис закрыт.",
      "Тіркелу кешігіп, кеңсе жабық болғанда өтініш дайындау.", "登记延迟且办公室关闭时，整理求助信息。",
      "Prepare a request when registration is delayed and the office is closed."
    ]
  },
  "lost-phone-and-documents": {
    category: "emergency",
    risk: "emergency",
    titles: ["Потеря телефона и документов", "Телефон мен құжаттардың жоғалуы", "手机与证件遗失",
      "Lost phone and documents"
    ],
    descriptions: [
      "Какие безопасные шаги предпринять, если потеряны телефон и документы и нет доступа к банку.",
      "Телефон мен құжаттар жоғалып, банкке қолжетімділік болмаса, қандай қауіпсіз қадамдар жасау керек.",
      "手机与证件遗失且无法使用银行账户时，可采取哪些安全步骤。",
      "Safe steps to take after losing your phone, documents and bank access."
    ]
  },
  "consulate-appointment-flow": {
    category: "emergency",
    risk: "emergency",
    titles: ["Обращение в консульство", "Консулдыққа жүгіну", "联系领事馆", "Contacting the consulate"],
    descriptions: ["Подготовить сведения для обращения в консульство Казахстана после потери паспорта.",
      "Паспорт жоғалғаннан кейін Қазақстан консулдығына жүгіну үшін мәлімет дайындау.",
      "护照遗失后，准备联系哈萨克斯坦领事馆所需的信息。",
      "Prepare information for Kazakhstan's consulate after losing a passport."
    ]
  },
  "community-misinformation-conflict": {
    category: "work",
    risk: "work_status_sensitive",
    titles: ["Противоречивые советы о работе", "Жұмыс туралы қайшы кеңестер", "相互矛盾的工作建议",
      "Conflicting work advice"
    ],
    descriptions: ["Как отделять советы сообщества от официальных правил о праве на работу.",
      "Қоғамдастық кеңестерін жұмыс істеу құқығы туралы ресми ережелерден ажырату.",
      "区分社区经验与关于工作许可的官方规定。", "Separate community advice from official work-authorization rules."
    ]
  }
};

const categories = {
  tourism: ["Путешествия", "Саяхат", "旅行", "Travel"],
  kazakhstan_entry: ["Поездка в Казахстан", "Қазақстанға сапар", "赴哈萨克斯坦", "Travel to Kazakhstan"],
  study: ["Учёба", "Оқу", "学习", "Study"],
  work: ["Работа", "Жұмыс", "工作", "Work"],
  business: ["Бизнес", "Бизнес", "商务", "Business"],
  medical: ["Здоровье", "Денсаулық", "健康", "Health"],
  emergency: ["Срочная помощь", "Шұғыл көмек", "紧急帮助", "Emergency"],
  documents: ["Документы", "Құжаттар", "证件", "Documents"],
  housing: ["Жильё", "Тұрғын үй", "住房", "Housing"],
  payments: ["Платежи", "Төлемдер", "支付", "Payments"],
  transport: ["Транспорт", "Көлік", "交通", "Transport"],
  translation: ["Китайский текст", "Қытайша мәтін", "中文文本", "Chinese text"],
  community_experience: ["Опыт сообщества", "Қоғамдастық тәжірибесі", "社区经验", "Community experience"],
  unclear: ["Нужно уточнить", "Нақтылау қажет", "需要澄清", "Needs clarification"],
  demo: ["Пример", "Мысал", "示例", "Example"]
};

const risks = {
  normal: ["Обычный", "Қалыпты", "一般", "Normal"],
  medium: ["Средний", "Орташа", "中等", "Medium"],
  legal_sensitive: ["Правовые риски", "Құқықтық тәуекелдер", "法律风险", "Legal risk"],
  work_status_sensitive: ["Риски разрешения на работу", "Жұмысқа рұқсат тәуекелдері", "工作许可风险",
    "Work-authorization risk"
  ],
  medical_sensitive: ["Медицинские риски", "Медициналық тәуекелдер", "医疗风险", "Medical risk"],
  emergency: ["Экстренная ситуация", "Шұғыл жағдай", "紧急情况", "Emergency"],
  unsafe: ["Опасный запрос", "Қауіпті сұрау", "危险请求", "Unsafe request"],
  prompt_injection: ["Подмена инструкций", "Нұсқауларды алмастыру", "指令注入", "Instruction injection"]
};

function languageIndex(language) {
  const index = context.LANGUAGES.indexOf(language || context.getPreferredLanguage());
  return index >= 0 ? index : 0;
}

function categoryLabel(value, language) {
  const copy = ownValue(categories, value);
  return copy ? copy[languageIndex(language)] : value || "";
}

function riskLabel(value, language) {
  const copy = ownValue(risks, value);
  return copy ? copy[languageIndex(language)] : value || "";
}

function decorateScenario(record, language) {
  const scenario = record || {};
  const copy = ownValue(catalog, scenario.scenario_id);
  const index = languageIndex(language);
  return Object.assign({}, scenario, {
    displayTitle: copy ? copy.titles[index] : scenario.title || scenario.scenario_id || "",
    displayDescription: copy ? copy.descriptions[index] : scenario.description || "",
    categoryLabel: categoryLabel(scenario.category || (copy && copy.category), language),
    riskLabel: riskLabel(scenario.risk_hint || (copy && copy.risk), language)
  });
}

function ownValue(table, key) {
  return Object.prototype.hasOwnProperty.call(table, key) ? table[key] : null;
}

module.exports = {
  decorateScenario,
  categoryLabel,
  riskLabel
};
