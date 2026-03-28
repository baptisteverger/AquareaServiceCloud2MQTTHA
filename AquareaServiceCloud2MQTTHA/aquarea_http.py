"""
HTTP helpers — equivalent of aquareaHTTP.go
"""

import logging
import aiohttp

logger = logging.getLogger(__name__)

HEADERS_BASE = {
    "Cache-Control": "max-age=0",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

HEADERS_HTML = {
    "Cache-Control": "max-age=0",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}


def _make_multipart(data: dict) -> aiohttp.FormData:
    form = aiohttp.FormData()
    for k, v in data.items():
        form.add_field(k, str(v))
    return form


class AquareaHTTPMixin:

    async def http_post(self, url: str, data: dict | None) -> bytes:
        """POST with multipart/form-data."""
        form = _make_multipart(data or {})
        async with self.session.post(url, data=form, headers=HEADERS_BASE) as resp:
            resp.raise_for_status()
            return await resp.read()

    async def http_get(self, url: str) -> bytes:
        async with self.session.get(url, headers=HEADERS_BASE) as resp:
            resp.raise_for_status()
            return await resp.read()

    async def http_get_html(self, url: str) -> bytes:
        """Simulate a browser page navigation (GET)."""
        async with self.session.get(url, headers=HEADERS_HTML) as resp:
            resp.raise_for_status()
            return await resp.read()

    async def http_get_with_referer(self, url: str, referer: str) -> bytes:
        headers = {
            **HEADERS_BASE,
            "Referer": referer,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        async with self.session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.read()

    async def http_post_with_referer(self, url: str, referer: str, data: dict | None) -> bytes:
        """POST with multipart/form-data and Referer header."""
        form = _make_multipart(data or {})
        headers = {
            **HEADERS_BASE,
            "Referer": referer,
            "Origin": "https://aquarea-service.panasonic.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        async with self.session.post(url, data=form, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.read()

    async def http_post_navigate(self, url: str, referer: str, data: dict | None) -> bytes:
        """Simulate a browser form-submit navigation (application/x-www-form-urlencoded)."""
        headers = {
            **HEADERS_HTML,
            "Referer": referer,
            "Origin": "https://aquarea-service.panasonic.com",
            "Sec-Fetch-User": "?1",
        }
        async with self.session.post(url, data=data or {}, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.read()