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
                value = self.dictionary_web_ui.get(val.text_value, val.text_value)
            elif val.type == "simple-value":
                value = val.value
            else:
                value = ""

            device_status[f"aquarea/{user.gwid}/state/{name}"] = value

        logger.debug(
            "Panasonic status data for device %s (%d values): %s",
            user.gwid,
            len(device_status),
            json.dumps(device_status, ensure_ascii=False),
        )
        return device_status

    async def get_device_status(
        self, user: AquareaEndUserJSON, shiesuahruefutohkun: str
    ) -> AquareaStatusResponseJSON:
        base = self.aquarea_service_cloud_url
        ref = base + "installer/functionStatus"
        home_ref = base + "installer/home"

        await self.http_post_navigate(
            base + "installer/functionStatus",
            home_ref,
            {"var.functionSelectedGwUid": user.gw_uid},
        )

        await self.http_get_with_referer(base + "page/api/installerState", ref)
        await self.http_get_with_referer(base + "page/api/text?var.types=%5B%222006%22%5D", ref)
        await self.http_get_with_referer(base + "page/api/text?var.types=%5B%222999%22%5D", ref)
        await self.http_get_with_referer(base + "page/api/text?var.types=%5B%222000%22%5D", ref)
        await self.http_get_with_referer(
            base + f"page/api/onetrust?shiesuahruefutohkun={shiesuahruefutohkun}", ref
        )
        await self.http_get_with_referer(
            base + f"page/api/userInfo?shiesuahruefutohkun={shiesuahruefutohkun}", ref
        )

        b = await self.http_post_with_referer(
            base + "installer/api/function/status",
            ref,
            {
                "var.deviceId": user.device_id,
                "shiesuahruefutohkun": shiesuahruefutohkun,
            },
        )
        return AquareaStatusResponseJSON.from_dict(json.loads(b))