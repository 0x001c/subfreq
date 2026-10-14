import os
from typing import Dict, Optional, Tuple
from playwright.async_api import BrowserContext, Page, async_playwright
import config

class BrowserManager:
    def __init__(self):
        self.playwright = None

    async def init_playwright(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()

    async def create_browser(self, proxy: Optional[Dict] = None, username: str = "test_user") -> Tuple[None, BrowserContext, Page]:
        await self.init_playwright()

        user_data_dir = os.path.abspath(os.path.join("chrome_profiles", f"profile_{username}"))
        os.makedirs(user_data_dir, exist_ok=True)

        launch_args = config.BROWSER_ARGS + [
            "--window-size=1280,720",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--enable-widevine-cdm",
        ]

        # 3. Hard Path k Chromu (Zůstává, to je jistota)
        executable_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(executable_path):
            executable_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(executable_path) and os.environ.get("LOCALAPPDATA"):
            executable_path = os.path.join(os.environ["LOCALAPPDATA"], r"Google\Chrome\Application\chrome.exe")

        print(f"[{username}] Spouštím Chrome: {executable_path}")

        # 4. TOTO JE TA OPRAVA! 
        # Říkáme Playwrightu, aby tam NEVKLÁDAL příkaz, který zabíjí DRM.
        ignore_args = [
            "--enable-automation",       # Skryje lištu
            "--disable-component-update" # <--- TOTO ZABÍJELO WIDEVINE!
        ]

        # 5. Spuštění
        context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir,
            executable_path=executable_path,
            headless=config.HEADLESS,
            args=launch_args,
            proxy=proxy,
            
            # Aplikujeme ignorování:
            ignore_default_args=ignore_args,
            
            viewport={"width": 1280, "height": 720},
            permissions=["geolocation", "notifications"],
            geolocation={"latitude": 40.7128, "longitude": -74.0060}
        )

        await self._inject_stealth(context)
        page = context.pages[0] if context.pages else await context.new_page()
        page.set_default_timeout(config.TIMEOUT)
        
        return None, context, page

    async def _inject_stealth(self, context: BrowserContext):
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        await context.add_init_script("""
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters)
            );
        """)

    async def close(self):
        if self.playwright:
            await self.playwright.stop()