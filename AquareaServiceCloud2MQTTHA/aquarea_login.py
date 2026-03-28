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
                # On vérifie que ce n'est pas None avant d'envoyer
                if ha_config:
                    await self.data_queue.put(ha_config)
            except Exception as e:
                logger.error("Erreur settings: %s", e)

            try:
                # IMPORTANT: parse_device_status renvoie les données 'state' (1 min)
                status_data = await self.parse_device_status(user, shiesuahruefutohkun)
                if status_data:
                    # On crée les entités pour le dossier 'state'
                    ha_config_state = self.encode_sensors(status_data, user)
                    if ha_config_state:
                        await self.data_queue.put(ha_config_state)
                    # Et on envoie les valeurs
                    await self.data_queue.put(status_data)
            except Exception as e:
                logger.error("Erreur status: %s", e)

            try:
                log_settings = await self.get_device_log_information(user, shiesuahruefutohkun)
                if log_settings:
                    ha_config = self.encode_sensors(log_settings, user)
                    if ha_config:
                        await self.data_queue.put(ha_config)
            except Exception as e:
                logger.error("Erreur logs: %s", e)

    async def aquarea_login(self):
        shiesuahruefutohkun = await self.get_shiesuahruefutohkun(
            self.aquarea_service_cloud_url
        )
        raw = (self.aquarea_service_cloud_login + self.aquarea_service_cloud_password).encode()
        password_md5 = hashlib.md5(raw).hexdigest()

        b = await self.http_post(
            self.aquarea_service_cloud_url + "installer/api/auth/login",
            {
                "var.loginId": self.aquarea_service_cloud_login,
                "var.password": password_md5,
                "var.inputOmit": "false",
                "shiesuahruefutohkun": shiesuahruefutohkun,
            },
        )
        login = AquareaLoginJSON.from_dict(json.loads(b))
        if login.error_code != 0:
            raise RuntimeError(f"Aquarea login error code: {login.error_code}")

    async def aquarea_installer_home(self):
        body = await self.http_get(self.aquarea_service_cloud_url + "installer/home")
        shiesuahruefutohkun = self.extract_shiesuahruefutohkun(body)
        self.extract_dictionary(body)

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
        """Fetch UI string translations from new page/api/text endpoints (SPA migration)."""
        import json as _json

        # Fetch text dictionaries from the new JSON API
        # Types: 2006=status labels, 2903=log item labels, 2000=misc, 2999=ui strings
        for type_id in ["2000", "2006", "2903", "2999"]:
            try:
                body = await self.http_get(
                    self.aquarea_service_cloud_url
                    + f"page/api/text?var.types=%5B%22{type_id}%22%5D"
                )
                data = _json.loads(body)
                if data.get("errorCode") == 0 and "text" in data:
                    self.dictionary_web_ui.update(data["text"])
            except Exception as e:
                logger.warning("Could not fetch text type %s: %s", type_id, e)

        # Build reverse dictionary (needed for changing settings)
        self.reverse_dictionary_web_ui = {v: k for k, v in self.dictionary_web_ui.items()}
        logger.info("Dictionary loaded: %d entries", len(self.dictionary_web_ui))

        # Fetch log item schema from the statistics API endpoint
        # (replaces scraping 'var logItems = $.parseJSON(...)' from old HTML pages)
        await self._fetch_log_items_from_api(user)

    async def _fetch_log_items_from_api(self, user: AquareaEndUserJSON):
        """Fetch log item schema from installer/api/function/statistics (new SPA API)."""
        import json as _json

        # Need a valid token — use cached one
        token = getattr(self, "_shiesuahruefutohkun", "")
        if not token:
            logger.warning("_fetch_log_items_from_api: no token available, skipping")
            return

        try:
            b = await self.http_post_with_referer(
                self.aquarea_service_cloud_url + "installer/api/function/statistics",
                self.aquarea_service_cloud_url + "installer/functionStatus",
                {"var.deviceId": user.device_id, "shiesuahruefutohkun": token},
            )
            data = _json.loads(b)
            if data.get("errorCode", -1) != 0:
                logger.warning("_fetch_log_items_from_api: errorCode=%s", data.get("errorCode"))
                return

            raw_items = data.get("logItems")
            if not raw_items:
                logger.warning("_fetch_log_items_from_api: no logItems field in response")
                return

            keys: list = _json.loads(raw_items)
            logger.info("_fetch_log_items_from_api: got %d log item keys", len(keys))
            self.extract_log_items_from_keys(keys)
            logger.info("_fetch_log_items_from_api: built %d log items", len(self.log_items))

        except Exception as e:
            logger.warning("_fetch_log_items_from_api: failed: %s", e)

    def extract_log_items_from_keys(self, keys: list):
        """Build self.log_items from an ordered list of 2903-xxxx dictionary keys."""
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