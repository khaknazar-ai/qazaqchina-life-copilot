// Match ChatRequest.user_message. Count Unicode code points, as Python does.
const CHAT_MAX_CHARS = 8000;
const MANUAL_MAX_CHARS = 12000;

const PHOTO_PROMPTS = {
  ru: {
    single: "Переведи и объясни текст с фото.",
    part: (number, count) => `Переведи и объясни часть ${number} из ${count} текста с фото.`,
    source: "Текст с фото:"
  },
  kk: {
    single: "Суреттегі мәтінді аударып, түсіндір.",
    part: (number, count) => `Суреттегі мәтіннің ${number}/${count} бөлігін аударып, түсіндір.`,
    source: "Суреттегі мәтін:"
  },
  zh: {
    single: "翻译并解释照片中的文字。",
    part: (number, count) => `翻译并解释照片文字的第 ${number}/${count} 部分。`,
    source: "照片中的文字："
  },
  en: {
    single: "Translate and explain the text in this photo.",
    part: (number, count) => `Translate and explain part ${number} of ${count} of the photo text.`,
    source: "Text from the photo:"
  }
};

function characterCount(text) {
  return Array.from(String(text || "")).length;
}

function buildPhotoChatPrompt(text, partNumber = 1, partCount = 1, language = "en") {
  const prompt = PHOTO_PROMPTS[language] || PHOTO_PROMPTS.en;
  return [
    partCount > 1 ? prompt.part(partNumber, partCount) : prompt.single,
    prompt.source,
    String(text || "")
  ].join("\n");
}

function splitPhotoText(text) {
  const characters = Array.from(String(text || ""));
  if (!characters.length) return [];
  const singleLimit = CHAT_MAX_CHARS - characterCount(buildPhotoChatPrompt(""));
  if (characters.length <= singleLimit) return [characters.join("")];
  // The number of parts cannot exceed the number of characters. Reserve that
  // many digits in both labels before splitting, so labels never exceed budget.
  const limit = CHAT_MAX_CHARS - characterCount(
    buildPhotoChatPrompt("", characters.length, characters.length)
  );
  const chunks = [];
  let start = 0;
  while (start < characters.length) {
    let end = Math.min(start + limit, characters.length);
    if (end < characters.length) {
      // Prefer a nearby word/line boundary, but keep every character and allow
      // long unbroken Chinese text. Array.from never splits a surrogate pair.
      for (let i = end - 1; i >= start + Math.floor(limit * 0.8); i -= 1) {
        if (/\s/.test(characters[i])) { end = i + 1; break; }
      }
    }
    chunks.push(characters.slice(start, end).join(""));
    start = end;
  }
  return chunks;
}

module.exports = { CHAT_MAX_CHARS, MANUAL_MAX_CHARS, characterCount, buildPhotoChatPrompt, splitPhotoText };
