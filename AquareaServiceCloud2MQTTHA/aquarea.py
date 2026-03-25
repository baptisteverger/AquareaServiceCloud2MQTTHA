"""
Main Aquarea class — equivalent of aquarea.go
"""

import asyncio
import json
import logging
import re
import ssl
from pathlib import Path

import aiohttp

from aquarea_types import (
    AquareaCommand,
    AquareaEndUserJSON,
    AquareaFunctionDescription,
    AquareaFunctionSettingGetJSON,
    AquareaLogItem,
)
from aquarea_http import AquareaHTTPMixin
from aquarea_login import AquareaLoginMixin
from aquarea_settings import AquareaSettingsMixin
from aquarea_device_status import AquareaDeviceStatusMixin
from aquarea_device_statistics import AquareaDeviceStatisticsMixin
from mqtt_discovery import AquareaDiscoveryMixin

TRANSLATION_FILE = "translation.json"
logger = logging.getLogger(__name__)


class Aquarea(
    AquareaHTTPMixin,
    AquareaLoginMixin,
    AquareaSettingsMixin,
    AquareaDeviceStatusMixin,
    AquareaDeviceStatisticsMixin,
    AquareaDiscoveryMixin,
):
    def __init__(self):
        self.aquarea_service_cloud_url: str = ""
        self.aquarea_service_cloud_login: str = ""
        self.aquarea_service_cloud_password: str = ""
        self.log_sec_offset: int = 0

        self.data_queue: asyncio.Queue = None
        self.status_queue: asyncio.Queue = None
        self.session: aiohttp.ClientSession = None

        self.dictionary_web_ui: dict[str, str] = {}
        self.reverse_dictionary_web_ui: dict[str, str] = {}
        self.users_map: dict[str, AquareaEndUserJSON] = {}
        self.translation: dict[str, AquareaFunctionDescription] = {}
        self.reverse_translation: dict[str, str] = {}
        self.log_items: list[AquareaLogItem] = []
        self.aquarea_settings: AquareaFunctionSettingGetJSON = AquareaFunctionSettingGetJSON()
        self._shiesuahruefutohkun: str = ""

    def load_translations(self, filename: str):
        raw: dict = json.loads(Path(filename).read_text(encoding="utf-8"))
        self.translation = {
            key: AquareaFunctionDescription.from_dict(val)
            for key, val in raw.items()
        }
        self.reverse_translation = {
            descr.name: key
            for key, descr in self.translation.items()
            if "setting-user-select" in key
        }

    async def get_shiesuahruefutohkun(self, url: str = None) -> str:
        """Fetch shiesuahruefutohkun from the new installerState API endpoint."""
        import json as _json
        # Must visit /installer/home first to set Referer
        home_url = self.aquarea_service_cloud_url + "installer/home"
        installer_state_url = self.aquarea_service_cloud_url + "page/api/installerState"
        logger.info("[TOKEN] Visiting installer/home first")
        await self.http_get(home_url)
        logger.info("[TOKEN] Fetching installerState with Referer")
        try:
            body = await self.http_get_with_referer(installer_state_url, home_url)
            logger.info("[TOKEN] Response: %s", body[:500])
            data = _json.loads(body)
            token = data.get("shiesuahruefutohkun")
            if not token:
                logger.error("[TOKEN] No shiesuahruefutohkun in response: %s", data)
                raise ValueError("Could not extract shiesuahruefutohkun from installerState")
            logger.info("[TOKEN] Got token: %s", token)
            return token
        except _json.JSONDecodeError as e:
            logger.error("[TOKEN] JSON decode error: %s — body: %s", e, body[:500])
            raise ValueError(f"Could not parse installerState response: {e}")

    async def get_end_user_shiesuahruefutohkun(self, user: AquareaEndUserJSON) -> str:
        """Reuse cached token if available, otherwise fetch fresh one."""
        if hasattr(self, "_shiesuahruefutohkun") and self._shiesuahruefutohkun:
            return self._shiesuahruefutohkun
        return await self.get_shiesuahruefutohkun()

    @staticmethod
    def extract_shiesuahruefutohkun(body: bytes) -> str:
        """Legacy method kept for compatibility."""
        import re as _re, json as _json
        # Try new JSON format first
        try:
            data = _json.loads(body)
            token = data.get("shiesuahruefutohkun")
            if token:
                return token
        except Exception:
            pass
        # Fall back to old HTML pattern
        match = _re.search(
            r"const shiesuahruefutohkun = '(.+)'",
            body.decode("utf-8", errors="replace"),
        )
        if match:
            return match.group(1)
        raise ValueError("Could not extract shiesuahruefutohkun")

    async def feed_data_from_aquarea(self):
        for user in self.users_map.values():
            try:
                shiesuahruefutohkun = await self.get_end_user_shiesuahruefutohkun(user)
            except Exception as e:
                await self.status_queue.put(False)
                logger.error("%s", e)
                logger.info("Will attempt to log in again")
                await self.aquarea_setup()
                continue

            try:
                settings = await self.get_device_settings(user, shiesuahruefutohkun)
                await self.data_queue.put(settings)
            except Exception as e:
                logger.error("get_device_settings: %s", e)

            try:
                device_status = await self.parse_device_status(user, shiesuahruefutohkun)
                await self.data_queue.put(device_status)
            except Exception as e:
                logger.error("parse_device_status: %s", e)

            try:
                log_data = await self.get_device_log_information(user, shiesuahruefutohkun)
                if log_data:
                    await self.data_queue.put(log_data)
            except Exception as e:
                logger.error("get_device_log_information: %s", e)


async def aquarea_handler(
    ctx: asyncio.Event,
    config: dict,
    data_queue: asyncio.Queue,
    command_queue: asyncio.Queue,
    status_queue: asyncio.Queue,
):
    logger.info("Starting Aquarea Service Cloud handler")

    aq = Aquarea()
    aq.aquarea_service_cloud_url = config["AquareaServiceCloudURL"]
    aq.aquarea_service_cloud_login = config["AquareaServiceCloudLogin"]
    aq.aquarea_service_cloud_password = config["AquareaServiceCloudPassword"]
    aq.log_sec_offset = config.get("LogSecOffset", 0)
    aq.data_queue = data_queue
    aq.status_queue = status_queue

    aq.load_translations(TRANSLATION_FILE)

    pool_interval = float(config["PoolInterval"])
    timeout_sec = float(config.get("AquareaTimeout", 30))

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    aq.session = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=ssl_ctx),
        timeout=aiohttp.ClientTimeout(total=timeout_sec),
    )

    logger.info("Attempting to log in to Aquarea Service Cloud")
    while not await aq.aquarea_setup():
        pass
    logger.info("Logged in to Aquarea Service Cloud")

    async def poll_loop():
        while not ctx.is_set():
            await aq.feed_data_from_aquarea()
            await asyncio.sleep(pool_interval)

    async def command_loop():
        while not ctx.is_set():
            try:
                cmd: AquareaCommand = await asyncio.wait_for(
                    command_queue.get(), timeout=1.0
                )
                await aq.send_setting(cmd)
            except asyncio.TimeoutError:
                pass

    try:
        await asyncio.gather(poll_loop(), command_loop())
    finally:
        await aq.session.close()