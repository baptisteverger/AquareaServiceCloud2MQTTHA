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

    keepalive = int(float(config.get("MqttKeepalive", 60)))

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
        # offline until Service Cloud connects
        await client.publish(STATUS_TOPIC, "offline", qos=0, retain=True)

        async def read_incoming():
            async for msg in client.messages:
                parts = str(msg.topic).split("/")
                if len(parts) > 3:
                    device_id = parts[1]
                    setting = parts[3]
                    value = msg.payload.decode()
                    logger.info(
                        "Received: Device ID %s setting: %s", device_id, setting
                    )
                    await command_queue.put(
                        AquareaCommand(
                            device_id=device_id, setting=setting, value=value
                        )
                    )

        async def dispatch_outgoing():
            while not ctx.is_set():
                # Drain data queue
                try:
                    while True:
                        data: dict[str, str] = data_queue.get_nowait()
                        for key, value in data.items():
                            # LIGNE À AJOUTER POUR LE LOG
                            logger.info(f"[MQTT SEND] {key} = {value}")
                            
                            await client.publish(key, value, qos=0, retain=True)
                except asyncio.QueueEmpty:
                    pass

                # Drain status queue
                try:
                    while True:
                        online: bool = status_queue.get_nowait()
                        status = "online" if online else "offline"
                        
                        # LOG POUR LE STATUT
                        logger.info(f"[MQTT SEND] {STATUS_TOPIC} = {status}")
                        
                        await client.publish(
                            STATUS_TOPIC, status, qos=0, retain=True
                        )
                except asyncio.QueueEmpty:
                    pass

                await asyncio.sleep(0.01)

            # Set offline on shutdown
            await client.publish(STATUS_TOPIC, "offline", qos=0, retain=True)

        await asyncio.gather(read_incoming(), dispatch_outgoing())
