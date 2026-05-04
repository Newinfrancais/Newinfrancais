"""
Formateur de Tweets style Cerfia / AlertInfos / Mediavenir
Inclut : détection langue, traduction EN→FR via LibreTranslate (gratuit),
         filtre qualité sémantique.
"""

import random
import re
import logging
import requests
from typing import Dict, Optional
from config import MAX_TWEET_LENGTH, AUTO_HASHTAGS

logger = logging.getLogger("bot.formatter")

# ============================================================
# TRADUCTION EN→FR (LibreTranslate — instances publiques gratuites)
# ============================================================

LIBRETRANSLATE_FALLBACKS = [
    "https://translate.argosopentech.com/translate",
    "https://libretranslate.de/translate",
    "https://libretranslate.com/translate",
]

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

def _is_english(text: str) -> bool:
    if not text:
        return False
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    if len(words) < 3:
        return False
    hits = sum(1 for w in words if w in ENGLISH_STOPWORDS)
    return (hits / len(words)) >= 0.18

def _translate_to_french(text: str) -> Optional[str]:
    payload = {"q": text, "source": "en", "target": "fr", "format": "text"}
    for url in LIBRETRANSLATE_FALLBACKS:
        try:
            r = requests.post(url, json=payload, timeout=8)
            if r.status_code == 200:
                translated = r.json().get("translatedText", "").strip()
                if translated and translated.lower() != text.lower():
                    logger.info(f"Traduit : {text[:60]} → {translated[:60]}")
                    return translated
        except Exception:
            continue
    logger.warning(f"Traduction échouée pour : {text[:60]}")
    return None

def maybe_translate(text: str) -> str:
    if _is_english(text):
        translated = _translate_to_french(text)
        return translated if translated else text
    return text


# ============================================================
# FILTRE QUALITÉ SÉMANTIQUE
# ============================================================

TEASER_PATTERNS = [
    re.compile(r'\btout savoir\b', re.I),
    re.compile(r'\ben savoir plus\b', re.I),
    re.compile(r'\blire la suite\b', re.I),
    re.compile(r'\bvoici pourquoi\b', re.I),
    re.compile(r'\bce qu[\'']il faut retenir\b', re.I),
    re.compile(r'\bce que l[\'']on sait\b', re.I),
    re.compile(r'\bce qu[\'']on sait\b', re.I),
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
# EMOJIS PAR THÈME
# ============================================================

EMOJI_MAP = {
    "guerre": "⚡", "conflit": "⚡", "cessez-le-feu": "🔴",
    "ukraine": "🇺🇦", "russie": "🇷🇺", "israel": "🇮🇱", "iran": "🇮🇷",
    "chine": "🇨🇳", "états-unis": "🇺🇸", "usa": "🇺🇸", "france": "🇫🇷",
    "europe": "🇪🇺", "otan": "🔵", "nato": "🔵",
    "alerte": "🚨", "urgent": "🚨", "breaking": "🚨",
    "attentat": "🚨", "explosion": "🚨", "fusillade": "🚨",
    "séisme": "🌍", "tremblement": "🌍", "tsunami": "🌊",
    "ouragan": "🌀", "tempête": "🌀", "inondation": "🌊", "incendie": "🔥",
    "élection": "🗳️", "vote": "🗳️", "parlement": "🏛️",
    "assemblée": "🏛️", "sénat": "🏛️", "président": "🏛️",
    "démission": "⚡", "premier ministre": "🏛️",
    "bourse": "📉", "krach": "📉", "récession": "📉",
    "inflation": "💰", "bce": "🏦", "fed": "🏦", "croissance": "📈",
    "procès": "⚖️", "condamn": "⚖️", "justice": "⚖️",
    "manifestation": "📢", "grève": "📢", "réforme": "📋",
    "décès": "🕊️", "mort de": "🕊️", "décédé": "🕊️",
    "champion": "🏆", "victoire": "🏆", "médaille": "🏅",
    "covid": "🦠", "vaccin": "💉", "espace": "🚀", "nasa": "🚀",
}

PREFIXES_URGENT = ["🚨 ALERTE", "🔴 URGENT", "⚡ FLASH", "🚨 BREAKING"]
PREFIXES_NORMAL = ["📌 INFO", "🔵 ACTU", "📰 INFO", "▶️ ACTU"]
SEPARATORS = [" — ", " | ", " - ", " : "]


def _is_urgent(title: str, summary: str, priority: int) -> bool:
    if priority >= 20:
        return True
    words = ["urgent", "breaking", "alerte", "flash", "attentat", "séisme", "explosion", "guerre"]
    return any(w in f"{title} {summary}".lower() for w in words)


def _clean_title(title: str) -> str:
    patterns = [
        r'^(EN DIRECT|DIRECT|LIVE|URGENT|BREAKING|FLASH|ALERTE)\s*[-–:,]?\s*',
        r'\s*[-–|]\s*(Le Monde|France Info|Les Échos|France 24|BFM|RFI|AFP|Reuters|BBC).*$',
        r'\s*\(.*?(AFP|Reuters|AP)\)$',
    ]
    cleaned = title
    for p in patterns:
        cleaned = re.sub(p, '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _source_tag(source: str) -> str:
    tags = {
        "Le Monde": "Le Monde", "France Info": "France Info",
        "Les Échos": "Les Échos", "France 24": "France 24",
        "RFI": "RFI", "Reuters": "Reuters", "BBC": "BBC",
    }
    for key, tag in tags.items():
        if key.lower() in source.lower():
            return tag
    return source.split(" - ")[0].strip()


def format_tweet(article: Dict) -> Optional[str]:
    title = maybe_translate(_clean_title(article["title"]))
    summary = maybe_translate(article.get("summary", ""))
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
    title = maybe_translate(_clean_title(article["title"]))
    summary = maybe_translate(article.get("summary", ""))
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
            context = f"\n\n▸ {first}."

    src = f"\n({source})"
    tweet = f"{prefix}{sep}{title}{context}{src}"

    if len(tweet) > MAX_TWEET_LENGTH:
        tweet = f"{prefix}{sep}{title}{src}"
    if len(tweet) > MAX_TWEET_LENGTH:
        avail = MAX_TWEET_LENGTH - len(f"{prefix}{sep}") - len(src) - 3
        tweet = f"{prefix}{sep}{title[:avail].rsplit(' ', 1)[0]}...{src}"

    return tweet
