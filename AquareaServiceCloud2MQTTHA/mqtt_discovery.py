"""
MQTT Home Assistant discovery — equivalent of mqttDiscovery.go
"""

import json
from dataclasses import dataclass, field, asdict

from aquarea_types import AquareaEndUserJSON


@dataclass
class _Device:
    manufacturer: str = ""
    model: str = ""
    name: str = ""
    identifiers: str = ""


def _panasonic(device_id: str) -> _Device:
    return _Device(
        manufacturer="Panasonic",
        model="Aquarea",
        identifiers=device_id,
        name=f"Aquarea {device_id}",
    )


def _clean(d: dict) -> dict:
    """Remove empty/false values (mimics omitempty)."""
    return {k: v for k, v in d.items() if v}


@dataclass
class MqttSwitch:
    name: str = ""
    availability_topic: str = ""
    command_topic: str = ""
    state_topic: str = ""
    payload_on: str = ""
    payload_off: str = ""
    unique_id: str = ""
    device: _Device = field(default_factory=_Device)


@dataclass
class MqttSensor:
    name: str = ""
    availability_topic: str = ""
    state_topic: str = ""
    unit_of_measurement: str = ""
    device_class: str = ""
    force_update: bool = False
    unique_id: str = ""
    device: _Device = field(default_factory=_Device)


@dataclass
class MqttBinarySensor:
    name: str = ""
    availability_topic: str = ""
    state_topic: str = ""
    device_class: str = ""
    force_update: bool = False
    payload_off: str = ""
    payload_on: str = ""
    unique_id: str = ""
    device: _Device = field(default_factory=_Device)


def _to_json(obj) -> str:
    d = asdict(obj)
    d["device"] = _clean(d["device"])
    return json.dumps(_clean(d))


def encode_binary_sensor(name: str, device_id: str, state_topic: str) -> tuple[str, str]:
    s = MqttBinarySensor(
        name=name,
        availability_topic="aquarea/status",
        state_topic=state_topic,
        payload_on="On",
        payload_off="Off",
        unique_id=f"{device_id}_{name}",
        device=_panasonic(device_id),
    )
    return f"homeassistant/binary_sensor/{device_id}/{name}/config", _to_json(s)


def encode_sensor(name: str, device_id: str, state_topic: str, unit: str = "") -> tuple[str, str]:
    s = MqttSensor(
        name=name,
        availability_topic="aquarea/status",
        state_topic=state_topic,
        unit_of_measurement=unit,
        unique_id=f"{device_id}_{name}",
        device=_panasonic(device_id),
    )
    return f"homeassistant/sensor/{device_id}/{name}/config", _to_json(s)


def encode_switch(name: str, device_id: str, state_topic: str, values: list[str]) -> tuple[str, str]:
    b = MqttSwitch(
        name=name,
        availability_topic="aquarea/status",
        command_topic=state_topic + "/set",
        state_topic=state_topic,
        unique_id=f"{device_id}_{name}",
        device=_panasonic(device_id),
    )

    found = False
    for v in values:
        if "Off" in v:
            b.payload_off = v
            found = True
        if "On" in v:
            b.payload_on = v
            found = True
        if "Request" in v:
            b.payload_on = v
            found = True

    if not found:
        raise ValueError("Cannot encode switch")

    return f"homeassistant/switch/{device_id}/{name}/config", _to_json(b)


class AquareaDiscoveryMixin:

    def encode_switches(self, topics: dict[str, str], user: AquareaEndUserJSON) -> dict[str, str]:
        config: dict[str, str] = {}
        for k, v in topics.items():
            if "/settings/" not in k or not k.endswith("/options"):
                continue
            parts = k.split("/")
            name, device_id = parts[3], parts[1]
            values = v.split("\n")
            if 1 <= len(values) <= 2:
                try:
                    ha_topic, ha_data = encode_switch(
                        name, device_id, k.removesuffix("/options"), values
                    )
                    config[ha_topic] = ha_data
                except ValueError:
                    pass
        return config

def encode_sensors(self, topics: dict[str, str], user: AquareaEndUserJSON) -> dict[str, str]:
    config: dict[str, str] = {}
    no_dupes: dict[str, str] = {}
    
    # ... (votre logique de filtrage reste la même) ...

    for k, v in no_dupes.items():
        parts = k.split("/")
        # parts[1] = device_id, parts[3] = name
        name, device_id = parts[3], parts[1]
        
        is_live = "/state/" in k
        suffix = "Live" if is_live else "Log"
        
        # 1. CRÉATION D'UN NOM D'AFFICHAGE (pour l'UI Home Assistant)
        display_name = f"{name} {suffix}" # "Zone2WaterTemperature Log"
        
        # 2. CRÉATION D'UN OBJECT_ID VALIDE (pour le TOPIC MQTT)
        # On remplace TOUT ce qui n'est pas alphanumérique par un underscore
        import re
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        object_id = f"{safe_name}_{suffix.lower()}" # "Zone2WaterTemperature_log"

        try:
            # On génère la base via vos fonctions
            if k.endswith("/unit"):
                _, ha_data = encode_sensor(display_name, device_id, k.removesuffix("/unit"), v)
            elif v in ("On", "Off"):
                _, ha_data = encode_binary_sensor(display_name, device_id, k)
            else:
                _, ha_data = encode_sensor(display_name, device_id, k)

            # 3. NETTOYAGE DU JSON FINAL
            data_dict = json.loads(ha_data)
            # On s'assure que l'ID unique et le nom sont propres
            data_dict["unique_id"] = f"{device_id}_{object_id}"
            data_dict["name"] = display_name 
            
            # 4. CONSTRUCTION DU TOPIC SANS ESPACES (Crucial)
            component = "binary_sensor" if v in ("On", "Off") else "sensor"
            ha_topic = f"homeassistant/{component}/{device_id}/{object_id}/config"
            
            config[ha_topic] = json.dumps(data_dict)
            
        except Exception:
            pass
    return config