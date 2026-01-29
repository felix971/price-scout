import asyncio
import logging
from playwright.async_api import async_playwright, Browser

logger = logging.getLogger("price-scout.pw-manager")

class PlaywrightManager:
    _instance = None
    _playwright = None
    _browser = None
    _lock = None
    _active_users = 0

    @classmethod
    def _get_lock(cls):
        """Lazily create lock bound to the current event loop."""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def get_page(cls):
        """
        Get a new page from the shared browser instance.
        Starts the browser if it's not running.
        """
        import random
        ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edge/130.0.0.0",
        ]

        async with cls._get_lock():
            if cls._browser is None:
                logger.info("🚀 Starting Shared Playwright Browser...")
                cls._playwright = await async_playwright().start()
                cls._browser = await cls._playwright.chromium.launch(headless=True)

            cls._active_users += 1
            
        context = await cls._browser.new_context(
            user_agent=random.choice(ua_list),
            viewport={"width": 1920, "height": 1080}
        )
        
        # Inject stealth scripts or other common configs here if needed
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        
        page = await context.new_page()
        
        # Block unnecessary resources to speed up loading
        async def route_intercept(route):
            if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
                await route.abort()
            else:
                await route.continue_()
                
        await page.route("**/*", route_intercept)
        
        return page, context

    @classmethod
    async def close_page(cls, context, page):
        """
        Close a page/context and decrement user count.
        Note: We DO NOT close the browser here to keep it hot for other tasks.
        """
        try:
            await page.close()
            await context.close()
        except Exception:
            pass
        
        # We don't auto-close the browser because new tasks might come in immediately.
        # In a long-running app like Streamlit, keeping one headless chrome open is fine.
        
    @classmethod
    async def shutdown(cls):
        """Force close the browser."""
        import warnings
        async with cls._get_lock():
            if cls._browser:
                logger.info("🛑 Shutting down Shared Playwright Browser...")
                try:
                    # Close all contexts (and their pages) before closing browser
                    for context in cls._browser.contexts:
                        try:
                            await context.close()
                        except Exception:
                            pass
                    await cls._browser.close()
                except Exception:
                    pass

                # Allow time for subprocess pipes to close gracefully on Windows
                await asyncio.sleep(1.0)

                try:
                    await cls._playwright.stop()
                except Exception:
                    pass

                cls._browser = None
                cls._playwright = None
                cls._lock = None

                # Force GC to collect Playwright subprocess transports now,
                # while sys.unraisablehook is still suppressing pipe errors
                import gc
                gc.collect()
