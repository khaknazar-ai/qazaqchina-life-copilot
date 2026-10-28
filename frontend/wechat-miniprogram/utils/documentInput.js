// Reviewable excerpts preserve every character. A boundary may split a clause;
// the UI therefore warns that other parts can contain conditions/negations.
const MAX_TEXT_FILE_BYTES = 256 * 1024;
const MAX_DOCUMENT_CHARS = 12000;
const TEXT_FILE_EXTENSIONS = [".txt", ".md", ".csv"];

function inputError(code) {
  const error = new Error(code);
  error.code = code;
  return error;
}

function readTextFile(file, fileSystem) {
  const name = String((file && file.name) || "").split(/[\\/]/).pop().trim();
  const extension = name.slice(name.lastIndexOf(".")).toLowerCase();
  const path = file && (file.path || file.tempFilePath);
  const size = Number(file && file.size);
  if (!name || !TEXT_FILE_EXTENSIONS.includes(extension)) {
    return Promise.reject(inputError("unsupported_file_type"));
  }
  if (!Number.isFinite(size) || size <= 0 || size > MAX_TEXT_FILE_BYTES) {
    return Promise.reject(inputError(size > MAX_TEXT_FILE_BYTES ? "file_too_large" : "empty_file"));
  }
  if (!path || !fileSystem || typeof fileSystem.readFile !== "function") {
    return Promise.reject(inputError("file_read_failed"));
  }
  return new Promise((resolve, reject) => {
    fileSystem.readFile({
      filePath: path,
      encoding: "utf8",
      success(result) {
        const text = String((result && result.data) || "")
          .replace(/^\uFEFF/, "")
          .replace(/\r\n?/g, "\n");
        if (!text.trim()) {
          reject(inputError("empty_file"));
          return;
        }
        if (text.includes("\u0000") || text.includes("\uFFFD")) {
          reject(inputError("file_read_failed"));
          return;
        }
        if (Array.from(text).length > MAX_DOCUMENT_CHARS) {
          reject(inputError("file_too_long"));
          return;
        }
        resolve({ title: name, text });
      },
      fail() {
        reject(inputError("file_read_failed"));
      }
    });
  });
}

function splitForReview(value) {
  const characters = Array.from(String(value || ""));
  const parts = [];
  let current = [];
  let passages = 0;
  for (const character of characters) {
    current.push(character);
    if (/[。！？\n]/.test(character)) passages += 1;
    if (current.length >= 1200 || passages >= 12) {
      parts.push(current.join("")); current = []; passages = 0;
    }
  }
  if (current.length) parts.push(current.join(""));
  return parts;
}
module.exports = {
  MAX_TEXT_FILE_BYTES,
  MAX_DOCUMENT_CHARS,
  TEXT_FILE_EXTENSIONS,
  readTextFile,
  splitForReview
};
