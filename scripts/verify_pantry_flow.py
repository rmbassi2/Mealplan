import asyncio
import os
import sys
import threading
import time
import uvicorn
from playwright.async_api import async_playwright

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "..", "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

class ServerThread(threading.Thread):
    def __init__(self, port=8001):
        super().__init__(daemon=True)
        self.port = port
        self.server = None

    def run(self):
        config = uvicorn.Config("main:app", host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.server.run()

    def stop(self):
        if self.server:
            self.server.should_exit = True

async def main():
    port = 8001
    server = ServerThread(port=port)
    server.start()
    print(f"Server started on port {port}...")
    time.sleep(1.5)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=True)
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15",
                device_scale_factor=2,
            )
            page = await context.new_page()

            url = f"http://127.0.0.1:{port}"
            print(f"Navigating to {url}...")
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(600)

            # If confirmation screen was saved from previous run, reset
            if await page.locator("#confirmationView").is_visible():
                print("Resetting previous confirmation screen...")
                await page.locator("#confirmationView button").filter(has_text="Change your mind").click()
                await page.wait_for_timeout(500)

            # 1. Verify pantry button in header
            pantry_btn = page.locator("#pantryBtn")
            assert await pantry_btn.is_visible(), "Pantry button should be visible in header"
            print("Pantry button in header is visible.")

            # 2. Verify Pantry Ready filter pill
            pantry_pill = page.locator("#filterPills button").filter(has_text="Pantry Ready")
            assert await pantry_pill.is_visible(), "Pantry Ready pill should be visible"
            print("Pantry Ready filter pill is visible.")

            # Initial view screenshot
            shot1 = os.path.join(SCREENSHOTS_DIR, "pantry_1_main_view.png")
            await page.screenshot(path=shot1)
            print(f"Saved initial view to: {shot1}")

            # 3. Click Pantry Ready filter pill
            print("Clicking Pantry Ready filter pill...")
            await pantry_pill.click()
            await page.wait_for_timeout(600)
            await page.wait_for_selector("#recipeList .recipe-card", state="visible")

            # 4. Open Pantry Modal
            print("Opening Pantry Modal...")
            await pantry_btn.click()
            await page.wait_for_timeout(600)
            modal = page.locator("#pantryModal")
            assert await modal.is_visible(), "Pantry modal should open"
            print("Pantry modal opened successfully.")

            # Modal screenshot
            shot2 = os.path.join(SCREENSHOTS_DIR, "pantry_2_modal_open.png")
            await page.screenshot(path=shot2)
            print(f"Saved pantry modal view to: {shot2}")

            # Toggle first pantry item
            first_item = page.locator("#pantryItemsContainer .cursor-pointer").first
            await first_item.click()
            await page.wait_for_timeout(300)

            # Close modal
            close_btn = page.locator("#closePantryModalBtn")
            await close_btn.click()
            await page.wait_for_timeout(600)
            assert not await modal.is_visible(), "Pantry modal should be closed"
            print("Pantry modal closed successfully.")

            # 5. Select first recipe card
            print("Selecting first recipe card...")
            first_card = page.locator("#recipeList .recipe-card").first
            await first_card.click()
            await page.wait_for_timeout(400)

            # 6. Click Next: Pick a Side
            lock_btn = page.locator("#lockItInBtn")
            await lock_btn.click()
            await page.wait_for_timeout(500)

            # 7. In side dish view, skip side and lock in
            print("Skipping side and locking in...")
            skip_btn = page.locator("#sideView button").filter(has_text="No Side Tonight")
            await skip_btn.click()
            await page.wait_for_timeout(1000)

            # 8. Verify confirmation screen
            confirm_view = page.locator("#confirmationView")
            assert await confirm_view.is_visible(), "Confirmation view should be visible"
            print("Confirmation view displayed successfully!")

            shot3 = os.path.join(SCREENSHOTS_DIR, "pantry_3_confirmation.png")
            await page.screenshot(path=shot3)
            print(f"Saved confirmation view to: {shot3}")

            print("All pantry verification steps completed successfully!")
            await browser.close()
    finally:
        server.stop()

if __name__ == "__main__":
    asyncio.run(main())
