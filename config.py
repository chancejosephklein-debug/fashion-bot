import os

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TREND_CHANNEL_ID = int(os.getenv("TREND_CHANNEL_ID", 0))
ALERT_ROLE_ID = int(os.getenv("ALERT_ROLE_ID", 0))
CHECK_INTERVAL_HOURS = 6

BRANDS = [
    "Hellstar", "Chrome Hearts", "Supreme", "Bape", "Stussy",
    "Denim Tears", "Corteiz", "Trapstar", "Essentials Fear of God",
    "Broken Planet", "Represent", "Palm Angels", "Off-White",
    "Nike Dunk", "Jordan 1", "Yeezy", "New Balance 550",
    "Sp5der", "Revenge", "Gallery Dept", "Rhude", "Eric Emanuel",
    "Syna World", "Nocta", "Nike Tech Fleece"
]

SUBREDDITS = [
    "streetwear", "sneakers", "fashionreps", "malefashion",
    "sneakermarket", "FashionRepsBST", "reselling"
]

HYPE_KEYWORDS = [
    "restock", "sold out", "hyped", "grail", "resell", "price",
    "trending", "dropping", "want to buy", "wtb", "iso",
    "hype", "fire", "must cop", "worth it", "investment", "flip"
]