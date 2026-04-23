"""
MQTT Home Assistant discovery — equivalent of mqttDiscovery.go

Settings discovery:
  - 1-2 options contenant On/Off/Request  → switch HA
  - 3+ options, ou 2 options sans On/Off  → select HA
"""

import json
import re
import os
from dataclasses import dataclass, field, asdict
from aquarea_types import AquareaEndUserJSON

# ---------------------------------------------------------------------------
# Chargement du mapping nom → unité depuis translation.json
# ---------------------------------------------------------------------------
_TRANSLATION_PATH = os.path.join(os.path.dirname(__file__), "translation.json")

def _load_unit_map(path: str = _TRANSLATION_PATH) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    return {
        v["name"]: v["unit"]
        for v in data.values()
        if "name" in v and "unit" in v
    }

UNIT_MAP: dict[str, str] = _load_unit_map()


# ---------------------------------------------------------------------------
# Dataclasses HA discovery
# ---------------------------------------------------------------------------

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
    """Retire les champs falsy, SAUF les listes (même vides on les garde)."""
    return {
        k: v for k, v in d.items()
        if v or (isinstance(v, list))
    }

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
class MqttSelect:
    """HA MQTT select — pour les settings à choix multiples."""
    name: str = ""
    availability_topic: str = ""
    command_topic: str = ""
    state_topic: str = ""
    options: list = field(default_factory=list)
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


# ---------------------------------------------------------------------------
# Encodeurs individuels
# ---------------------------------------------------------------------------

def encode_binary_sensor(name: str, device_id: str, state_topic: str) -> tuple[str, str]:
    safe = name.replace(" ", "_")
    s = MqttBinarySensor(
        name=name,
        availability_topic="aquarea/status",
        state_topic=state_topic,
        payload_on="On",
        payload_off="Off",
        unique_id=f"{device_id}_{safe}",
        device=_panasonic(device_id),
    )
    return "", _to_json(s)


def encode_sensor(name: str, device_id: str, state_topic: str, unit: str = "") -> tuple[str, str]:
    safe = name.replace(" ", "_")
    s = MqttSensor(
        name=name,
        availability_topic="aquarea/status",
        state_topic=state_topic,
        unit_of_measurement=unit,
        unique_id=f"{device_id}_{safe}",
        device=_panasonic(device_id),
    )
    return "", _to_json(s)


def encode_switch(name: str, device_id: str, state_topic: str, values: list[str]) -> tuple[str, str]:
    """Switch On/Off. Lève ValueError si aucune valeur On/Off/Request trouvée."""
    safe = name.replace(" ", "_")
    b = MqttSwitch(
        name=name,
        availability_topic="aquarea/status",
        command_topic=state_topic + "/set",
        state_topic=state_topic,
        unique_id=f"{device_id}_{safe}",
        device=_panasonic(device_id),
    )
    found = False
    for v in values:
        vs = v.strip()
        if "Off" in vs:
            b.payload_off = vs
            found = True
        if "On" in vs:
            b.payload_on = vs
            found = True
        if "Request" in vs:
            b.payload_on = vs
            found = True
    if not found:
        raise ValueError(f"Cannot encode switch: {values}")
    ha_topic = f"homeassistant/switch/{device_id}/{safe}/config"
    return ha_topic, _to_json(b)


def encode_select(name: str, device_id: str, state_topic: str, options: list[str]) -> tuple[str, str]:
    """Select multi-options."""
    safe = name.replace(" ", "_")
    s = MqttSelect(
        name=name,
        availability_topic="aquarea/status",
        command_topic=state_topic + "/set",
        state_topic=state_topic,
        options=[o.strip() for o in options if o.strip()],
        unique_id=f"{device_id}_{safe}",
        device=_panasonic(device_id),
    )
    ha_topic = f"homeassistant/select/{device_id}/{safe}/config"
    return ha_topic, _to_json(s)


# ---------------------------------------------------------------------------
# Mixin principal
# ---------------------------------------------------------------------------

class AquareaDiscoveryMixin:

    def encode_switches(self, topics: dict[str, str], user: AquareaEndUserJSON) -> dict[str, str]:
        """
        Génère la discovery HA pour tous les settings Aquarea.

        Routing par type:
          - ≤2 options dont On/Off/Request  → switch HA
          - tout le reste                   → select HA
        """
        config: dict[str, str] = {}

        for k, v in topics.items():
            if "/settings/" not in k or not k.endswith("/options"):
                continue

            parts = k.split("/")
            if len(parts) < 4:
                continue

            device_id = parts[1]
            name = parts[3]
            state_topic = k.removesuffix("/options")

            values = [opt.strip() for opt in v.split("\n") if opt.strip()]
            if not values:
                continue

            has_on_off = any(
                "Off" in val or "On" in val or "Request" in val
                for val in values
            )

            if len(values) <= 2 and has_on_off:
                # Tentative switch binaire
                try:
                    ha_topic, ha_data = encode_switch(name, device_id, state_topic, values)
                    config[ha_topic] = ha_data
                except ValueError:
                    # Fallback select
                    ha_topic, ha_data = encode_select(name, device_id, state_topic, values)
                    config[ha_topic] = ha_data
            else:
                # Select multi-choix (Heat/Cool/Auto, niveaux, etc.)
                ha_topic, ha_data = encode_select(name, device_id, state_topic, values)
                config[ha_topic] = ha_data

        return config

    def encode_sensors(self, topics: dict[str, str], user: AquareaEndUserJSON) -> dict[str, str]:
        config: dict[str, str] = {}
        no_dupes: dict[str, str] = {}

        # Déduplification : garder /unit si présent, sinon valeur brute
        for k, v in topics.items():
            if "/log/" not in k and "/state/" not in k:
                continue
            if k.endswith("/unit"):
                no_dupes[k] = v
            elif f"{k}/unit" not in topics:
                no_dupes[k] = v

        for k, v in no_dupes.items():
            parts = k.split("/")
            if len(parts) < 4:
                continue
            name = parts[3]
            device_id = parts[1]

            is_live = "/state/" in k
            suffix = "Live" if is_live else "Log"
            display_name = f"{name} {suffix}"

            clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
            object_id = f"{clean_name}_{suffix.lower()}"

            try:
                if k.endswith("/unit"):
                    _, ha_data = encode_sensor(display_name, device_id, k.removesuffix("/unit"), v)
                    component = "sensor"
                elif v in ("On", "Off"):
                    _, ha_data = encode_binary_sensor(display_name, device_id, k)
                    component = "binary_sensor"
                else:
                    unit = UNIT_MAP.get(name, "")
                    _, ha_data = encode_sensor(display_name, device_id, k, unit)
                    component = "sensor"

                data_dict = json.loads(ha_data)
                data_dict["unique_id"] = f"{device_id}_{object_id}"
                data_dict["name"] = display_name

                ha_topic = f"homeassistant/{component}/{device_id}/{object_id}/config".replace(" ", "")
                config[ha_topic] = json.dumps(data_dict)

            except Exception:
                pass

        return config