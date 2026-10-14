# config.py - FINÁLNÍ VERZE (CLEAN)
# Všechny příkazy, které zabíjejí DRM, byly odstraněny.

HEADLESS = False  # Musí být False
TIMEOUT = 30000

# Spotify URLs
SPOTIFY_LOGIN_URL = "https://accounts.spotify.com/en/login"
SPOTIFY_WEB_PLAYER_URL = "https://open.spotify.com/"

# POUZE BEZPEČNÉ ARGUMENTY
BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--ignore-certificate-errors",
    "--no-first-run",
    "--no-default-browser-check",
    # "--disable-component-update",  <--- TOTO TU NESMÍ BÝT! SMAŽ TO!
    
    "--autoplay-policy=no-user-gesture-required",
    "--enable-widevine-cdm",
]

# Concurrency
MAX_CONCURRENT_SESSIONS = 4

# Fallback UA
FALLBACK_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

# Seznam skladeb
TARGET_SONGS = [
    "https://open.spotify.com/track/2IvaDs1lO1w88OGUVp4ysU", # Doplň své ID
]

FILLER_TRACKS = [
    "https://open.spotify.com/track/5PSrRHtvlzB8VMkVj0j6ka", # Rejdou Dice
    "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b", # The Weeknd - Blinding Lights
    "https://open.spotify.com/track/4LRPiXqCikLlN15c3yImP7", # Harry Styles - As It Was
    "https://open.spotify.com/track/5PjdY0CKGZdEuoNab3yDmX", # The Kid LAROI, Justin Bieber - STAY
    "https://open.spotify.com/track/02MWAaffLxlfxAUY7c5dvx", # Glass Animals - Heat Waves
    "https://open.spotify.com/track/6tDDoYIxWvWObX22olsuy9", # Harry Styles - Watermelon Sugar
    "https://open.spotify.com/track/39LLxExYz6ewLAcYrzQQyP", # Dua Lipa - Levitating
    "https://open.spotify.com/track/5QO79kh1waicV47BqGRL3g", # The Weeknd - Save Your Tears
    "https://open.spotify.com/track/4ZtFanR9U6ndgddUvNcjcG", # Olivia Rodrigo - good 4 u
    "https://open.spotify.com/track/27NovPIUIRrOZoCHxABJwK", # Lil Nas X - MONTERO
    "https://open.spotify.com/track/6PQ88X9TkUIAUIZJzjrCiS", # Ed Sheeran - Bad Habits
    "https://open.spotify.com/track/3USxtqRwSYz57Ewm6wWRMp", # The Neighbourhood - Sweater Weather
    "https://open.spotify.com/track/7qiZfU4dY1lWllzX7mPBI3", # Ed Sheeran - Shape of You
]