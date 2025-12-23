import os
import re
import asyncio
from apify import Actor
from playwright.async_api import async_playwright

async def main():
    async with Actor:
        # Get input
        actor_input = await Actor.get_input() or {}
        
        # Fallback to env vars if not in input (for local testing convenience)
        zoho_email = actor_input.get('ZOHO_EMAIL') or os.getenv('ZOHO_EMAIL')
        zoho_password = actor_input.get('ZOHO_PASSWORD') or os.getenv('ZOHO_PASSWORD')
        customer_name = actor_input.get('CUSTOMER_NAME') or 'Valued Customer'

        if not zoho_email or not zoho_password:
            await Actor.fail_run("Missing ZOHO_EMAIL or ZOHO_PASSWORD")
            return

        Actor.log.info(f"Starting Zoho Lens session creation for: {customer_name}")

        async with async_playwright() as p:
            # Apify actors run in headless mode by default in the Docker container
            # The base image sets up the environment variables for display
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = await browser.new_context(viewport={'width': 1280, 'height': 800})
            page = await context.new_page()

            try:
                # 1. Login
                Actor.log.info("Navigating to login page...")
                login_url = "https://accounts.zoho.com/signin?servicename=ZohoLens&signupurl=https://www.zoho.com/lens/signup.html"
                await page.goto(login_url)
                
                Actor.log.info("Filling credentials...")
                await page.wait_for_selector("#login_id", timeout=60000)
                await page.fill("#login_id", zoho_email)
                await page.click("#nextbtn")
                
                await page.wait_for_selector("#password", timeout=60000)
                await page.fill("#password", zoho_password)
                
                # Wait for navigation
                start_time = asyncio.get_event_loop().time()
                await page.click("#nextbtn")
                
                # 2. Dashboard - "Start Now"
                Actor.log.info("Waiting for dashboard...")
                start_btn_selector = "button:has-text('Start Now'), div[role='button']:has-text('Start Now')"
                
                # Check for dashboard load or error
                try:
                    await page.wait_for_selector(start_btn_selector, timeout=60000)
                except Exception as e:
                    await page.screenshot(path="dashboard_timeout.png")
                    await Actor.push_data({"error": "Timeout waiting for dashboard", "detail": str(e)})
                    # Save screenshot to Key-Value store
                    with open("dashboard_timeout.png", "rb") as f:
                        await Actor.set_value("dashboard_timeout.png", f.read(), content_type="image/png")
                    raise e
                
                Actor.log.info("Clicking 'Start Now'...")
                start_buttons = page.locator(start_btn_selector)
                
                # Handle new tab
                async with context.expect_page() as new_page_info:
                    await start_buttons.first.click()
                
                session_page = await new_page_info.value
                await session_page.wait_for_load_state("networkidle")
                Actor.log.info("Switched to session page.")

                # 3. Session Invitation
                Actor.log.info("Extracting join link...")
                link_selector = "#inviteCustomer_JoinUrl"
                
                try:
                    await session_page.wait_for_selector(link_selector, timeout=60000)
                    join_url = await session_page.inner_text(link_selector)
                    join_url = join_url.strip()
                    
                    if join_url:
                        Actor.log.info(f"Link found: {join_url}")
                        await Actor.push_data({"join_url": join_url, "status": "success"})
                    else:
                        raise Exception("Link element empty")
                        
                except Exception as e:
                   await session_page.screenshot(path="link_error.png")
                   with open("link_error.png", "rb") as f:
                        await Actor.set_value("link_error.png", f.read(), content_type="image/png")
                   raise e

            except Exception as e:
                Actor.log.error(f"Run failed: {e}")
                await Actor.fail_run(str(e))
            finally:
                await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
