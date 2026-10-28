// Fictional display-only stories. Never uploaded, published or offered to retrieval.
const stories = [
  {
    id: "preview-campus", scenario: "study", author: "Аружан",
    role: ["Студентка", "Студент", "学生", "Student"],
    city: ["Шанхай", "Шанхай", "上海", "Shanghai"],
    title: ["Первый день в кампусе", "Кампустағы алғашқы күн", "初到校园的一天", "My first day on campus"],
    body: [
      "В первый день я несколько раз перепутала корпуса. Помогла простая заметка: название общежития по-китайски, карта кампуса и вопросы для учебного офиса. Вечером собрала всё в одном месте — на следующий день было спокойнее.",
      "Алғашқы күні ғимараттарды бірнеше рет шатастырдым. Жатақхананың қытайша атауы, кампус картасы және оқу бөліміне қоятын сұрақтар жазылған жазба көмектесті. Кешке бәрін бір жерге жинадым, келесі күн жеңілірек өтті.",
      "第一天我总是走错楼。后来我把宿舍的中文名称、校园地图和想问教务处的问题放进同一条笔记里。第二天找路时就没那么慌了。",
      "On my first day I kept mixing up buildings. I saved the dorm name in Chinese, a campus map and my questions for the student office in one note. The next morning felt much easier."
    ]
  },
  {
    id: "preview-home", scenario: "housing", author: "Данияр",
    role: ["Живёт в Китае", "Қытайда тұрады", "在中国生活", "Lives in China"],
    city: ["Гуанчжоу", "Гуанчжоу", "广州", "Guangzhou"],
    title: ["Что я записал перед просмотром квартиры", "Пәтерді көрер алдында не жаздым", "看房前的一张清单", "My apartment viewing notes"],
    body: [
      "На просмотре легко забыть половину вопросов. Я заранее записал, что хочу спросить о шуме, бытовой технике и дороге до работы. После каждого просмотра добавлял пару строк впечатлений — так сравнивать варианты оказалось проще.",
      "Пәтерді көргенде сұрақтардың жартысы ұмытылып кетеді. Шу, тұрмыстық техника және жұмысқа баратын жол туралы сұрақтарды алдын ала жаздым. Әр пәтерден кейін әсерімді қысқаша белгілеп отырдым, нұсқаларды салыстыру оңай болды.",
      "看房时很容易忘记想问的问题。我提前记下噪音、家电和通勤方面的问题，每看完一套就写几句感受。这样比较起来清楚多了。",
      "I kept forgetting questions during viewings. I wrote down what to ask about noise, appliances and the commute, then added a few impressions after each visit. Comparing places became easier."
    ]
  },
  {
    id: "preview-message", scenario: "translation", author: "Мадина",
    role: ["Студентка", "Студент", "学生", "Student"],
    city: ["Пекин", "Бейжің", "北京", "Beijing"],
    title: ["Сообщение, которое я не сразу поняла", "Бірден түсінбеген хабарлама", "没看懂的一条消息", "A message I did not understand"],
    body: [
      "Получила длинное сообщение из учебной группы и не поняла, к какому корпусу оно относится. Выписала незнакомые слова и подготовила короткий вопрос на китайском. Староста уточнил место, а я сохранила ответ рядом с исходным сообщением.",
      "Оқу тобынан ұзақ хабарлама келді, бірақ қай ғимарат туралы екенін түсінбедім. Бейтаныс сөздерді жазып, қытайша қысқа сұрақ дайындадым. Топ жетекшісі орнын нақтылады, жауабын бастапқы хабарламамен бірге сақтадым.",
      "班级群里发来一条很长的消息，我没弄清楚说的是哪栋楼。我记下不认识的词，准备了一个简短的中文问题。班长确认地点后，我把回复和原消息存到了一起。",
      "A long class message left me unsure which building it meant. I noted the unfamiliar words and prepared one short question in Chinese. The class representative clarified the location, and I saved the reply beside the original."
    ]
  },
  {
    id: "preview-expo", scenario: "business", author: "Асем",
    role: ["Предпринимательница", "Кәсіпкер", "创业者", "Entrepreneur"],
    city: ["Ханчжоу", "Ханчжоу", "杭州", "Hangzhou"],
    title: ["Как не потерять заметки после выставки", "Көрмеден кейін жазбаларды жоғалтпау", "展会之后如何整理笔记", "Keeping my exhibition notes together"],
    body: [
      "После нескольких встреч все разговоры начали смешиваться. Для каждой встречи я оставляла отдельную заметку: что обсудили, какие вопросы остались и что проверить позже. В конце дня получился понятный список следующих шагов.",
      "Бірнеше кездесуден кейін әңгімелер араласып кетті. Әр кездесу үшін не талқыланғанын, қандай сұрақтар қалғанын және кейін нені тексеру керегін бөлек жаздым. Күн соңында келесі қадамдар тізімі дайын болды.",
      "见了几拨人后，聊天内容开始混在一起。我给每次见面单独记下讨论内容、待问的问题和之后要核实的事。一天结束时，接下来要做什么就很清楚了。",
      "After several meetings the conversations blurred together. I kept a separate note for each one: what we discussed, open questions and things to check later. By the evening I had a clear list of next steps."
    ]
  }
];

function list(language, filters = {}) {
  const index = Math.max(0, ["ru", "kk", "zh", "en"].indexOf(language));
  const query = String(filters.query || "").trim().toLowerCase();
  const city = String(filters.city || "").trim().toLowerCase();
  return stories.filter((s) => (!filters.scenario || s.scenario === filters.scenario)
    && (!city || s.city.join(" ").toLowerCase().includes(city))
    && (!query || [s.author, ...s.title, ...s.body, ...s.city].join(" ").toLowerCase().includes(query)))
    .map((s) => ({ id: s.id, author: s.author, role: s.role[index], city: s.city[index],
      title: s.title[index], body: s.body[index], initial: s.author.slice(0, 1),
      is_synthetic: true, allow_ai_retrieval: false }));
}

module.exports = { list };
