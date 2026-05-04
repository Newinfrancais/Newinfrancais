import os

OPENTWEET_API_KEY = os.environ.get("OPENTWEET_API_KEY", "")
OPENTWEET_BASE_URL = "https://opentweet.io/api/v1"

RSS_FEEDS = {
    "Le Monde": "https://www.lemonde.fr/rss/en_continu.xml",
    "Le Monde - International": "https://www.lemonde.fr/international/rss_full.xml",
    "Le Monde - Politique": "https://www.lemonde.fr/politique/rss_full.xml",
    "Le Monde - Economie": "https://www.lemonde.fr/economie/rss_full.xml",
    "France Info": "https://www.francetvinfo.fr/titres.rss",
    "France Info - Monde": "https://www.francetvinfo.fr/monde.rss",
    "France Info - Politique": "https://www.francetvinfo.fr/politique.rss",
    "France Info - Economie": "https://www.francetvinfo.fr/economie.rss",
    "France Info - Faits divers": "https://www.francetvinfo.fr/faits-divers.rss",
    "Les Echos": "https://syndication.lesechos.fr/rss/rss_une_titres.xml",
    "France 24": "https://www.france24.com/fr/rss",
    "France 24 - Europe": "https://www.france24.com/fr/europe/rss",
    "France 24 - Moyen-Orient": "https://www.france24.com/fr/moyen-orient/rss",
    "RFI": "https://www.rfi.fr/fr/rss",
    # Sources anglophones — traduits automatiquement EN→FR
    "Reuters": "https://feeds.reuters.com/reuters/topNews",
    "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
}

MAX_TWEETS_PER_RUN = 4
MAX_ARTICLE_AGE_HOURS = 24
MAX_TWEET_LENGTH = 275

PRIORITY_KEYWORDS = [
    "urgent", "breaking", "alerte", "attentat", "séisme", "tremblement",
    "guerre", "cessez-le-feu", "élection", "démission", "mort", "décès",
    "crash", "explosion", "tsunami", "ouragan", "tempête",
    "krach", "récession", "inflation", "BCE", "Fed", "OTAN", "NATO",
    "Macron", "Trump", "Poutine", "Zelensky", "Netanyahu",
    "war", "attack", "earthquake", "killed", "election", "resign",
    "ceasefire",
]

AUTO_HASHTAGS = ["#Actu", "#Info"]

SEEN_FILE = "data/seen_articles.json"
SEEN_RETENTION_HOURS = 72
