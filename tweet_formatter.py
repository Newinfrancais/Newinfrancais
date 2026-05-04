"""
Formateur de Tweets style Cerfia / AlertInfos / Mediavenir
Inclut : detection langue, traduction EN->FR via MyMemory (gratuit),
         filtre qualite semantique.
Si la traduction echoue, l'article est ignore (jamais de tweet en anglais).
"""

import random
import re
import logging
import requests
from typing import Dict, Optional
from config import MAX_TWEET_LENGTH, AUTO_HASHTAGS

logger = logging.getLogger("bot.formatter")

# ============================================================
# TRADUCTION EN->FR (MyMemory — 50 000 chars/jour avec email)
# ============================================================

MYMEMORY_EMAIL = "newinfrancais@hotmail.com"
MYMEMORY_URL = "https://api.mymemory.translated.net/get"

ENGLISH_STOPWORDS = {
    "the","is","are","was","were","has","have","had","will","would","could",
    "should","this","that","these","those","with","from","into","after",
    "before","about","through","during","without","within","across","behind",
    "as","at","by","for","in","of","on","or","to","and","but","not","it",
    "its","be","do","go","get","set","put","say","see","know","think","come",
    "take","make","give","find","tell","ask","seem","feel","try","leave",
    "call","keep","let","show","hear","play","run","move","live","hold",
    "bring","happen","write","include","continue","also","over","new","first",
    "last","more","most","other","than","then","some","such","when","which",
    "who","how","what","where","why","there","their","they","them","just",
    "been","up","out","can","said","says","while","against","own","same",
    "so","few","both","too","very","here","all","each","him","her","his",
    "she","he","we","you","our","your",
}


def _fit_mymemory_limit(text: str, max_bytes: int = 450) -> str:
    """Tronque le texte pour rester sous la limite MyMemory (~500 bytes)."""
    if not text:
        return ""
    raw = text.strip().encode("utf-8")
    if len(raw) <= max_bytes:
        return text.strip()
    raw = raw[:max_bytes]
    while raw:
        try:
            return raw.decode("utf-8").rsplit(" ", 1)[0].strip()
        except UnicodeDecodeError:
            raw = raw[:-1]
    return ""


def _is_english(text: str) -> bool:
    if not text:
        return False
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    if len(words) < 3:
        return False
    hits = sum(1 for w in words if w in ENGLISH_STOPWORDS)
    return (hits / len(words)) >= 0.18


def _translate_to_french(text: str) -> Optional[str]:
    """Traduit via MyMemory. Retourne None si echec."""
    text = _fit_mymemory_limit(text)
    if not text:
        return None
    try:
        r = requests.get(
            MYMEMORY_URL,
            params={"q": text, "langpair": "en|fr", "de": MYMEMORY_EMAIL},
            timeout=8,
        )
        if r.status_code != 200:
            logger.warning("[MyMemory] HTTP %s", r.status_code)
            return None
        data = r.json()
        translated = (data.get("responseData") or {}).get("translatedText", "").strip()
        if translated and translated.lower() != text.lower():
            logger.info("[MyMemory] %s -> %s", text[:60], translated[:60])
            return translated
        logger.warning("[MyMemory] traduction vide ou identique pour : %s", text[:60])
        return None
    except Exception as e:
        logger.warning("[MyMemory] Erreur : %s", e)
        return None


def maybe_translate(text: str) -> Optional[str]:
    """
    Si le texte est en anglais, tente de le traduire.
    Retourne None si anglais et traduction impossible (article a ignorer).
    Retourne le texte original si deja en francais.
    """
    if not text:
        return text
    if _is_english(text):
        return _translate_to_french(text)
    return text


# ============================================================
# FILTRE QUALITE SEMANTIQUE
# ============================================================

TEASER_PATTERNS = [
    re.compile(r'\btout savoir\b', re.I),
    re.compile(r'\ben savoir plus\b', re.I),
    re.compile(r'\blire la suite\b', re.I),
    re.compile(r'\bvoici pourquoi\b', re.I),
    re.compile(r"\bce qu['\u2019]il faut retenir\b", re.I),
    re.compile(r"\bce que l['\u2019]on sait\b", re.I),
    re.compile(r"\bce qu['\u2019]on sait\b", re.I),
    re.compile(r'\bla suite\s*\|', re.I),
    re.compile(r'\best-il vrai que\b', re.I),
]


def is_quality_ok(title: str, summary: str = "") -> bool:
    for pattern in TEASER_PATTERNS:
        if pattern.search(title):
            return False
    if len((title + summary).strip()) < 40:
        return False
    return True


# ============================================================
# EMOJIS PAR THEME
# ============================================================

EMOJI_MAP = {
    "guerre": "\u26a1", "conflit": "\u26a1", "cessez-le-feu": "\U0001f534",
    "ukraine": "\U0001f1fa\U0001f1e6", "russie": "\U0001f1f7\U0001f1fa",
    "israel": "\U0001f1ee\U0001f1f1", "iran": "\U0001f1ee\U0001f1f7",
    "chine": "\U0001f1e8\U0001f1f3", "etats-unis": "\U0001f1fa\U0001f1f8",
    "usa": "\U0001f1fa\U0001f1f8", "france": "\U0001f1eb\U0001f1f7",
    "europe": "\U0001f1ea\U0001f1fa", "otan": "\U0001f535", "nato": "\U0001f535",
    "alerte": "\U0001f6a8", "urgent": "\U0001f6a8", "breaking": "\U0001f6a8",
    "attentat": "\U0001f6a8", "explosion": "\U0001f6a8", "fusillade": "\U0001f6a8",
    "seisme": "\U0001f30d", "tremblement": "\U0001f30d", "tsunami": "\U0001f30a",
    "ouragan": "\U0001f300", "tempete": "\U0001f300", "inondation": "\U0001f30a",
    "incendie": "\U0001f525",
    "election": "\U0001f5f3\ufe0f", "vote": "\U0001f5f3\ufe0f",
    "parlement": "\U0001f3db\ufe0f", "assemblee": "\U0001f3db\ufe0f",
    "senat": "\U0001f3db\ufe0f", "president": "\U0001f3db\ufe0f",
    "demission": "\u26a1", "premier ministre": "\U0001f3db\ufe0f",
    "bourse": "\U0001f4c9", "krach": "\U0001f4c9", "recession": "\U0001f4c9",
    "inflation": "\U0001f4b0", "bce": "\U0001f3e6", "fed": "\U0001f3e6",
    "croissance": "\U0001f4c8",
    "proces": "\u2696\ufe0f", "condamn": "\u2696\ufe0f", "justice": "\u2696\ufe0f",
    "manifestation": "\U0001f4e2", "greve": "\U0001f4e2", "reforme": "\U0001f4cb",
    "deces": "\U0001f54a\ufe0f", "mort de": "\U0001f54a\ufe0f",
    "decede": "\U0001f54a\ufe0f",
    "champion": "\U0001f3c6", "victoire": "\U0001f3c6", "medaille": "\U0001f3c5",
    "covid": "\U0001f9a0", "vaccin": "\U0001f489", "espace": "\U0001f680",
    "nasa": "\U0001f680",
}

PREFIXES_URGENT = ["\U0001f6a8 ALERTE", "\U0001f534 URGENT", "\u26a1 FLASH", "\U0001f6a8 BREAKING"]
PREFIXES_NORMAL = ["\U0001f4cc INFO", "\U0001f535 ACTU", "\U0001f4f0 INFO", "\u25b6\ufe0f ACTU"]
SEPARATORS = [" \u2014 ", " | ", " - ", " : "]


def _is_urgent(title: str, summary: str, priority: int) -> bool:
    if priority >= 20:
        return True
    words = ["urgent", "breaking", "alerte", "flash", "attentat", "seisme", "explosion", "guerre"]
    return any(w in f"{title} {summary}".lower() for w in words)


def _clean_title(title: str) -> str:
    patterns = [
        r'^(EN DIRECT|DIRECT|LIVE|URGENT|BREAKING|FLASH|ALERTE)\s*[-:,]?\s*',
        r'\s*[-|]\s*(Le Monde|France Info|Les Echos|France 24|BFM|RFI|AFP|Reuters|BBC).*$',
        r'\s*\(.*?(AFP|Reuters|AP)\)$',
    ]
    cleaned = title
    for p in patterns:
        cleaned = re.sub(p, '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _source_tag(source: str) -> str:
    tags = {
        "Le Monde": "Le Monde", "France Info": "France Info",
        "Les Echos": "Les Echos", "France 24": "France 24",
        "RFI": "RFI", "Reuters": "Reuters", "BBC": "BBC",
    }
    for key, tag in tags.items():
        if key.lower() in source.lower():
            return tag
    return source.split(" - ")[0].strip()


def format_tweet(article: Dict) -> Optional[str]:
    raw_title = _clean_title(article["title"])
    title = maybe_translate(raw_title)
    if title is None:
        logger.info("[formatter] Article anglais non traduit, ignore : %s", raw_title[:80])
        return None

    raw_summary = article.get("summary", "")
    summary = maybe_translate(raw_summary) or ""

    priority = article.get("priority", 0)
    source = _source_tag(article["source"])

    if not is_quality_ok(title, summary):
        return None

    urgent = _is_urgent(title, summary, priority)
    prefix = random.choice(PREFIXES_URGENT if urgent else PREFIXES_NORMAL)
    sep = random.choice(SEPARATORS)
    src = f"({source})"

    available = MAX_TWEET_LENGTH - len(f"{prefix}{sep}{src}") - 2
    if len(title) > available:
        title = title[:available - 3].rsplit(' ', 1)[0] + "..."

    tweet = f"{prefix}{sep}{title} {src}"
    for h in AUTO_HASHTAGS:
        if len(tweet) + len(h) + 1 <= MAX_TWEET_LENGTH:
            tweet += f" {h}"
            break
    return tweet


def format_tweet_with_context(article: Dict) -> Optional[str]:
    raw_title = _clean_title(article["title"])
    title = maybe_translate(raw_title)
    if title is None:
        logger.info("[formatter] Article anglais non traduit, ignore : %s", raw_title[:80])
        return None

    raw_summary = article.get("summary", "")
    summary = maybe_translate(raw_summary) or ""

    source = _source_tag(article["source"])
    priority = article.get("priority", 0)

    if not is_quality_ok(title, summary):
        return None

    urgent = _is_urgent(title, summary, priority)
    prefix = random.choice(PREFIXES_URGENT if urgent else PREFIXES_NORMAL)
    sep = random.choice(SEPARATORS)

    context = ""
    if summary and summary.lower() != title.lower():
        first = summary.split('.')[0].strip()
        if first and len(first) > 20:
            context = f"\n\n\u25b8 {first}."

    src = f"\n({source})"
    tweet = f"{prefix}{sep}{title}{context}{src}"

    if len(tweet) > MAX_TWEET_LENGTH:
        tweet = f"{prefix}{sep}{title}{src}"
    if len(tweet) > MAX_TWEET_LENGTH:
        avail = MAX_TWEET_LENGTH - len(f"{prefix}{sep}") - len(src) - 3
        tweet = f"{prefix}{sep}{title[:avail].rsplit(' ', 1)[0]}...{src}"

    return tweet
