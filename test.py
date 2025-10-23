from playwright.async_api import async_playwright
import asyncio
import json

async def get_cookies(url):
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("wss://play.kamingo.in?token=1234")
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto(url)
        cookies = await context.cookies()
        
        await browser.close()
        
        return cookies

# RUN
async def main():
    url = "https://adstransparency.google.com/advertiser/AR16735076323512287233/creative/CR14238713547210096641?region=IN"
    cookies = await get_cookies(url)
    print(json.dumps(cookies, indent=2))

asyncio.run(main())