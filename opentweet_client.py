"""
Client OpenTweet API
=====================
Gère la publication de tweets via l'API REST d'OpenTweet.
Documentation : https://opentweet.io/api/v1/docs
"""

import logging
import requests
import time
from typing import Optional

from config import OPENTWEET_API_KEY, OPENTWEET_BASE_URL

logger = logging.getLogger("bot.opentweet")


class OpenTweetClient:
    """Client pour l'API OpenTweet — publication de tweets sans API X officielle."""

    def __init__(self):
        if not OPENTWEET_API_KEY:
            raise ValueError(
                "OPENTWEET_API_KEY manquante. "
                "Définis-la en variable d'environnement ou dans un fichier .env"
            )
        self.headers = {
            "Authorization": f"Bearer {OPENTWEET_API_KEY}",
            "Content-Type": "application/json",
        }
        self.base = OPENTWEET_BASE_URL

    def post_tweet(self, text: str, publish_now: bool = True) -> dict:
        """
        Publie un tweet immédiatement.

        Args:
            text: Contenu du tweet (max 280 chars)
            publish_now: Si True, publie immédiatement. Si False, sauvegarde en brouillon.

        Returns:
            dict avec "success" (bool), "id" (str ou None), "error" (str ou None)
        """
        try:
            payload = {
                "text": text,
                "publish_now": publish_now,
            }

            response = requests.post(
                f"{self.base}/posts",
                headers=self.headers,
                json=payload,
                timeout=30,
            )

            if response.status_code in (200, 201):
                data = response.json()
                post_id = data.get("id") or data.get("data", {}).get("id")
                logger.info(f"Tweet publié (id: {post_id}) : {text[:60]}...")
                return {"success": True, "id": post_id, "error": None}
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error(f"Erreur OpenTweet : {error_msg}")
                return {"success": False, "id": None, "error": error_msg}

        except requests.Timeout:
            logger.error("Timeout lors de l'appel OpenTweet")
            return {"success": False, "id": None, "error": "timeout"}
        except Exception as e:
            logger.error(f"Erreur OpenTweet : {e}")
            return {"success": False, "id": None, "error": str(e)}

    def schedule_tweet(self, text: str, scheduled_date: str) -> dict:
        """
        Programme un tweet pour une date future.

        Args:
            text: Contenu du tweet
            scheduled_date: Date ISO 8601 (ex: "2026-04-10T09:00:00Z")
        """
        try:
            payload = {
                "text": text,
                "scheduled_date": scheduled_date,
            }

            response = requests.post(
                f"{self.base}/posts",
                headers=self.headers,
                json=payload,
                timeout=30,
            )

            if response.status_code in (200, 201):
                data = response.json()
                post_id = data.get("id") or data.get("data", {}).get("id")
                logger.info(f"Tweet programmé pour {scheduled_date} (id: {post_id})")
                return {"success": True, "id": post_id, "error": None}
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                return {"success": False, "id": None, "error": error_msg}

        except Exception as e:
            return {"success": False, "id": None, "error": str(e)}

    def batch_post(self, tweets: list, publish_now: bool = True) -> list:
        """
        Publie plusieurs tweets en une seule requête (max 50).

        Args:
            tweets: Liste de textes de tweets
            publish_now: Publier immédiatement

        Returns:
            Liste de résultats pour chaque tweet
        """
        results = []
        for text in tweets:
            result = self.post_tweet(text, publish_now=publish_now)
            results.append(result)
            # Petit délai entre chaque post pour respecter les rate limits
            time.sleep(2)
        return results

    def check_connection(self) -> bool:
        """Vérifie que la clé API est valide."""
        try:
            response = requests.get(
                f"{self.base}/posts",
                headers=self.headers,
                params={"limit": 1},
                timeout=15,
            )
            if response.status_code == 200:
                logger.info("Connexion OpenTweet OK")
                return True
            else:
                logger.error(f"Connexion OpenTweet échouée : HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Connexion OpenTweet échouée : {e}")
            return False
