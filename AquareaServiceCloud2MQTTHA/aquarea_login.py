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
                if log_settings and self.log_items:
                    ha_config = self.encode_sensors(log_settings, user)
                    await self.data_queue.put(ha_config)
                elif log_settings and not self.log_items:
                    logger.warning(
                        "aquarea_initial_fetch: log schema unknown — "
                        "skipping HA discovery for log sensors."
                    )
                    await self.data_queue.put(log_settings)
            except Exception as e:
                logger.error("get_device_log_information/encode_sensors: %s", e)
        logger.info("aquarea_initial_fetch: done")

    async def fetch_log_items(self, user: "AquareaEndUserJSON", shiesuahruefutohkun: str):
        """Fetch log item schema from installer/api/function/statistics endpoint.

        The response contains:
          - logItems: JSON string with ordered list of 2903-xxxx keys
          - The type-2903 text dictionary (fetched in get_dictionary) maps these to labels.
        """
        import json as _json
        base = self.aquarea_service_cloud_url

        # Fetch type-2903 text dictionary if not yet loaded
        if not any(k.startswith("2903-") for k in self.dictionary_web_ui):
            logger.info("fetch_log_items: fetching type-2903 text dictionary")
            try:
                body = await self.http_get(base + "page/api/text?var.types=%5B%222903%22%5D")
                data = _json.loads(body)
                if data.get("errorCode") == 0 and "text" in data:
                    self.dictionary_web_ui.update(data["text"])
                    self.reverse_dictionary_web_ui = {v: k for k, v in self.dictionary_web_ui.items()}
                    logger.info("fetch_log_items: loaded %d type-2903 entries", len(data["text"]))
            except Exception as e:
                logger.warning("fetch_log_items: could not load type-2903: %s", e)

        # Call the statistics API which returns the ordered logItems list
        logger.info("fetch_log_items: calling installer/api/function/statistics")
        try:
            b = await self.http_post_with_referer(
                base + "installer/api/function/statistics",
                base + "installer/functionStatus",
                {"var.deviceId": user.device_id, "shiesuahruefutohkun": shiesuahruefutohkun},
            )
            data = _json.loads(b)
            logger.info("fetch_log_items: response keys=%s", list(data.keys()))

            if data.get("errorCode", -1) != 0:
                logger.warning("fetch_log_items: errorCode=%s", data.get("errorCode"))
                return

            log_items_raw = data.get("logItems")
            if not log_items_raw:
                logger.warning("fetch_log_items: no logItems in response")
                return

            # logItems is a JSON string of a list of 2903-xxxx keys
            keys: list[str] = _json.loads(log_items_raw)
            logger.info("fetch_log_items: got %d log item keys", len(keys))

            # Build log_items by resolving each key through the 2903 dictionary,
            # then parsing the label string (same format as old HTML logItems)
            self.log_items = []
            self.extract_log_items_from_keys(keys)
            logger.info("fetch_log_items: extracted %d log items", len(self.log_items))

        except Exception as e:
            logger.warning("fetch_log_items: statistics endpoint failed: %s", e)

    def extract_log_items_from_keys(self, keys: list):
        """Build self.log_items from a list of 2903-xxxx dictionary keys."""
        unit_re = re.compile(r"(.+)\[(.+)\]")
        multi_choice_re = re.compile(r"(\d+)\s*:\s*([^,]+),?")
        remove_brackets_re = re.compile(r"\(.+\)")

        self.log_items = []
        for key in keys:
            val = self.dictionary_web_ui.get(key, key)
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
                    AquareaLogItem(name=name, unit="", values={m[0]: m[1].strip() for m in subs})
                )
            else:
                self.log_items.append(AquareaLogItem(name=name, unit=unit_part, values={}))

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