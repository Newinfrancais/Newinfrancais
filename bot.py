"""
Bot Twitter Actu — Script principal (version cloud + images + filtre IA)
Chaque run = 1 cycle : collecter → traduire → filtrer IA → publier.

Usage :
    python bot.py              # Cycle normal
    python bot.py --dry-run    # Simuler sans publier
    python bot.py --check      # Vérifier la connexion OpenTweet
    python bot.py --debug      # Logs détaillés
"""

import argparse
import logging
import sys
import time
import random
from datetime import datetime, timezone

from config import MAX_TWEETS_PER_RUN
from news_collector import fetch_news, mark_posted
from tweet_formatter import format_tweet, format_tweet_with_context
from tweet_quality_checker import check_tweet_quality
from opentweet_client import OpenTweetClient


def setup_logging(debug=False):
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

logger = logging.getLogger("bot.main")


def run_cycle(dry_run=False):
    stats = {"posted": 0, "failed": 0, "skipped": 0, "filtered": 0, "rejected_ia": 0, "images": 0}

    logger.info("=" * 50)
    logger.info(f"  Cycle — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info("=" * 50)

    articles = fetch_news()
    if not articles:
        logger.info("Aucun nouvel article à publier")
        return stats

    logger.info(f"{len(articles)} articles disponibles")

    client = None
    if not dry_run:
        try:
            client = OpenTweetClient()
        except ValueError as e:
            logger.error(f"Impossible d'initialiser OpenTweet : {e}")
            return stats

    published_count = 0
    for article in articles:
        if published_count >= MAX_TWEETS_PER_RUN:
            stats["skipped"] += 1
            continue

        # 1. Formater (inclut traduction EN→FR si besoin)
        if article["priority"] >= 20:
            tweet = format_tweet_with_context(article)
        else:
            tweet = format_tweet(article)

        if tweet is None:
            stats["filtered"] += 1
            continue

        # 2. Filtre qualité IA (OpenRouter)
        ok, reason = check_tweet_quality(tweet, source=article.get("source", ""))
        if not ok:
            logger.info(f"[IA REJETÉ — {reason}] {tweet[:80]}")
            stats["rejected_ia"] += 1
            continue

        image_url = article.get("image_url")

        if dry_run:
            img_tag = " [+IMAGE]" if image_url else ""
            print(f"\n  [DRY-RUN]{img_tag} ({len(tweet)} chars) | Prio={article['priority']}")
            print(f"  {tweet}")
            if image_url:
                print(f"  Image: {image_url[:80]}")
            mark_posted(article["id"])
            stats["posted"] += 1
            published_count += 1
            if image_url:
                stats["images"] += 1
        else:
            media_urls = None
            if image_url:
                uploaded_url = client.upload_image(image_url)
                if uploaded_url:
                    media_urls = [uploaded_url]
                    stats["images"] += 1

            result = client.post_tweet(tweet, media_urls=media_urls)

            if result.get("success"):
                mark_posted(article["id"])
                stats["posted"] += 1
                published_count += 1
                img_info = " (+image)" if media_urls else ""
                logger.info(f"✅ Publié{img_info} : {tweet[:70]}...")
            else:
                stats["failed"] += 1
                logger.error(f"❌ Échec : {result.get('error', 'erreur inconnue')}")

        time.sleep(random.uniform(2, 8))

    logger.info(
        f"\n📊 Résultat : {stats['posted']} publiés ({stats['images']} avec image), "
        f"{stats['rejected_ia']} rejetés par IA, {stats['filtered']} filtrés, "
        f"{stats['failed']} échecs, {stats['skipped']} en attente"
    )
    return stats


def main():
    parser = argparse.ArgumentParser(description="Bot Twitter Actu")
    parser.add_argument("--dry-run", action="store_true", help="Simuler sans publier")
    parser.add_argument("--check", action="store_true", help="Vérifier la connexion OpenTweet")
    parser.add_argument("--debug", action="store_true", help="Logs détaillés")
    args = parser.parse_args()

    setup_logging(debug=args.debug)

    if args.check:
        try:
            client = OpenTweetClient()
            ok = client.check_connection()
            print("✅ Connexion OK" if ok else "❌ Connexion échouée")
            sys.exit(0 if ok else 1)
        except ValueError as e:
            print(f"❌ {e}")
            sys.exit(1)

    stats = run_cycle(dry_run=args.dry_run)
    if stats["failed"] > 0 and stats["posted"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
