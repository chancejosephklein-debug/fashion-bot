import os

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TREND_CHANNEL_ID = int(os.getenv("TREND_CHANNEL_ID", 0))
ALERT_ROLE_ID = int(os.getenv("ALERT_ROLE_ID", 0))
CHECK_INTERVAL_HOURS = 6

# Base watchlist — the bot ALSO auto-discovers new brands from Reddit
BRANDS = [
    "Hellstar", "Chrome Hearts", "Supreme", "Bape", "Stussy",
    "Denim Tears", "Corteiz", "Trapstar", "Essentials Fear of God",
    "Broken Planet", "Represent", "Palm Angels", "Off-White",
    "Nike Dunk", "Jordan 1", "Yeezy", "New Balance 550",
    "Sp5der", "Revenge", "Gallery Dept", "Rhude", "Eric Emanuel",
    "Syna World", "Nocta", "Nike Tech Fleece",
    # broader catalogue so reports rotate
    "Carhartt", "Stone Island", "Moncler", "Comme des Garcons",
    "Maison Margiela", "Rick Owens", "Balenciaga", "Yeezy Gap",
    "Supreme Box Logo", "Bape Shark", "Kith", "Palace",
    "A Bathing Ape", "Asics Gel", "Salomon", "Samba",
    "Adidas Samba", "Air Force 1", "Air Max 1", "Air Max 95",
    "Nike SB", "Travis Scott", "Fragment", "Sacai",
    "Fear of God", "Vlone", "Anti Social Social Club", "KAWS",
    "CdG Play", "Pleasures", "FTP", "Dime", "Golf Wang",
    "Champion Reverse Weave", "Ralph Lauren", "Tommy Hilfiger",
    "Diesel", "Vivienne Westwood", "True Religion", "Evisu",
]

SUBREDDITS = [
    "streetwear", "sneakers", "fashionreps", "malefashion",
    "sneakermarket", "FashionRepsBST", "reselling", "japanesestreetwear",
    "rawdenim", "goodyearwelt", "mfacirclejerk", "DHgate",
    "QualityReps", "Repsneakers", "sneakerdeals", "SupremeClothing",
]

HYPE_KEYWORDS = [
    "restock", "sold out", "hyped", "grail", "resell", "price",
    "trending", "dropping", "want to buy", "wtb", "iso",
    "hype", "fire", "must cop", "worth it", "investment", "flip",
    "resale", "steal", "cheap", "plug", "batch", "qc", "legit check",
]

# Timezone for report timestamps
TIMEZONE = "America/Los_Angeles"
LOCATION_LABEL = "Yuba City, CA"