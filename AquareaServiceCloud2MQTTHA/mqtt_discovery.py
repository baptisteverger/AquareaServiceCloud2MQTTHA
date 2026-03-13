"""
MQTT Home Assistant discovery — equivalent of mqttDiscovery.go
"""

import json
import re
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
        unique_id=f"{device_id}_{name.replace(' ', '_')}",
        device=_panasonic(device_id),
    )
    return "", _to_json(s)

def encode_sensor(name: str, device_id: str, state_topic: str, unit: str = "") -> tuple[str, str]:
    s = MqttSensor(
        name=name,
        availability_topic="aquarea/status",
        state_topic=state_topic,
        unit_of_measurement=unit,
        unique_id=f"{device_id}_{name.replace(' ', '_')}",
        device=_panasonic(device_id),
    )
    return "", _to_json(s)

def encode_switch(name: str, device_id: str, state_topic: str, values: list[str]) -> tuple[str, str]:
    # Nettoyage du nom pour l'ID unique
    safe_name = name.replace(" ", "_")
    b = MqttSwitch(
        name=name,
        availability_topic="aquarea/status",
        command_topic=state_topic + "/set",
        state_topic=state_topic,
        unique_id=f"{device_id}_{safe_name}",
        device=_panasonic(device_id),
    )
    found = False
    for v in values:
        if "Off" in v: b.payload_off = v; found = True
        if "On" in v: b.payload_on = v; found = True
        if "Request" in v: b.payload_on = v; found = True
    if not found: raise ValueError("Cannot encode switch")
    
    ha_topic = f"homeassistant/switch/{device_id}/{safe_name}/config"
    return ha_topic, _to_json(b)


class AquareaDiscoveryMixin:
    def encode_switches(self, topics: dict[str, str], user: AquareaEndUserJSON) -> dict[str, str]:
        config: dict[str, str] = {}
        for k, v in topics.items():
            if "/settings/" not in k or not k.endswith("/options"): continue
            parts = k.split("/")
            name, device_id = parts[3], parts[1]
            values = v.split("\n")
            if 1 <= len(values) <= 2:
                try:
                    ha_topic, ha_data = encode_switch(name, device_id, k.removesuffix("/options"), values)
                    config[ha_topic] = ha_data
                except ValueError: pass
        return config

    def encode_sensors(self, topics: dict[str, str], user: AquareaEndUserJSON) -> dict[str, str]:
        config: dict[str, str] = {}
        no_dupes: dict[str, str] = {}
        
        # LOGIQUE DE FILTRAGE (Indispensable)
        for k, v in topics.items():
            if "/log/" not in k and "/state/" not in k: continue
            if k.endswith("/unit"):
                no_dupes[k] = v
            elif f"{k}/unit" not in topics:
                no_dupes[k] = v

        for k, v in no_dupes.items():
            parts = k.split("/")
            name, device_id = parts[3], parts[1]
            
            is_live = "/state/" in k
            suffix = "Live" if is_live else "Log"
            display_name = f"{name} {suffix}"
            
            # Sécurisation du topic (remplace espaces par underscores)
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
            object_id = f"{safe_name}_{suffix.lower()}"

            try:
                if k.endswith("/unit"):
                    _, ha_data = encode_sensor(display_name, device_id, k.removesuffix("/unit"), v)
                elif v in ("On", "Off"):
                    _, ha_data = encode_binary_sensor(display_name, device_id, k)
                else:
                    _, ha_data = encode_sensor(display_name, device_id, k)

                data_dict = json.loads(ha_data)
                data_dict["unique_id"] = f"{device_id}_{object_id}"
                data_dict["name"] = display_name 
                
                component = "binary_sensor" if v in ("On", "Off") else "sensor"
                # CONSTRUCTION DU TOPIC SANS ESPACES
                ha_topic = f"homeassistant/{component}/{device_id}/{object_id}/config"
                
                config[ha_topic] = json.dumps(data_dict)
            except Exception: pass
        return config