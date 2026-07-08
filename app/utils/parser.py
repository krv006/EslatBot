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
    r"\b(meni|menga|iltimos|eslatib\s+tur(gin)?|eslat(gin)?|eslatma)\b",
    re.IGNORECASE,
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
    text = " " + raw.strip() + " "
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

    # --- Vaqt ---
    # 1) "8:30", "21.15" ko'rinishida
    m = re.search(r"\b(?P<h>\d{1,2})[:.](?P<m>\d{2})\s*(da|de)?\b", low)
    if m and 0 <= int(m.group("h")) <= 23 and 0 <= int(m.group("m")) <= 59:
        result["hour"] = int(m.group("h"))
        result["minute"] = int(m.group("m"))
        text = text[:m.start()] + " " + text[m.end():]
        low = text.lower()
    else:
        # 2) "soat 8 da" / "soat 8"
        m = re.search(r"\bsoat\s+(?P<h>\d{1,2})\s*(da|de|ga)?\b", low)
        if m and 0 <= int(m.group("h")) <= 23:
            result["hour"] = int(m.group("h"))
            result["minute"] = 0
            text = text[:m.start()] + " " + text[m.end():]
            low = text.lower()
        else:
            # 3) "8 da" / "8da"
            m = re.search(r"\b(?P<h>\d{1,2})\s*(da|de)\b", low)
            if m and 0 <= int(m.group("h")) <= 23:
                result["hour"] = int(m.group("h"))
                result["minute"] = 0
                text = text[:m.start()] + " " + text[m.end():]

    # --- Eslatma matnini tozalash ---
    cleaned = FILLER_RE.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    if cleaned:
        result["text"] = cleaned
    return result


def parse_time(raw: str) -> tuple[int, int] | None:
    """Alohida yuborilgan vaqtni o'qiydi: '09:00', '9.30', '21', 'soat 8'."""
    s = raw.strip().lower().replace("soat", "").strip()
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return h, mi
        return None
    m = re.fullmatch(r"(\d{1,2})\s*(da|de)?", s)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            return h, 0
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
