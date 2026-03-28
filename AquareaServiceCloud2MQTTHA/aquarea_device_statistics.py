"""
Device statistics / log — equivalent of aquareaDeviceStatistics.go
"""

import json
import logging
import time

from aquarea_types import AquareaEndUserJSON, AquareaLogDataJSON

logger = logging.getLogger(__name__)


class AquareaDeviceStatisticsMixin:

    async def get_device_log_information(
        self, user: AquareaEndUserJSON, shiesuahruefutohkun: str
    ) -> dict[str, str] | None:

        # Utiliser les indices réels (avec trous) tels que renvoyés par
        # /page/api/functionStatistics — le navigateur fait pareil.
        indices: list[int] = getattr(self, "log_item_indices", None) or []
        if indices:
            value_list = json.dumps({"logItems": indices})
        else:
            value_list = '{"logItems":[]}'

        start_date = int(time.time()) - self.log_sec_offset

        b = await self.http_post(
            self.aquarea_service_cloud_url + "installer/api/data/log",
            {
                "var.deviceId": user.device_id,
                "shiesuahruefutohkun": shiesuahruefutohkun,
                "var.target": "0",
                "var.startDate": f"{start_date}000",
                "var.logItems": value_list,
            },
        )

        raw = json.loads(b)
        log_data = AquareaLogDataJSON.from_dict(raw)
        if not log_data.log_data:
            return None

        device_log: dict[str, list[str]] = json.loads(log_data.log_data)
        if not device_log:
            return None

        last_key = max(device_log.keys(), key=lambda k: int(k))
        stats: dict[str, str] = {}

        for i, val in enumerate(device_log[last_key]):
            if i < len(self.log_items):
                item = self.log_items[i]
                name = item.name
                if item.unit:
                    stats[f"aquarea/{user.gwid}/log/{name}/unit"] = item.unit
                val = item.values.get(str(val), str(val))
            else:
                name = f"item{i:03d}"

            stats[f"aquarea/{user.gwid}/log/{name}"] = str(val)

        stats[f"aquarea/{user.gwid}/log/Timestamp"] = str(last_key)
        stats[f"aquarea/{user.gwid}/log/CurrentError"] = str(log_data.error_code)
        return stats