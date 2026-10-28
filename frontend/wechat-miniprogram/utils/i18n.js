const context = require("./clientContext");
const interfaceCopy = require("./interfaceCopy");
const workspaceCopy = require("./workspaceCopy");
const accountCopy = require("./accountCopy");

// Main navigation and task actions; backend answer language is requested separately.
const translations = {
  sourceCoverageLimited: ["Для ответа не найдено подходящих проверенных источников; конкретные требования нужно уточнить.",
    "Жауапқа сай тексерілген дереккөз табылмады; нақты талаптарды анықтау керек.",
    "未找到适合此回答的可信来源；具体要求仍需核实。",
    "Source coverage is limited: no trusted registry source was selected for this answer."
  ],
  noVerifiedAnswer: ["Нет проверенных сведений для конкретного ответа. Уточните условия в официальной службе.",
    "Нақты жауап үшін тексерілген мәлімет жоқ. Шарттарды ресми қызметтен нақтылаңыз.",
    "暂无支持具体答复的已核实信息，请向官方机构确认条件。",
    "There is no verified information for a specific answer. Confirm conditions with the official service."
  ],
  retryCaseSave: ["Повторить сохранение", "Сақтауды қайталау", "重试保存", "Retry save"],
  caseSaveRetryHint: ["Не все сообщения сохранены. Нажмите «Повторить сохранение», чтобы завершить в том же деле.",
    "Барлық хабарламалар сақталмады. Сол істе аяқтау үшін «Сақтауды қайталау» түймесін басыңыз.",
    "部分消息尚未保存，请点击“重试保存”在同一事项中完成。",
    "Some messages are still unsaved. Choose Retry save to finish saving in the same case."
  ],
  savedQuestionNote: ["Вопрос сохранён как заметка; ответ не сохранён.",
    "Сұрақ жазба ретінде сақталды; жауап сақталмады.", "问题已保存为笔记，回答未保存。",
    "Question saved as a note; no answer was saved."
  ],
  reopenTicketHint: ["Чтобы отправить сообщение, верните обращение в работу. Черновик сохранён.",
    "Хабарлама жіберу үшін өтінішті қайта ашыңыз. Жоба сақталды.", "请重新开启请求后再发送消息，草稿已保留。",
    "Reopen the request to send a reply. Your draft is kept."
  ],
  verifyVisaGuidance: ["До принятия решения уточните правила в местном управлении въезда и выезда и международном отделе университета.",
    "Әрекет етпес бұрын жергілікті кіру-шығу басқармасынан және университеттің халықаралық бөлімінен ережелерді нақтылаңыз.",
    "采取行动前，请向当地出入境管理部门及大学国际事务办公室核实。",
    "Confirm with the local Exit-Entry Administration and your university international office before acting."
  ],
  verifyRegistrationGuidance: ["До принятия решения уточните правила в местном органе общественной безопасности, у организации размещения или в университете.",
    "Әрекет етпес бұрын жергілікті қоғамдық қауіпсіздік органынан, тұратын жеріңізден немесе университеттен ережелерді нақтылаңыз.",
    "采取行动前，请向当地公安机关、住宿提供方或大学核实。",
    "Confirm with the local public security authority, accommodation provider, or university before acting."
  ],
  reviewedInterpretation: ["Пояснение после проверки", "Тексерілген түсіндірме", "审核后的解释", "Reviewed interpretation"],
  unreviewedMaterialNotice: ["Непроверенные материалы не используются для подтверждения ответа.",
    "Тексерілмеген материалдар жауапты растау үшін қолданылмайды.", "未经审核的材料不用于支持本回答。",
    "Unreviewed material is not used to support this answer."
  ],
  chatInputLimit: ["До 8000 символов в одном сообщении.", "Бір хабарламада 8000 таңбаға дейін.",
    "每条消息最多 8000 个字符。", "Up to 8000 characters per message."
  ],
  chatTextTooLong: [
    "Сообщение длиннее 8000 символов. Сократите его или выберите часть текста на экране фото.",
    "Хабарлама 8000 таңбадан асады. Оны қысқартыңыз немесе фото экранында мәтін бөлігін таңдаңыз.",
    "消息超过 8000 个字符，请缩短或在照片页面选择一部分文字。",
    "Message exceeds 8000 characters. Shorten it or choose a part on the photo page."
  ],
  manualInputLimit: ["До 12000 символов. Длинный текст можно отправить в чат по частям.",
    "12000 таңбаға дейін. Ұзын мәтінді чатқа бөліп жіберуге болады.", "最多 12000 个字符，长文本可分段发送至对话。",
    "Up to 12000 characters. Long text can be sent to chat in parts."
  ],
  manualTextRequired: ["Введите текст уведомления.", "Хабарлама мәтінін енгізіңіз.",
    "请输入通知文字。", "Enter the notice text."
  ],
  demoEscalationHelp: ["Запросите помощь специалиста или официального органа.",
    "Маманнан немесе ресми органнан көмек сұраңыз.", "请向专业人员或官方机构寻求帮助。",
    "Request help from a specialist or official service."
  ],
  safetyEmergencyContact: ["Если возможно, перейдите в безопасное место и немедленно обратитесь в местную экстренную службу. Приложение не является диспетчерской экстренной помощи.",
    "Мүмкін болса, қауіпсіз жерге барып, жергілікті шұғыл көмек қызметіне дереу хабарласыңыз. Бұл қосымша шұғыл көмек диспетчері емес.",
    "如有可能，请前往安全地点并立即联系当地紧急救援机构。本应用不是紧急调度服务。",
    "Contact local emergency services or official authorities if immediate danger exists."
  ],
  safetyQueueFollowup: ["Очередь поддержки служит для последующего разбора; она не вызывает экстренную помощь.",
    "Қолдау кезегі кейінгі қарауға арналған; ол шұғыл көмек шақырмайды.",
    "人工支持队列仅用于后续跟进记录，不会调度紧急救援。",
    "Use the human support queue only as a follow-up record, not emergency dispatch."
  ],
  safetyPreserveFacts: ["Сохраните важные сведения и документы, если это безопасно.",
    "Қауіпсіз болса, маңызды мәліметтер мен құжаттарды сақтаңыз.",
    "在安全的情况下保留关键事实和文件。",
    "Preserve key facts and documents if it is safe to do so."
  ],
  safetyVerifyOfficial: ["Перед действиями уточните актуальные требования в официальном источнике.",
    "Әрекет етпес бұрын қолданыстағы талаптарды ресми дереккөзден нақтылаңыз.",
    "行动前请通过官方来源核实最新要求。",
    "Verify the requirement with an official or curated source."
  ],
  safetyPreferOfficial: ["Только практический опыт: он не заменяет официальные требования.",
    "Бұл тек практикалық тәжірибе; ол ресми талаптарды алмастырмайды.",
    "仅供实践经验参考，不能替代官方要求。",
    "Prefer official/curated guidance over community experience."
  ],
  safetyEscalateRisk: ["Если высок риск, связанный со статусом, сроком, работой, полицией или документами, создайте обращение к специалисту.",
    "Мәртебе, мерзім, жұмыс, полиция не құжат бойынша тәуекел жоғары болса, маманға өтініш жасаңыз.",
    "涉及身份、期限、就业、警方或证件的高风险情况，请提交人工协助请求。",
    "Create an escalation request when status, deadline, employment, police, or document risk is high."
  ],
  safetyAdminCare: ["Ограничьтесь безопасной подготовкой документов и обращением за медицинской помощью.",
    "Құжаттарды қауіпсіз дайындап, медициналық көмекке жүгініңіз.",
    "仅采取安全的事务性步骤，例如准备资料和寻求医疗服务。",
    "Give safe administrative steps only, such as preparing documents and seeking care."
  ],
  safetyUrgentMedical: ["При серьёзных или усиливающихся симптомах нужна срочная медицинская помощь. В остальных случаях уточните запись, страховку и оплату у сотрудников больницы.",
    "Ауыр не күшейіп жатқан белгілер болса, шұғыл медициналық көмекке жүгініңіз. Басқа жағдайда қабылдау, сақтандыру және төлемді аурухана қызметкерлерінен нақтылаңыз.",
    "症状严重或加重时请及时就医；其他情况请向医院工作人员核实挂号、保险和支付流程。",
    "For urgent symptoms, contact qualified medical professionals or official medical services."
  ],
  safetyHumanNotDiagnosis: ["Попросите человека помочь с языком, документами или маршрутом обращения; диагноз ставит медицинский специалист.",
    "Тіл, құжат не қайда жүгіну бойынша адамнан көмек сұраңыз; диагнозды медицина маманы қояды.",
    "人工协助可用于语言、材料或就医指引；诊断应由医疗专业人员提供。",
    "Use human escalation for language, document, or navigation help, not diagnosis."
  ],
  safetyNoMoreMoney: ["Не отправляйте дополнительные деньги, пока требование не проверено.",
    "Талап тексерілмейінше қосымша ақша жібермеңіз.",
    "在要求尚未核实前，不要继续转账。",
    "Do not send more money while the request is unclear."
  ],
  safetyPreservePaymentEvidence: ["Сохраните скриншоты, чеки, имена аккаунтов, номера телефонов и сведения об операциях; не публикуйте личные данные.",
    "Скриншоттарды, түбіртектерді, аккаунт аттарын, телефон нөмірлерін және операцияларды сақтаңыз; жеке деректерді жарияламаңыз.",
    "保存截图、收据、账户名称、电话号码和交易记录；不要公开个人信息。",
    "Preserve screenshots, receipts, usernames, phone numbers, and transaction records."
  ],
  safetyAskHumanReview: ["Попросите специалиста проверить ситуацию, если есть риск для денег, аренды, работы или доступа к аккаунту.",
    "Ақша, жалға алу, жұмыс не аккаунтқа кіру тәуекелі болса, маманнан тексеруді сұраңыз.",
    "如涉及资金、房东、雇主或账户访问风险，请请求人工审核。",
    "Ask for human review when money, landlord, employer, or account access risk is involved."
  ],
  safetyCompareSource: ["Сверьте утверждение с официальными или проверенными редакцией источниками.",
    "Тұжырымды ресми не редакция тексерген дереккөздермен салыстырыңыз.",
    "请将该说法与官方或经审核的来源进行比对。",
    "Compare the claim against official or curated sources."
  ],
  safetyCommunityConflict: ["Не полагайтесь на сообщения сообщества, которые не проверены или противоречат более надёжным источникам.",
    "Тексерілмеген не сенімдірек дереккөздерге қайшы қауымдастық пікіріне сүйенбеңіз.",
    "不要依赖未经核实或与更可信来源冲突的社区信息。",
    "Warn the user when community information is unverified or conflicts with higher-trust sources."
  ],
  safetyEscalateSource: ["Передайте противоречия между источниками человеку для проверки.",
    "Дереккөздер арасындағы қайшылықтарды адамға тексеруге жіберіңіз.",
    "请将来源之间的冲突交由人工审核。",
    "Escalate source conflicts for human review."
  ],
  safetyUseTrustedInformation: ["Используйте только сведения, подтверждённые доступными проверенными источниками.",
    "Қолжетімді тексерілген дереккөздер растайтын мәліметті ғана пайдаланыңыз.",
    "请仅依据现有可信证据中的信息。",
    "Use only information supported by trusted sources."
  ],
  photoWarningPersonalData: ["Фото может содержать документы, телефоны, адреса, медицинские, визовые или платёжные сведения.",
    "Фотода құжаттар, телефондар, мекенжайлар, медициналық, визалық немесе төлем деректері болуы мүмкін.",
    "照片可能包含个人证件、电话号码、地址、医疗、签证或支付信息。",
    "Photos may contain personal documents, phone numbers, addresses, medical, visa, or payment information."
  ],
  photoWarningSensitiveUpload: ["Загружайте документы с личными данными только при необходимости для текущего вопроса.",
    "Жеке деректері бар құжаттарды ағымдағы сұрақ үшін қажет болғанда ғана жүктеңіз.",
    "仅在当前任务确有需要时上传敏感文件。",
    "Do not upload sensitive documents unless it is necessary for your current task."
  ],
  photoWarningUntrustedInput: ["Текст с фото предоставлен пользователем и не считается проверенным источником.",
    "Фотодан алынған мәтінді пайдаланушы ұсынады, ол тексерілген дереккөз болып саналмайды.",
    "提取的文字属于用户提供的内容，不是可信依据。",
    "Extracted text is user-provided input and is not trusted evidence."
  ],
  photoWarningVerifySource: ["Перед действием сверьте распознанный или введённый текст с официальными или проверенными источниками.",
    "Әрекет етпес бұрын танылған не енгізілген мәтінді ресми немесе тексерілген дереккөздермен салыстырыңыз.",
    "采取行动前，请用官方或已审核的来源核对识别或手动输入的文字。",
    "OCR or manual transcription text must be verified against official or curated sources before acting."
  ],
  photoWarningDoNotCite: ["Не используйте текст с фото как подтверждённый источник.",
    "Фотодан алынған мәтінді расталған дереккөз ретінде пайдаланбаңыз.", "请勿将照片提取文字作为可信依据引用。",
    "Do not cite extracted photo text as trusted evidence."
  ],
  photoWarningUnavailable: ["Распознавание недоступно. Введите текст вручную.",
    "Мәтінді тану қолжетімсіз. Мәтінді қолмен енгізіңіз.", "文字识别不可用，请手动输入文字。",
    "OCR unavailable; enter the text manually."
  ],
  photoWarningManual: ["Использован текст, введённый вручную.", "Қолмен енгізілген мәтін пайдаланылды.",
    "使用了手动输入的文字，未进行图片识别。", "Manual transcription was used instead of OCR text."
  ],
  photoWarningDemo: ["Демонстрационный режим OCR: фото не распознаётся.",
    "OCR демо режимі: фотодағы мәтін танылмайды.", "当前使用演示识别器，不会识别实际照片。",
    "Fake OCR provider; not production OCR."
  ],
  photoWarningCloud: ["Распознавание может ошибаться. Проверьте имена, даты и числа.",
    "Мәтінді тануда қате болуы мүмкін. Аты-жөндерді, күндерді және сандарды тексеріңіз.",
    "云端识别可能有误，请核对姓名、日期和数字。",
    "Cloud OCR can misread text. Verify names, dates and numbers."
  ],
  photoWarningLocalDisabled: ["Локальное распознавание не настроено или отключено.",
    "Жергілікті мәтін тану бапталмаған немесе өшірілген.", "本地文字识别尚未配置或启用。",
    "Local OCR is not configured/enabled."
  ],
  photoWarningNotExecuted: ["Распознавание текста не выполнялось.", "Мәтінді тану орындалмады.",
    "未进行文字识别。", "No OCR was executed."
  ],
  photoWarningDefaultFallback: ["По умолчанию доступен демонстрационный режим или ручной ввод.",
    "Әдепкіде демо режимі немесе қолмен енгізу қолжетімді.", "默认仍使用演示模式或手动输入。",
    "Fake/manual OCR remains the default."
  ],
  photoWarningLocalDetected: ["Компоненты локального OCR найдены, но распознавание в этом режиме пока недоступно.",
    "Жергілікті OCR компоненттері табылды, бірақ бұл режимде мәтінді тану әзірге қолжетімсіз.",
    "已检测到本地识别组件，但此模式尚不支持实际识别。",
    "Local OCR components were detected, but real OCR execution is not implemented in this phase."
  ],
  photoWarningNoLocalEngine: ["Система локального распознавания не найдена.",
    "Жергілікті мәтін тану жүйесі табылмады.", "未检测到本地文字识别引擎。", "No local OCR engine was detected."
  ],
  manualTextTooLong: ["Текст длиннее 12000 символов. Сократите его перед обработкой.",
    "Мәтін 12000 таңбадан асады. Өңдеу алдында оны қысқартыңыз.", "文字超过 12000 个字符，请缩短后再处理。",
    "The text exceeds 12000 characters. Shorten it before processing."
  ],
  photoPart: ["Часть", "Бөлік", "部分", "Part"],
  photoChoosePart: ["Выбрать часть", "Бөлікті таңдау", "选择部分", "Choose part"],
  photoPartNotice: [
    "В чат попадёт только выбранная часть. В остальных частях могут быть важные условия. Полный текст сохранён на экране фото; отправляйте части отдельно после проверки.",
    "Чатқа тек таңдалған бөлік жіберіледі. Қалған бөліктерде маңызды шарттар болуы мүмкін. Толық мәтін фото экранында сақталған; тексергеннен кейін бөліктерді жеке жіберіңіз.",
    "仅选中部分会发送到对话。其他部分可能包含重要条件。全文保留在照片页面，请检查后逐段发送。",
    "Only the selected part will go to chat. Other parts may contain important conditions. The full text remains on the photo page; review and send each part separately."
  ],
  pilotAccess: ["Код доступа участника", "Қатысушының кіру коды", "参与者访问码", "Participant access code"],
  pilotNotice: ["Код хранится только до закрытия приложения.", "Код тек қолданба жабылғанша сақталады.",
    "访问码仅保留至应用关闭。", "The code is kept only until the app closes."
  ],
  pilotConnect: ["Войти", "Кіру", "登录", "Sign in"],
  pilotDisconnect: ["Выйти", "Шығу", "退出", "Sign out"],
  pilotCodeInvalid: ["Вставьте код доступа целиком: 32–256 символов без пробелов внутри кода.",
    "Кіру кодын толық енгізіңіз: код ішінде бос орынсыз 32–256 таңба.", "请输入完整访问码：32–256 个字符，码内不能包含空格。",
    "Paste the complete access code: 32–256 characters with no spaces inside the code."
  ],
  pilotError: ["Не удалось войти. Проверьте код и соединение.",
    "Кіру мүмкін болмады. Кодты және байланысты тексеріңіз.", "登录失败，请检查访问码及网络连接。",
    "Sign-in failed. Check your code and connection."
  ],
  cloudChatNotice: ["Ответ готовится с помощью Alibaba Cloud. Не отправляйте лишние персональные сведения.",
    "Жауап Alibaba Cloud көмегімен дайындалады. Артық жеке деректерді жібермеңіз.",
    "回答由 Alibaba Cloud 协助生成，请勿发送不必要的个人信息。",
    "Answers use Alibaba Cloud. Avoid sending unnecessary personal information."
  ],
  localChatNotice: ["Локальный демонстрационный режим: облачная модель отключена.",
    "Жергілікті демо режим: бұлттық модель өшірулі.", "本地演示模式：云端模型未启用。",
    "Local demo mode: the cloud model is disabled."
  ],
  cloudChatFallback: [
    "Не удалось подготовить проверенный ответ. Ниже — общие безопасные шаги.",
    "Тексерілген жауап дайындалмады. Төменде жалпы қауіпсіз қадамдар берілген.",
    "未能生成经核实的回答。以下是一般性的安全建议。",
    "A verified answer could not be prepared. General safe steps are shown below."
  ],
  cloudPhotoConsent: ["Разрешаю отправить выбранное фото в Alibaba Cloud для распознавания текста",
    "Таңдалған фотодағы мәтінді тану үшін оны Alibaba Cloud қызметіне жіберуге келісемін",
    "同意将选定照片发送至 Alibaba Cloud 进行文字识别", "Allow sending this photo to Alibaba Cloud for text recognition"
  ],
  photoModeCloud: [
    "Фото будет обработано облачным OCR Alibaba Cloud. Проверьте изображение перед отправкой.",
    "Фото Alibaba Cloud қызметінде өңделеді. Жіберер алдында суретті тексеріңіз.",
    "照片将由 Alibaba Cloud 识别，发送前请检查图片。", "Alibaba Cloud OCR is enabled. Review the photo before sending."
  ],
  photoModeLocal: [
    "Локальное распознавание включено: фото обрабатывается на этом компьютере.",
    "Жергілікті тану қосулы: фото осы компьютерде өңделеді.",
    "本地文字识别已启用：照片将在此计算机上处理。",
    "Local text recognition is on. The photo is processed on this computer."
  ],
  photoModeDemo: ["Демонстрационный режим: распознавание фотографии отключено. Можно ввести текст вручную.",
    "Демо режим: фото танылмайды. Мәтінді қолмен енгізуге болады.", "演示模式：不识别实际照片，可手动输入文字。",
    "Demo mode: actual photo recognition is disabled; you can enter text manually."
  ],
  photoModeUnavailable: ["Не удалось определить режим OCR. Повторно откройте экран.",
    "OCR режимін анықтау мүмкін болмады. Экранды қайта ашыңыз.", "无法确定识别模式，请重新打开此页面。",
    "Cannot determine OCR mode. Reopen this page."
  ],
  photoLocalUnavailable: [
    "Tesseract не найден или не хватает языковых данных. Проверьте установку и перезапустите backend.",
    "Tesseract табылмады немесе тіл деректері жетіспейді. Орнатуды тексеріп, backend-ті қайта іске қосыңыз.",
    "未找到 Tesseract 或缺少语言数据。请检查安装并重启后端。",
    "Tesseract was not found or language data is missing. Check the setup and restart the backend."
  ],
  photoConsentRequired: ["Перед отправкой отметьте согласие на облачное распознавание.",
    "Жіберер алдында бұлтта тануға келісім беріңіз.", "发送前请确认同意云端识别。",
    "Confirm cloud processing before sending the photo."
  ],
  chooseRealPhoto: ["Сначала выберите фотографию или введите текст вручную.",
    "Алдымен фото таңдаңыз немесе мәтінді қолмен енгізіңіз.", "请先选择实际照片或手动输入文字。",
    "Choose a real photo or enter text manually first."
  ],
  home: ["Главная", "Басты бет", "首页", "Home"],
  chat: ["Моя ситуация", "Менің жағдайым", "我的情况", "Chat"],
  explain: ["Понять китайский текст", "Қытайша мәтінді түсіну", "理解中文通知", "Understand Chinese text"],
  emergency: ["Срочная помощь", "Шұғыл көмек", "紧急帮助", "Emergency help"],
  support: ["Помощь и обратная связь", "Көмек және кері байланыс", "帮助与反馈", "Help and feedback"],
  privacy: ["Мои данные", "Менің деректерім", "我的数据", "Privacy and data"],
  photo: ["Фото уведомления", "Хабарлама фотосы", "通知照片", "Photo of a notice"],
  checklist: ["Мои шаги", "Менің қадамдарым", "行动清单", "Checklist"],
  send: ["Отправить", "Жіберу", "发送", "Send"],
  newConversation: ["Новая ситуация", "Жаңа жағдай", "新情况", "New conversation"],
  question: ["Опишите вашу ситуацию", "Жағдайыңызды сипаттаңыз", "请描述您的情况", "Describe your situation"],
  direct: ["Краткий ответ", "Қысқаша жауап", "简要回答", "Direct answer"],
  scenario: ["Ситуация", "Жағдай", "场景", "Scenario"],
  risk: ["Уровень риска", "Тәуекел деңгейі", "风险等级", "Risk level"],
  steps: ["Следующие шаги", "Келесі қадамдар", "下一步建议", "Recommended next steps"],
  sources: ["Источники", "Дереккөздер", "来源", "Sources"],
  human: ["Обратиться к человеку", "Адамнан көмек сұрау", "请求人工帮助", "Request human help"],
  report: ["Помощь и обратная связь", "Көмек және кері байланыс", "帮助与反馈", "Help and feedback"],
  feedbackSend: ["Отправить отзыв", "Пікір жіберу", "提交反馈", "Submit feedback"],
  escalationSend: ["Отправить обращение", "Өтініш жіберу", "提交求助请求", "Send request"],
  chooseImage: ["Выбрать фото", "Фото таңдау", "选择照片", "Choose photo"],
  previewPhoto: ["Отправить на распознавание", "Мәтінді тануға жіберу", "发送并识别文字",
    "Send for text recognition"
  ],
  photoToChat: ["Использовать текст в чате", "Мәтінді чатта пайдалану", "在对话中使用文字", "Use text in chat"],
  explainAction: ["Объяснить", "Түсіндіру", "解释", "Explain"],
  generateChecklist: ["Составить список шагов", "Қадамдар тізімін жасау", "生成清单", "Create a step list"],
  deleteRequest: ["Запросить удаление", "Жоюды сұрау", "请求删除", "Request deletion"],
  copySource: ["Копировать ссылку", "Сілтемені көшіру", "复制来源链接", "Copy source link"],
  checked: ["Проверено", "Тексерілген", "核查日期", "Reviewed"],
  accessed: ["Дата обращения к источнику", "Дереккөзге қол жеткізілген күн", "访问日期", "Accessed"],
  anonymousNotice: [
    "Случайный идентификатор на этом устройстве связывает вопросы и обращения. Это не вход в аккаунт и не подтверждение личности.",
    "Осы құрылғыдағы кездейсоқ идентификатор сұрақтар мен өтініштерді байланыстырады. Бұл аккаунтқа кіру немесе жеке басты растау емес.",
    "本设备的随机标识用于关联问题和请求，不是账号登录或身份验证。",
    "A random identifier on this device links questions and requests. It is not account login or identity verification."
  ],
  requestFailed: ["Не удалось отправить запрос. Повторите позже.", "Сұрау жіберілмеді. Кейін қайталаңыз.",
    "请求失败，请稍后重试。", "Request failed. Please retry later."
  ],
  translationAccessRequired: ["Войдите в профиле, чтобы получить перевод.", "Аударма алу үшін профильге кіріңіз.",
    "请先在个人设置中登录，再获取翻译。", "Sign in from Profile before requesting a translation."
  ],
  enterMessage: ["Сначала опишите ситуацию.", "Алдымен жағдайды сипаттаңыз.", "请先描述您的情况。",
    "Enter a message first."
  ],
  official: ["Официальный источник", "Ресми дереккөз", "官方来源", "Official source"],
  curated: ["Проверенное руководство", "Тексерілген нұсқаулық", "审核指南", "Curated guide"],
  institutional: ["Институциональный опыт — не официальные правила",
    "Мекеме өкілінің тәжірибесі — ресми ереже емес", "机构人员经验，非官方规定",
    "Institutional experience only; not official guidance"
  ],
  practical: ["Практический опыт — не официальные правила", "Практикалық тәжірибе — ресми ереже емес",
    "实践经验，非官方规定", "Practical context only; not official guidance"
  ],
  unverified: ["Источник не подтверждён", "Дереккөз расталмаған", "来源未核实", "Source trust not established"],
  synthetic: ["Демонстрационный источник — не официальное подтверждение",
    "Демонстрациялық дереккөз — ресми растау емес", "演示来源，非官方依据",
    "Synthetic demo source; not official evidence"
  ],
  demoEvidence: [
    "Ответ использует демонстрационные материалы. Они не подтверждают реальные правила или процедуры.",
    "Жауапта демонстрациялық материалдар қолданылған. Олар нақты ережелер мен рәсімдерді растамайды.",
    "此回答使用演示材料，不能作为实际规定或流程的依据。",
    "This answer uses synthetic demonstration material. It does not establish real requirements or procedures."
  ],
  demoNotice: ["Внутреннее демо. Проверяйте важные действия по реальным официальным источникам.",
    "Ішкі демонстрация. Маңызды әрекеттерді нақты ресми дереккөздерден тексеріңіз.",
    "内部演示。重要行动请核实真实官方来源。", "Internal demo. Verify important actions against real official sources."
  ],
  emergencyNotice: [
    "Это не экстренная служба. При непосредственной опасности обратитесь в местные экстренные службы или официальные органы.",
    "Бұл шұғыл қызмет емес. Тікелей қауіп төнсе, жергілікті шұғыл қызметтерге немесе ресми органдарға жүгініңіз.",
    "此处不是紧急调度服务。若有即时危险，请联系当地应急服务或官方机构。",
    "This is not emergency dispatch. For immediate danger, contact local emergency services or official authorities."
  ],
  highRisk: ["Важное предупреждение о риске", "Маңызды тәуекел ескертуі", "高风险提示",
    "High-risk safety notice"
  ],
  officialRequired: ["Перед действием проверьте официальный источник",
    "Әрекет етпес бұрын ресми дереккөзді тексеріңіз", "采取行动前须核实官方来源",
    "Official source required before acting"
  ],
  tabChat: ["Чат", "Чат", "对话", "Chat"],
  tabExplain: ["Текст", "Мәтін", "通知", "Explain"],
  tabEmergency: ["Срочно", "Шұғыл", "紧急", "Emergency"]
};

function labels() {
  const index = context.LANGUAGES.indexOf(context.getPreferredLanguage());
  const ui = {};
  Object.keys(translations).forEach((key) => {
    ui[key] = translations[key][index];
  });
  Object.keys(interfaceCopy).forEach((key) => {
    ui[key] = interfaceCopy[key][index];
  });
  Object.keys(workspaceCopy).forEach((key) => {
    ui[key] = workspaceCopy[key][index];
  });
  Object.keys(accountCopy).forEach((key) => { ui[key] = accountCopy[key][index]; });
  return ui;
}

function pageState() {
  const language = context.getPreferredLanguage();
  return {
    ui: labels(),
    preferredLanguage: language,
    languageIndex: context.LANGUAGES.indexOf(language),
    languageLabels: ["Русский", "Қазақша", "中文", "English"]
  };
}

const photoWarningKeys = {
  "Photos may contain personal documents, phone numbers, addresses, medical, visa, or payment information.": "photoWarningPersonalData",
  "Do not upload sensitive documents unless it is necessary for your current task.": "photoWarningSensitiveUpload",
  "Extracted text is user-provided input and is not trusted evidence.": "photoWarningUntrustedInput",
  "OCR or manual transcription text must be verified against official or curated sources before acting.": "photoWarningVerifySource",
  "Do not cite extracted photo text as trusted evidence.": "photoWarningDoNotCite",
  "OCR unavailable; enter the text manually.": "photoWarningUnavailable",
  "Manual transcription was used instead of OCR text.": "photoWarningManual",
  "Fake OCR provider; not production OCR.": "photoWarningDemo",
  "Cloud OCR can misread text. Verify names, dates and numbers.": "photoWarningCloud",
  "Local OCR is not configured/enabled.": "photoWarningLocalDisabled",
  "No OCR was executed.": "photoWarningNotExecuted",
  "Fake/manual OCR remains the default.": "photoWarningDefaultFallback",
  "Local OCR components were detected, but real OCR execution is not implemented in this phase.": "photoWarningLocalDetected",
  "No local OCR engine was detected.": "photoWarningNoLocalEngine"
};

function photoWarning(value) {
  return Object.prototype.hasOwnProperty.call(photoWarningKeys, value) ? labels()[photoWarningKeys[value]] : value;
}

const policyStepKeys = {
  "Contact local emergency services or official authorities if immediate danger exists.": "safetyEmergencyContact",
  "Use the human support queue only as a follow-up record, not emergency dispatch.": "safetyQueueFollowup",
  "Preserve key facts and documents if it is safe to do so.": "safetyPreserveFacts",
  "Verify the requirement with an official or curated source.": "safetyVerifyOfficial",
  "Prefer official/curated guidance over community experience.": "safetyPreferOfficial",
  "Create an escalation request when status, deadline, employment, police, or document risk is high.": "safetyEscalateRisk",
  "Give safe administrative steps only, such as preparing documents and seeking care.": "safetyAdminCare",
  "For urgent symptoms, contact qualified medical professionals or official medical services.": "safetyUrgentMedical",
  "Use human escalation for language, document, or navigation help, not diagnosis.": "safetyHumanNotDiagnosis",
  "Do not send more money while the request is unclear.": "safetyNoMoreMoney",
  "Preserve screenshots, receipts, usernames, phone numbers, and transaction records.": "safetyPreservePaymentEvidence",
  "Ask for human review when money, landlord, employer, or account access risk is involved.": "safetyAskHumanReview",
  "Compare the claim against official or curated sources.": "safetyCompareSource",
  "Warn the user when community information is unverified or conflicts with higher-trust sources.": "safetyCommunityConflict",
  "Escalate source conflicts for human review.": "safetyEscalateSource",
  "Answer only within the available trusted evidence.": "safetyUseTrustedInformation",
  "Recommend official verification when sources are missing or uncertain.": "safetyVerifyOfficial"
};

function policyStep(value) {
  return Object.prototype.hasOwnProperty.call(policyStepKeys, value) ? labels()[policyStepKeys[value]] : value;
}

function escalationNotice(value) {
  return ["Existing chat workflow marked human or official escalation as required.",
    "Checklist engine recommends human or official escalation.",
    "Escalation / official verification required"].includes(value) ? labels().demoEscalationHelp : value;
}
function refresh(page) {
  const state = pageState();
  page.setData(state);
  if (typeof wx.setTabBarItem === "function") {
    const consul = (context.getAccount() || {}).account_type === "consul";
    [consul ? state.ui.consulCabinet : state.ui.assistant, consul ? state.ui.consulRequests : state.ui.cases, state.ui.knowledge, state.ui.profile].forEach((text, index) => {
      wx.setTabBarItem({
        index,
        text
      });
    });
  }
  if (typeof wx.setNavigationBarTitle === "function" && typeof getCurrentPages === "function") {
    const pages = getCurrentPages();
    const current = pages[pages.length - 1];
    const keys = {
      home: "assistant",
      cases: "cases",
      "case-detail": "cases",
      knowledge: "knowledge",
      profile: "profile",
      chat: "tabChat",
      demo: "demo",
      "demo-detail": "demo",
      "photo-intake": "navPhoto",
      checklist: "navChecklist",
      explain: "tabExplain",
      emergency: "tabEmergency",
      support: "navSupport",
      privacy: "privacy",
      consul: "consulRequests"
    };
    const name = current && (current.route || "").split("/")[1];
    if ((context.getAccount() || {}).account_type === "consul") {
      keys.home = "consulCabinet";
      keys.cases = "consulRequests";
    }
    if (keys[name]) wx.setNavigationBarTitle({
      title: state.ui[keys[name]]
    });
  }
}

module.exports = {
  labels,
  photoWarning,
  policyStep,
  escalationNotice,
  pageState,
  refresh
};
