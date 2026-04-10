"""
Bot Twitter Actu — Script principal (OpenTweet + hashtags tendance)
====================================================================
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
from opentweet_client import OpenTweetClient
from trending import enrich_tweet_with_trends, reset_cache


def setup_logging(debug=False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

logger = logging.getLogger("bot.main")


def run_cycle(dry_run=False):
    stats = {"posted": 0, "failed": 0, "skipped": 0, "images": 0, "trends": 0}

    logger.info("=" * 50)
    logger.info(f"  Cycle — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info("=" * 50)

    # Reset le cache des tendances a chaque cycle
    reset_cache()

    articles = fetch_news()

    if not articles:
        logger.info("Aucun nouvel article a publier")
        return stats

    logger.info(f"{len(articles)} articles disponibles, publication de {min(len(articles), MAX_TWEETS_PER_RUN)} max")

    client = None
    if not dry_run:
        try:
            client = OpenTweetClient()
        except ValueError as e:
            logger.error(f"Impossible d'initialiser OpenTweet : {e}")
            return stats

    for article in articles[:MAX_TWEETS_PER_RUN]:

        if article["priority"] >= 20:
            tweet = format_tweet_with_context(article)
        else:
            tweet = format_tweet(article)

        # Enrichir avec les hashtags tendance
        tweet_original = tweet
        tweet = enrich_tweet_with_trends(tweet, article, max_tweet_length=275)
        if tweet != tweet_original:
            stats["trends"] += 1

        image_url = article.get("image_url")

        if dry_run:
            img_tag = " [+IMG]" if image_url else ""
            trend_tag = " [+TREND]" if tweet != tweet_original else ""
            print(f"\n  [DRY-RUN]{img_tag}{trend_tag} ({len(tweet)} chars)")
            print(f"  {tweet}")
            if image_url:
                print(f"  Image: {image_url[:80]}")
            mark_posted(article["id"])
            stats["posted"] += 1
            if image_url:
                stats["images"] += 1
        else:
            # Upload l'image si disponible
            media_urls = None
            if image_url:
                logger.info(f"Upload image pour : {article['title'][:50]}...")
                uploaded_url = client.upload_image(image_url)
                if uploaded_url:
                    media_urls = [uploaded_url]
                    stats["images"] += 1
                    logger.info("Image uploadee avec succes")
                else:
                    logger.warning("Image non disponible, publication sans image")

            # Publier le tweet
            result = client.post_tweet(tweet, media_urls=media_urls)

            if result.get("success"):
                mark_posted(article["id"])
                stats["posted"] += 1
                img_info = " (+image)" if media_urls else ""
                logger.info(f"Publie{img_info} : {tweet[:70]}...")
            else:
                stats["failed"] += 1
                error = result.get("error", "erreur inconnue")
                logger.error(f"Echec : {error}")

        # Delai aleatoire entre les tweets (3-10 secondes)
        delay = random.uniform(3, 10)
        time.sleep(delay)

    stats["skipped"] = max(0, len(articles) - MAX_TWEETS_PER_RUN)

    logger.info(f"\nResultat : {stats['posted']} publies ({stats['images']} avec image, "
                f"{stats['trends']} avec hashtag tendance), "
                f"{stats['failed']} echecs, {stats['skipped']} en attente")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Bot Twitter Actu")
    parser.add_argument("--dry-run", action="store_true", help="Simuler sans publier")
    parser.add_argument("--check", action="store_true", help="Verifier la connexion OpenTweet")
    parser.add_argument("--debug", action="store_true", help="Logs detailles")
    args = parser.parse_args()

    setup_logging(debug=args.debug)

    if args.check:
        try:
            client = OpenTweetClient()
            if client.check_connection():
                print("Connexion OpenTweet fonctionnelle")
                sys.exit(0)
            else:
                print("Connexion OpenTweet echouee")
                sys.exit(1)
        except ValueError as e:
            print(f"{e}")
            sys.exit(1)

    stats = run_cycle(dry_run=args.dry_run)

    if stats["failed"] > 0 and stats["posted"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
