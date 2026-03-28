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

_UNIT_RE = re.compile(r"(.+)\[(.+)\]")
_MULTI_CHOICE_RE = re.compile(r"(\d+)\s*:\s*([^,\]]+)")
_REMOVE_PARENS_RE = re.compile(r"\(.+?\)")


def _key_to_index(key: str) -> int:
    """Convertit '2903-01e8' en indice numérique pour var.logItems."""
    hex_part = key.split("-")[1]
    return (int(hex_part, 16) - 0x0104) // 4


def _parse_log_label(raw_label: str) -> AquareaLogItem:
    label = raw_label.replace("(Actual)", "Actual").replace("(Target)", "Target")
    label = _REMOVE_PARENS_RE.sub("", label).strip()

    split = _UNIT_RE.search(label)
    if not split:
        name = label.strip().title().replace(" ", "").replace(":", "")
        return AquareaLogItem(name=name, unit="", values={})

    name_raw = split.group(1).strip().title().replace(" ", "").replace(":", "")
    unit_part = split.group(2).strip()

    choices = _MULTI_CHOICE_RE.findall(unit_part)
    if choices:
        return AquareaLogItem(
            name=name_raw,
            unit="",
            values={m[0]: m[1].strip() for m in choices},
        )
    return AquareaLogItem(name=name_raw, unit=unit_part, values={})


class AquareaLoginMixin:

    async def aquarea_setup(self) -> bool:
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
        """First data fetch and Home Assistant discovery.

        Order matters:
          1. parse_device_status  — navigates to functionStatus, establishes
                                    device context in the server session.
          2. fetch_log_items      — /page/api/functionStatistics requires a
                                    valid session with a selected device.
          3. get_device_settings  — functionSetting, also needs device context.
          4. get_device_log_information — uses log_items built in step 2.
        """
        for user in self.users_map.values():
            try:
                shiesuahruefutohkun = await self.get_end_user_shiesuahruefutohkun(user)
            except Exception:
                continue

            # 1. Status — establishes device session context
            try:
                status_data = await self.parse_device_status(user, shiesuahruefutohkun)
                if status_data:
                    ha_config_state = self.encode_sensors(status_data, user)
                    if ha_config_state:
                        await self.data_queue.put(ha_config_state)
                    await self.data_queue.put(status_data)
            except Exception as e:
                logger.error("Erreur status: %s", e)

            # 2. Log items schema — needs device context established above
            if not self.log_items:
                try:
                    await self.fetch_log_items(shiesuahruefutohkun, self._log_labels_2903)
                except Exception as e:
                    logger.error("Erreur fetch_log_items: %s", e)

            # 3. Settings
            try:
                settings = await self.get_device_settings(user, shiesuahruefutohkun)
                ha_config = self.encode_switches(settings, user)
                if ha_config:
                    await self.data_queue.put(ha_config)
            except Exception as e:
                logger.error("Erreur settings: %s", e)

            # 4. Logs
            try:
                log_data = await self.get_device_log_information(user, shiesuahruefutohkun)
                if log_data:
                    ha_config = self.encode_sensors(log_data, user)
                    if ha_config:
                        await self.data_queue.put(ha_config)
            except Exception as e:
                logger.error("Erreur logs: %s", e)

    async def aquarea_login(self):
        import json as _json

        await self.http_get(self.aquarea_service_cloud_url + "page/api/settings")

        raw = (self.aquarea_service_cloud_login + self.aquarea_service_cloud_password).encode()
        password_md5 = hashlib.md5(raw).hexdigest()
        b = await self.http_post(
            self.aquarea_service_cloud_url + "installer/api/auth/login",
            {
                "var.loginId": self.aquarea_service_cloud_login,
                "var.password": password_md5,
                "var.inputOmit": "true",
                "shiesuahruefutohkun": "undefined",
            },
        )
        login = AquareaLoginJSON.from_dict(_json.loads(b))
        if login.error_code != 0:
            raise RuntimeError(f"Aquarea login error code: {login.error_code}")

        await self.http_get(self.aquarea_service_cloud_url + "installer/home")
        home_url = self.aquarea_service_cloud_url + "installer/home"
        installer_state_url = self.aquarea_service_cloud_url + "page/api/installerState"
        body = await self.http_get_with_referer(installer_state_url, home_url)
        data = _json.loads(body)
        token = data.get("shiesuahruefutohkun")
        if not token:
            raise ValueError(f"No shiesuahruefutohkun in installerState: {data}")
        self._shiesuahruefutohkun = token
        logger.info("Login OK, token: %s", token)

    async def aquarea_installer_home(self):
        shiesuahruefutohkun = self._shiesuahruefutohkun

        b = await self.http_post(
            self.aquarea_service_cloud_url + "installer/api/endusers",
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
        """Fetch UI string translations via JSON APIs.
        Log items schema is fetched later in aquarea_initial_fetch, after
        device context is established by parse_device_status.
        """
        base = self.aquarea_service_cloud_url
        home_ref = base + "installer/home"

        for type_code in ["2000", "2006", "2999"]:
            try:
                body = await self.http_get_with_referer(
                    base + f"page/api/text?var.types=%5B%22{type_code}%22%5D",
                    home_ref,
                )
                data = json.loads(body)
                if data.get("errorCode", -1) == 0:
                    self.dictionary_web_ui.update(data.get("text", {}))
            except Exception as e:
                logger.warning("get_dictionary type %s: %s", type_code, e)

        # Stocker les labels 2903 pour les réutiliser dans fetch_log_items
        self._log_labels_2903: dict[str, str] = {}
        try:
            body = await self.http_get_with_referer(
                base + "page/api/text?var.types=%5B%222903%22%5D",
                home_ref,
            )
            data = json.loads(body)
            if data.get("errorCode", -1) == 0:
                self._log_labels_2903 = data.get("text", {})
                self.dictionary_web_ui.update(self._log_labels_2903)
        except Exception as e:
            logger.warning("get_dictionary type 2903: %s", e)

        self.reverse_dictionary_web_ui = {v: k for k, v in self.dictionary_web_ui.items()}

    async def fetch_log_items(self, token: str, log_labels_2903: dict[str, str]):
        """
        Appelle /page/api/functionStatistics pour obtenir la liste ordonnée des
        clés 2903-xxxx. Doit être appelé APRÈS parse_device_status.
        """
        base = self.aquarea_service_cloud_url
        ref = base + "installer/functionStatus"  # referer correct après navigation

        body = await self.http_get_with_referer(
            base + f"page/api/functionStatistics?shiesuahruefutohkun={token}",
            ref,
        )
        data = json.loads(body)

        if data.get("errorCode", -1) != 0:
            raise RuntimeError(f"fetch_log_items errorCode={data.get('errorCode')}")

        raw_items = data.get("logItems", "[]")
        ordered_keys: list[str] = json.loads(raw_items) if isinstance(raw_items, str) else raw_items

        self.log_item_indices = [_key_to_index(k) for k in ordered_keys]
        self.log_items = [_parse_log_label(log_labels_2903.get(k, k)) for k in ordered_keys]

        logger.info("fetch_log_items: %d log items, indices sample: %s",
                    len(self.log_items), self.log_item_indices[:10])

    # ------------------------------------------------------------------
    # Legacy — kept for reference, no longer called
    # ------------------------------------------------------------------

    def extract_dictionary(self, body: bytes):
        match = re.search(
            r"const jsonMessage = eval\('\((.+)\)'", body.decode("utf-8", errors="replace")
        )
        if match:
            result = match.group(1).replace("\\", "")
            self.dictionary_web_ui.update(json.loads(result))

    def extract_log_items(self, body: bytes):
        pass