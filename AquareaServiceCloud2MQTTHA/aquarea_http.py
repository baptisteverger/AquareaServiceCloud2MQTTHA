"""
HTTP helpers — equivalent of aquareaHTTP.go
"""

HEADERS_BASE = {
    "Cache-Control": "max-age=0",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:74.0) "
        "Gecko/20100101 Firefox/74.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/webp,*/*;q=0.8"
    ),
    "Upgrade-Insecure-Requests": "1",
}


class AquareaHTTPMixin:
    async def http_post(self, url: str, data: dict | None, referer: str = None) -> bytes:
        headers = {**HEADERS_BASE, "Content-Type": "application/x-www-form-urlencoded"}
        if referer:
            headers["Referer"] = referer
        async with self.session.post(url, data=data or {}, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.read()

    async def http_get(self, url: str) -> bytes:
        async with self.session.get(url, headers=HEADERS_BASE) as resp:
            resp.raise_for_status()
            return await resp.read()

    async def http_get_with_referer(self, url: str, referer: str) -> bytes:
        headers = {**HEADERS_BASE, "Referer": referer, "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin"}
        async with self.session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.read()