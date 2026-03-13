"""
MQTT handler — equivalent of mqtt.go
Requires: pip install aiomqtt
"""

import asyncio
import logging

import aiomqtt

from aquarea_types import AquareaCommand

logger = logging.getLogger(__name__)

SUBSCRIBE_TOPIC = "aquarea/+/settings/+/set"
STATUS_TOPIC = "aquarea/status"


async def mqtt_handler(
    ctx: asyncio.Event,
    config: dict,
    data_queue: asyncio.Queue,
    command_queue: asyncio.Queue,
    status_queue: asyncio.Queue,
):
    logger.info("Starting MQTT handler")

    try:
        keepalive = int(float(config.get("MqttKeepalive", 60)))
        logger.info("MQTT connecting to %s:%s", config.get("MqttServer"), config.get("MqttPort", 1883))

        async with aiomqtt.Client(
            hostname=config["MqttServer"],
            port=config.get("MqttPort", 1883),
            username=config.get("MqttLogin") or None,
            password=config.get("MqttPass") or None,
            identifier=config.get("MqttClientID", "aquarea"),
            keepalive=keepalive,
            clean_session=True,
            will=aiomqtt.Will(topic=STATUS_TOPIC, payload="offline", qos=0, retain=True),
        ) as client:
            logger.info("MQTT connected")
            await client.subscribe(SUBSCRIBE_TOPIC, qos=2)
            await client.publish(STATUS_TOPIC, "offline", qos=0, retain=True)

            async def read_incoming():
                async for msg in client.messages:
                    parts = str(msg.topic).split("/")
                    if len(parts) > 3:
                        device_id = parts[1]
                        setting = parts[3]
                        value = msg.payload.decode()
                        logger.info("Received: Device ID %s setting: %s", device_id, setting)
                        await command_queue.put(
                            AquareaCommand(device_id=device_id, setting=setting, value=value)
                        )

            async def dispatch_outgoing():
                logger.info("MQTT dispatcher started")
                while not ctx.is_set():
                    try:
                        while True:
                            data = data_queue.get_nowait()
                            if not isinstance(data, dict):
                                logger.warning("Invalid MQTT payload: %s", data)
                                continue
                            for key, value in data.items():
                                logger.debug("[MQTT SEND] topic=%s payload=%s", key, value)
                                await client.publish(key, value, qos=0, retain=True)
                    except asyncio.QueueEmpty:
                        pass

                    try:
                        while True:
                            online: bool = status_queue.get_nowait()
                            status = "online" if online else "offline"
                            await client.publish(STATUS_TOPIC, status, qos=0, retain=True)
                    except asyncio.QueueEmpty:
                        pass

                    await asyncio.sleep(0.01)

                await client.publish(STATUS_TOPIC, "offline", qos=0, retain=True)

            await asyncio.gather(read_incoming(), dispatch_outgoing())

    except Exception as e:
        logger.exception("MQTT handler crashed: %s", e)
        raise