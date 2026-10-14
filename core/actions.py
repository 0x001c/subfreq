import asyncio
import json
import os
import random
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
import config


class LoginRequiredError(Exception):
    """Raised when an action requires a fresh login."""


class SpotifyBot:
    def __init__(self, page: Page, username: str, password: str):
        self.page = page
        self.username = username
        self.password = password
        self.cookies_path = f"cookies/{self.username}.json"
        self.fillers = []

    async def human_click(self, selector: str) -> bool:
        """
        Simulates human-like mouse movement and clicking using Bezier curves.
        """
        try:
            element = await self.page.wait_for_selector(selector, timeout=5000)
        except Exception:
            print(f"[{self.username}] Element not found: {selector}")
            return False

        box = await element.bounding_box()
        if not box:
            return False

        target_x = box["x"] + box["width"] / 2 + random.uniform(-5, 5)
        target_y = box["y"] + box["height"] / 2 + random.uniform(-5, 5)

        # Start from a random position or current mouse position
        start_x = random.randint(0, 1000)
        start_y = random.randint(0, 1000)

        steps = 20
        for i in range(steps):
            t = i / steps
            # Linear interpolation with noise
            x = start_x + (target_x - start_x) * t + random.uniform(-2, 2)
            y = start_y + (target_y - start_y) * t + random.uniform(-2, 2)

            await self.page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.005, 0.015))

        await self.page.mouse.move(target_x, target_y)
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await self.page.mouse.click(target_x, target_y)
        return True

    async def save_cookies(self):
        if not os.path.exists("cookies"):
            os.makedirs("cookies")
        cookies = await self.page.context.cookies()
        with open(self.cookies_path, "w") as f:
            json.dump(cookies, f)
        print(f"[{self.username}] Cookies saved.")

    async def load_cookies(self):
        if not os.path.exists(self.cookies_path):
            return False
        try:
            with open(self.cookies_path, "r") as f:
                cookies = json.load(f)
                await self.page.context.add_cookies(cookies)
            print(f"[{self.username}] Cookies loaded.")
            return True
        except Exception:
            return False

    async def handle_cookies(self):
        """Remove the OneTrust banner directly from the DOM."""
        try:
            await self.page.evaluate("document.querySelector('#onetrust-banner-sdk')?.remove()")
        except Exception:
            pass

    async def _check_authenticated(self, timeout: int = 8000) -> bool:
        try:
            await self.page.wait_for_selector(
                'div[data-testid="user-widget-link"], button[data-testid="user-widget-link"]',
                timeout=timeout,
            )
            return True
        except Exception:
            return False

    async def fix_account_region(self):
        try:
            await self.page.goto("https://www.spotify.com/account/profile/", wait_until="domcontentloaded")
        except Exception:
            return

        await self.handle_cookies()

        select = self.page.locator("select#country")
        if await select.count() == 0:
            return

        try:
            if await select.is_disabled():
                return
        except Exception:
            return

        try:
            options = await select.element_handle()
            if not options:
                return
        except Exception:
            return

        try:
            await select.select_option(index=-1)
            save_btn = self.page.locator('button[type="submit"], button[data-testid="profile-save-button"]').first
            await save_btn.click(timeout=5000, force=True)
        except Exception:
            pass

    async def login(self):
        print(f"[{self.username}] Logging in...")

        await self.load_cookies()

        await self.page.goto(config.SPOTIFY_WEB_PLAYER_URL, wait_until="domcontentloaded")
        await self.handle_cookies()

        if await self._check_authenticated(timeout=8000):
            print(f"[{self.username}] Session Valid")
            await self.fix_account_region()
            await self.save_cookies()
            return

        print(f"[{self.username}] Not authenticated; proceeding to login form...")
        await self.page.goto(config.SPOTIFY_LOGIN_URL, wait_until="domcontentloaded")
        await self.handle_cookies()

        username_selectors = [
            'input#login-username',
            'input[data-testid="login-username"]',
            'input[name="username"]',
        ]
        password_selectors = [
            'input#login-password',
            'input[data-testid="login-password"]',
            'input[name="password"]',
        ]

        async def fill_field(selectors, value, label, wait_timeout=8000):
            for selector in selectors:
                try:
                    await self.page.wait_for_selector(selector, state="visible", timeout=wait_timeout)
                except Exception:
                    continue

                try:
                    await self.human_click(selector)
                except Exception as exc:
                    print(f"[{self.username}] human_click failed on {selector}: {exc}")

                try:
                    await self.page.keyboard.type(value, delay=random.randint(40, 120))
                except Exception as exc:
                    print(f"[{self.username}] Typing failed on {selector}, fallback fill: {exc}")

                current_value = ""
                try:
                    current_value = await self.page.input_value(selector)
                except Exception:
                    pass

                if not current_value:
                    await self.page.fill(selector, value)

                try:
                    confirmed = await self.page.input_value(selector)
                    if confirmed:
                        print(f"[{self.username}] {label.capitalize()} captured with {selector}.")
                        return True
                except Exception:
                    pass

            return False

        async def find_first_visible(selectors, wait_timeout):
            for selector in selectors:
                try:
                    await self.page.wait_for_selector(selector, state="visible", timeout=wait_timeout)
                    return selector
                except Exception:
                    continue
            return None

        async def pause_for_manual_fix():
            print(f"[{self.username}] ⚠️ Element not found. PAUSED for Manual 2FA/Fix.")
            input("Press ENTER to continue after you solve it manually...")

        def is_element_not_found_error(exc: Exception) -> bool:
            message = str(exc)
            return (
                "Element not found" in message
                or "Could not locate" in message
                or "Could not click login button" in message
            )

        try:
            username_ok = await fill_field(username_selectors, self.username, "username", wait_timeout=8000)
            if not username_ok:
                raise Exception(f"[{self.username}] Could not locate username field.")

            password_selector = await find_first_visible(password_selectors, wait_timeout=3000)
            if password_selector:
                password_ok = await fill_field([password_selector], self.password, "password", wait_timeout=3000)
                if not password_ok:
                    raise Exception(f"[{self.username}] Could not fill password field.")
            else:
                print(f"[{self.username}] No password field detected. Possible passwordless / 2FA flow.")

            try:
                await self.human_click('button#login-button')
            except Exception:
                try:
                    await self.page.click('button#login-button', timeout=5000)
                except Exception as exc:
                    raise Exception(f"[{self.username}] Could not click login button: {exc}")
        except PlaywrightTimeoutError:
            await pause_for_manual_fix()
        except Exception as exc:
            if is_element_not_found_error(exc):
                await pause_for_manual_fix()
            else:
                raise

        try:
            authed = await self._check_authenticated(timeout=25000)
        except PlaywrightTimeoutError:
            print(f"⚠️ Login stalled for {self.username}. Please check the browser manually.")
            input("👉 Solve the issue in the browser and press ENTER to continue...")
            authed = await self._check_authenticated(timeout=25000)

        if not authed:
            error = await self.page.query_selector('div[data-testid="login-error-message"]')
            if error:
                err_text = await error.inner_text()
                raise Exception(f"Login failed: {err_text}")
            raise Exception(f"[{self.username}] Login failed: user widget not found.")

        print(f"[{self.username}] Login successful.")
        await self.fix_account_region()
        await self.save_cookies()

    def _resolve_track_url(self, track_id_or_url: str) -> str | None:
        if not track_id_or_url:
            return None

        raw = track_id_or_url.strip()
        if not raw:
            return None

        if raw.startswith("http://") or raw.startswith("https://"):
            return raw

        if raw.startswith("spotify:track:"):
            raw = raw.split(":")[-1].strip()

        if len(raw) < 10:
            return None

        return f"https://open.spotify.com/track/{raw}"

    async def play_track(self, track_id_or_url: str, duration_range: tuple = (45, 180)):
        track_url = self._resolve_track_url(track_id_or_url)
        if not track_url:
            print(f"[{self.username}] Invalid track id/url: {track_id_or_url}")
            return False

        print(f"[{self.username}] Opening track: {track_url}")

        try:
            await self.page.goto(track_url, wait_until="domcontentloaded")
        except Exception as exc:
            print(f"[{self.username}] Failed to load track URL: {exc}")
            return False

        await self.handle_cookies()
        await asyncio.sleep(3)

        listen_duration = random.randint(duration_range[0], duration_range[1])
        print(f"[{self.username}] Listening for {listen_duration} seconds...")
        await asyncio.sleep(listen_duration)
        return True

    async def run_session(self):
        await self.login()

        target_songs = getattr(config, "TARGET_SONGS", [])
        if not target_songs:
            target_songs = ["Target Track"]

        filler_tracks = getattr(config, "FILLER_TRACKS", [])
        if not filler_tracks:
            filler_tracks = target_songs

        target_turn = True

        while True:
            try:
                if target_turn:
                    song = random.choice(target_songs)
                    result = await self.play_track(song, duration_range=(130, 190))
                else:
                    filler = random.choice(filler_tracks)
                    result = await self.play_track(filler, duration_range=(40, 60))

                target_turn = not target_turn
                await asyncio.sleep(3)

                if result is False:
                    continue

            except LoginRequiredError as e:
                print(f"[{self.username}] Detected logout: {e}. Re-authenticating...")
                await self.login()
                await asyncio.sleep(2)
            except Exception as e:
                print(f"[{self.username}] Error in session loop: {e}")
                try:
                    await self.page.reload()
                except Exception:
                    pass
                await asyncio.sleep(5)
