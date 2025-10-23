from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from playwright.sync_api import sync_playwright
from urllib.parse import unquote
import base64
import traceback

app = FastAPI(title="Full Headers & Cookies Extractor (binary-safe)")

@app.get("/extract")
def extract_headers_cookies(
    url: str = Query(..., description="Page URL to open"),
    target_request: str | None = Query(None, description="Substring of request URL to capture headers/cookies for"),
    headless: bool = Query(False, description="Run headless (true) or headed (false). Default: False (headed)"),
):
    try:
        # Accept raw or URL-encoded input
        url = unquote(url)
        if target_request:
            target_request = unquote(target_request)

        with sync_playwright() as p:
            # Launch browser (headed by default)
            browser = p.chromium.launch(headless=headless, args=["--start-maximized"])
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                ignore_https_errors=True,
            )
            page = context.new_page()

            # Storage for captured request/response pairs
            captured = {}  # req_url -> list of {request:..., response:...} (list to record multiple requests to same URL)
            ua = None

            # Safe helper to decode or base64-encode post_data
            def safe_post_data(pd):
                if pd is None:
                    return None
                try:
                    # Playwright sometimes returns already-decoded str, sometimes bytes
                    if isinstance(pd, str):
                        return pd  # assume readable text
                    if isinstance(pd, bytes):
                        return pd.decode("utf-8")
                except UnicodeDecodeError:
                    return base64.b64encode(pd).decode()
                # As last resort, try to encode/decode
                try:
                    return str(pd)
                except Exception:
                    return base64.b64encode(bytes(pd)).decode()

            # Request listener
            def on_request(request):
                try:
                    pd = None
                    # Some Playwright versions provide request.post_data() method, some a property .post_data
                    try:
                        pd = request.post_data
                    except Exception:
                        try:
                            pd = request.post_data()
                        except Exception:
                            pd = None

                    pd_safe = None
                    if pd:
                        # pd could be str or bytes
                        if isinstance(pd, str):
                            try:
                                # try to keep as text
                                pd_safe = pd
                            except UnicodeDecodeError:
                                pd_safe = base64.b64encode(pd.encode()).decode()
                        else:
                            # bytes
                            try:
                                pd_safe = pd.decode("utf-8")
                            except Exception:
                                pd_safe = base64.b64encode(pd).decode()

                    # request.headers is a dict-like mapping
                    req_info = {
                        "method": request.method,
                        "url": request.url,
                        "headers": dict(request.headers),
                        "post_data": pd_safe,
                    }

                    # stash current request info; use list to allow multiple entries per URL
                    captured.setdefault(request.url, []).append({"request": req_info, "response": None})
                except Exception:
                    # don't allow event handler to crash the whole app
                    captured.setdefault("__errors__", []).append({
                        "phase": "request",
                        "error": traceback.format_exc()
                    })

            # Response listener
            def on_response(response):
                try:
                    # response.request gives the corresponding request
                    req = response.request
                    resp_headers = dict(response.headers)
                    status = response.status
                    # Try to attach response info to the last request entry for this URL
                    entries = captured.get(req.url)
                    entry = None
                    if entries and len(entries) > 0 and entries[-1]["response"] is None:
                        entry = entries[-1]
                    else:
                        # if no matching request entry, create a new one
                        entry = {"request": {"method": req.method, "url": req.url, "headers": dict(req.headers), "post_data": None}, "response": None}
                        captured.setdefault(req.url, []).append(entry)

                    entry["response"] = {
                        "status": status,
                        "headers": resp_headers
                    }
                except Exception:
                    captured.setdefault("__errors__", []).append({
                        "phase": "response",
                        "error": traceback.format_exc()
                    })

            # Attach listeners (wrap to avoid propagate errors)
            page.on("request", on_request)
            page.on("response", on_response)

            # Navigate
            print("🌐 Navigating to", url)
            page.goto(url, timeout=120000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)  # allow additional AJAX to finish

            # Grab UA
            try:
                ua = page.evaluate("() => navigator.userAgent")
            except Exception:
                ua = None

            # Extract cookies from context (all cookies available to the context)
            cookies = context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in cookies}

            # Build a single Cookie header string (for using in requests)
            cookie_header = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])

            # Find matching target request(s)
            matched = None
            matched_url = None
            if target_request:
                # find first request URL that contains the target_request substring
                for req_url, entries in captured.items():
                    if req_url == "__errors__":
                        continue
                    if target_request in req_url:
                        matched = entries  # list of entries for that URL
                        matched_url = req_url
                        break

            # If no explicit target_request, try to match the main page URL (may be redirected)
            if not matched:
                # find an entry whose URL contains the page url or equals
                for req_url, entries in captured.items():
                    if req_url == "__errors__":
                        continue
                    if url in req_url or req_url == url:
                        matched = entries
                        matched_url = req_url
                        break

            # If still no matched request, choose the most relevant XHR/fetch (heuristic)
            if not matched:
                # prefer requests with '/anji/' or 'LookupService' if available
                for req_url, entries in captured.items():
                    if req_url == "__errors__":
                        continue
                    if "LookupService" in req_url or "/anji/" in req_url:
                        matched = entries
                        matched_url = req_url
                        break

            # Prepare response: include everything collected for matched request(s) and a summary of all requests
            def normalize_entry(e):
                # Ensure request and response exist
                req = e.get("request", {})
                resp = e.get("response")
                # add UA to request.headers if missing
                headers = dict(req.get("headers") or {})
                if ua:
                    headers.setdefault("User-Agent", ua)
                return {
                    "request": {
                        "method": req.get("method"),
                        "url": req.get("url"),
                        "headers": headers,
                        "post_data": req.get("post_data"),
                    },
                    "response": resp
                }

            matched_normalized = [normalize_entry(e) for e in (matched or [])]

            # Also prepare a concise list of all captured request URLs (first 200)
            all_req_urls = [u for u in captured.keys() if u != "__errors__"][:200]

            # Close browser
            browser.close()

            return JSONResponse({
                "page_url": url,
                "matched_request_url": matched_url or None,
                "matched_entries": matched_normalized,     # list of request/response objects for the matched URL
                "cookies_dict": cookie_dict,
                "cookie_header": cookie_header,            # single Cookie header string you can paste into requests
                "user_agent": ua,
                "all_captured_request_urls": all_req_urls,
                "total_requests_captured": len(all_req_urls),
                "errors": captured.get("__errors__", []),
            })

    except Exception as e:
        return JSONResponse({"error": str(e), "trace": traceback.format_exc()}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3000  )