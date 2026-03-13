"""
Entry point — equivalent of main.go
"""

# Must be before any other import that touches asyncio internals.
# aiomqtt/paho-mqtt use add_reader/add_writer which only work with
# SelectorEventLoop, not the default IocpProactor on Windows.
import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import asyncio
import json
import logging
import platform
import signal
from pathlib import Path

from aquarea import aquarea_handler
from mqtt import mqtt_handler

CONFIG_FILE_OTHER = "/data/options.json"
CONFIG_FILE_WINDOWS = "options.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s",
    datefmt="%Y/%m/%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def read_config() -> dict:
    config_file = (
        CONFIG_FILE_WINDOWS if platform.system() == "Windows" else CONFIG_FILE_OTHER
    )
    return json.loads(Path(config_file).read_text(encoding="utf-8"))



async def main():
    logger.info("Tentative de lecture de la configuration...") # NEW
    try:
        config = read_config()
        logger.info(config)
        logger.info("Configuration lue avec succès") # NEW
    except Exception as e:
        logger.error("Erreur critique lors de la lecture du JSON : %s", e) # NEW
        return

    data_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    command_queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    status_queue: asyncio.Queue = asyncio.Queue()

    stop_event = asyncio.Event()
    
    # On vérifie ce que le script a réellement compris du serveur MQTT
    logger.info("MQTT Server configuré sur : %s", config.get("MqttServer")) 

    logger.info("Lancement de la tâche MQTT...") # NEW
    mqtt_task = asyncio.create_task(
        mqtt_handler(stop_event, config, data_queue, command_queue, status_queue),
        name="mqtt"
    )
    logger.info(mqtt_task)
    logger.info("Lancement de la tâche Aquarea...") # NEW


    logger.info("Tâches lancées, attente du gather...") # NEW
    try:
        await asyncio.gather(mqtt_task)
    except Exception as e:
        logger.exception("Erreur dans la boucle principale : %s", e) # NEW


if __name__ == "__main__":
    asyncio.run(main())
