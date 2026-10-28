"""Source-bounded document summaries for Kazakhstan visa applications in China."""

from __future__ import annotations

from backend.app.answer_quality.models import GroundedAnswerDraft, GroundedAnswerSection
from backend.app.answer_quality.policies import build_source_note
from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario
from backend.app.domain.sources import Citation, is_retrievable_source
from backend.app.source_registry.registry import SourceRegistry

_CONSULAR_DOCUMENTS_SOURCE_ID = "KZ-FOREIGNER-BEIJING-CONSULAR-DOCUMENTS-001"
_EVISA_SOURCE_ID = "KZ-FOREIGNER-EVISA-CATEGORIES-001"
_B10_SCOPE_SOURCE_ID = "KZ-FOREIGNER-BEIJING-B10-SCOPE-001"

_DOCUMENT_QUESTION_TERMS = {
    "documents",
    "document",
    "docs",
    "paperwork",
    "requirements",
    "what to bring",
    "what to take",
    "what do i need",
    "which documents",
    "required documents",
    "documents needed",
    "visa documents",
    "list of documents",
    "документ",
    "какие бумаги",
    "какие документы",
    "список документов",
    "список бумаг",
    "нужные документы",
    "документы для",
    "что нужно",
    "что требуется",
    "что принести",
    "что взять",
    "для подачи",
    "құжат",
    "қандай құжат",
    "қажет құжаттар",
    "не керек",
    "қандай құжаттар",
    "需要什么材料",
    "需要哪些材料",
    "材料清单",
    "申请材料",
    "签证材料",
    "哪些材料",
    "什么材料",
    "要什么材料",
    "文件",
}

_CATEGORY_TERMS = {
    "b10": ("b10", "в10"),
    "c9": ("c9", "с9"),
    "b8": ("b8", "в8"),
    "b2": ("b2", "в2"),
    "c3": ("c3", "с3"),
    "c5": ("c5", "с5"),
    "c10": ("c10", "с10"),
}

_CATEGORY_WORDS = {
    "b10": (
        "private visa",
        "private",
        "family visit",
        "частная виза",
        "частн",
        "жеке сапар",
        "私人访问",
    ),
    "c9": (
        "study visa",
        "student visa",
        "education visa",
        "study",
        "учебная виза",
        "студенческая виза",
        "учеб",
        "оқу визасы",
        "教育签证",
    ),
    "b8": (
        "permanent residence visa",
        "виза на пмж",
        "виза для пмж",
        "постоянное проживание",
        "пмж",
        "residence visa",
        "永久居留签证",
    ),
    "b2": ("business visa", "деловая виза", "бизнес-виза", "іскерлік виза", "商务签证"),
    "c3": (
        "work visa",
        "employment visa",
        "work",
        "рабочая виза",
        "работ",
        "жұмыс",
        "工作签证",
        "工作",
    ),
    "c5": (
        "business immigrant",
        "business immigration",
        "бизнес-иммигрант",
        "виза бизнес иммигранта",
        "бизнес-иммиграция",
        "商务移民签证",
    ),
    "c10": (
        "ethnic kazakh",
        "ethnic kazakhs",
        "этнический казах",
        "этнические казахи",
        "этникалық қазақ",
        "哈萨克族",
    ),
    "tourist_evisa": (
        "tourist visa",
        "tourist evisa",
        "tourist e visa",
        "туристическая виза",
        "туристік виза",
        "旅游签证",
    ),
}

_LABELS = {
    "ru": ("Документы со страницы Посольства РК в КНР", "Что сделать"),
    "kk": ("ҚХР-дағы ҚР елшілігінің бетінде көрсетілген құжаттар", "Не істеу керек"),
    "zh": ("哈萨克斯坦驻华使馆页面所列材料", "下一步"),
    "en": ("Documents listed by the Kazakhstan Embassy in China", "Next step"),
}

_NEXT_STEPS = {
    "ru": 'Сверь список с консульским отделом перед подачей: на ' \
          'странице не указана дата обновления, а требования, сборы и ' \
          'сроки могут измениться.',
    "kk": 'Өтініш бермес бұрын тізімді консулдық бөліммен нақтыла: ' \
          'бетте жаңартылған күн көрсетілмеген, талаптар, алымдар мен ' \
          'мерзімдер өзгеруі мүмкін.',
    "zh": "提交前请向领事部门核对清单：页面未显示更新时间，材料、费用和办理期限可能变化。",
    "en": 'Confirm this list with the Consular Section before ' \
          'applying: the page shows no update date, and requirements, ' \
          'fees, and timelines may change.',
}

_UNCERTAINTY = {
    "ru": "На странице консульства не указана дата обновления; сведения могут устареть.",
    "kk": "Консулдық бетте жаңартылған күн көрсетілмеген; мәліметтер ескіруі мүмкін.",
    "zh": "领事页面未标注更新时间，信息可能已过时。",
    "en": "The consular page shows no update date; its details may be outdated.",
}

_B10_SCOPE = {
    "ru": 'Важно: на странице B10 предназначена для ограниченного ' \
          'перечня случаев — похорон или болезни близких при наличии ' \
          'подтверждений; бывших соотечественников; супругов, детей ' \
          'или родителей, едущих вместе с гражданами Казахстана; а ' \
          'также супругов и детей, не являющихся этническими казахами, ' \
          'которые едут с этническими казахами. Это не общая ' \
          'туристическая категория.',
    "kk": 'Маңызды: бетте B10 шектеулі жағдайларға арналған — ' \
          'растайтын құжаттары бар жақын адамның жерлеуіне не ауруына ' \
          'байланысты сапар; бұрынғы отандастар; Қазақстан азаматымен ' \
          'бірге баратын жұбайы, балалары немесе ата-анасы; этникалық ' \
          'қазақтармен бірге баратын, этникалық қазақ емес жұбайы мен ' \
          'балалары. Бұл жалпы туристік санат емес.',
    "zh": '注意：页面所列B10仅适用于有限情形：有证明材料的近亲属葬礼或疾病；前同胞；与哈萨克斯' \
          '坦公民同行的配偶、子女或父母；以及' \
          '与哈萨克族人士同行、本人并非哈萨克族的配偶和子女。它不是一般旅游类别。',
    "en": 'Important: the page limits B10 to listed cases: a funeral ' \
          'or illness of close relatives with evidence; former ' \
          'compatriots; spouses, children, or parents travelling with ' \
          'Kazakhstan citizens; and non-ethnic-Kazakh spouses or ' \
          'children travelling with ethnic Kazakhs. It is not a ' \
          'general leisure-tourism category.',
}

_ANSWERS: dict[str, dict[str, str]] = {
    "ru": {
        "b10": 'Для B10 страница перечисляет: личную подачу; анкету; фото ' \
               '3,5×4,5 см; действующий паспорт минимум с двумя чистыми ' \
               'визовыми страницами и сроком действия не менее чем на 3 ' \
               'месяца дольше запрашиваемой визы; копию паспорта; для ' \
               'граждан КНР — копию удостоверения личности; оригинал ' \
               'приглашения, согласованного МВД РК, или письменное ' \
               'ходатайство получателя визы; подтверждение планируемого ' \
               'места проживания в Казахстане. Страница также указывает ' \
               'однократную визу до 90 суток и многократную до 180 суток ' \
               '(не более 90 суток за въезд). Сбор на странице: 515 CNY за ' \
               'однократную или 1285 CNY за многократную визу; сбор не ' \
               'возвращается. Указан срок 5 рабочих дней, ускоренная выдача ' \
               'не предусмотрена.',
        "c9": 'Для C9 страница перечисляет: личную подачу; анкету; фото ' \
              '3,5×4,5 см; действующий паспорт минимум с двумя чистыми ' \
              'визовыми страницами и сроком действия не менее чем на 3 ' \
              'месяца дольше запрашиваемой визы; копию паспорта; для ' \
              'граждан КНР — копию удостоверения личности; приглашение, ' \
              'согласованное МВД РК; при обучении на гранте — приказ о ' \
              'зачислении или квитанцию об оплате; при платном обучении — ' \
              'договор образовательных услуг; письмо-ходатайство вуза с ' \
              'фото и печатью. Срок визы на странице: однократная до 90 ' \
              'суток, многократная до 1 года. Сбор на странице: 515 CNY за ' \
              'однократную или 1285 CNY за многократную визу, не ' \
              'возвращается; срок — 5 рабочих дней, ускорение не ' \
              'предусмотрено.',
        "b8": 'Для B8 страница перечисляет: личную подачу; анкету; фото ' \
              '3,5×4,5 см; действующий паспорт минимум с двумя чистыми ' \
              'визовыми страницами и сроком действия не менее чем на 3 ' \
              'месяца дольше запрашиваемой визы; копию паспорта; для ' \
              'граждан КНР — копию удостоверения личности; рукописное ' \
              'ходатайство получателя визы; легализованную и переведённую ' \
              'справку об отсутствии судимости; банковскую выписку от 500 ' \
              '000 KZT; справку о наличии или отсутствии недвижимости; ' \
              'медицинскую страховку; для несовершеннолетнего — ' \
              'легализованное и переведённое свидетельство о рождении, а ' \
              'для зарубежного свидетельства о браке — легализацию и ' \
              'перевод. Страница указывает согласование документов ' \
              'компетентными органами, сбор 515/1285 CNY и отсутствие ' \
              'ускоренного режима; срок обработки не указан.',
        "b2": 'Для B2 страница перечисляет: удостоверение личности и ' \
              'паспорт со сроком действия не менее 6 месяцев и минимум ' \
              'двумя свободными страницами, плюс копии; анкету; две ' \
              'недавние цветные фотографии анфас на светлом фоне без ' \
              'головного убора (на странице указан размер 2 дюйма); копию ' \
              'приглашения из Казахстана; письмо с места работы с фото и ' \
              'печатью; копию лицензии на ведение бизнеса. Сбор на ' \
              'странице: 515 CNY за однократную или 1285 CNY за ' \
              'многократную визу; не возвращается. Указан срок 5 рабочих ' \
              'дней.',
        "c3": 'Для C3 страница перечисляет: удостоверение личности и ' \
              'паспорт со сроком действия не менее 6 месяцев и минимум ' \
              'двумя свободными страницами, плюс копии; заявление; две ' \
              'недавние цветные фотографии анфас на светлом фоне без ' \
              'головного убора (на странице указан размер 2 дюйма); копию ' \
              'приглашения из Казахстана; письмо с места работы с фото и ' \
              'печатью; копию лицензии на ведение бизнеса; разрешение на ' \
              'работу в Казахстане с QR-кодом, если не применяется ' \
              'установленное законом исключение. Сбор на странице: 515 CNY ' \
              'за однократную или 1285 CNY за многократную визу; не ' \
              'возвращается. Указан срок 5 рабочих дней.',
        "c5": 'Для C5 страница перечисляет: паспорт со сроком действия не ' \
              'менее 6 месяцев и минимум двумя свободными страницами, плюс ' \
              'копии; анкету; две недавние цветные фотографии; приглашение ' \
              'МВД Казахстана; международную медицинскую страховку; ' \
              'справку об отсутствии судимости; медицинскую справку; ' \
              'справку об отсутствии запрета на предпринимательскую ' \
              'деятельность по решению суда. Для перечисленных справок ' \
              'страница указывает перевод на казахский или русский язык и ' \
              'оформление апостиля через соответствующие органы КНР. Сбор ' \
              'на странице: 515 CNY за однократную или 1285 CNY за ' \
              'многократную визу; не возвращается. Указан срок 5 рабочих ' \
              'дней.',
        "c10": 'Для C10 (личные поездки этнических казахов) страница ' \
               'перечисляет: анкету из консульского отдела; две фотографии ' \
               '3,5×4,5 см; действующий паспорт с двумя чистыми страницами ' \
               'и сроком действия не менее 3 месяцев; копию паспорта; для ' \
               'граждан КНР — копию удостоверения личности; копию домовой ' \
               'книги; заявление из консульского отдела. Нужно взять ' \
               'оригиналы документов. Для детей до 16 лет страница ' \
               'дополнительно указывает свидетельство о браке родителей, ' \
               'свидетельство о рождении и удостоверения личности родителей ' \
               '— граждан КНР. На странице указаны однократная виза до 90 ' \
               'суток или многократная до 3 лет, срок оформления 5 рабочих ' \
               'дней и отсутствие консульского сбора.',
        "tourist_evisa": 'Для туристической e‑Visa национальная инструкция требует ' \
                         'сначала проверить доступность категории для гражданства и ' \
                         'цели поездки, получить приглашение, одобренное ' \
                         'уполномоченным органом, затем подать онлайн-заявку на Visa ' \
                         'and Migration Portal с номером приглашения. Данные ' \
                         'заявления должны совпадать с паспортом и приглашением; ' \
                         'консульский сбор оплачивается онлайн и зависит от категории ' \
                         'и числа въездов. Страница указывает срок рассмотрения ' \
                         'e‑Visa 1 рабочий день после одобрения приглашения; время ' \
                         'оформления приглашения в него не входит. e‑Visa ' \
                         'однократная; въезд и выезд по ней разрешены через ' \
                         'международные аэропорты Казахстана.',
        "clarify": 'Список зависит от категории. На странице есть B10 (частная ' \
                   'поездка), C9 (учёба), B8 (оформление ПМЖ), B2 (бизнес), C3 ' \
                   '(работа), C5 (бизнес-иммиграция) и C10 (личная поездка ' \
                   'этнических казахов). Напиши код категории, например B2 или ' \
                   'C3; туристическая e‑Visa оформляется по отдельной ' \
                   'национальной инструкции.',
        "business_clarify": 'Уточни категорию: B2 — деловая поездка, C5 — ' \
                            'бизнес-иммиграция. Список документов на странице ' \
                            'различается.',
    },
    "kk": {
        "b10": 'B10 үшін бетте мыналар көрсетілген: құжаттарды жеке ' \
               'тапсыру; анкета; 3,5×4,5 см фото; кемінде екі бос визалық ' \
               'беті бар және сұралған визаның мерзімі аяқталғаннан кейін ' \
               'кемінде 3 ай жарамды паспорт; паспорт көшірмесі; ҚХР ' \
               'азаматтарына жеке куәлік көшірмесі; ҚР ІІМ келіскен ' \
               'шақырудың түпнұсқасы немесе виза алушының жазбаша өтініші; ' \
               'Қазақстандағы жоспарланған тұратын жерді растау. Бетте бір ' \
               'мәрте визаның мерзімі 90 күнге дейін, көп мәртелі визаныкі ' \
               '180 күнге дейін (әр кіргенде 90 күннен аспайды) деп ' \
               'көрсетілген. Беттегі алым: бір мәрте кіруге 515 CNY, көп ' \
               'мәрте кіруге 1285 CNY; қайтарылмайды. Мерзімі — 5 жұмыс ' \
               'күні, жеделдету қарастырылмаған.',
        "c9": 'C9 үшін бетте мыналар көрсетілген: жеке тапсыру; анкета; ' \
              '3,5×4,5 см фото; кемінде екі бос визалық беті бар және ' \
              'сұралған виза мерзімінен кейін кемінде 3 ай жарамды ' \
              'паспорт; паспорт көшірмесі; ҚХР азаматтарына жеке куәлік ' \
              'көшірмесі; ҚР ІІМ келіскен шақыру; грантпен оқыса — ' \
              'қабылдау туралы бұйрық немесе оқу ақысын төлеу түбіртегі; ' \
              'ақылы оқу үшін білім беру қызметтері шарты; оқу орнының ' \
              'фотосы мен мөрі бар өтініші. Бетте бір мәрте визаның ' \
              'мерзімі 90 күнге дейін, көп мәртелі визаныкі 1 жылға дейін ' \
              'деп көрсетілген. Бетте бір мәрте кіруге 515 CNY, көп мәрте ' \
              'кіруге 1285 CNY алым көрсетілген; қайтарылмайды. Мерзімі — ' \
              '5 жұмыс күні, жеделдету жоқ.',
        "b8": 'B8 үшін бетте мыналар көрсетілген: жеке тапсыру; анкета; ' \
              '3,5×4,5 см фото; кемінде екі бос визалық беті бар және ' \
              'сұралған виза мерзімінен кейін кемінде 3 ай жарамды ' \
              'паспорт; паспорт көшірмесі; ҚХР азаматтарына жеке куәлік ' \
              'көшірмесі; өтініш берушінің қолмен жазылған өтініші; ' \
              'заңдастырылған және аударылған соттылығы жоқтығы туралы ' \
              'анықтама; кемінде 500 000 KZT банк үзіндісі; жылжымайтын ' \
              'мүлік бар-жоғы туралы анықтама; медициналық сақтандыру; ' \
              'кәмелетке толмаған балаға заңдастырылған әрі аударылған туу ' \
              'туралы куәлік, ал шетелдік неке куәлігіне заңдастыру мен ' \
              'аударма. Құжаттар уәкілетті органдармен келісіледі. Бетте ' \
              '515/1285 CNY алымы және жеделдетудің жоқтығы көрсетілген; ' \
              'қарау мерзімі жазылмаған.',
        "b2": 'B2 үшін бетте мыналар көрсетілген: жеке куәлік және кемінде ' \
              '6 ай жарамды, екі бос беті бар паспорт, олардың ' \
              'көшірмелері; анкета; ашық түсті фонда бас киімсіз ' \
              'түсірілген соңғы екі түсті фото (бетте өлшемі 2 дюйм деп ' \
              'көрсетілген); Қазақстаннан шақыру көшірмесі; фотосы және ' \
              'мөрі бар жұмыс орнынан хат; бизнес лицензиясының көшірмесі. ' \
              'Беттегі алым: бір мәрте кіруге 515 CNY, көп мәрте кіруге ' \
              '1285 CNY; қайтарылмайды. Мерзімі — 5 жұмыс күні.',
        "c3": 'C3 үшін бетте мыналар көрсетілген: жеке куәлік және кемінде ' \
              '6 ай жарамды, екі бос беті бар паспорт, олардың ' \
              'көшірмелері; өтініш; ашық түсті фонда бас киімсіз ' \
              'түсірілген соңғы екі түсті фото (бетте өлшемі 2 дюйм деп ' \
              'көрсетілген); Қазақстаннан шақыру көшірмесі; фотосы және ' \
              'мөрі бар жұмыс орнынан хат; бизнес лицензиясының көшірмесі; ' \
              'заңдағы ерекшелік қолданылмаса, QR-коды бар Қазақстанда ' \
              'жұмыс істеуге рұқсат. Беттегі алым: 515/1285 CNY, ' \
              'қайтарылмайды. Мерзімі — 5 жұмыс күні.',
        "c5": 'C5 үшін бетте мыналар көрсетілген: кемінде 6 ай жарамды, ' \
              'екі бос беті бар паспорт және көшірмелері; анкета; соңғы ' \
              'екі түсті фото; Қазақстан ІІМ-нің шақыруы; халықаралық ' \
              'медициналық сақтандыру; соттылығы жоқтығы туралы анықтама; ' \
              'медициналық анықтама; сот шешімімен кәсіпкерлікке тыйым ' \
              'салынбағаны туралы анықтама. Бетте аталған анықтамаларды ' \
              'қазақша не орысшаға аударып, ҚХР органдары арқылы апостиль ' \
              'қою көрсетілген. Алым — бір мәрте кіруге 515 CNY немесе көп ' \
              'мәрте кіруге 1285 CNY, қайтарылмайды; мерзімі — 5 жұмыс ' \
              'күні.',
        "c10": 'C10 (этникалық қазақтардың жеке сапары) үшін бетте мыналар ' \
               'көрсетілген: консулдықтан берілетін анкета; екі 3,5×4,5 см ' \
               'фото; екі бос беті бар және кемінде 3 ай жарамды паспорт; ' \
               'паспорт көшірмесі; ҚХР азаматтарына жеке куәлік көшірмесі; ' \
               'үй кітапшасының көшірмесі; консулдықтан берілетін өтініш. ' \
               'Құжаттардың түпнұсқаларын алып бару керек. 16 жасқа ' \
               'толмаған балаларға ата-анасының неке куәлігі, туу туралы ' \
               'куәлік және ата-анасының ҚХР жеке куәліктері қосымша ' \
               'көрсетілген. Бетте бір мәрте визаның мерзімі 90 күнге ' \
               'дейін, көп мәртелі визаныкі 3 жылға дейін, рәсімдеу мерзімі ' \
               '5 жұмыс күні және консулдық алым жоқ деп жазылған.',
        "tourist_evisa": 'Туристік e‑Visa үшін ұлттық нұсқаулық алдымен азаматтық пен ' \
                         'сапар мақсаты бойынша жарамдылықты тексеруді, уәкілетті ' \
                         'орган мақұлдаған шақыру алуды, содан кейін Visa and ' \
                         'Migration Portal сайтында шақыру нөмірімен онлайн өтініш ' \
                         'беруді талап етеді. Өтініштегі деректер паспорт пен ' \
                         'шақыруға сәйкес болуы керек; алым онлайн төленеді және ' \
                         'санат пен кіру санына байланысты. Бетте e‑Visa қарау ' \
                         'мерзімі шақыру мақұлданғаннан кейін 1 жұмыс күні деп ' \
                         'көрсетілген; шақыруды рәсімдеу уақыты бұған кірмейді. ' \
                         'e‑Visa бір мәрте кіруге беріледі, кіру және шығу тек ' \
                         'Қазақстанның халықаралық әуежайлары арқылы рұқсат етіледі.',
        "clarify": 'Құжаттар санатқа байланысты. Бетте B10 (жеке сапар), C9 ' \
                   '(оқу), B8 (ПМЖ рәсімдеу), B2 (бизнес), C3 (жұмыс), C5 ' \
                   '(бизнес-иммиграция) және C10 (этникалық қазақтардың жеке ' \
                   'сапары) көрсетілген. B2 немесе C3 сияқты кодын жаз; ' \
                   'туристік e‑Visa бөлек ұлттық нұсқаулықпен рәсімделеді.',
        "business_clarify": 'Санатты нақтыла: B2 — іскерлік сапар, C5 — ' \
                            'бизнес-иммиграция. Беттегі құжаттар тізімі әртүрлі.',
    },
    "zh": {
        "b10": 'B10页面列出的材料：本人递交申请表；3.5×4.5厘米照片；有效护照至少有两页签证空白' \
               '页，且有效期比申请签证结束日期多' \
               '至少3个月；护照复印件；中国公民身份证复印件；经哈萨克斯坦内务部批准的邀请函原' \
               '件，或签证申请人的书面申请；在哈萨克斯坦计' \
               '划居住地点的证明。页面注明单次签证最长90天，多次签证最长180天（每次停留不超过9' \
               '0天）。页面列示单次签证515元、多' \
               '次签证1285元，费用不退；办理5个工作日，不提供加急服务。',
        "c9": 'C9页面列出的材料：本人递交申请表；3.5×4.5厘米照片；至少有两页签证空白页、有效期' \
              '比申请签证结束日期多至少3个月的' \
              '护照及复印件；中国公民身份证复印件；经哈萨克斯坦内务部批准的邀请函；奖学金学习' \
              '者提供录取命令或学费收据；自费学习者提供教' \
              '育服务合同；高校出具并盖章、附照片的申请信。页面注明单次签证最长90天，多次签证' \
              '最长1年。页面列示单次515元、多次12' \
              '85元，费用不退；办理5个工作日，不提供加急服务。',
        "b8": 'B8页面列出的材料：本人递交申请表；3.5×4.5厘米照片；至少有两页签证空白页、有效期' \
              '比申请签证结束日期多至少3个月的' \
              '护照及复印件；中国公民身份证复印件；申请人手写申请；经认证并翻译的无犯罪记录证' \
              '明；至少50万坚戈的银行流水；房产有无证明' \
              '；医疗保险；未成年人需经认证和翻译的出生证明，外国婚姻证明需认证和翻译。材料须' \
              '由哈萨克斯坦主管部门批准。页面列示515/' \
              '1285元费用且不提供加急服务；未列办理时限。',
        "b2": 'B2页面列出的材料：身份证件及有效期至少6个月、至少两页空白页的护照和复印件；签证' \
              '申请表；两张近期彩色正面照片，浅色背景' \
              '、不得戴帽（页面写明尺寸为2英寸）；哈萨克斯坦邀请函复印件；附照片并盖章的工作单' \
              '位申请信；营业执照复印件。页面列示单次5' \
              '15元、多次1285元，费用不退；办理5个工作日。',
        "c3": 'C3页面列出的材料：身份证件及有效期至少6个月、至少两页空白页的护照和复印件；申请' \
              '表；两张近期彩色正面照片，浅色背景、不' \
              '得戴帽（页面写明尺寸为2英寸）；哈萨克斯坦邀请函复印件；附照片并盖章的工作单位申' \
              '请信；营业执照复印件；除法定豁免外，提供' \
              '带二维码的哈萨克斯坦工作许可。页面列示单次515元、多次1285元，费用不退；办理5个工作日。',
        "c5": 'C5页面列出的材料：有效期至少6个月且至少有两页空白页的护照及复印件；申请表；两张' \
              '近期彩色照片；哈萨克斯坦内务部邀请函；' \
              '国际医疗保险；无犯罪记录证明；医疗证明；无因法院裁决而被禁止从事商业活动的证明' \
              '。页面称上述证明需译为哈萨克语或俄语，并经' \
              '中国有关部门办理附加证明书。页面列示单次515元、多次1285元，费用不退；办理5个工作日。',
        "c10": 'C10（哈萨克族私人访问）页面列出的材料：领事部门提供的申请表；两张3.5×4.5厘米照' \
               '片；至少有两页空白页、有效期至少' \
               '3个月的护照及复印件；中国公民身份证复印件；户口簿复印件；领事部门提供的申请书' \
               '。须携带文件原件。16岁以下儿童另需父母结' \
               '婚证、出生证明及父母的中国身份证。页面列示单次签证最长90天、多次签证最长3年，办理5个工作日且不收领事费。',
        "tourist_evisa": '旅游e‑Visa国家指南要求先按国籍和旅行目的检查资格，取得主管机关批准的' \
                         '邀请函，再在Visa and ' \
                         'Migration ' \
                         'Portal输入邀请编号在线申请。申请信息必须与护照和邀请函一致；领事费在' \
                         '线支付，金额取决于签证类别和入境次数。页面称邀' \
                         '请获批后e‑Visa办理时间为1个工作日，不包括邀请审批时间。e‑Visa为单次入境，入境和离境仅限哈萨克斯坦国际机场。',
        "clarify": '材料取决于签证类别。页面列有B10私人访问、C9教育、B8办理永久居留、B2商务、C' \
                   '3工作、C5商务移民和面向哈萨克族的' \
                   'C10私人访问。请发送类别代码（例如B2或C3）；旅游e‑Visa按另一份国家指南申请。',
        "business_clarify": "请确认类别：B2是商务访问，C5是商务移民。页面列出的材料不同。",
    },
    "en": {
        "b10": 'For B10, the page lists: personal submission; application ' \
               'form; 3.5×4.5 cm photo; valid passport with at least two ' \
               'blank visa pages and validity extending at least three ' \
               'months beyond the requested visa; passport copy; PRC ID ' \
               'copy for PRC citizens; original invitation approved by ' \
               "Kazakhstan's MIA or the recipient's written petition; proof " \
               'of planned accommodation in Kazakhstan. The page lists ' \
               'single entry up to 90 days or multiple entry up to 180 days ' \
               '(no more than 90 days per entry). The page lists 515 CNY ' \
               'single-entry or 1,285 CNY multiple-entry, non-refundable; ' \
               'five working days; no expedited service.',
        "c9": 'For C9, the page lists: personal submission; application ' \
              'form; 3.5×4.5 cm photo; valid passport with at least two ' \
              'blank visa pages and validity extending at least three ' \
              'months beyond the requested visa, plus passport copy; PRC ' \
              'ID copy for PRC citizens; invitation approved by ' \
              "Kazakhstan's MIA; for grant-funded study, an admission " \
              'order or tuition receipt; for paid study, an ' \
              'education-services contract; a university petition letter ' \
              'with photo and stamp. The page lists single entry up to 90 ' \
              'days or multiple entry up to one year. The page lists ' \
              '515/1,285 CNY for single/multiple entry, non-refundable; ' \
              'five working days; no expedited service.',
        "b8": 'For B8, the page lists: personal submission; application ' \
              'form; 3.5×4.5 cm photo; valid passport with at least two ' \
              'blank visa pages and validity extending at least three ' \
              'months beyond the requested visa, plus passport copy; PRC ' \
              'ID copy for PRC citizens; handwritten petition by the visa ' \
              'applicant; legalized and translated criminal-record ' \
              'certificate; bank statement of at least KZT 500,000; ' \
              'property certificate; medical insurance; for a minor, ' \
              'legalized and translated birth certificate, and ' \
              'legalization and translation of a foreign marriage ' \
              'certificate where applicable. Documents require approval by ' \
              "Kazakhstan's competent authorities. The page lists " \
              '515/1,285 CNY fees and no expedited service; it does not ' \
              'state a processing time.',
        "b2": 'For B2, the page lists: identity document and passport ' \
              'valid for at least six months with at least two blank ' \
              'pages, plus copies; visa application; two recent color ' \
              'front-facing photos on a light background without headwear ' \
              '(the page says 2-inch size); copy of an invitation from ' \
              'Kazakhstan; employer letter with photo and stamp; ' \
              'business-license copy. The page lists 515 CNY single-entry ' \
              'or 1,285 CNY multiple-entry, non-refundable; five working ' \
              'days.',
        "c3": 'For C3, the page lists: identity document and passport ' \
              'valid for at least six months with at least two blank ' \
              'pages, plus copies; application; two recent color ' \
              'front-facing photos on a light background without headwear ' \
              '(the page says 2-inch size); copy of an invitation from ' \
              'Kazakhstan; employer letter with photo and stamp; ' \
              'business-license copy; Kazakhstan work permit with QR code ' \
              'unless a statutory exception applies. The page lists ' \
              '515/1,285 CNY for single/multiple entry, non-refundable; ' \
              'five working days.',
        "c5": 'For C5, the page lists: passport valid for at least six ' \
              'months with at least two blank pages, plus copies; ' \
              'application form; two recent color photos; invitation from ' \
              "Kazakhstan's Ministry of Internal Affairs; international " \
              'medical insurance; criminal-record certificate; medical ' \
              'certificate; certificate confirming there is no ' \
              'court-imposed business-activity ban. The page says these ' \
              'certificates must be translated into Kazakh or Russian and ' \
              'processed for apostille through the relevant PRC ' \
              'authorities. The page lists 515/1,285 CNY for ' \
              'single/multiple entry, non-refundable; five working days.',
        "c10": 'For C10 (private travel by ethnic Kazakhs), the page lists: ' \
               'application form from the Consular Section; two 3.5×4.5 cm ' \
               'photos; valid passport with at least two blank pages and at ' \
               'least three months validity, plus passport copy; PRC ID ' \
               'copy for PRC citizens; household-registration-book copy; ' \
               'petition form from the Consular Section. Bring original ' \
               'documents. For children under 16, the page additionally ' \
               "lists parents' marriage certificate, birth certificate, and " \
               "parents' PRC identity cards. The page lists single entry up " \
               'to 90 days or multiple entry up to three years, five ' \
               'working days, and no consular fee.',
        "tourist_evisa": 'For a tourist e-Visa, the national guide says to check ' \
                         'eligibility for the citizenship and purpose, obtain an ' \
                         'invitation approved by the authorized body, then apply ' \
                         'online through the Visa and Migration Portal using the ' \
                         'invitation number. Application details must match the ' \
                         'passport and invitation; the consular fee is paid online ' \
                         'and depends on category and number of entries. The page ' \
                         'states one business day to process the e-Visa after ' \
                         'invitation approval; invitation processing is excluded. The ' \
                         'e-Visa is single-entry, and entry and exit are allowed only ' \
                         "through Kazakhstan's international airports.",
        "clarify": 'The document list depends on the category. The page lists ' \
                   'B10 private visit, C9 education, B8 for applying for ' \
                   'permanent residence, B2 business, C3 work, C5 business ' \
                   'immigration, and C10 private travel for ethnic Kazakhs. ' \
                   'Send the category code, such as B2 or C3. Tourist e-Visa ' \
                   'uses a separate national guide.',
        "business_clarify": 'Which category do you mean: B2 for a business visit or C5 ' \
                            'for business immigration? The page lists different ' \
                            'documents for each.',
    },
}


def build_kazakhstan_consular_document_answer(
    user_message: str,
    language: LanguageCode,
    registry: SourceRegistry,
    *,
    context_text: str = "",
) -> tuple[GroundedAnswerDraft, list[Citation], dict[str, str | None]] | None:
    """Answer document questions from the dated official page snapshot only."""
    category = _document_category(user_message)
    if not _is_document_question(user_message):
        return None
    if category is None:
        for previous_user_message in reversed(_user_turns(context_text)):
            category = _document_category(previous_user_message)
            if category:
                break
    lang = language.value if language.value in _ANSWERS else "en"
    if category is None:
        category = "clarify"
    source_id = _EVISA_SOURCE_ID if category == "tourist_evisa" else _CONSULAR_DOCUMENTS_SOURCE_ID
    source = registry.get_source_by_id(source_id)
    if (
        source is None
        or source.source_type.value != "official"
        or not is_retrievable_source(source)
    ):
        return None
    answer = _ANSWERS[lang][category]
    b10_scope_source = None
    b10_scope = None
    if category == "b10":
        b10_scope_source = registry.get_source_by_id(_B10_SCOPE_SOURCE_ID)
        if (
            b10_scope_source is None
            or b10_scope_source.source_type.value != "official"
            or not is_retrievable_source(b10_scope_source)
        ):
            return None
        b10_scope = _B10_SCOPE[lang]
        answer = f"{b10_scope}\n\n{answer}"
    title, next_step_label = _LABELS[lang]
    next_step = _NEXT_STEPS[lang]
    grounded_facts = []
    citations = []
    if b10_scope_source is not None and b10_scope is not None:
        grounded_facts.append(
            GroundedAnswerSection(
                heading=title,
                body=b10_scope,
                source_ids=[_B10_SCOPE_SOURCE_ID],
            )
        )
        citations.append(
            Citation(
                citation_id="KZ-CONSULAR-DOCS-B10-SCOPE",
                source_id=_B10_SCOPE_SOURCE_ID,
                claim=b10_scope,
                supporting_quote=b10_scope_source.content,
                confidence=0.91,
            )
        )
    grounded_facts.append(
        GroundedAnswerSection(heading=title, body=_ANSWERS[lang][category], source_ids=[source_id])
    )
    citations.append(
        Citation(
            citation_id=f"KZ-CONSULAR-DOCS-{category.upper()}",
            source_id=source_id,
            claim=_ANSWERS[lang][category],
            supporting_quote=source.content,
            confidence=0.91,
        )
    )
    draft = GroundedAnswerDraft(
        scenario=UserScenario.kazakhstan_entry.value,
        risk_level=RiskLevel.legal_sensitive.value,
        language=lang,
        direct_answer=answer,
        grounded_facts=grounded_facts,
        recommended_steps=[GroundedAnswerSection(heading=next_step_label, body=next_step)],
        uncertainty=[_UNCERTAINTY[lang]],
        source_notes=[build_source_note(source)]
        + ([build_source_note(b10_scope_source)] if b10_scope_source is not None else []),
    )
    selected_source_ids = [source_id]
    if b10_scope_source is not None:
        selected_source_ids.append(_B10_SCOPE_SOURCE_ID)
    return (
        draft,
        citations,
        {
            "intent": f"consular_documents_{category}",
            "category": None if category in {"clarify", "business_clarify"} else category.upper(),
            "source_ids": ",".join(selected_source_ids),
            "snapshot_date": "2026-10-26",
        },
    )


def _is_document_question(message: str) -> bool:
    text = _normalize(message)
    return any(_normalize(term) in text for term in _DOCUMENT_QUESTION_TERMS)


def _document_category(message: str) -> str | None:
    text = _normalize(message)
    matched_codes = {
        category
        for category, terms in _CATEGORY_TERMS.items()
        if any(_normalize(term) in text for term in terms)
    }
    if {"b2", "c5"}.issubset(matched_codes):
        return "business_clarify"
    if len(matched_codes) == 1:
        return next(iter(matched_codes))
    if len(matched_codes) > 1:
        return "clarify"
    for category in ("tourist_evisa", "c5", "c3", "c9", "b8", "b2", "b10", "c10"):
        if any(_normalize(term) in text for term in _CATEGORY_WORDS[category]):
            return category
    if any(term in text for term in ("business", "бизнес", "делов", "командиров", "商务")):
        return "business_clarify"
    return None


def _user_turns(context_text: str) -> list[str]:
    return [
        line.partition(":")[2].strip()
        for line in context_text.splitlines()
        if line.casefold().startswith("user:")
    ]


def _normalize(text: str) -> str:
    import re

    return " ".join(re.sub(r"[^\w\u4e00-\u9fff]+", " ", text.casefold().replace("ё", "е")).split())
