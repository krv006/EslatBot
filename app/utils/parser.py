"""Erkin yozilgan matndan vaqt va takrorlanishni avtomatik ajratib olish.

Misollar:
    "har kuni soat 8 da dori ichishni eslat"  -> daily, 08:00, "dori ichish"
    "kun ora 21:30 kitob o'qish"              -> every2, 21:30, "kitob o'qish"
    "juma kuni 10 da suzishga borish"          -> weekly(juma), 10:00
    "har oyning 15-kuni 9:00 kvartira puli"    -> monthly(15), 09:00
"""
import re
from datetime import datetime

WEEKDAYS = {
    "dushanba": 0,
    "seshanba": 1,
    "chorshanba": 2,
    "payshanba": 3,
    "juma": 4,
    "shanba": 5,
    "yakshanba": 6,
}

WEEKDAY_NAMES = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba",
                 "Juma", "Shanba", "Yakshanba"]

FREQ_NAMES = {
    "once": "Bir marta",
    "daily": "Har kuni",
    "every2": "Kun ora",
    "weekly": "Haftada bir",
    "monthly": "Oyda bir",
}

MONTH_NAMES = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentyabr", "oktyabr", "noyabr", "dekabr",
]

# Matndan olib tashlanadigan "shovqin" so'zlar
FILLER_RE = re.compile(
    r"\b(meni|menga|iltimos|"
    r"eslatib\s+(?:tur|yubor|qo'y)(?:gin)?|eslatib|eslat(?:gin)?|eslatma)\b",
    re.IGNORECASE,
)

# Turli apostroflarni bir xilga keltirish (STT har xil yozishi mumkin)
_APOSTROPHES = "ʻʼ'‘`´"


def _normalize(s: str) -> str:
    for ch in _APOSTROPHES:
        s = s.replace(ch, "'")
    return s


# So'z bilan aytilgan sonlar: "soat o'nda", "sakkiz yarimda", "o'n beshda"
_NUM_UNITS = {
    "bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "besh": 5,
    "olti": 6, "yetti": 7, "sakkiz": 8, "to'qqiz": 9,
}
_NUM_TENS = {"o'n": 10, "yigirma": 20}

# Uzunroq so'zlar oldinda turishi shart (to'qqiz "uch"dan oldin tekshirilsin)
_WORD_ALT = r"(?:yigirma|to'qqiz|sakkiz|yetti|to'rt|olti|besh|ikki|uch|bir|o'n)"
_WORD_EXPR = rf"{_WORD_ALT}(?:\s+{_WORD_ALT})?"


def _word_expr_to_hour(expr: str) -> int | None:
    """'o'n besh' -> 15, 'sakkiz' -> 8. Soat chegarasidan chiqsa None."""
    total = 0
    for token in expr.split():
        if token in _NUM_TENS:
            total += _NUM_TENS[token]
        elif token in _NUM_UNITS:
            total += _NUM_UNITS[token]
        else:
            return None
    return total if 0 < total <= 23 else None


# Minut so'zlari: "nol nol" -> 0, "qirq besh" -> 45, "o'ttiz" -> 30
_MIN_TENS = {"nol": 0, "o'n": 10, "yigirma": 20, "o'ttiz": 30,
             "qirq": 40, "ellik": 50}
_MIN_ALT = r"(?:ellik|qirq|o'ttiz|yigirma|to'qqiz|sakkiz|yetti|olti|besh|to'rt|uch|ikki|bir|o'n|nol)"
_MIN_EXPR = rf"{_MIN_ALT}(?:\s+{_MIN_ALT})?"
# "u"siz shaklda faqat aniq minut so'zlari (aks holda "o'n besh"=15:00 buziladi)
_MIN_SAFE_EXPR = rf"(?:ellik|qirq|o'ttiz|nol)(?:\s+{_MIN_ALT})?"


def _min_expr_to_minute(expr: str) -> int | None:
    total = 0
    for token in expr.split():
        if token in _MIN_TENS:
            total += _MIN_TENS[token]
        elif token in _NUM_UNITS:
            total += _NUM_UNITS[token]
        else:
            return None
    return total if 0 <= total <= 59 else None


# Vaqt shablonlari: (regex, minut manbai). Tartib muhim — aniqrog'i oldinda.
_TIME_PATTERNS = [
    # 8:30 / 21.15
    (re.compile(r"\b(?P<h>\d{1,2})[:.](?P<m>\d{2})\s*(?:da|de|ga)?\b"), "group"),
    # soat 8 / soat 8 yarim
    (re.compile(r"\bsoat\s+(?P<h>\d{1,2})(?P<half>\s+yarim)?\s*(?:da|de|ga)?\b"), "half"),
    # 8 yarimda
    (re.compile(r"\b(?P<h>\d{1,2})\s+yarim\s*(?:da|de|ga)?\b"), "thirty"),
    # 8 da
    (re.compile(r"\b(?P<h>\d{1,2})\s*(?:da|de)\b"), "zero"),
    # sakkizu nol nolda / to'qqizu qirq beshda / o'n biru yigirmada
    (re.compile(rf"\b(?:soat\s+)?(?P<w>{_WORD_EXPR})[\s-]*(?:u|yu)\b\s+(?P<min>{_MIN_EXPR})\s*(?:da|de|ga)?\b"), "wordmin"),
    # sakkiz o'ttizda / sakkiz nol nolda ("u"siz — faqat aniq minut so'zlari)
    (re.compile(rf"\b(?:soat\s+)?(?P<w>{_WORD_EXPR})\s+(?P<min>{_MIN_SAFE_EXPR})\s*(?:da|de|ga)?\b"), "wordmin"),
    # soat o'nda / soat sakkiz yarim
    (re.compile(rf"\bsoat\s+(?P<w>{_WORD_EXPR})(?P<half>\s+yarim)?\s*(?:da|de|ga)?\b"), "word"),
    # sakkizda / o'n beshda / sakkiz yarimda
    (re.compile(rf"\b(?P<w>{_WORD_EXPR})(?P<half>\s+yarim)?\s*(?:da|de)\b"), "word"),
]


def _find_time(low: str) -> tuple[int, int, int, int] | None:
    """Matndan vaqtni topadi: (soat, minut, boshi, oxiri) yoki None."""
    for pattern, mode in _TIME_PATTERNS:
        m = pattern.search(low)
        if not m:
            continue
        if mode == "wordmin":
            hour = _word_expr_to_hour(m.group("w"))
            minute = _min_expr_to_minute(m.group("min"))
            if hour is None or minute is None:
                continue
        elif mode == "word":
            hour = _word_expr_to_hour(m.group("w"))
            if hour is None:
                continue
            minute = 30 if m.group("half") else 0
        else:
            hour = int(m.group("h"))
            if mode == "group":
                minute = int(m.group("m"))
            elif mode == "thirty":
                minute = 30
            elif mode == "half":
                minute = 30 if m.group("half") else 0
            else:
                minute = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute, m.start(), m.end()
    return None


# Kun bo'lagi: "kechqurun sakkizda" -> 20:00
_EVENING_WORDS = ("kechqurun", "kechasi", "tushdan keyin", "peshindan keyin")
_PERIOD_RE = re.compile(
    r"\b(ertalab|erta bilan|kechqurun|kechasi|tushdan keyin|peshindan keyin|kunduzi)\b"
)


def parse_text(raw: str) -> dict:
    """Matnni tahlil qiladi. Topilmagan qiymatlar None bo'ladi."""
    result = {
        "text": None,
        "freq": None,
        "weekday": None,
        "monthday": None,
        "hour": None,
        "minute": None,
        "once_offset": None,  # 0=bugun, 1=ertaga, 2=indinga
    }
    text = " " + _normalize(raw.strip()) + " "
    low = text.lower()

    # --- Bir martalik: bugun / ertaga / indinga ---
    m = re.search(r"\b(bugun|ertaga|indin(?:ga)?)\b", low)
    if m:
        word = m.group(1)
        result["freq"] = "once"
        if word == "bugun":
            result["once_offset"] = 0
        elif word == "ertaga":
            result["once_offset"] = 1
        else:
            result["once_offset"] = 2
        text = text[:m.start()] + " " + text[m.end():]
        low = text.lower()

    # --- Takrorlanish turi ---
    m = re.search(r"\bkun\s*ora\b|\bkunora\b|\bhar\s+2\s+kun(da)?\b", low)
    if m:
        result["freq"] = "every2"
        text = text[:m.start()] + " " + text[m.end():]
        low = text.lower()

    if result["freq"] is None:
        m = re.search(r"\bhar\s+kuni?\b|\bkuniga\b|\bkunda\b", low)
        if m:
            result["freq"] = "daily"
            text = text[:m.start()] + " " + text[m.end():]
            low = text.lower()

    # Hafta kuni nomi (masalan "juma kuni" yoki "har juma")
    if result["freq"] is None:
        for name, idx in WEEKDAYS.items():
            m = re.search(rf"\b(har\s+)?{name}(\s+kuni)?\b", low)
            if m:
                result["freq"] = "weekly"
                result["weekday"] = idx
                text = text[:m.start()] + " " + text[m.end():]
                low = text.lower()
                break

    if result["freq"] is None:
        m = re.search(r"\bhar\s+hafta(da)?\b|\bhaftada\s+bir\b|\bhaftasiga\b", low)
        if m:
            result["freq"] = "weekly"
            text = text[:m.start()] + " " + text[m.end():]
            low = text.lower()

    # Oylik: "har oyning 15-kuni", "oyda bir", "har oy"
    m = re.search(
        r"\b(har\s+oy(ning)?|oyda\s+bir|oyiga)\b(\s+(?P<day>\d{1,2})\s*-?\s*(kuni|sanasi(da)?|chislo(da)?)?)?",
        low,
    )
    if m and result["freq"] is None:
        result["freq"] = "monthly"
        if m.group("day"):
            day = int(m.group("day"))
            if 1 <= day <= 31:
                result["monthday"] = day
        text = text[:m.start()] + " " + text[m.end():]
        low = text.lower()

    # "15-kuni" alohida kelsa (monthly aniqlangandan keyin)
    if result["freq"] == "monthly" and result["monthday"] is None:
        m = re.search(r"\b(?P<day>\d{1,2})\s*-?\s*(kuni|sanasi(da)?|chislo(da)?)\b", low)
        if m:
            day = int(m.group("day"))
            if 1 <= day <= 31:
                result["monthday"] = day
                text = text[:m.start()] + " " + text[m.end():]
                low = text.lower()

    # --- Vaqt (raqam yoki so'z bilan: "8:30", "soat o'nda", "sakkiz yarimda") ---
    found = _find_time(low)
    if found:
        hour, minute, start, end = found
        result["hour"] = hour
        result["minute"] = minute
        text = text[:start] + " " + text[end:]
        low = text.lower()

        # Kun bo'lagi: "kechqurun sakkizda" -> 20:00, "ertalab 8 da" -> 08:00
        pm = _PERIOD_RE.search(low)
        if pm:
            period = pm.group(1)
            if period in _EVENING_WORDS and result["hour"] < 12:
                result["hour"] += 12
            elif period == "kunduzi" and result["hour"] <= 5:
                result["hour"] += 12
            text = text[:pm.start()] + " " + text[pm.end():]

    # --- Eslatma matnini tozalash ---
    cleaned = FILLER_RE.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    if cleaned:
        result["text"] = cleaned
    return result


def parse_time(raw: str) -> tuple[int, int] | None:
    """Alohida yuborilgan vaqtni o'qiydi: '09:00', '9.30', '21', 'soat 8', "o'nda"."""
    s = _normalize(raw.strip().lower()).replace("soat", "").strip()
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return h, mi
        return None
    m = re.fullmatch(r"(\d{1,2})(\s+yarim)?\s*(da|de|ga)?", s)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            return h, 30 if m.group(2) else 0
        return None
    # So'z bilan: "o'nda", "sakkiz yarim", "o'n besh"
    m = re.fullmatch(rf"({_WORD_EXPR})(\s+yarim)?\s*(da|de|ga)?", s)
    if m:
        h = _word_expr_to_hour(m.group(1))
        if h is not None:
            return h, 30 if m.group(2) else 0
    return None


def describe(freq: str, weekday: int | None, monthday: int | None,
             hour: int, minute: int, start_date: str | None = None) -> str:
    """Insonga tushunarli tavsif: 'Har juma, soat 09:00'."""
    t = f"{hour:02d}:{minute:02d}"
    if freq == "once":
        if start_date:
            dt = datetime.fromisoformat(start_date)
            return (f"Bir marta: {dt.day}-{MONTH_NAMES[dt.month - 1]} "
                    f"({WEEKDAY_NAMES[dt.weekday()].lower()}), soat {t}")
        return f"Bir marta, soat {t}"
    if freq == "daily":
        return f"Har kuni, soat {t}"
    if freq == "every2":
        return f"Kun ora, soat {t}"
    if freq == "weekly":
        day = WEEKDAY_NAMES[weekday] if weekday is not None else "?"
        return f"Har {day.lower()}, soat {t}"
    if freq == "monthly":
        return f"Har oyning {monthday}-kuni, soat {t}"
    return t
