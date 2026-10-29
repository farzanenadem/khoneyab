import html
import re

ARABIC_TO_PERSIAN = {
    "ي": "ی",
    "ك": "ک",
    "ة": "ه",
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ٱ": "ا",
    "ؤ": "و",
    "ئ": "ی",
    "ء": "",
}

DIACRITICS_RE = re.compile(r"[ًٌٍَُِّْٰ]")
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
INVISIBLE_RE = re.compile(r"[‍‎‏﻿‪-‮⁦-⁩]")
# Keeps `# + . -` so that c#, c++, node.js and front-end survive.
PUNCTUATION_RE = re.compile(r"[،؛؟٪٫٬۔,;:!?()\[\]{}\"'«»/\\|…*•=<>~^`@$%&_]")
TOKEN_RE =re.compile(r"[a-z0-9#+]+(?:[.\-][a-z0-9#+]+)*|[؀-ۿ]+")

PERSIAN_STOPWORDS = {
    "و", "در", "به", "از", "که", "با", "را", "این", "آن", "ان", "برای", "یا", "تا",
    "هم", "های", "ها", "هایی", "می", "است", "هست", "هستم", "باشد", "باشم", "بشم",
    "یک", "یه", "دنبال", "هستیم", "مرتبط", "ترجیحا", "ترجیح", "صورت", "بصورت",
    "حوزه", "زمینه", "موقعیت", "شغلی", "شغل", "کار", "میخوام", "میخواهم", "خواهم",
    "دارم", "دارد", "داشته", "بر", "اساس", "مثل", "مانند", "نیز", "ولی", "اما",
    "بلد", "کنم", "کند", "کردن", "شود", "the", "and", "or", "of", "in", "a", "an",
    "to", "for", "with", "خانم", "اقا", "استخدام",
    # conversational words common in chat messages
    "من", "تو", "ما", "شما", "او", "چه", "چی", "کدام", "کدوم", "برایم", "برام", "برای",
    "مناسب", "اگهی", "اگهیهایی", "پیشنهاد", "بده", "بدید", "لطفا", "سلام", "میشه",
    "دو", "سه", "چهار", "پنج", "یکی", "چند", "خوب", "خیلی", "هم", "دیگه", "دیگر",
}


def normalize_persian(text: str) -> str:
    """Unify Arabic letter variants with Persian ones and drop diacritics."""
    for ar, fa in ARABIC_TO_PERSIAN.items():
        text = text.replace(ar, fa)

    text = DIACRITICS_RE.sub("", text)

    return text


def normalize_for_search(text: str) -> str:
    """Normalization applied identically to documents and queries before matching."""
    if not text:
        return ""
    text = normalize_persian(str(text))
    text = text.translate(DIGITS)
    text = INVISIBLE_RE.sub("", text)
    text = text.replace("‌", " ").replace("ـ", "")
    text = PUNCTUATION_RE.sub(" ", text)
    text = text.lower()
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str, drop_stopwords: bool = True) -> list[str]:
    tokens = TOKEN_RE.findall(normalize_for_search(text))
    if drop_stopwords:
        tokens = [t for t in tokens if t not in PERSIAN_STOPWORDS and len(t) > 1]
    return tokens


def html_to_text(raw_html: str) -> str:
    """Convert a job description HTML fragment to plain text, one item per line."""
    if not raw_html:
        return ""
    text = re.sub(r"<\s*(br|/p|/li|/div|/h\d|/ul|/ol)\s*/?>", "\n", raw_html, flags=re.I)
    text = re.sub(r"<\s*li[^>]*>", "• ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
