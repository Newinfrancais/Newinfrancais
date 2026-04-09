"""
Bot Twitter Actu — Script principal (version cloud)
=====================================================
Conçu pour être exécuté par GitHub Actions toutes les 15-30 min.
Chaque exécution = 1 cycle : collecter → formater → publier.

Usage local :
    python bot.py              → Exécute un cycle
    python bot.py --dry-run    → Simule sans publier
    python bot.py --check      → Vérifie la connexion OpenTweet
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


# ============================================================
# LOGGING
# ============================================================

def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

logger = logging.getLogger("bot.main")


# ============================================================
# CYCLE PRINCIPAL
# ============================================================

def run_cycle(dry_run: bool = False) -> dict:
    """
    Exécute un cycle complet : collecte → format → publication.

    Returns:
        dict avec posted (int), failed (int), skipped (int)
    """
    stats = {"posted": 0, "failed": 0, "skipped": 0}

    # 1. Collecter les articles
    logger.info("=" * 50)
    logger.info(f"  Cycle — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    logger.info("=" * 50)

    articles = fetch_news()

    if not articles:
        logger.info("Aucun nouvel article à publier")
        return stats

    logger.info(f"{len(articles)} articles disponibles, publication de {min(len(articles), MAX_TWEETS_PER_RUN)} max")

    # 2. Initialiser le client OpenTweet (sauf dry-run)
    client = None
    if not dry_run:
        try:
            client = OpenTweetClient()
        except ValueError as e:
            logger.error(f"Impossible d'initialiser OpenTweet : {e}")
            return stats

    # 3. Formater et publier
    for article in articles[:MAX_TWEETS_PER_RUN]:

        # Choisir le format selon la priorité
        if article["priority"] >= 20:
            tweet = format_tweet_with_context(article)
        else:
            tweet = format_tweet(article)

        if dry_run:
            print(f"\n  [DRY-RUN] ({len(tweet)} chars)")
            print(f"  {tweet}")
            print(f"  └─ Source: {article['source']} | Prio: {article['priority']}")
            mark_posted(article["id"])
            stats["posted"] += 1
        else:
            result = client.post_tweet(tweet)

            if result["success"]:
                mark_posted(article["id"])
                stats["posted"] += 1
                logger.info(f"✅ Publié : {tweet[:70]}...")
            else:
                stats["failed"] += 1
                logger.error(f"❌ Échec : {result['error']}")

        # Délai aléatoire entre les tweets (2-8 secondes)
        delay = random.uniform(2, 8)
        time.sleep(delay)

    stats["skipped"] = max(0, len(articles) - MAX_TWEETS_PER_RUN)

    logger.info(f"\n📊 Résultat : {stats['posted']} publiés, {stats['failed']} échecs, {stats['skipped']} en attente")
    return stats


def check_connection():
    """Vérifie la connexion à OpenTweet."""
    try:
        client = OpenTweetClient()
        if client.check_connection():
            print("✅ Connexion OpenTweet fonctionnelle")
            return True
        else:
            print("❌ Connexion OpenTweet échouée — vérifie ta clé API")
            return False
    except ValueError as e:
        print(f"❌ {e}")
        return False


# ============================================================
# POINT D'ENTRÉE
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Bot Twitter Actu (Cloud)")
    parser.add_argument("--dry-run", action="store_true", help="Simuler sans publier")
    parser.add_argument("--check", action="store_true", help="Vérifier la connexion OpenTweet")
    parser.add_argument("--debug", action="store_true", help="Activer les logs détaillés")
    args = parser.parse_args()

    setup_logging(debug=args.debug)

    if args.check:
        success = check_connection()
        sys.exit(0 if success else 1)

    stats = run_cycle(dry_run=args.dry_run)

    # Code de sortie non-zéro si des échecs
    if stats["failed"] > 0 and stats["posted"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
