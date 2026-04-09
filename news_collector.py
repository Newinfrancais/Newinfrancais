"""
Collecteur d'actualités via flux RSS (version cloud)
======================================================
Récupère les dernières actualités, déduplique (exact + sémantique),
et retourne les articles triés par priorité.
"""

import feedparser
import hashlib
import json
import os
import re
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from config import (
    RSS_FEEDS, PRIORITY_KEYWORDS,
    SEEN_FILE, SEEN_RETENTION_HOURS, MAX_ARTICLE_AGE_HOURS,
)

logger = logging.getLogger("bot.collector")


# ============================================================
# ANTI-DOUBLON (persistant via fichier JSON)
# ============================================================

def _load_seen() -> dict:
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_seen(seen: dict):
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def _clean_seen(seen: dict) -> dict:
    cutoff = time.time() - (SEEN_RETENTION_HOURS * 3600)
    return {k: v for k, v in seen.items() if v.get("ts", 0) > cutoff}


def _article_hash(title: str, link: str) -> str:
    content = f"{title.strip().lower()}|{link.strip().lower()}"
    return hashlib.md5(content.encode()).hexdigest()


# ============================================================
# DÉDUPLICATION SÉMANTIQUE
# ============================================================

def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'^(en direct|direct|live|urgent|breaking|flash|alerte)\s*[-–:,]?\s*', '', text)
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _are_similar(t1: str, t2: str, threshold: float = 0.55) -> bool:
    w1 = set(_normalize(t1).split())
    w2 = set(_normalize(t2).split())
    if not w1 or not w2:
        return False
    intersection = w1 & w2
    union = w1 | w2
    return len(intersection) / len(union) >= threshold


def _deduplicate(articles: List[Dict]) -> List[Dict]:
    sorted_arts = sorted(articles, key=lambda a: a["priority"], reverse=True)
    result = []
    for art in sorted_arts:
        if not any(_are_similar(art["title"], ex["title"]) for ex in result):
            result.append(art)
    removed = len(articles) - len(result)
    if removed:
        logger.info(f"Déduplication : {removed} doublons retirés")
    return result


# ============================================================
# PRIORITÉ
# ============================================================

def _compute_priority(title: str, summary: str) -> int:
    text = f"{title} {summary}".lower()
    return sum(10 for kw in PRIORITY_KEYWORDS if kw.lower() in text)


def _parse_date(entry) -> Optional[datetime]:
    for attr in ["published_parsed", "updated_parsed"]:
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6])
            except (TypeError, ValueError):
                continue
    return None


# ============================================================
# COLLECTE PRINCIPALE
# ============================================================

def fetch_news() -> List[Dict]:
    """
    Récupère les dernières actualités depuis tous les flux RSS.
    Filtre les doublons déjà publiés + déduplique les articles similaires.
    """
    seen = _clean_seen(_load_seen())
    _save_seen(seen)  # Sauvegarder le nettoyage

    articles = []
    cutoff = datetime.utcnow() - timedelta(hours=MAX_ARTICLE_AGE_HOURS)

    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                logger.warning(f"Flux inaccessible : {source}")
                continue

            for entry in feed.entries[:12]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()

                if not title or not link:
                    continue

                # Filtrer par date
                pub = _parse_date(entry)
                if pub and pub < cutoff:
                    continue

                # Filtrer les déjà vus
                aid = _article_hash(title, link)
                if aid in seen:
                    continue

                # Nettoyer le résumé
                summary_clean = re.sub(r'<[^>]+>', '', summary)[:300]

                articles.append({
                    "id": aid,
                    "title": title,
                    "summary": summary_clean,
                    "link": link,
                    "source": source,
                    "priority": _compute_priority(title, summary_clean),
                    "published": pub.isoformat() if pub else None,
                })

        except Exception as e:
            logger.error(f"Erreur sur {source}: {e}")

    # Déduplication sémantique inter-sources
    articles = _deduplicate(articles)

    # Tri par priorité puis date
    articles.sort(key=lambda a: (a["priority"], a["published"] or ""), reverse=True)

    logger.info(f"{len(articles)} articles uniques prêts")
    return articles


def mark_posted(article_id: str):
    """Marque un article comme publié."""
    seen = _load_seen()
    seen[article_id] = {"ts": time.time()}
    _save_seen(seen)
