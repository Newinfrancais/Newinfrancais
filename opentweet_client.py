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
        self.x_account_id = None

        # Récupérer l'ID du compte X connecté
        self._fetch_account_id()

    def _fetch_account_id(self):
        """Récupère l'ID du compte X connecté pour cibler les posts."""
        try:
            response = requests.get(
                f"{self.base}/accounts",
                headers=self.headers,
                timeout=15,
            )
            logger.info(f"GET /accounts — HTTP {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                accounts = data if isinstance(data, list) else data.get("accounts", [])
                if accounts:
                    self.x_account_id = accounts[0].get("id")
                    logger.info(f"Compte X trouvé : {accounts[0].get('username', 'inconnu')} (id: {self.x_account_id})")
                else:
                    logger.warning("Aucun compte X connecté trouvé dans OpenTweet")
            else:
                logger.warning(f"Impossible de récupérer les comptes X : HTTP {response.status_code} — {response.text[:200]}")
        except Exception as e:
            logger.warning(f"Erreur lors de la récupération des comptes X : {e}")

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

            # Ajouter l'ID du compte X si disponible
            if self.x_account_id:
                payload["x_account_id"] = self.x_account_id

            logger.info(f"POST /posts — payload: {payload}")

            response = requests.post(
                f"{self.base}/posts",
                headers=self.headers,
                json=payload,
                timeout=30,
            )

            logger.info(f"POST /posts — HTTP {response.status_code}")
            logger.info(f"POST /posts — réponse: {response.text[:500]}")

            if response.status_code in (200, 201):
                data = response.json()

                # La réponse peut être dans data["posts"][0] ou directement dans data
                post = None
                if "posts" in data and isinstance(data["posts"], list) and data["posts"]:
                    post = data["posts"][0]
                elif "id" in data:
                    post = data
                elif "data" in data and isinstance(data["data"], dict):
                    post = data["data"]

                if post:
                    post_id = post.get("id")
                    posted = post.get("posted", False)
                    x_post_id = post.get("x_post_id")
                    logger.info(f"Post créé (id: {post_id}, posted: {posted}, x_post_id: {x_post_id})")

                    # Si publish_now mais pas encore publié, tenter /publish
                    if publish_now and not posted and post_id:
                        logger.info(f"Post non publié immédiatement, tentative via /posts/{post_id}/publish...")
                        return self._publish_post(post_id, text)

                    return {"success": True, "id": post_id, "error": None}
                else:
                    logger.warning(f"Réponse inattendue : {data}")
                    return {"success": True, "id": None, "error": None}
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:300]}"
                logger.error(f"Erreur OpenTweet : {error_msg}")
                return {"success": False, "id": None, "error": error_msg}

        except requests.Timeout:
            logger.error("Timeout lors de l'appel OpenTweet")
            return {"success": False, "id": None, "error": "timeout"}
        except Exception as e:
            logger.error(f"Erreur OpenTweet : {e}")
            return {"success": False, "id": None, "error": str(e)}

    def _publish_post(self, post_id: str, text: str) -> dict:
        """Publie un post déjà créé via l'endpoint /publish."""
        try:
            response = requests.post(
                f"{self.base}/posts/{post_id}/publish",
                headers=self.headers,
                timeout=30,
            )
            logger.info(f"POST /posts/{post_id}/publish — HTTP {response.status_code}")
            logger.info(f"POST /posts/{post_id}/publish — réponse: {response.text[:500]}")

            if response.status_code in (200, 201):
                data = response.json()
                x_post_id = data.get("x_post_id")
                logger.info(f"Publié via /publish (x_post_id: {x_post_id})")
                return {"success": True, "id": post_id, "error": None}
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:300]}"
                logger.error(f"Erreur /publish : {error_msg}")
                return {"success": False, "id": post_id, "error": error_msg}
        except Exception as e:
            logger.error(f"Erreur /publish : {e}")
            return {"success": False, "id": post_id, "error": str(e)}

    def check_connection(self) -> bool:
        """Vérifie que la clé API est valide et affiche les infos du compte."""
        try:
            response = requests.get(
                f"{self.base}/me",
                headers=self.headers,
                timeout=15,
            )
            logger.info(f"GET /me — HTTP {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Compte: {data}")
                can_post = data.get("limits", {}).get("can_post", "?")
                remaining = data.get("limits", {}).get("remaining_posts_today", "?")
                logger.info(f"Peut poster: {can_post}, Posts restants aujourd'hui: {remaining}")
                return True
            else:
                logger.error(f"GET /me échoué : HTTP {response.status_code} — {response.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Connexion échouée : {e}")
            return False
