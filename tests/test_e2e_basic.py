"""E2E tests for RuggyLab OS using Playwright."""
import asyncio

from playwright.async_api import async_playwright


async def test_login_flow():
    """Test user login flow."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        # Navigate to app
        await page.goto("http://127.0.0.1:8000/app")
        
        # Check if login page is visible
        assert await page.is_visible("text=Login")
        
        # Fill login form
        await page.fill("input[name='username']", "admin")
        await page.fill("input[name='password']", "change_me_admin_password")
        await page.click("button:has-text('Login')")
        
        # Wait for dashboard
        await page.wait_for_url("**/app**")
        assert "Dashboard" in await page.text_content("h1")
        
        await browser.close()


async def test_sample_creation_flow():
    """Test creating a sample via UI."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        await page.goto("http://127.0.0.1:8000/app")
        await page.fill("input[name='username']", "admin")
        await page.fill("input[name='password']", "change_me_admin_password")
        await page.click("button:has-text('Login')")
        await page.wait_for_url("**/app**")
        
        # Navigate to samples
        await page.click("a:has-text('Samples')")
        await page.click("button:has-text('Add Sample')")
        
        # Check form is visible
        assert await page.is_visible("text=Sample Code")
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_login_flow())
    asyncio.run(test_sample_creation_flow())
    print("✓ E2E tests passed")
