"""Local preparation guidance; no dispatch, contact registry or medical diagnosis."""

from backend.app.domain.enums import LanguageCode

_STEPS = {
    "ru": [
        "Если можете сделать это безопасно, отойдите от непосредственной опасности.",
        "Попросите человека рядом помочь связаться с местной экстренной службой "
        "или ответственным сотрудником.",
        "Сообщите место и что произошло. При непосредственной опасности "
        "не ждите ответа этого приложения.",
    ],
    "kk": [
        "Қауіпсіз болса, тікелей қауіптен алыстаңыз.",
        "Жаныңыздағы адамнан жергілікті жедел қызметпен немесе жауапты "
        "қызметкермен байланысуға көмектесуін сұраңыз.",
        "Қайда екеніңізді және не болғанын айтыңыз. Тікелей қауіп болса, "
        "осы қолданбаның жауабын күтпеңіз.",
    ],
    "zh": [
        "如果能够安全移动，请远离眼前的危险。",
        "请身边的人帮助联系当地应急服务或相关工作人员。",
        "说明您所在的位置和发生的情况。如有紧迫危险，请勿等待本应用回复。",
    ],
    "en": [
        "Move to a safe place away from immediate danger if you can do so safely.",
        "Ask someone nearby to help contact local emergency services or the responsible staff.",
        "Explain your location and what happened. Do not wait for this app "
        "when there is immediate danger.",
    ],
}
_DISCLAIMER = {
    "ru": "Приложение не является официальной службой, юристом или врачом. "
    "Оно не вызывает экстренную помощь. Подтвердите необходимые действия "
    "в соответствующей службе.",
    "kk": "Қолданба ресми қызмет, заңгер немесе дәрігер емес. Ол жедел көмек "
    "шақырмайды. Қажетті әрекеттерді тиісті қызметтен нақтылаңыз.",
    "zh": "本应用不是官方机构、律师或医生，也不会呼叫应急救援。请向相关机构确认所需行动。",
    "en": "This app is not an official authority, lawyer, or doctor. "
    "It does not dispatch emergency help. Confirm required actions "
    "with the appropriate service.",
}


def emergency_copy(language: LanguageCode) -> tuple[list[str], str]:
    key = language.value if language.value in _STEPS else "en"
    return list(_STEPS[key]), _DISCLAIMER[key]


def emergency_specific_step(language: LanguageCode, emergency_type: str) -> str | None:
    values = {
        "lost_phone": (
            "Проверьте официальные функции блокировки устройства и аккаунтов; "
            "не передавайте пароли и коды посторонним.",
            "Құрылғы мен аккаунттарды бұғаттаудың ресми функцияларын тексеріңіз; "
            "құпиясөздер мен кодтарды бөтен адамға бермеңіз.",
            "查看设备和账户的官方锁定功能，不要向陌生人提供密码或验证码。",
            "Check official device and account lock functions; "
            "do not give passwords or verification codes to strangers.",
        ),
        "document_problem": (
            "Обратитесь за официальной поддержкой в службу, выдавшую документ, "
            "или соответствующее консульство.",
            "Құжат берген қызметтен немесе тиісті консулдықтан ресми көмек сұраңыз.",
            "请联系签发证件的机构或相关领事机构，寻求官方帮助。",
            "Contact the issuing service or appropriate consulate for official support.",
        ),
    }
    if emergency_type not in values:
        return None
    languages = ("ru", "kk", "zh", "en")
    return values[emergency_type][
        languages.index(language.value) if language.value in languages else 3
    ]
