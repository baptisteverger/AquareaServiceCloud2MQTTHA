"""
Device status — equivalent of aquareaDeviceStatus.go
"""

import json
import logging

from aquarea_types import AquareaEndUserJSON, AquareaStatusResponseJSON

logger = logging.getLogger(__name__)


class AquareaDeviceStatusMixin:

    async def parse_device_status(
        self, user: AquareaEndUserJSON, shiesuahruefutohkun: str
    ) -> dict[str, str]:
        response = await self.get_device_status(user, shiesuahruefutohkun)
        device_status: dict[str, str] = {}

        for key, val in response.status_data_info.items():
            name = self.translation[key].name if key in self.translation else key

            if val.type == "basic-text":
                value = self.dictionary_web_ui.get(val.text_value, "")
            elif val.type == "simple-value":
                value = val.value
            else:
                value = ""

            # DEBUG TEMPORAIRE
            logger.info("[DEBUG STATUS] %s = %s", name, value)

            device_status[f"aquarea/{user.gwid}/state/{name}"] = value

        return device_status

    async def get_device_status(
        self, user: AquareaEndUserJSON, shiesuahruefutohkun: str
    ) -> AquareaStatusResponseJSON:
        b = await self.http_post(
            self.aquarea_service_cloud_url + "/installer/api/function/status",
            {
                "var.deviceId": user.device_id,
                "shiesuahruefutohkun": shiesuahruefutohkun,
            },
        )
        return AquareaStatusResponseJSON.from_dict(json.loads(b))