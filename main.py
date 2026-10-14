import asyncio
import random
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

import config
from core.actions import SpotifyBot
from core.browser import BrowserManager


ACCOUNTS_FILE = Path("accounts.txt")


def load_accounts(path: Path = ACCOUNTS_FILE) -> List[Dict[str, str]]:
    accounts: List[Dict[str, str]] = []
    if not path.exists():
        print(f"Account file not found: {path}. Expected format 'email:password:proxy'.")
        return accounts

    with path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split(":", 2)
            if len(parts) != 3:
                print(f"Skipping line {line_number}: expected 'email:password:proxy'.")
                continue

            username, password, proxy_raw = (part.strip() for part in parts)
            if not username or not password or not proxy_raw:
                print(f"Skipping line {line_number}: username, password, and proxy required.")
                continue

            accounts.append({
                "username": username,
                "password": password,
                "proxy_raw": proxy_raw,
            })

    return accounts


def parse_proxy_string(proxy_raw: str) -> Dict[str, str]:
    """Convert raw proxy strings into Playwright's proxy dict with scheme preserved."""
    raw = proxy_raw.strip()
    if not raw:
        raise ValueError("Proxy string is empty.")

    # Handle HOST:PORT:USERNAME:PASSWORD format commonly used in accounts.txt
    if raw.count(":") == 3 and "://" not in raw:
        host, port_str, username, password = (part.strip() for part in raw.split(":", 3))

        if not host or not port_str:
            raise ValueError(f"Proxy is missing host or port: {proxy_raw}")

        try:
            port = int(port_str)
        except ValueError as exc:
            raise ValueError("Port could not be cast to integer") from exc

        return {
            "server": f"http://{host}:{port}",
            "username": username or None,
            "password": password or None,
        }

    raw_with_scheme = raw if "://" in raw else f"http://{raw}"
    parsed = urlparse(raw_with_scheme)

    if not parsed.hostname or not parsed.port:
        raise ValueError(f"Proxy is missing host or port: {proxy_raw}")

    server = f"{parsed.scheme or 'http'}://{parsed.hostname}:{parsed.port}"

    return {
        "server": server,
        "username": parsed.username or None,
        "password": parsed.password or None,
    }


async def run_account(account: Dict[str, str], browser_manager: BrowserManager, semaphore: asyncio.Semaphore):
    username = account["username"]
    password = account["password"]
    proxy_raw = account["proxy_raw"]

    try:
        proxy_config = parse_proxy_string(proxy_raw)
    except ValueError as exc:
        print(f"[{username}] Invalid proxy: {exc}")
        return          

    async with semaphore:
        browser = context = page = None
        
        try:
            # ZMĚNA: Předáváme username pro vytvoření unikátního profilu
            browser, context, page = await browser_manager.create_browser(proxy=proxy_config, username=username)
            
            bot = SpotifyBot(page, username, password)
            await bot.login()
            
            # ... zbytek kódu pro přehrávání zůstává stejný ...
            target_songs = getattr(config, "TARGET_SONGS", [])
            if not target_songs:
                target_songs = ["Target Track"] # Fallback, raději doplň config!

            filler_tracks = getattr(config, "FILLER_TRACKS", [])
            if not filler_tracks:
                filler_tracks = target_songs

            target_turn = True
            
            # Loop
            while True:
                try:
                    if target_turn:
                        song = random.choice(target_songs)
                        await bot.play_track(song, duration_range=(30, 130))
                    else:
                        filler = random.choice(filler_tracks)
                        await bot.play_track(filler, duration_range=(30, 60))

                    target_turn = not target_turn
                    await asyncio.sleep(3)
                except Exception as exc_inner:
                    print(f"[{username}] Error in session loop: {exc_inner}")
                    try:
                        await page.reload()
                    except Exception:
                        pass
                    await asyncio.sleep(5)

        except Exception as exc:
            print(f"[{username}] Session crashed: {exc}")
        finally:
            # ZMĚNA: Bezpečné zavírání. Persistent context zavírá vše.
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            # Browser je None, takže ho ignorujeme


async def main():
    accounts = load_accounts()

    if not accounts:
        print("No accounts found. Populate accounts.txt with 'email:password:proxy'.")
        return

    if not getattr(config, "TARGET_SONGS", []):
        print("No target URLs found in config")
        return

    browser_manager = BrowserManager()
    await browser_manager.init_playwright()

    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_SESSIONS)
    tasks = [asyncio.create_task(run_account(account, browser_manager, semaphore)) for account in accounts]

    try:
        await asyncio.gather(*tasks)
    finally:
        await browser_manager.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopping bot...")
