"""
Formateur de Tweets style Cerfia / AlertInfos / Mediavenir
=============================================================
Transforme un article en tweet court, percutant, avec emojis et source.
"""

import random
import re
from typing import Dict
from config import MAX_TWEET_LENGTH, AUTO_HASHTAGS

# ============================================================
# EMOJIS PAR THÈME
# ============================================================

EMOJI_MAP = {
    # Géopolitique
    "guerre": "⚡", "conflit": "⚡", "cessez-le-feu": "🔴",
    "ukraine": "🇺🇦", "russie": "🇷🇺", "israel": "🇮🇱", "iran": "🇮🇷",
    "chine": "🇨🇳", "états-unis": "🇺🇸", "usa": "🇺🇸", "france": "🇫🇷",
    "europe": "🇪🇺", "otan": "🔵", "nato": "🔵",
    # Urgence
    "alerte": "🚨", "urgent": "🚨", "breaking": "🚨",
    "attentat": "🚨", "explosion": "🚨", "fusillade": "🚨",
    # Catastrophes
    "séisme": "🌍", "tremblement": "🌍", "tsunami": "🌊",
    "ouragan": "🌀", "tempête": "🌀", "inondation": "🌊", "incendie": "🔥",
    # Politique
    "élection": "🗳️", "vote": "🗳️", "parlement": "🏛️",
    "assemblée": "🏛️", "sénat": "🏛️", "président": "🏛️",
    "démission": "⚡", "premier ministre": "🏛️",
    # Économie
    "bourse": "📉", "krach": "📉", "récession": "📉",
    "inflation": "💰", "bce": "🏦", "fed": "🏦", "croissance": "📈",
    # Justice
    "procès": "⚖️", "condamn": "⚖️", "justice": "⚖️",
    "manifestation": "📢", "grève": "📢", "réforme": "📋",
    # Décès
    "décès": "🕊️", "mort de": "🕊️", "décédé": "🕊️",
    # Sport
    "champion": "🏆", "victoire": "🏆", "médaille": "🏅",
    # Autre
    "covid": "🦠", "vaccin": "💉", "espace": "🚀", "nasa": "🚀",
}

PREFIXES_URGENT = ["🚨 ALERTE", "🔴 URGENT", "⚡ FLASH", "🚨 BREAKING"]
PREFIXES_NORMAL = ["📌 INFO", "🔵 ACTU", "📰 INFO", "▶️ ACTU"]
SEPARATORS = [" — ", " | ", " - ", " : "]


def _is_urgent(title: str, summary: str, priority: int) -> bool:
    if priority >= 20:
        return True
    words = ["urgent", "breaking", "alerte", "flash", "attentat", "séisme", "explosion", "guerre"]
    text = f"{title} {summary}".lower()
    return any(w in text for w in words)


def _clean_title(title: str) -> str:
    patterns = [
        r'^(EN DIRECT|DIRECT|LIVE|URGENT|BREAKING|FLASH|ALERTE)\s*[-–:,]?\s*',
        r'^(EN DIRECT|DIRECT)\s*[-–]\s*',
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


def format_tweet(article: Dict) -> str:
    """
    Formate un article en tweet style Cerfia/AlertInfos.

    Exemples de sortie :
        🚨 ALERTE — Titre de l'actu (Le Monde) #Actu
        📌 INFO | Titre de l'actu (France 24) #Info
    """
    title = _clean_title(article["title"])
    summary = article.get("summary", "")
    priority = article.get("priority", 0)
    source = _source_tag(article["source"])
    urgent = _is_urgent(title, summary, priority)

    prefix = random.choice(PREFIXES_URGENT if urgent else PREFIXES_NORMAL)
    sep = random.choice(SEPARATORS)
    src = f"({source})"

    # Espace dispo pour le titre
    shell = f"{prefix}{sep}{src}"
    available = MAX_TWEET_LENGTH - len(shell) - 2

    if len(title) > available:
        title = title[:available - 3].rsplit(' ', 1)[0] + "..."

    tweet = f"{prefix}{sep}{title} {src}"

    # Ajouter un hashtag si place
    for h in AUTO_HASHTAGS:
        if len(tweet) + len(h) + 1 <= MAX_TWEET_LENGTH:
            tweet += f" {h}"
            break

    return tweet


def format_tweet_with_context(article: Dict) -> str:
    """
    Version avec contexte pour les actus urgentes / importantes.

    Exemple :
        🚨 ALERTE — Titre principal

        ▸ Contexte résumé en une phrase.
        (Le Monde)
    """
    title = _clean_title(article["title"])
    summary = article.get("summary", "")
    source = _source_tag(article["source"])
    priority = article.get("priority", 0)
    urgent = _is_urgent(title, summary, priority)

    prefix = random.choice(PREFIXES_URGENT if urgent else PREFIXES_NORMAL)
    sep = random.choice(SEPARATORS)

    line1 = f"{prefix}{sep}{title}"

    context = ""
    if summary and summary.lower() != title.lower():
        first = summary.split('.')[0].strip()
        if first and len(first) > 20:
            context = f"\n\n▸ {first}."

    src = f"\n({source})"
    tweet = f"{line1}{context}{src}"

    # Tronquer si trop long
    if len(tweet) > MAX_TWEET_LENGTH:
        tweet = f"{line1}{src}"
    if len(tweet) > MAX_TWEET_LENGTH:
        avail = MAX_TWEET_LENGTH - len(f"{prefix}{sep}") - len(src) - 3
        title_short = title[:avail].rsplit(' ', 1)[0] + "..."
        tweet = f"{prefix}{sep}{title_short}{src}"

    return tweet
