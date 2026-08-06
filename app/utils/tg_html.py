"""CKEditor HTML -> Telegram HTML.

Telegram sendMessage(parse_mode=HTML) faqat cheklangan teglarni qo'llaydi:
  <b> <i> <u> <s> <a> <code> <pre> <blockquote> <tg-spoiler>
CKEditor esa <p>, <ul>/<li>, <h1..6>, <br>, <strong>, <em> va h.k. chiqaradi.
Qo'llab-quvvatlanmagan teg yuborilsa Telegram butun xabarni rad etadi (BadRequest).

Shu modul CKEditor chiqishini Telegram tushunadigan xavfsiz HTML'ga o'giradi:
  • ruxsat etilgan formatlar saqlanadi (strong->b, em->i, ...),
  • blok teglar (p, div, h*, li) mos joyda qatorga o'tkaziladi,
  • qolgan barcha teglar tashlanadi (matni saqlanadi),
  • matndagi <, >, & belgilari xavfsiz ekranlanadi.
"""
import html
import re
from html.parser import HTMLParser

TG_LIMIT = 4096  # Telegram bitta xabar uzunligi chegarasi

# CKEditor tegi -> Telegram tegi (ochilish/yopilishda saqlanadi)
_INLINE = {
    "b": "b", "strong": "b",
    "i": "i", "em": "i",
    "u": "u", "ins": "u",
    "s": "s", "strike": "s", "del": "s",
    "code": "code",
    "pre": "pre",
    "blockquote": "blockquote",
}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class _Converter(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.out.append("\n")
        elif tag in _INLINE:
            self.out.append(f"<{_INLINE[tag]}>")
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            self.out.append(f'<a href="{html.escape(href, quote=True)}">')
        elif tag in _HEADINGS:
            self.out.append("<b>")
        elif tag == "li":
            self.out.append("• ")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in _INLINE:
            self.out.append(f"</{_INLINE[tag]}>")
        elif tag == "a":
            self.out.append("</a>")
        elif tag in _HEADINGS:
            self.out.append("</b>\n")
        elif tag in ("p", "div", "li"):
            self.out.append("\n")

    def handle_data(self, data):
        # Matn ichidagi <, >, & — Telegram uchun ekranlanadi
        self.out.append(html.escape(data, quote=False))


def html_to_telegram(raw: str) -> str:
    """CKEditor HTML'ni Telegram-xavfsiz HTML'ga o'giradi va chegaraga sig'diradi."""
    if not raw:
        return ""
    conv = _Converter()
    conv.feed(raw)
    text = "".join(conv.out)
    # Ortiqcha bo'sh qatorlarni yig'ishtiramiz
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > TG_LIMIT:
        # Xavfsiz kesish: teg o'rtasidan kesmaslik uchun oxirgi bo'sh joydan
        cut = text.rfind("\n", 0, TG_LIMIT - 1)
        if cut < TG_LIMIT - 200:
            cut = text.rfind(" ", 0, TG_LIMIT - 1)
        text = text[: cut if cut > 0 else TG_LIMIT - 1].rstrip() + "…"
    return text
