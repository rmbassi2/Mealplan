import asyncio
import os
import sys
from playwright.async_api import async_playwright

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "..", "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

async def run_verification():
    print("Launching browser verification...")
    async with async_playwright() as p:
        # Launch Chrome or Edge installed on system
        browser = await p.chromium.launch(
            channel="chrome",
            headless=True,
        )
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
            device_scale_factor=2,
        )
        page = await context.new_page()

        print("Navigating to http://127.0.0.1:8000...")
        await page.goto("http://127.0.0.1:8000", wait_until="networkidle")

        # If a prior run left dinner locked in, reset to voting view
        await page.wait_for_timeout(500)
        if await page.locator("#confirmationView").is_visible():
            print("Resetting prior locked-in meal plan for fresh test run...")
            pick_again = page.locator("#confirmationView button").filter(has_text="Change your mind")
            await pick_again.click()
            await page.wait_for_timeout(400)

        # 1. Wait for recipe cards to render
        await page.wait_for_selector("#recipeList .recipe-card", state="visible", timeout=10000)
        cards = await page.query_selector_all("#recipeList .recipe-card")
        print(f"Rendered {len(cards)} recipe cards.")
        assert len(cards) == 3, f"Expected 3 cards, got {len(cards)}"

        # Verify filter pills rendered
        pills = await page.query_selector_all("#filterPills button")
        print(f"Rendered {len(pills)} mood filter pills.")
        assert len(pills) >= 10, f"Expected at least 10 filter pills, got {len(pills)}"

        # Initial view screenshot with filter pills & badges
        initial_shot = os.path.join(SCREENSHOTS_DIR, "1_initial_options.png")
        await page.screenshot(path=initial_shot)
        print(f"Saved initial view screenshot to: {initial_shot}")

        # Test clicking a mood filter pill (e.g. Quick)
        print("Clicking '⚡ Quick (<30m)' filter pill...")
        quick_pill = page.locator("#filterPills button").filter(has_text="Quick")
        await quick_pill.click()
        await page.wait_for_timeout(600)
        await page.wait_for_selector("#recipeList .recipe-card", state="visible")
        quick_cards = await page.query_selector_all("#recipeList .recipe-card")
        print(f"Rendered {len(quick_cards)} recipes for Quick filter.")
        assert len(quick_cards) > 0, "Expected at least 1 recipe card for Quick filter"

        filtered_shot = os.path.join(SCREENSHOTS_DIR, "1b_filtered_quick_options.png")
        await page.screenshot(path=filtered_shot)
        print(f"Saved filtered quick view screenshot to: {filtered_shot}")

        # Verify Lock It In button is initially disabled
        lock_btn = page.locator("#lockItInBtn")
        is_disabled = await lock_btn.is_disabled()
        print(f"Lock It In initially disabled: {is_disabled}")
        assert is_disabled, "Button should be disabled before selection"

        # 2. Tap the first recipe card
        print("Clicking first recipe card...")
        card_0 = page.locator("#recipeList .recipe-card").nth(0)
        await card_0.click()
        await page.wait_for_timeout(300)

        # Verify card 0 is selected
        card_0 = page.locator("#recipeList .recipe-card").nth(0)
        aria_checked = await card_0.get_attribute("aria-checked")
        is_disabled = await lock_btn.is_disabled()
        print(f"Card 0 aria-checked: {aria_checked}, Lock It In disabled: {is_disabled}")
        assert aria_checked == "true", "First card should be selected"
        assert not is_disabled, "Lock It In button should be enabled after card selection"

        # Card selected screenshot
        card_selected_shot = os.path.join(SCREENSHOTS_DIR, "2_card_selected.png")
        await page.screenshot(path=card_selected_shot)
        print(f"Saved card selected screenshot to: {card_selected_shot}")

        # 3. Type into custom field -> verify card is automatically deselected
        print("Typing in custom field 'Spicy Thai Green Curry Takeout'...")
        custom_input = page.locator("#customNoteInput")
        await custom_input.scroll_into_view_if_needed()
        await page.wait_for_timeout(200)
        await custom_input.fill("Spicy Thai Green Curry Takeout")
        await page.wait_for_timeout(300)

        # Check card 0 is now deselected
        card_0_after = page.locator("#recipeList .recipe-card").nth(0)
        aria_checked_after_typing = await card_0_after.get_attribute("aria-checked")
        is_active_badge_visible = await page.locator("#customActiveBadge").is_visible()
        is_disabled_typing = await lock_btn.is_disabled()
        print(f"Card 0 aria-checked after typing: {aria_checked_after_typing}")
        print(f"Custom active badge visible: {is_active_badge_visible}")
        print(f"Lock It In disabled: {is_disabled_typing}")
        assert aria_checked_after_typing == "false", "Recipe card must be deselected when typing custom craving"
        assert is_active_badge_visible, "Custom Active badge must be visible"
        assert not is_disabled_typing, "Lock It In button must remain enabled for custom text"

        # Custom typing screenshot
        custom_shot = os.path.join(SCREENSHOTS_DIR, "3_custom_craving_active.png")
        await page.screenshot(path=custom_shot)
        print(f"Saved custom craving screenshot to: {custom_shot}")

        # 3b. Test pasting an external recipe URL
        print("Testing pasting external recipe URL into custom field...")
        test_url = "https://www.seriouseats.com/the-best-crispy-roast-potatoes-recipe"
        await custom_input.fill(test_url)
        await page.wait_for_timeout(800)

        is_preview_visible = await page.locator("#urlPreviewContainer").is_visible()
        preview_title = await page.locator("#urlPreviewTitle").inner_text()
        print(f"URL preview visible: {is_preview_visible}, title: {preview_title}")
        assert is_preview_visible, "URL preview pill must be visible when URL is entered"

        url_shot = os.path.join(SCREENSHOTS_DIR, "3b_url_preview_active.png")
        await page.screenshot(path=url_shot)
        print(f"Saved URL preview screenshot to: {url_shot}")

        # 4. Select a card again to verify clicking card deselects/clears custom note
        print("Re-selecting second card...")
        card_1 = page.locator("#recipeList .recipe-card").nth(1)
        await card_1.scroll_into_view_if_needed()
        await card_1.click()
        await page.wait_for_timeout(300)

        reselected_card_shot = os.path.join(SCREENSHOTS_DIR, "4_recipe_reselected.png")
        await page.screenshot(path=reselected_card_shot)
        print(f"Saved re-selected card screenshot to: {reselected_card_shot}")

        # 5. Click 'Lock It In' and verify confirmation view
        print("Clicking 'Lock It In' button...")
        await lock_btn.click()

        # Wait for confirmation view and let pop-in animation finish
        await page.wait_for_selector("#confirmationView", state="visible", timeout=8000)
        await page.wait_for_timeout(600)
        confirm_text = await page.locator("#confirmationView h2").inner_text()
        chef_notified_text = await page.locator("#confirmationView p").first.inner_text()
        chosen_dish = await page.locator("#confirmDishTitle").inner_text()

        print(f"Confirmation view text: '{confirm_text}'")
        print(f"Subtitle: '{chef_notified_text}'")
        print(f"Chosen dish: '{chosen_dish}'")

        assert "Dinner is locked in!" in confirm_text, f"Expected 'Dinner is locked in!', got {confirm_text}"
        assert "notified" in chef_notified_text.lower(), f"Expected chef notification text, got {chef_notified_text}"

        # Confirmation screenshot
        confirm_shot = os.path.join(SCREENSHOTS_DIR, "5_confirmation_screen.png")
        await page.screenshot(path=confirm_shot)
        print(f"Saved confirmation screenshot to: {confirm_shot}")

        # 6. Verify subsequent visit persistence on reload
        print("\nReloading page to test subsequent visit behavior...")
        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(500)

        # Check that confirmation screen is immediately displayed
        is_confirm_visible = await page.locator("#confirmationView").is_visible()
        is_voting_hidden = await page.locator("#votingView").is_hidden()
        reloaded_dish = await page.locator("#confirmDishTitle").inner_text()

        print(f"Confirmation visible on reload: {is_confirm_visible}")
        print(f"Voting view hidden on reload: {is_voting_hidden}")
        print(f"Retained dish name: '{reloaded_dish}'")

        assert is_confirm_visible, "Confirmation view must be displayed on subsequent visit"
        assert is_voting_hidden, "Voting view must be hidden on subsequent visit"
        assert reloaded_dish == chosen_dish, f"Expected '{chosen_dish}', got '{reloaded_dish}'"

        subsequent_shot = os.path.join(SCREENSHOTS_DIR, "6_subsequent_visit_locked_in.png")
        await page.screenshot(path=subsequent_shot)
        print(f"Saved subsequent visit screenshot to: {subsequent_shot}")

        # 7. Test "Change your mind? Pick again" button
        print("Testing 'Change your mind? Pick again' button...")
        pick_again_btn = page.locator("#confirmationView button").filter(has_text="Change your mind")
        await pick_again_btn.click()
        await page.wait_for_timeout(400)

        is_voting_visible_again = await page.locator("#votingView").is_visible()
        is_confirm_hidden_again = await page.locator("#confirmationView").is_hidden()
        print(f"Voting view visible again: {is_voting_visible_again}")
        print(f"Confirmation view hidden again: {is_confirm_hidden_again}")

        assert is_voting_visible_again, "Voting view should be restored after clicking Pick Again"
        assert is_confirm_hidden_again, "Confirmation view should be hidden after clicking Pick Again"

        await browser.close()
        print("\nAll browser verifications (including subsequent visits) passed successfully!")

if __name__ == "__main__":
    asyncio.run(run_verification())
