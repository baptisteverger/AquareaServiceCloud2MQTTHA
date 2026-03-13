"""
Device settings — equivalent of aquareaDeviceSettings.go
"""

import json
import logging

from aquarea_types import AquareaEndUserJSON, AquareaFunctionSettingGetJSON

logger = logging.getLogger(__name__)


class AquareaSettingsMixin:

    async def send_setting(self, cmd) -> None:
        """Send a setting command to Aquarea Service Cloud."""
        if cmd.value == "----":
            logger.info("Dummy value - not sending to Aquarea Service Cloud")
            return

        if not self.aquarea_settings.settings_background_data:
            logger.info("Background data not received yet")
            return

        function_name = self.reverse_translation.get(cmd.setting)
        if not function_name:
            logger.warning("Unknown setting: %s", cmd.setting)
            return

        function_name_post = function_name.replace(
            "function-setting-user-select-", "userSelect"
        )
        function_info = self.translation.get(function_name)
        value = cmd.value

        if function_info:
            if function_info.kind == "basic":
                value = self.reverse_dictionary_web_ui.get(value, value)
                value = function_info.reverse_values.get(value, value)

            elif function_info.kind == "placeholder":
                i = int(value, 0)
                if "HolidayMode" not in cmd.setting:
                    i += 128
                value = f"0x{i & 0xFF:X}"

        user = self.users_map.get(cmd.device_id)
        if not user:
            logger.warning("Unknown device: %s", cmd.device_id)
            return

        shiesuahruefutohkun = await self.get_end_user_shiesuahruefutohkun(user)
        bg = self.aquarea_settings.settings_background_data

        logger.info("Setting %s to %s on %s", cmd.setting, value, cmd.device_id)
        await self.http_post(
            self.aquarea_service_cloud_url + "/installer/api/function/setting/user/set",
            {
                "var.deviceId": user.device_id,
                "var.preOperation": bg.get("0x80", {}).get("value", ""),
                "var.preMode": bg.get("0xE0", {}).get("value", ""),
                "var.preTank": bg.get("0xE1", {}).get("value", ""),
                f"var.{function_name_post}": value,
                "shiesuahruefutohkun": shiesuahruefutohkun,
            },
        )

    async def get_device_settings(
        self, user: AquareaEndUserJSON, shiesuahruefutohkun: str
    ) -> dict[str, str]:
        b = await self.http_post(
            self.aquarea_service_cloud_url + "/installer/api/function/setting/get",
            {
                "var.deviceId": user.device_id,
                "shiesuahruefutohkun": shiesuahruefutohkun,
            },
        )
        self.aquarea_settings = AquareaFunctionSettingGetJSON.from_dict(json.loads(b))
        settings: dict[str, str] = {}

        for key, val in self.aquarea_settings.setting_data_info.items():
            if "user" not in key:
                continue

            if key not in self.translation:
                logger.warning("No metadata in translation.json for: %s", key)
                continue

            translation = self.translation[key]
            value = None

            if val.type == "basic-text":
                value = self.dictionary_web_ui.get(val.text_value, "")

            elif val.type == "select":
                if translation.kind == "basic":
                    raw = translation.values.get(val.selected_value, "")
                    value = self.dictionary_web_ui.get(raw, raw)

                    options = "\n".join(
                        self.dictionary_web_ui.get(opt, opt)
                        for opt in translation.values.values()
                    )
                    settings[
                        f"aquarea/{user.gwid}/settings/{translation.name}/options"
                    ] = options

                elif translation.kind == "placeholder":
                    i = int(val.selected_value, 0)
                    if "HolidayMode" not in translation.name:
                        i -= 128
                    # Two's complement signed 8-bit
                    value = str(int.from_bytes((i & 0xFF).to_bytes(1, "big"), "big", signed=True))

            elif val.type == "placeholder-text":
                value = val.placeholder

            if value is not None:
                settings[f"aquarea/{user.gwid}/settings/{translation.name}"] = value

        # DEBUG TEMPORAIRE
        for k, v in settings.items():
            logger.info("[DEBUG SETTINGS] %s = %s", k, v)
        return settings