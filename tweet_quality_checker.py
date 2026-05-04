"""
Filtre qualité IA — utilise OpenRouter (gratuit, sans CB) pour juger
si un tweet apporte une vraie information ou non.

Modèle : meta-llama/llama-3.1-8b-instruct:free (gratuit sur OpenRouter)
Clé API : gratuite sur openrouter.ai
"""

import logging
import os
import requests
import json
import re
from typing import Tuple

logger = logging.getLogger("bot.quality")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"

SYSTEM_PROMPT = """Tu es un éditeur de compte Twitter d'actualités françaises (style Cerfia, AlertInfos).
Tu reçois un tweet candidat à la publication. Tu dois décider s'il mérite d'être publié.

Réponds UNIQUEMENT par un JSON sur une ligne, rien d'autre :
{"publish": true, "reason": "explication courte"}
ou
{"publish": false, "reason": "explication courte"}

Critères pour rejeter (publish: false) :
- Le tweet pose une question sans y répondre (ex: "Trump sous influence des chrétiens ?")
- Le tweet est un teaser sans information réelle (ex: "Voici ce qu'il faut retenir")
- Le tweet n'annonce rien de concret (trop vague)

Critères pour publier (publish: true) :
- Le tweet annonce un fait précis (mort, accord, résultat, chiffre, décision, événement)
- Le tweet a une valeur informationnelle claire
- Le tweet susciterait de la curiosité ou de l'engagement chez les lecteurs"""


def check_tweet_quality(tweet: str, source: str = "") -> Tuple[bool, str]:
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY manquante — filtre IA désactivé, tweet accepté")
        return True, "no_api_key"

    prompt = f"Tweet candidat :\n{tweet}\n\nSource : {source}"

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/Newinfrancais/Newinfrancais",
                "X-Title": "Newinfrancais Bot",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 80,
                "temperature": 0.1,
            },
            timeout=10,
        )

        if response.status_code != 200:
            logger.warning(f"OpenRouter erreur {response.status_code} — tweet accepté par défaut")
            return True, "api_error"

        content = response.json()["choices"][0]["message"]["content"].strip()
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            return True, "parse_error"

        result = json.loads(match.group())
        publish = bool(result.get("publish", True))
        reason = result.get("reason", "")

        if not publish:
            logger.info(f"[IA REJETÉ] {reason} | {tweet[:60]}")
        return publish, reason

    except requests.Timeout:
        return True, "timeout"
    except Exception as e:
        logger.warning(f"OpenRouter erreur : {e} — tweet accepté par défaut")
        return True, str(e)
