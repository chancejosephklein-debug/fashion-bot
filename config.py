import os

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TREND_CHANNEL_ID = int(os.getenv("TREND_CHANNEL_ID", 0))
ALERT_ROLE_ID = int(os.getenv("ALERT_ROLE_ID", 0))
CHECK_INTERVAL_HOURS = int(os.getenv("CHECK_INTERVAL_HOURS", 24))

TRENDSMCP_API_KEY = os.getenv("TRENDSMCP_API_KEY")
TRENDSMCP_URL = "https://api.trendsmcp.ai/api"

BRANDS = [
    "Hellstar", "Chrome Hearts", "Supreme", "Bape", "Stussy",
    "Denim Tears", "Corteiz", "Trapstar", "Essentials Fear of God",
    "Broken Planet", "Represent", "Palm Angels", "Off-White",
    "Sp5der", "Revenge", "Gallery Dept", "Rhude", "Eric Emanuel",
    "Syna World", "Nocta", "Nike Tech Fleece",
    "Nike Dunk", "Jordan 1", "Jordan 4", "Yeezy", "New Balance 550",
    "New Balance 9060", "Asics Gel", "Salomon", "Samba", "Adidas Samba",
    "Air Force 1", "Air Max 1", "Air Max 95", "Nike SB", "Dunk Low",
    "Dunk High", "Jordan 11", "Air Max 97",
    "Rick Owens", "Balenciaga", "Maison Margiela", "Comme des Garcons",
    "CdG Play", "Stone Island", "Moncler", "Vivienne Westwood",
    "Diesel", "True Religion", "Evisu", "Ralph Lauren",
    "Tommy Hilfiger", "Carhartt", "Carhartt WIP",
    "Travis Scott", "Fragment", "Sacai", "KAWS", "Vlone",
    "Anti Social Social Club", "Golf Wang", "FTP", "Dime",
    "Pleasures", "Kith", "Palace", "Fear of God",
    "Aelfric Eden", "Cole Buxton", "Vuja De", "Entire Studios",
]

TIMEZONE = "America/Los_Angeles"
LOCATION_LABEL = "Yuba City, CA"