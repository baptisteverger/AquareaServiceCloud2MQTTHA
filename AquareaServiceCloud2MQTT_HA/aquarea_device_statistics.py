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

        indices = ",".join(str(i) for i in range(len(self.log_items)))
        value_list = f'{{"logItems":[{indices},]}}'
        start_date = int(time.time()) - self.log_sec_offset

        b = await self.http_post(
            self.aquarea_service_cloud_url + "/installer/api/data/log",
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

        device_log: dict[int, list[str]] = json.loads(log_data.log_data)
        if not device_log:
            return None

        last_key = max(device_log.keys())
        stats: dict[str, str] = {}

        for i, val in enumerate(device_log[last_key]):
            item = self.log_items[i]
            topic = f"aquarea/{user.gwid}/log/{item.name}"

            if item.unit:
                stats[f"{topic}/unit"] = item.unit

            val = item.values.get(val, val)
            stats[topic] = val

        stats[f"aquarea/{user.gwid}/log/Timestamp"] = str(last_key)
        stats[f"aquarea/{user.gwid}/log/CurrentError"] = str(log_data.error_code)
        return stats
