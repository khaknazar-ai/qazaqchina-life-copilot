"""Shared conservative patterns for outbound text, memory, OCR and public content."""

import re

# Preserve entire address values, including abbreviated house/apartment labels.
# A longer redaction is preferable to leaving the street or apartment behind.
ADDRESS_PATTERNS = [
    re.compile(
        r"(?i)(?:\b(?:address|адрес(?:ім|им)?|мекенжай(?:ым|ы)?)\b|住址|地址)"
        r"\s*[:：=]\s*[^\n;!?。]{1,240}"
    ),
    re.compile(
        r"(?i)(?<!\w)(?:улица|ул\.|проспект|пр-т|переулок|пер\.|"
        r"набережная|наб\.|микрорайон|мкр\.)\s*"
        r"(?=[^\n;!?。]{0,200}\d)[^\n;!?。]{1,220}"
    ),
    re.compile(
        r"(?i)(?<!\w)[А-ЯЁӘҒҚҢӨҰҮҺІ][А-ЯЁӘҒҚҢӨҰҮҺІа-яёәғқңөұүһі .'-]{0,60}"
        r"\s+(?:көшесі|көш\.|даңғылы|шағынауданы)"
        r"(?=[^\n;!?。]{0,140}\d)[^\n;!?。]{1,160}"
    ),
    re.compile(
        r"(?i)\b\d{1,5}\s+[A-Z][A-Za-z0-9.' -]{2,60}\s+"
        r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Boulevard|Blvd|District|Building|Room)"
        r"\b(?:[ ,]+(?:apt\.?|apartment|unit|room|flat|#)\s*[\w-]+)?"
    ),
    re.compile(
        r"[\u4e00-\u9fffA-Za-z0-9]{2,60}(?:路|街|大道|巷)\s*\d{1,5}\s*号?"
        r"(?:[\u4e00-\u9fff\d\s-]{0,30}(?:室|楼|单元))?"
    ),
]

SECRET_PATTERNS = [
    re.compile(
        r"(?i)(?:\b(?:api[_ -]?key|secret|token|password|пароль|токен|"
        r"құпиясөз|құпия\s+сөз)\b|密码|密钥)\s*[:：=]\s*[^\s,;]{3,}"
    ),
    re.compile(r"\b(?:sk|dk|rk|pk|xoxb|xoxp)-[A-Za-z0-9_=-]{8,}\b"),
]

LABELED_ID_PATTERN = re.compile(
    r"(?i)(?:\b(?:passport|паспорт|төлқұжат|iin|иин|жсн)\b|护照号|身份证号)"
    r"\s*(?:number|номер|нөмірі|№|no\.?)?\s*[:：=#]?\s*"
    r"(?:[A-ZА-Я]{1,3}[ -]*)?(?:\d[ -]?){5,17}\d(?![A-ZА-Я0-9-])"
)

PRIVATE_CONTACT_PATTERN = re.compile(
    r"(?i)(?:\b(?:wechat|weixin|telegram)\b|微信号)\s*[:：=]\s*[@\w.+-]{3,80}"
)

LABELED_PHONE_PATTERN = re.compile(
    r"(?i)(?:\b(?:phone|telephone|mobile|телефон|телефон\s+нөмірі)\b|电话|手机号)"
    r"\s*[:：=]\s*\+?(?:\d[\s().-]?){7,}\d(?!\d)"
)
