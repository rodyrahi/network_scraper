from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from playwright.async_api import async_playwright
import asyncio
import json
from typing import List, Dict, Any
from urllib.parse import unquote

app = FastAPI(title="Cookie Extractor API", version="1.0.0")

class CookieRequest(BaseModel):
    base_url: str
    requested_url: str
    token: str  # USER PROVIDES TOKEN

class CookieResponse(BaseModel):
    success: bool
    cookies: List[Dict[str, Any]]
    count: int
    message: str = None

@app.post("/extract-cookies", response_model=CookieResponse)
async def extract_cookies(request: CookieRequest):
    """POST: Extract cookies (RECOMMENDED)"""
    try:
        cookies = await get_cookies(request.base_url, request.requested_url, request.token)
        return CookieResponse(
            success=True,
            cookies=cookies,
            count=len(cookies)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/extract-cookies/")
async def extract_cookies_get(
    base_url: str = Query(...),
    requested_url: str = Query(...),
    token: str = Query(...)
):
    """GET: Extract cookies"""
    try:
        base_url = unquote(base_url)
        requested_url = unquote(requested_url)
        
        cookies = await get_cookies(base_url, requested_url, token)
        
        return {
            "success": True,
            "cookies": cookies,
            "count": len(cookies)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_cookies(base_url: str, requested_url: str, token: str) -> list:
    """Extract cookies after visiting both URLs"""
    async with async_playwright() as p:
        # USER TOKEN INJECTED HERE!
        browser = await p.chromium.connect_over_cdp(f"wss://play.kamingo.in?token={token}")
        context = await browser.new_context()
        page = await context.new_page()
        
        print(f"🌐 Visiting: {base_url}")
        await page.goto(base_url, wait_until="networkidle")
        
        print(f"🌐 Visiting: {requested_url}")
        await page.goto(requested_url, wait_until="networkidle")
        
        cookies = await context.cookies()
        await browser.close()
        
        return cookies

@app.get("/")
async def root():
    return {
        "message": "Cookie Extractor API ✅", 
        "port": "3000",
        "docs": "/docs",
        "need": "token in request"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)