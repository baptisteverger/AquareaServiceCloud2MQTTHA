"""
Device statistics / log — equivalent of aquareaDeviceStatistics.go
"""

import json
import time

from aquarea_types import AquareaEndUserJSON, AquareaLogDataJSON


class AquareaDeviceStatisticsMixin:

    async def get_device_log_information(
        self, user: AquareaEndUserJSON, shiesuahruefutohkun: str
    ) -> dict[str, str] | None:

        # Build a valid JSON logItems list; omit indices when schema is unknown
        # so the server returns all available items.
        # Note: no leading slash — base URL already ends with '/'.
        # Note: no trailing comma inside the array — that is invalid JSON.
        if self.log_items:
            indices = ",".join(str(i) for i in range(len(self.log_items)))
            value_list = f'{{"logItems":[{indices}]}}'
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

        log_data = AquareaLogDataJSON.from_dict(json.loads(b))
        if not log_data.log_data:
            return None

        device_log: dict[str, list[str]] = json.loads(log_data.log_data)
        if not device_log:
            return None

        # Keys are timestamps as strings; pick the most recent one numerically.
        last_key = max(device_log.keys(), key=lambda k: int(k))
        stats: dict[str, str] = {}

        for i, val in enumerate(device_log[last_key]):
            if i < len(self.log_items):
                item = self.log_items[i]
                name = item.name
                if item.unit:
                    stats[f"aquarea/{user.gwid}/log/{name}/unit"] = item.unit
                val = item.values.get(val, val)
            else:
                # Schema not yet loaded — publish under a numeric name so data
                # is not silently lost while log_items is being populated.
                name = f"item{i:03d}"

            stats[f"aquarea/{user.gwid}/log/{name}"] = val

        stats[f"aquarea/{user.gwid}/log/Timestamp"] = str(last_key)
        stats[f"aquarea/{user.gwid}/log/CurrentError"] = str(log_data.error_code)
        return stats