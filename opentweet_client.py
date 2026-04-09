"""
Client OpenTweet API (avec support images)
=============================================
"""

import logging
import requests
import time
import tempfile
import os
from typing import Optional

from config import OPENTWEET_API_KEY, OPENTWEET_BASE_URL

logger = logging.getLogger("bot.opentweet")


class OpenTweetClient:

    def __init__(self):
        if not OPENTWEET_API_KEY:
            raise ValueError("OPENTWEET_API_KEY manquante.")
        self.headers = {
            "Authorization": f"Bearer {OPENTWEET_API_KEY}",
            "Content-Type": "application/json",
        }
        self.base = OPENTWEET_BASE_URL
        self.x_account_id = None
        self._fetch_account_id()

    def _fetch_account_id(self):
        try:
            response = requests.get(f"{self.base}/accounts", headers=self.headers, timeout=15)
            logger.info(f"GET /accounts — HTTP {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                accounts = data if isinstance(data, list) else data.get("accounts", [])
                if accounts:
                    self.x_account_id = accounts[0].get("id")
                    logger.info(f"Compte X trouve : {accounts[0].get('username', 'inconnu')} (id: {self.x_account_id})")
                else:
                    logger.warning("Aucun compte X connecte trouve dans OpenTweet")
            else:
                logger.warning(f"Impossible de recuperer les comptes X : HTTP {response.status_code}")
        except Exception as e:
            logger.warning(f"Erreur recuperation comptes X : {e}")

    def upload_image(self, image_url):
        """
        Telecharge une image depuis une URL et l'upload sur OpenTweet.
        Retourne l'URL hebergee par OpenTweet, ou None en cas d'echec.
        """
        try:
            # Telecharger l'image
            logger.info(f"Telechargement image : {image_url[:80]}...")
            img_response = requests.get(
                image_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=15,
                stream=True,
            )

            if img_response.status_code != 200:
                logger.warning(f"Impossible de telecharger l'image : HTTP {img_response.status_code}")
                return None

            # Determiner l'extension
            content_type = img_response.headers.get("Content-Type", "")
            if "png" in content_type:
                ext = ".png"
            elif "webp" in content_type:
                ext = ".webp"
            elif "gif" in content_type:
                ext = ".gif"
            else:
                ext = ".jpg"

            # Verifier la taille (max 5MB)
            content_length = len(img_response.content)
            if content_length > 5 * 1024 * 1024:
                logger.warning(f"Image trop grande ({content_length} bytes), skip")
                return None

            if content_length < 1000:
                logger.warning(f"Image trop petite ({content_length} bytes), probablement invalide")
                return None

            # Sauvegarder temporairement
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(img_response.content)
                tmp_path = tmp.name

            try:
                # Upload sur OpenTweet
                upload_headers = {
                    "Authorization": f"Bearer {OPENTWEET_API_KEY}",
                }

                with open(tmp_path, "rb") as f:
                    response = requests.post(
                        f"{self.base}/upload",
                        headers=upload_headers,
                        files={"file": (f"image{ext}", f, f"image/{ext.replace('.', '')}")},
                        timeout=30,
                    )

                logger.info(f"POST /upload — HTTP {response.status_code}")
                logger.info(f"POST /upload — reponse: {response.text[:300]}")

                if response.status_code in (200, 201):
                    data = response.json()
                    uploaded_url = data.get("url")
                    if uploaded_url:
                        logger.info(f"Image uploadee : {uploaded_url[:80]}")
                        return uploaded_url
                    else:
                        logger.warning(f"Pas d'URL dans la reponse upload : {data}")
                        return None
                else:
                    logger.warning(f"Upload echoue : HTTP {response.status_code}")
                    return None
            finally:
                os.unlink(tmp_path)

        except Exception as e:
            logger.warning(f"Erreur upload image : {e}")
            return None

    def post_tweet(self, text, publish_now=True, media_urls=None):
        """
        Publie un tweet, optionnellement avec une image.

        Args:
            text: Contenu du tweet
            publish_now: Publier immediatement
            media_urls: Liste d'URLs d'images (uploadees via upload_image)
        """
        try:
            payload = {"text": text, "publish_now": publish_now}
            if self.x_account_id:
                payload["x_account_id"] = self.x_account_id
            if media_urls:
                payload["media_urls"] = media_urls

            logger.info(f"POST /posts — publish_now={publish_now}, media={bool(media_urls)}")

            response = requests.post(f"{self.base}/posts", headers=self.headers, json=payload, timeout=30)

            logger.info(f"POST /posts — HTTP {response.status_code}")
            logger.info(f"POST /posts — reponse: {response.text[:500]}")

            if response.status_code in (200, 201):
                data = response.json()
                post = None
                if "posts" in data and isinstance(data["posts"], list) and data["posts"]:
                    post = data["posts"][0]
                elif "id" in data:
                    post = data

                if post:
                    post_id = post.get("id")
                    posted = post.get("posted", False)
                    x_post_id = post.get("x_post_id")
                    logger.info(f"Post cree (id: {post_id}, posted: {posted}, x_post_id: {x_post_id})")

                    if publish_now and not posted and post_id:
                        logger.info(f"Pas publie, tentative /posts/{post_id}/publish...")
                        return self._publish_post(post_id, text)

                    return {"success": True, "id": post_id, "error": None}
                else:
                    logger.warning(f"Reponse inattendue : {data}")
                    return {"success": True, "id": None, "error": None}
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:300]}"
                logger.error(f"Erreur OpenTweet : {error_msg}")
                return {"success": False, "id": None, "error": error_msg}

        except requests.Timeout:
            return {"success": False, "id": None, "error": "timeout"}
        except Exception as e:
            logger.error(f"Erreur OpenTweet : {e}")
            return {"success": False, "id": None, "error": str(e)}

    def _publish_post(self, post_id, text):
        try:
            response = requests.post(f"{self.base}/posts/{post_id}/publish", headers=self.headers, timeout=30)
            logger.info(f"POST /publish — HTTP {response.status_code}")
            logger.info(f"POST /publish — reponse: {response.text[:500]}")

            if response.status_code in (200, 201):
                data = response.json()
                logger.info(f"Publie via /publish (x_post_id: {data.get('x_post_id')})")
                return {"success": True, "id": post_id, "error": None}
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:300]}"
                logger.error(f"Erreur /publish : {error_msg}")
                return {"success": False, "id": post_id, "error": error_msg}
        except Exception as e:
            return {"success": False, "id": post_id, "error": str(e)}

    def check_connection(self):
        try:
            response = requests.get(f"{self.base}/me", headers=self.headers, timeout=15)
            logger.info(f"GET /me — HTTP {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Compte: {data}")
                return True
            else:
                logger.error(f"GET /me failed: HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
