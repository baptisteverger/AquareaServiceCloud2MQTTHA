# aquarea2mqtt-python

Python port of [aquarea2mqtt](https://github.com/rondoval/aquarea2mqtt) by rondoval — connects Panasonic Aquarea heat pumps to Home Assistant via MQTT.

> **Note:** This is a Python port of the original Go project. The logic and structure have been ported from Go to Python, and adapted for use on Windows and other platforms without requiring a Go toolchain.

## How it works

```
Panasonic Aquarea Cloud ──► aquarea2mqtt-python ──► MQTT broker ──► Home Assistant
```

The script logs into the Aquarea Service Cloud, polls your device at a configurable interval, and publishes data to MQTT. It supports **Home Assistant MQTT Discovery**, so your Aquarea devices appear automatically in HA without any manual configuration.

---

## Requirements

- Python 3.11+
- A running MQTT broker (e.g. [Mosquitto](https://mosquitto.org/))
- A Panasonic Aquarea account (Service Cloud or Smart Cloud)

---

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/aquarea2mqtt-python
cd aquarea2mqtt-python
pip install -r requirements.txt
```

---

## Configuration

Copy the example config and fill in your credentials:

```bash
cp options.example.json options.json
```

Edit `options.json`:

```json
{
  "AquareaServiceCloudURL": "https://aquarea-smart.panasonic.com/",
  "AquareaServiceCloudLogin": "your@email.com",
  "AquareaServiceCloudPassword": "yourpassword",
  "AquareaTimeout": "30",
  "PoolInterval": "60",
  "LogSecOffset": 3600,
  "MqttServer": "192.168.1.100",
  "MqttPort": 1883,
  "MqttLogin": "",
  "MqttPass": "",
  "MqttClientID": "aquarea",
  "MqttKeepalive": "60"
}
```

| Key | Description |
|-----|-------------|
| `AquareaServiceCloudURL` | Aquarea portal URL — use `https://aquarea-smart.panasonic.com/` for Smart Cloud or `https://aquarea-service.panasonic.com/` for Service Cloud |
| `AquareaServiceCloudLogin` | Your Aquarea account email |
| `AquareaServiceCloudPassword` | Your Aquarea account password |
| `AquareaTimeout` | HTTP timeout in seconds |
| `PoolInterval` | Polling interval in seconds |
| `LogSecOffset` | How far back (in seconds) to fetch log data |
| `MqttServer` | IP or hostname of your MQTT broker |
| `MqttPort` | MQTT port (default: `1883`) |
| `MqttLogin` | MQTT username (leave empty if not required) |
| `MqttPass` | MQTT password (leave empty if not required) |
| `MqttClientID` | MQTT client identifier |
| `MqttKeepalive` | MQTT keepalive in seconds |

> ⚠️ Never commit `options.json` — it contains your credentials. It is listed in `.gitignore`.

---

## Running

```bash
# Linux / macOS
python main.py

# Windows
py main.py
```

---

## Home Assistant integration

1. In Home Assistant, install the **Mosquitto broker** add-on
   (Settings → Add-ons → Add-on store → Mosquitto broker)
2. Enable the **MQTT integration**
   (Settings → Devices & services → MQTT — HA will suggest it automatically)
3. Set `MqttServer` in `options.json` to your Home Assistant IP address
4. Run the script — your Aquarea devices will appear automatically in HA

---

## MQTT topics

| Topic | Description |
|-------|-------------|
| `aquarea/status` | `online` / `offline` |
| `aquarea/{gwid}/state/{name}` | Device state values |
| `aquarea/{gwid}/settings/{name}` | Current setting values |
| `aquarea/{gwid}/settings/{name}/set` | Change a setting (publish here) |
| `aquarea/{gwid}/log/{name}` | Statistics / log values |
| `aquarea/{gwid}/log/{name}/unit` | Unit of the statistic |

---

## File structure

| File | Description |
|------|-------------|
| `main.py` | Entry point |
| `aquarea.py` | Main class, assembles all modules |
| `aquarea_types.py` | Data types and JSON mappings |
| `aquarea_http.py` | HTTP helpers |
| `aquarea_login.py` | Login, dictionary and log item loading |
| `aquarea_settings.py` | Read and write device settings |
| `aquarea_device_status.py` | Device status polling |
| `aquarea_device_statistics.py` | Device log / statistics |
| `mqtt.py` | MQTT handler |
| `mqtt_discovery.py` | Home Assistant MQTT discovery payloads |
| `translation.json` | Aquarea function name mappings |
| `options.example.json` | Configuration template |

---

## Based on

Python port of **[aquarea2mqtt](https://github.com/rondoval/aquarea2mqtt)** by [rondoval](https://github.com/rondoval), itself forked from [lsochanowski/Aquarea2mqtt](https://github.com/lsochanowski/Aquarea2mqtt).

The logic, structure, and `translation.json` have been ported from Go to Python. All credit for the original reverse-engineering work and API knowledge goes to the original authors.

---

## License

GPL-3.0 — see [LICENSE](LICENSE).

This project is a derivative work of aquarea2mqtt (GPL-3.0) and is distributed under the same license.
