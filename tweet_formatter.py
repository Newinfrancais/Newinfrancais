"""
Formateur de Tweets style Cerfia / AlertInfos / Mediavenir
===========================================================
Logique de construction du tweet :
  1. Le RÉSUMÉ est le corps principal du tweet (il contient le fait brut).
  2. Le TITRE sert de fallback si le résumé est absent ou trop court.
  3. Les titres allusifs sans contenu factuel sont bloqués.
  4. Traduction EN->FR via MyMemory (50 000 chars/jour avec email).
  5. Si la traduction échoue sur un contenu anglais, l'article est ignoré.
"""

import random
import re
import logging
import requests
from typing import Dict, Optional
from config import MAX_TWEET_LENGTH, AUTO_HASHTAGS

logger = logging.getLogger("bot.formatter")

# ============================================================
# TRADUCTION EN->FR (MyMemory)
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
        logger.warning("[MyMemory] traduction vide/identique : %s", text[:60])
        return None
    except Exception as e:
        logger.warning("[MyMemory] Erreur : %s", e)
        return None


def maybe_translate(text: str) -> Optional[str]:
    if not text:
        return text
    if _is_english(text):
        return _translate_to_french(text)
    return text


# ============================================================
# NETTOYAGE DU RÉSUMÉ RSS
# ============================================================

def _clean_summary(summary: str) -> str:
    """
    Supprime les balises HTML résiduelles, les liens, les mentions
    de type 'Lire la suite' et normalise les espaces.
    """
    if not summary:
        return ""
    # Balises HTML
    text = re.sub(r'<[^>]+>', ' ', summary)
    # URLs
    text = re.sub(r'https?://\S+', '', text)
    # Mentions type "Lire la suite", "En savoir plus", "Voir aussi"...
    text = re.sub(
        r'\b(lire la suite|en savoir plus|voir aussi|en direct|retrouvez|suivez|'
        r'abonnez-vous|notre dossier|notre article|toute l\S*info)\b.*',
        '', text, flags=re.IGNORECASE
    )
    # Nettoyer les espaces multiples
    text = re.sub(r'\s+', ' ', text).strip()
    # Supprimer les points de suspension en début
    text = re.sub(r'^[.\s…]+', '', text).strip()
    return text


def _extract_best_sentence(summary: str, max_chars: int = 200) -> str:
    """
    Extrait la première phrase complète et informative du résumé.
    On ignore les phrases trop courtes (< 30 chars) car elles sont
    souvent des artefacts RSS ("AFP.", "Publié le...", etc.).
    """
    summary = _clean_summary(summary)
    if not summary:
        return ""

    sentences = re.split(r'(?<=[.!?])\s+', summary)
    for sent in sentences:
        sent = sent.strip()
        if len(sent) >= 30:
            # Tronquer proprement si trop long
            if len(sent) > max_chars:
                sent = sent[:max_chars].rsplit(' ', 1)[0].rstrip('.,;:') + "…"
            return sent
    # Fallback : retourner le début du résumé tronqué
    if len(summary) > max_chars:
        return summary[:max_chars].rsplit(' ', 1)[0].rstrip('.,;:') + "…"
    return summary


# ============================================================
# FILTRE QUALITÉ — TITRES ALLUSIFS SANS VALEUR INFORMATIVE
# ============================================================

# Patterns qui signalent un titre de presse "accroche" sans fait brut
VAGUE_TITLE_PATTERNS = [
    # Titres interrogatifs ou mystérieux
    re.compile(r'\?$'),
    re.compile(r'\b(pourquoi|comment|qui est|qu[e\']est-ce|faut-il)\b', re.I),
    # Formules teaser
    re.compile(r'\b(tout savoir|en savoir plus|lire la suite|voici|ce qu.il faut|'
               r'ce que l.on sait|ce qu.on sait|la suite|est-il vrai)\b', re.I),
    # Guillemets autour d'un seul mot/expression courte = titre allusif
    re.compile(r'^[^"«»]{0,30}[«\""].{1,25}[»\""][^"«»]{0,30}$'),
]

# Mots-clés de contenu vague (ex: "sous pression", "dans la tourmente")
VAGUE_EXPRESSIONS = [
    "sous pression", "dans la tourmente", "en crise", "sous le feu",
    "au coeur de", "au cœur de", "fait polémique", "fait débat",
    "sème la discorde", "crée la polémique", "le point sur",
    "ce qu'il faut savoir", "meurtrière", "meurtrière ?",
]


def _title_is_vague(title: str) -> bool:
    """
    Retourne True si le titre est trop allusif pour constituer
    une information à lui seul. Dans ce cas, on DOIT avoir un
    résumé de qualité — sinon l'article est ignoré.
    """
    tl = title.lower()
    for pattern in VAGUE_TITLE_PATTERNS:
        if pattern.search(title):
            return True
    for expr in VAGUE_EXPRESSIONS:
        if expr in tl:
            return True
    return False


def is_quality_ok(body: str) -> bool:
    """
    Vérifie que le corps du tweet (résumé ou titre) est suffisamment
    informatif pour être publié.
    """
    if len(body.strip()) < 35:
        return False
    # Rejeter si le corps lui-même est trop vague
    bl = body.lower()
    for expr in VAGUE_EXPRESSIONS:
        if expr in bl:
            return False
    return True


# ============================================================
# CONSTRUCTION DU CORPS DU TWEET
# ============================================================

def _build_body(article: Dict) -> Optional[str]:
    """
    Construit le corps informatif du tweet.

    Priorité :
      1. Première phrase du résumé si >= 30 chars et informative.
      2. Titre nettoyé si le résumé est absent/trop court ET le titre n'est pas vague.
      3. None → article ignoré.
    """
    raw_summary = article.get("summary", "")
    raw_title = _clean_title(article["title"])

    # --- Essai 1 : résumé ---
    if raw_summary:
        best = _extract_best_sentence(raw_summary, max_chars=220)
        if best:
            translated = maybe_translate(best)
            if translated is None:
                logger.info("[formatter] Résumé anglais non traduit, ignore")
                return None
            if is_quality_ok(translated):
                return translated

    # --- Essai 2 : titre (seulement s'il n'est pas vague) ---
    if _title_is_vague(raw_title):
        logger.info("[formatter] Titre vague et résumé inexploitable, ignore : %s", raw_title[:80])
        return None

    translated_title = maybe_translate(raw_title)
    if translated_title is None:
        logger.info("[formatter] Titre anglais non traduit, ignore : %s", raw_title[:80])
        return None

    if not is_quality_ok(translated_title):
        return None

    return translated_title


# ============================================================
# EMOJIS PAR THÈME
# ============================================================

PREFIXES_URGENT = ["\U0001f6a8 ALERTE", "\U0001f534 URGENT", "\u26a1 FLASH", "\U0001f6a8 BREAKING"]
PREFIXES_NORMAL = ["\U0001f4cc INFO", "\U0001f535 ACTU", "\U0001f4f0 INFO", "\u25b6\ufe0f ACTU"]
SEPARATORS = [" \u2014 ", " | ", " - "]


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
        "Les Echos": "Les Échos", "France 24": "France 24",
        "RFI": "RFI", "Reuters": "Reuters", "BBC": "BBC",
    }
    for key, tag in tags.items():
        if key.lower() in source.lower():
            return tag
    return source.split(" - ")[0].strip()


def _is_urgent(title: str, summary: str, priority: int) -> bool:
    if priority >= 20:
        return True
    words = ["urgent", "breaking", "alerte", "flash", "attentat", "seisme", "explosion", "guerre"]
    return any(w in f"{title} {summary}".lower() for w in words)


# ============================================================
# FONCTIONS PUBLIQUES
# ============================================================

def format_tweet(article: Dict) -> Optional[str]:
    """
    Format court : PREFIX — Corps informatif (Source) #Hashtag
    Le corps est le résumé en priorité, le titre en fallback.
    """
    body = _build_body(article)
    if body is None:
        return None

    source = _source_tag(article["source"])
    priority = article.get("priority", 0)
    urgent = _is_urgent(article["title"], article.get("summary", ""), priority)

    prefix = random.choice(PREFIXES_URGENT if urgent else PREFIXES_NORMAL)
    sep = random.choice(SEPARATORS)
    src = f"({source})"

    available = MAX_TWEET_LENGTH - len(f"{prefix}{sep} {src}") - 2
    if len(body) > available:
        body = body[:available - 1].rsplit(' ', 1)[0].rstrip('.,;:') + "…"

    tweet = f"{prefix}{sep}{body} {src}"

    for h in AUTO_HASHTAGS:
        if len(tweet) + len(h) + 1 <= MAX_TWEET_LENGTH:
            tweet += f" {h}"
            break

    return tweet


def format_tweet_with_context(article: Dict) -> Optional[str]:
    """
    Format étendu (priorité haute) : même logique, corps sur deux lignes si de place.
    """
    body = _build_body(article)
    if body is None:
        return None

    source = _source_tag(article["source"])
    priority = article.get("priority", 0)
    urgent = _is_urgent(article["title"], article.get("summary", ""), priority)

    prefix = random.choice(PREFIXES_URGENT if urgent else PREFIXES_NORMAL)
    sep = random.choice(SEPARATORS)
    src = f"\n({source})"

    tweet = f"{prefix}{sep}{body}{src}"

    if len(tweet) > MAX_TWEET_LENGTH:
        avail = MAX_TWEET_LENGTH - len(f"{prefix}{sep}") - len(src) - 2
        body = body[:avail].rsplit(' ', 1)[0].rstrip('.,;:') + "…"
        tweet = f"{prefix}{sep}{body}{src}"

    return tweet
