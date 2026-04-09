"""
Collecteur d'actualites via flux RSS (version cloud + images)
"""

import feedparser
import hashlib
import json
import os
import re
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from config import (
    RSS_FEEDS, PRIORITY_KEYWORDS,
    SEEN_FILE, SEEN_RETENTION_HOURS, MAX_ARTICLE_AGE_HOURS,
)

logger = logging.getLogger("bot.collector")

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


# ============================================================
# ANTI-DOUBLON
# ============================================================

def _load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_seen(seen):
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def _clean_seen(seen):
    cutoff = time.time() - (SEEN_RETENTION_HOURS * 3600)
    return {k: v for k, v in seen.items() if v.get("ts", 0) > cutoff}


def _article_hash(title, link):
    content = f"{title.strip().lower()}|{link.strip().lower()}"
    return hashlib.md5(content.encode()).hexdigest()


# ============================================================
# DEDUPLICATION SEMANTIQUE
# ============================================================

def _normalize(text):
    text = text.lower().strip()
    text = re.sub(r'^(en direct|direct|live|urgent|breaking|flash|alerte)\s*[-\u2013:,]?\s*', '', text)
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _are_similar(t1, t2, threshold=0.55):
    w1 = set(_normalize(t1).split())
    w2 = set(_normalize(t2).split())
    if not w1 or not w2:
        return False
    intersection = w1 & w2
    union = w1 | w2
    return len(intersection) / len(union) >= threshold


def _deduplicate(articles):
    sorted_arts = sorted(articles, key=lambda a: a["priority"], reverse=True)
    result = []
    for art in sorted_arts:
        if not any(_are_similar(art["title"], ex["title"]) for ex in result):
            result.append(art)
    removed = len(articles) - len(result)
    if removed:
        logger.info(f"Deduplication : {removed} doublons retires")
    return result


# ============================================================
# EXTRACTION D'IMAGE
# ============================================================

def _extract_image(entry):
    """Extrait l'URL de l'image d'un article RSS."""
    image_url = None

    # 1. media_content (Le Monde, etc.)
    media = entry.get("media_content", [])
    if media:
        for m in media:
            url = m.get("url", "")
            if url and ("image" in m.get("type", "") or any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"])):
                image_url = url
                break
        if not image_url and media:
            image_url = media[0].get("url", "")

    # 2. media_thumbnail (BBC, Reuters, etc.)
    if not image_url:
        thumbs = entry.get("media_thumbnail", [])
        if thumbs:
            image_url = thumbs[0].get("url", "")

    # 3. enclosures avec type image
    if not image_url:
        for enc in entry.get("enclosures", []):
            if "image" in enc.get("type", ""):
                image_url = enc.get("href", enc.get("url", ""))
                break

    # 4. Chercher <img> dans le summary/description
    if not image_url:
        content = entry.get("summary", entry.get("description", ""))
        img_match = re.search(r'<img[^>]+src=["\']([^"\'>\s]+)', content)
        if img_match:
            image_url = img_match.group(1)

    # 5. links avec type image
    if not image_url:
        for link in entry.get("links", []):
            if "image" in link.get("type", ""):
                image_url = link.get("href", "")
                break

    # Valider l'URL
    if image_url and image_url.startswith("http"):
        return image_url

    return None


# ============================================================
# PRIORITE
# ============================================================

def _compute_priority(title, summary):
    text = f"{title} {summary}".lower()
    return sum(10 for kw in PRIORITY_KEYWORDS if kw.lower() in text)


def _parse_date(entry):
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

def _fetch_feed(url):
    """Tente de recuperer un flux RSS, avec fallback sur requests si feedparser echoue."""
    feed = feedparser.parse(url)
    if feed.entries:
        return feed

    # Fallback : certains sites bloquent feedparser mais pas requests
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        if r.status_code == 200:
            feed = feedparser.parse(r.text)
            return feed
    except Exception:
        pass

    return feed


def fetch_news():
    """
    Recupere les dernieres actualites depuis tous les flux RSS.
    Inclut l'URL de l'image quand disponible.
    """
    seen = _clean_seen(_load_seen())
    _save_seen(seen)

    articles = []
    cutoff = datetime.utcnow() - timedelta(hours=MAX_ARTICLE_AGE_HOURS)

    for source, url in RSS_FEEDS.items():
        try:
            feed = _fetch_feed(url)

            if feed.bozo and not feed.entries:
                logger.warning(f"Flux inaccessible : {source}")
                continue

            for entry in feed.entries[:12]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()

                if not title or not link:
                    continue

                pub = _parse_date(entry)
                if pub and pub < cutoff:
                    continue

                aid = _article_hash(title, link)
                if aid in seen:
                    continue

                summary_clean = re.sub(r'<[^>]+>', '', summary)[:300]

                # Extraire l'image
                image_url = _extract_image(entry)

                articles.append({
                    "id": aid,
                    "title": title,
                    "summary": summary_clean,
                    "link": link,
                    "source": source,
                    "priority": _compute_priority(title, summary_clean),
                    "published": pub.isoformat() if pub else None,
                    "image_url": image_url,
                })

        except Exception as e:
            logger.error(f"Erreur sur {source}: {e}")

    articles = _deduplicate(articles)
    articles.sort(key=lambda a: (a["priority"], a["published"] or ""), reverse=True)

    with_img = sum(1 for a in articles if a.get("image_url"))
    logger.info(f"{len(articles)} articles uniques prets ({with_img} avec image)")
    return articles


def mark_posted(article_id):
    seen = _load_seen()
    seen[article_id] = {"ts": time.time()}
    _save_seen(seen)
