"""
Module de hashtags tendance France
====================================
Recupere les tendances Twitter France gratuitement
et les matche avec le contenu des tweets pour ajouter
les hashtags les plus pertinents.
"""

import logging
import re
import requests

logger = logging.getLogger("bot.trending")

TRENDS_URL = "https://getdaytrends.com/france/"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Cache des tendances (evite de requeter a chaque tweet)
_cache = {"trends": [], "fetched": False}


def fetch_trends():
    """Recupere les tendances Twitter France actuelles."""
    if _cache["fetched"]:
        return _cache["trends"]

    try:
        response = requests.get(TRENDS_URL, headers=HTTP_HEADERS, timeout=10)

        if response.status_code != 200:
            logger.warning(f"Impossible de recuperer les tendances : HTTP {response.status_code}")
            return []

        html = response.text

        # Extraire les tendances depuis le HTML
        trends = []

        # Methode 1 : liens vers /france/trend/
        found = re.findall(r'<a[^>]*href="/france/trend/[^"]*"[^>]*>([^<]+)</a>', html)
        trends.extend(found)

        # Methode 2 : hashtags
        hashtags = re.findall(r'(#\w+)', html)
        trends.extend(hashtags)

        # Methode 3 : balises tag
        tags = re.findall(r'class="tag"[^>]*>([^<]+)</a>', html)
        trends.extend(tags)

        # Deduplication en gardant l'ordre
        seen = set()
        unique_trends = []
        for t in trends:
            t_clean = t.strip()
            t_lower = t_clean.lower()
            if t_lower not in seen and len(t_clean) > 1:
                seen.add(t_lower)
                unique_trends.append(t_clean)

        _cache["trends"] = unique_trends
        _cache["fetched"] = True

        logger.info(f"{len(unique_trends)} tendances France recuperees")
        return unique_trends

    except Exception as e:
        logger.warning(f"Erreur recuperation tendances : {e}")
        return []


def _normalize(text):
    """Normalise un texte pour la comparaison."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def find_matching_hashtags(tweet_text, article_title, article_summary="", max_hashtags=2):
    """
    Trouve les hashtags tendance pertinents pour un tweet.

    Compare les tendances actuelles avec le contenu du tweet/article
    et retourne les hashtags les plus pertinents.

    Args:
        tweet_text: Le texte du tweet
        article_title: Le titre de l'article
        article_summary: Le resume de l'article
        max_hashtags: Nombre max de hashtags a ajouter

    Returns:
        Liste de hashtags (avec le #) pertinents
    """
    trends = fetch_trends()
    if not trends:
        return []

    # Texte complet a analyser
    full_text = _normalize(f"{tweet_text} {article_title} {article_summary}")
    text_words = set(full_text.split())

    matches = []

    for trend in trends:
        trend_clean = trend.strip()

        # Si la tendance est un hashtag, comparer sans le #
        trend_compare = trend_clean.lstrip('#').lower()
        trend_words = set(_normalize(trend_compare).split())

        # Verifier si la tendance apparait dans le texte
        matched = False

        # Match exact (mot entier)
        if trend_compare in full_text:
            matched = True

        # Match par mots (pour les tendances multi-mots)
        if not matched and trend_words:
            common = trend_words & text_words
            # Si au moins 50% des mots de la tendance sont dans le texte
            if len(common) >= max(1, len(trend_words) * 0.5):
                matched = True

        if matched:
            # Formater en hashtag
            if trend_clean.startswith('#'):
                hashtag = trend_clean
            else:
                # Transformer en hashtag (retirer espaces, garder majuscules)
                hashtag = '#' + re.sub(r'\s+', '', trend_clean)

            matches.append(hashtag)

            if len(matches) >= max_hashtags:
                break

    return matches


def enrich_tweet_with_trends(tweet_text, article, max_tweet_length=280):
    """
    Enrichit un tweet avec des hashtags tendance pertinents
    sans depasser la limite de caracteres.

    Args:
        tweet_text: Le tweet original
        article: Dict avec title, summary
        max_tweet_length: Limite de caracteres

    Returns:
        Le tweet enrichi avec les hashtags tendance
    """
    hashtags = find_matching_hashtags(
        tweet_text,
        article.get("title", ""),
        article.get("summary", ""),
        max_hashtags=2,
    )

    if not hashtags:
        return tweet_text

    enriched = tweet_text
    for tag in hashtags:
        # Verifier que le hashtag n'est pas deja dans le tweet
        if tag.lower() in enriched.lower():
            continue
        # Verifier qu'on ne depasse pas la limite
        if len(enriched) + len(tag) + 1 <= max_tweet_length:
            enriched += f" {tag}"

    if enriched != tweet_text:
        added = [h for h in hashtags if h.lower() in enriched.lower() and h.lower() not in tweet_text.lower()]
        if added:
            logger.info(f"Hashtags tendance ajoutes : {', '.join(added)}")

    return enriched


def reset_cache():
    """Reset le cache des tendances (utile entre les cycles)."""
    _cache["trends"] = []
    _cache["fetched"] = False
