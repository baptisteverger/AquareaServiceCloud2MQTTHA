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
        for user in self.users_map.values():
            try:
                shiesuahruefutohkun = await self.get_end_user_shiesuahruefutohkun(user)
            except Exception:
                continue

            try:
                settings = await self.get_device_settings(user, shiesuahruefutohkun)
                ha_config = self.encode_switches(settings, user)
                await self.data_queue.put(ha_config)
            except Exception as e:
                logger.error("%s", e)

            try:
                await self.parse_device_status(user, shiesuahruefutohkun)
            except Exception as e:
                logger.error("%s", e)

            try:
                log_settings = await self.get_device_log_information(user, shiesuahruefutohkun)
                if log_settings:
                    ha_config = self.encode_sensors(log_settings, user)
                    await self.data_queue.put(ha_config)
            except Exception as e:
                logger.error("%s", e)

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

        # Step 3: fetch token — only available after successful login
        self._shiesuahruefutohkun = await self.get_shiesuahruefutohkun()
        logger.info("Got shiesuahruefutohkun: %s", self._shiesuahruefutohkun)

    async def aquarea_installer_home(self):
        body = await self.http_get(self.aquarea_service_cloud_url + "installer/home")
        self.extract_dictionary(body)
        shiesuahruefutohkun = self._shiesuahruefutohkun

        b = await self.http_post(
            self.aquarea_service_cloud_url + "/installer/api/endusers",
            {
                "var.name": "",
                "var.deviceId": "",
                "var.idu": "",
                "var.odu": "",
                "var.sortItem": "userName",
                "var.sortOrder": "0",
                "var.offset": "0",
                "var.limit": "999",
                "var.mapSizeX": "0",
                "var.mapSizeY": "0",
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
        """Fetch UI string translations from all sub-pages."""
        await self.get_end_user_shiesuahruefutohkun(user)

        body = await self.http_post(
            self.aquarea_service_cloud_url + "installer/functionSetting", None
        )
        self.extract_dictionary(body)

        # Build reverse dictionary (needed for changing settings)
        self.reverse_dictionary_web_ui = {v: k for k, v in self.dictionary_web_ui.items()}

        body = await self.http_post(
            self.aquarea_service_cloud_url + "installer/functionStatus", None
        )
        self.extract_dictionary(body)

        body = await self.http_post(
            self.aquarea_service_cloud_url + "installer/functionStatistics", None
        )
        self.extract_dictionary(body)
        self.extract_log_items(body)

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