# AquareaServiceCloud2MQTTHA

Home Assistant add-on that connects your **Panasonic Aquarea** heat pump to Home Assistant via MQTT, using the [Aquarea Service Cloud](https://aquarea-service.panasonic.com/) API.

---

## Features

- **Real-time status** — inlet/outlet water temperature, mode, pump speed, flow rate, compressor frequency, and more
- **Full log data** — 81 sensors from the Aquarea diagnostic log (temperatures, pressures, energy, timers…)
- **Settings control** — switches, selects and buttons for all user-accessible settings (Operation, OperationMode, ForceDHW, QuietMode, TankSensor, Powerful, Sterilization, ForceDefrost…)
- **Home Assistant MQTT discovery** — entities appear automatically in HA with correct device classes and units
- **Multi-language** — sensor and setting labels follow the API language (configurable: en, fr, de, es, it, nl, pl…)
- **100% dynamic** — sensor names, units and binary values come from the Panasonic API at startup, no hardcoded sensor list
- **Compatible with all Aquarea Gen H/J/K models** — unknown settings are published as read-only sensors (passthrough)

---

## Installation

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**
2. Click the three-dot menu → **Repositories**
3. Add: `https://github.com/baptisteverger/AquareaServiceCloud2MQTTHA`
4. Find **AquareaServiceCloud2MQTTHA** and click **Install**

---

## Prerequisites

- A [Mosquitto MQTT broker](https://github.com/home-assistant/addons/tree/master/mosquitto) (or any MQTT broker)
- An [Aquarea Service Cloud](https://aquarea-service.panasonic.com/) account linked to your heat pump
- MQTT integration enabled in Home Assistant

---

## Configuration

| Parameter | Description | Default |
|---|---|---|
| `AquareaServiceCloudURL` | Panasonic API base URL | `https://aquarea-service.panasonic.com/` |
| `AquareaServiceCloudLogin` | Your Aquarea Service Cloud email | *(required)* |
| `AquareaServiceCloudPassword` | Your Aquarea Service Cloud password | *(required)* |
| `AquareaTimeout` | HTTP request timeout in seconds | `30` |
| `PoolInterval` | Polling interval in seconds | `60` |
| `LogSecOffset` | How many seconds back to fetch log data | `3600` |
| `MqttServer` | MQTT broker hostname or IP | *(required)* |
| `MqttPort` | MQTT broker port | `1883` |
| `MqttLogin` | MQTT username (leave empty if none) | `` |
| `MqttPass` | MQTT password (leave empty if none) | `` |
| `MqttClientID` | MQTT client identifier | `aquarea` |
| `MqttKeepalive` | MQTT keepalive in seconds | `60` |
| `Language` | Label language for sensor/setting names | `en` |
| `LogLevel` | Logging verbosity: `DEBUG`, `INFO`, `WARNING` | `INFO` |

### Language codes

`en` · `fr` · `de` · `es` · `it` · `nl` · `pl` · `pt` · `cs` · `sv` · `fi` · `nb` · `da` · `el` · `ro` · `sk` · `sl` · `hr` · `bg` · `hu` · `tr`

> **Note:** changing the language after initial setup will rename entities in HA. Delete the old entities from the MQTT integration before restarting.

---

## MQTT Topics

All topics are prefixed with `aquarea/{device_id}/`.

### Status (live)
```
aquarea/{device_id}/state/{SensorName}        → current value
```

### Log (historical, from last log entry)
```
aquarea/{device_id}/log/{SensorName}          → value
aquarea/{device_id}/log/{SensorName}/unit     → unit (°C, kW, Hz…)
aquarea/{device_id}/log/Timestamp             → Unix timestamp ms
aquarea/{device_id}/log/CurrentError          → error code
```

### Settings (read/write)
```
aquarea/{device_id}/settings/{SettingName}           → current value
aquarea/{device_id}/settings/{SettingName}/options   → available options (newline-separated)
aquarea/{device_id}/settings/{SettingName}/label     → display name
aquarea/{device_id}/settings/{SettingName}/set       → write topic (send new value here)
```

### HA Discovery
```
homeassistant/sensor/{device_id}/{name}/config
homeassistant/binary_sensor/{device_id}/{name}/config
homeassistant/switch/{device_id}/{name}/config
homeassistant/select/{device_id}/{name}/config
homeassistant/button/{device_id}/{name}/config
```

### Availability
```
aquarea/status    → "online" / "offline"
```

---

## Entities created in Home Assistant

### Controls (settings)

| Entity | Type | Description |
|---|---|---|
| Operation | Switch | Turn heat pump on/off |
| Operation mode | Select | Tank / Heat / Cool / Auto / … |
| Zone operation setting | Select | Zone1/Zone2 on/off combinations |
| Force DHW | Switch | Force domestic hot water |
| Weekly timer | Switch | Enable/disable weekly schedule |
| Holiday mode | Switch | Activate holiday mode |
| Quiet timer | Switch | Enable quiet timer |
| Quiet mode | Select | Off / Level 1 / Level 2 / Level 3 |
| Priority | Select | Sound / Capacity |
| Room heater | Switch | Enable room heater |
| Tank heater | Switch | Enable tank heater |
| Tank sensor | Select | Top / Center |
| Powerful | Select | Off / 30 min / 60 min / 90 min |
| Force heater | Switch | Force backup heater |
| Sterilization | Button | Request sterilization |
| Force defrost | Button | Request manual defrost |
| Zone 1/2 target temperature (heat/cool) | Number | Target water temperature |
| Tank target temperature | Number | DHW target temperature |
| Holiday mode heat/tank shift temp | Number | Temperature offset during holiday |

### Sensors (live + log)

Over **115 entities** covering temperatures, pressures, energy consumption/generation, pump data, compressor metrics, binary statuses and more. All names, units and translated values come directly from the Panasonic API.

---

## Troubleshooting

**No entities appear in HA**
- Check the MQTT broker is reachable and credentials are correct
- Enable MQTT discovery in the HA MQTT integration
- Check the add-on logs for errors

**Settings show raw codes (e.g. `2010-00E1`)**
- The type-2010 dictionary failed to load; the add-on uses a built-in English fallback
- Check network connectivity to `aquarea-service.panasonic.com`

**Some sensors show `Unknown` or `-78 °C`**
- These are sensors for optional equipment not installed on your unit (Zone 2, buffer tank, solar, pool, bivalent)
- Values are published as-is from Panasonic — `-78`, `-31`, `-46` are sentinel values for unconnected physical sensors

**Changing `Language` breaks entity names**
- Delete the existing Aquarea device from the MQTT integration in HA, then restart the add-on

---

## Credits

- Original Go implementation: [kamaradclimber/Aquarea2mqtt](https://github.com/kamaradclimber/Aquarea2mqtt)
