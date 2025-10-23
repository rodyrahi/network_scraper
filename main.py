from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright
import asyncio
import json
from typing import List, Dict, Any

app = FastAPI(title="Cookie Extractor API", version="1.0.0")

# Pydantic models
class CookieRequest(BaseModel):
    base_url: str
    requested_url: str

class CookieResponse(BaseModel):
    success: bool
    cookies: List[Dict[str, Any]]
    count: int
    message: str = None

# Global event loop for async
loop = asyncio.get_event_loop()

@app.post("/extract-cookies", response_model=CookieResponse)
async def extract_cookies(request: CookieRequest):
    """
    Extract cookies from requested_url after visiting base_url
    """
    try:
        cookies = await loop.run_in_executor(
            None, 
            lambda: asyncio.run(get_cookies(request.base_url, request.requested_url))
        )
        
        return CookieResponse(
            success=True,
            cookies=cookies,
            count=len(cookies)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_cookies(base_url: str, requested_url: str) -> list:
    """Extract cookies after visiting both URLs"""
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("wss://play.kamingo.in?token=1234")
        context = await browser.new_context()
        page = await context.new_page()
        
        # Visit base_url first (login/session)
        await page.goto(base_url, wait_until="networkidle")
        
        # Then visit requested_url
        await page.goto(requested_url, wait_until="networkidle")
        
        # Get ALL cookies
        cookies = await context.cookies()
        
        await browser.close()
        
        return cookies

# Health check
@app.get("/")
async def root():
    return {"message": "Cookie Extractor API is running! 🎉"}

# Simple GET version
@app.get("/extract-cookies/{base_url}/{requested_url}")
async def extract_cookies_get(base_url: str, requested_url: str):
    """GET version for quick testing"""
    try:
        cookies = await loop.run_in_executor(
            None, 
            lambda: asyncio.run(get_cookies(base_url, requested_url))
        )
        
        return {
            "success": True,
            "cookies": cookies,
            "count": len(cookies)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)