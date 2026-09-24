import os

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TREND_CHANNEL_ID = int(os.getenv("TREND_CHANNEL_ID", 0))
ALERT_ROLE_ID = int(os.getenv("ALERT_ROLE_ID", 0))

APIFY_TOKEN = os.getenv("APIFY_TOKEN")

TIKTOK_ACTOR = "clockworks/tiktok-scraper"
STOCKX_ACTOR = "xtracto/stockx-search-scraper"
GRAILED_ACTOR = "shahidirfan/grailed-product-scraper"

APIFY_BASE = "https://api.apify.com/v2"

TIMEZONE = "America/Los_Angeles"
LOCATION_LABEL = "Yuba City, CA"

BRANDS = [
    "Hellstar", "Chrome Hearts", "Supreme", "Bape", "Stussy",
    "Denim Tears", "Corteiz", "Trapstar", "Essentials Fear of God",
    "Broken Planet", "Represent", "Palm Angels", "Off-White",
    "Sp5der", "Revenge", "Gallery Dept", "Rhude", "Eric Emanuel",
    "Syna World", "Nocta", "Nike Tech Fleece",
    "Nike Dunk", "Jordan 1", "Jordan 4", "Yeezy", "New Balance 550",
    "Asics Gel", "Salomon", "Samba", "Air Force 1", "Air Max 1",
    "Rick Owens", "Balenciaga", "Stone Island", "Moncler",
    "Diesel", "True Religion", "Evisu", "Ralph Lauren", "Carhartt",
    "Travis Scott", "Fragment", "KAWS", "Vlone", "Kith", "Palace",
]
