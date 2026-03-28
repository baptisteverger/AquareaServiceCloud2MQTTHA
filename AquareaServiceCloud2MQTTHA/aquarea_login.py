"""
Login & initialisation — equivalent of aquareaLogin.go
"""

import hashlib
import json
import logging
import re

from aquarea_types import (
    AquareaEndUserJSON,
    AquareaEndUsersListJSON,
    AquareaLoginJSON,
    AquareaLogItem,
)

logger = logging.getLogger(__name__)


class AquareaLoginMixin:

    async def aquarea_setup(self) -> bool:
        """Full login sequence. Returns True on success."""
        try:
            await self.aquarea_login()
        except Exception as e:
            logger.error("Login failed: %s", e)
            return False

        try:
            await self.aquarea_installer_home()
        except Exception as e:
            logger.error("Installer home failed: %s", e)
            return False

        await self.aquarea_initial_fetch()
        return True

    async def aquarea_initial_fetch(self):
        """First data fetch and Home Assistant discovery."""
        logger.info("aquarea_initial_fetch: start")
        for user in self.users_map.values():
            logger.info("aquarea_initial_fetch: processing user %s", user.gwid)
            try:
                shiesuahruefutohkun = await self.get_end_user_shiesuahruefutohkun(user)
            except Exception as e:
                logger.error("get_end_user_shiesuahruefutohkun failed: %s", e)
                continue

            try:
                logger.info("aquarea_initial_fetch: calling parse_device_status first (activates device in session)")
                await self.parse_device_status(user, shiesuahruefutohkun)
            except Exception as e:
                logger.error("parse_device_status: %s", e)

            try:
                logger.info("aquarea_initial_fetch: calling get_device_settings")
                settings = await self.get_device_settings(user, shiesuahruefutohkun)
                logger.info("aquarea_initial_fetch: settings count=%d", len(settings))
                ha_config = self.encode_switches(settings, user)
                await self.data_queue.put(ha_config)
            except Exception as e:
                logger.error("get_device_settings/encode_switches: %s", e)

            try:
                logger.info("aquarea_initial_fetch: fetching log item schema")
                await self.fetch_log_items(user, shiesuahruefutohkun)
                logger.info("aquarea_initial_fetch: log_items count=%d", len(self.log_items))
            except Exception as e:
                logger.error("fetch_log_items: %s", e)

            try:
                logger.info("aquarea_initial_fetch: calling get_device_log_information")
                log_settings = await self.get_device_log_information(user, shiesuahruefutohkun)
                if log_settings:
                    ha_config = self.encode_sensors(log_settings, user)
                    await self.data_queue.put(ha_config)
            except Exception as e:
                logger.error("get_device_log_information/encode_sensors: %s", e)
        logger.info("aquarea_initial_fetch: done")

    async def aquarea_login(self):
        # Step 1: fetch settings to establish session/cookie
        logger.info("Fetching page/api/settings to establish session")
        await self.http_get(self.aquarea_service_cloud_url + "page/api/settings")

        # Step 2: login — browser sends shiesuahruefutohkun as undefined
        raw = (self.aquarea_service_cloud_login + self.aquarea_service_cloud_password).encode()
        password_md5 = hashlib.md5(raw).hexdigest()
        logger.info("Posting login for %s", self.aquarea_service_cloud_login)
        b = await self.http_post(
            self.aquarea_service_cloud_url + "installer/api/auth/login",
            {
                "var.loginId": self.aquarea_service_cloud_login,
                "var.password": password_md5,
                "var.inputOmit": "true",
                "shiesuahruefutohkun": "undefined",
            },
        )
        logger.info("Login response: %s", b[:200])
        login = AquareaLoginJSON.from_dict(json.loads(b))
        if login.error_code != 0:
            raise RuntimeError(f"Aquarea login error code: {login.error_code}")

        # Step 3: replicate exact browser sequence after login
        import json as _json
        base = self.aquarea_service_cloud_url

        # Visit installer/home HTML to get Referer context for installerState
        logger.info("Visiting installer/home")
        self._installer_home_body = await self.http_get(base + "installer/home")

        # Fetch installerState WITH Referer header
        installer_state_url = base + "page/api/installerState"
        home_url = base + "installer/home"
        body = await self.http_get_with_referer(installer_state_url, home_url)
        logger.info("installerState response: %s", body[:200])
        data = _json.loads(body)
        token = data.get("shiesuahruefutohkun")
        if not token:
            raise ValueError(f"No token in installerState: {data}")
        self._shiesuahruefutohkun = token
        logger.info("Got shiesuahruefutohkun: %s", token)

        # Replicate remaining browser calls to finalize API session
        await self.http_get(base + "page/api/text?var.types=%5B%222000%22%5D")
        await self.http_get(base + "page/api/text?var.types=%5B%222005%22%5D")
        await self.http_get(base + "page/api/text?var.types=%5B%222999%22%5D")
        await self.http_get(base + "page/api/text?var.types=%5B%223051%22%5D")
        await self.http_get(base + f"page/api/onetrust?shiesuahruefutohkun={token}")
        await self.http_get(base + f"page/api/home?shiesuahruefutohkun={token}")

        # Navigate to functionStatus + functionSetting so JSESSIONID is
        # marked by the server as having access to settings endpoints
        logger.info("Navigating to functionStatus and functionSetting")
        ref_status = base + "installer/functionStatus"
        ref_setting = base + "installer/functionSetting"
        await self.http_get_html(base + "installer/functionStatus")
        await self.http_get_with_referer(base + "page/api/installerState", ref_status)
        await self.http_get_with_referer(base + f"page/api/userInfo?shiesuahruefutohkun={token}", ref_status)
        await self.http_get_html(base + "installer/functionSetting")
        await self.http_get_with_referer(base + "page/api/installerState", ref_setting)
        await self.http_get_with_referer(base + f"page/api/userInfo?shiesuahruefutohkun={token}", ref_setting)
        logger.info("Session fully established")

    async def aquarea_installer_home(self):
        shiesuahruefutohkun = self._shiesuahruefutohkun
        logger.info("Using cached token for installer_home: %s", shiesuahruefutohkun)

        b = await self.http_post(
            self.aquarea_service_cloud_url + "/installer/api/endusers",
            {
                "var.sortItem": "userName",
                "var.sortOrder": "0",
                "var.offset": "0",
                "var.limit": "92599",
                "var.readNew": "1",
                "shiesuahruefutohkun": shiesuahruefutohkun,
            },
        )
        end_users_list = AquareaEndUsersListJSON.from_dict(json.loads(b))
        for user in end_users_list.endusers:
            self.users_map[user.gwid] = user
            
        await self.get_dictionary(end_users_list.endusers[0])
        await self.status_queue.put(True)

    async def get_dictionary(self, user: AquareaEndUserJSON):
        """Fetch UI string translations using new page/api/text endpoints."""
        import json as _json
        token = self._shiesuahruefutohkun
        base = self.aquarea_service_cloud_url

        # Fetch text dictionaries from new API
        for type_id in ["2000", "2001", "2005", "2006", "2999", "3051"]:
            try:
                body = await self.http_get(base + f"page/api/text?var.types=%5B%22{type_id}%22%5D")
                data = _json.loads(body)
                if data.get("errorCode") == 0 and "text" in data:
                    self.dictionary_web_ui.update(data["text"])
            except Exception as e:
                logger.warning("Could not fetch text type %s: %s", type_id, e)

        # Build reverse dictionary
        self.reverse_dictionary_web_ui = {v: k for k, v in self.dictionary_web_ui.items()}
        logger.info("Dictionary loaded: %d entries", len(self.dictionary_web_ui))

    def extract_dictionary(self, body: bytes):
        match = re.search(
            r"const jsonMessage = eval\('\((.+)\)'", body.decode("utf-8", errors="replace")
        )
        if match:
            result = match.group(1).replace("\\", "")
            self.dictionary_web_ui.update(json.loads(result))

    async def fetch_log_items(self, user: "AquareaEndUserJSON", shiesuahruefutohkun: str):
        """Populate self.log_items by navigating to the function-data-log SPA page.

        The old code scraped 'var logItems = $.parseJSON(...)' from a server-rendered
        HTML page.  The new Next.js SPA still returns the same embedded variable in the
        HTML shell of installer/function-data-log, so we POST to navigate there (same
        pattern as functionStatus) then try the old regex.  If the variable is gone in
        a future update the method logs a warning and leaves log_items untouched so the
        numeric-fallback in get_device_log_information keeps things running.
        """
        base = self.aquarea_service_cloud_url
        ref = base + "installer/functionStatus"

        logger.info("fetch_log_items: navigating to function-data-log")
        try:
            # The SPA page is reached via POST with gwUid, same as functionStatus.
            body = await self.http_post_navigate(
                base + "installer/function-data-log",
                ref,
                {"var.functionSelectedGwUid": user.gw_uid},
            )
        except Exception as e:
            logger.warning("fetch_log_items: navigation failed (%s), trying plain GET", e)
            try:
                body = await self.http_get_html(base + "installer/function-data-log")
            except Exception as e2:
                logger.warning("fetch_log_items: plain GET also failed: %s", e2)
                return

        self.extract_log_items(body)

        if self.log_items:
            logger.info("fetch_log_items: extracted %d log items from page HTML", len(self.log_items))
        else:
            logger.warning(
                "fetch_log_items: 'var logItems' not found in function-data-log page. "
                "Log sensors will be published with numeric names (item000, item001, …) "
                "until a schema source is found."
            )

    def extract_log_items(self, body: bytes):
        match = re.search(
            r"var logItems = \$\.parseJSON\('(.+)'\);",
            body.decode("utf-8", errors="replace"),
        )
        if not match:
            return

        items: list[str] = json.loads(match.group(1))

        unit_re = re.compile(r"(.+)\[(.+)\]")
        multi_choice_re = re.compile(r"(\d+):([^,]+),?")
        remove_brackets_re = re.compile(r"\(.+\)")

        self.log_items = []
        for val in items:
            val = self.dictionary_web_ui.get(val, val)
            val = val.replace("(Actual)", "Actual").replace("(Target)", "Target")
            val = remove_brackets_re.sub("", val).strip()

            split = unit_re.search(val)
            if not split:
                self.log_items.append(AquareaLogItem(name=val, unit="", values={}))
                continue

            name = split.group(1).strip().title()
            name = name.replace(":", "").replace(" ", "")
            unit_part = split.group(2)

            subs = multi_choice_re.findall(unit_part)
            if subs:
                self.log_items.append(
                    AquareaLogItem(name=name, unit="", values={m[0]: m[1] for m in subs})
                )
            else:
                self.log_items.append(AquareaLogItem(name=name, unit=unit_part, values={}))