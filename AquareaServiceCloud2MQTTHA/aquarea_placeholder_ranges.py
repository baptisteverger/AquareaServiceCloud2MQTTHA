"""
Dynamic placeholder range computation for Aquarea user settings.

Panasonic's Aquarea Service Cloud computes the valid range for each numeric
("placeholder") setting on the client side, in JavaScript. The logic depends on
the device model (read from settingDataInfo system keys) and hardware config
(read from settingBackgroundData).

This module reverse-engineers that logic so we can compute the correct HA
number entity min/max/step for any Aquarea installation.

Key functions extracted from:
  /statics/_next/static/chunks/pages/installer/function-setting-<hash>.js

  R(zone, currentValues, bgData)  → statusNo for heat zone temperature
  D(zone, currentValues, bgData)  → statusNo for cool zone temperature
  L(min, max, startHex, step=1)   → ascending options dict
  K(start, end, startHex)         → descending options dict (holiday shifts)

All options sets for each user placeholder setting are hardcoded here from
the JS, and the statusNo functions are ported to Python verbatim.
"""

import re
import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Panasonic range builder functions (ported from JS)
# ---------------------------------------------------------------------------

def _L(min_val: int, max_val: int, start_hex: int, step: int = 1) -> dict[str, int]:
    """L(e,t,s,step=1): ascending range, maps hex → value."""
    result: dict[str, int] = {}
    s = start_hex
    o = min_val
    while o <= max_val:
        result[f"0x{s:02X}"] = o
        o += step
        s += step
    return result


def _K(start_val: int, end_val: int, start_hex: int) -> dict[str, int]:
    """K(e,t,s): descending range (holiday shift), maps hex → value."""
    result: dict[str, int] = {}
    s = start_hex
    n = start_val
    while n >= end_val:
        if s == -1:
            key = "0xFF"
            s = 255
        else:
            key = f"0x{s & 0xFF:02X}"
        result[key] = n
        n -= 1
        s -= 1
    return result


# ---------------------------------------------------------------------------
# All option sets for each placeholder user setting (from Panasonic JS)
# options[statusNo] → {hex: value, ...}
# ---------------------------------------------------------------------------

_OPTIONS: dict[str, dict[int, dict[str, int]]] = {
    # user008 = Zone1 heat target (water shift or direct water temp)
    # user009 = Zone2 heat target (same sets)
    "user008": {
        0: _L(-5, 5, 123),    # water shift −5…+5°C
        1: _L(20, 55, 148),   # direct 20…55°C
        2: _L(20, 60, 148),   # direct 20…60°C
        3: _L(20, 65, 148),   # direct 20…65°C
        4: _L(10, 30, 138),   # direct 10…30°C
        5: _L(15, 35, 143),   # direct 15…35°C
        6: _L(20, 75, 148),   # direct 20…75°C
        8: _L(20, 75, 148),
        9: _L(25, 75, 153),
    },
    "user009": {
        0: _L(-5, 5, 123),
        1: _L(20, 55, 148),
        2: _L(20, 60, 148),
        3: _L(20, 65, 148),
        4: _L(10, 30, 138),
        5: _L(15, 35, 143),
        6: _L(20, 75, 148),
        8: _L(20, 75, 148),
        9: _L(25, 75, 153),
    },
    # user010 = Zone1 cool target, user011 = Zone2 cool target
    "user010": {
        0: _L(-5, 5, 123),    # water shift −5…+5°C
        1: _L(5, 20, 133),    # direct 5…20°C
        2: _L(18, 35, 146),   # direct 18…35°C
        3: _L(-5, 5, 123),    # hidden (same as 0, won't be shown)
    },
    "user011": {
        0: _L(-5, 5, 123),
        1: _L(5, 20, 133),
        2: _L(18, 35, 146),
        3: _L(-5, 5, 123),
    },
    # user013 = tank target temperature
    "user013": {
        0: _L(40, 65, 168),   # 40…65°C (most models)
        1: _L(40, 75, 168),   # 40…75°C (high-capacity models)
    },
    # user023 = holiday mode heat shift, user024 = holiday mode tank shift
    "user023": {0: _K(15, -25, 15)},
    "user024": {0: _K(15, -25, 15)},
}


# ---------------------------------------------------------------------------
# statusNo computation (ported from Panasonic JS functions R, D, user013 rule)
# ---------------------------------------------------------------------------

class PlaceholderRange(NamedTuple):
    min: int
    max: int
    step: int


def _R(zone: int, cur: dict, bg: dict) -> int:
    """
    Panasonic JS function R(zone, currentValues, bgData).
    Returns statusNo for heat zone temperature (user008=zone1, user009=zone2).
    """
    n = cur.get("operation003")
    o = cur.get("system005") if zone == 1 else cur.get("system008")
    r = cur.get("system006") if zone == 1 else cur.get("system009")
    a = 0
    if o == "0x01":
        if r == "0x01":
            if n == "0x01":
                a = 0
            elif n == "0x02":
                s8A = bg.get("data0x8A")
                s8C = bg.get("data0x8C")
                if s8A == "0x01":
                    a = 1 if s8C == "0x01" else (8 if s8C == "0x05" else 2)
                elif s8A == "0x02":
                    a = 9 if s8C == "0x05" else 3
                elif s8A == "0x03":
                    a = 2 if s8C == "0x01" else (6 if s8C == "0x04" else (9 if s8C == "0x05" else 1))
        elif r == "0x02":
            a = 7
        elif r in ("0x03", "0x04"):
            a = 4
    elif o == "0x02":
        a = 5
    return a


def _D(zone: int, cur: dict, bg: dict) -> int:
    """
    Panasonic JS function D(zone, currentValues, bgData).
    Returns statusNo for cool zone temperature (user010=zone1, user011=zone2).
    """
    n = cur.get("operation023")
    o = cur.get("system005") if zone == 1 else cur.get("system008")
    r = cur.get("system006") if zone == 1 else cur.get("system009")
    a = 0
    if o == "0x01":
        if r == "0x01":
            if n == "0x01":
                a = 0
            elif n == "0x02":
                a = 1
        elif r == "0x02":
            a = 3
        elif r in ("0x03", "0x04"):
            a = 2
    elif o == "0x02":
        a = 3
    return a


def _status_user013(cur: dict) -> int:
    """
    user013 getRules: statusNo=1 by default, =0 if system021=="0x01".
    (system021=="0x01" = heat pump without high-capacity tank mode)
    """
    return 0 if cur.get("system021") == "0x01" else 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_placeholder_ranges(
    setting_data_info: dict,
    setting_background_data: dict,
) -> dict[str, PlaceholderRange]:
    """
    Compute the correct min/max/step for each placeholder user setting,
    given the device's settingDataInfo and settingBackgroundData from
    /installer/api/function/setting/get.

    Returns:
        {setting_key: PlaceholderRange}
        e.g. {"function-setting-user-select-013": PlaceholderRange(40, 65, 1)}
    """
    # Build current-values dict: system005 → selectedValue, user008 → selectedValue, ...
    cur: dict[str, str | None] = {}
    for k, v in setting_data_info.items():
        m = re.match(r"function-setting-(system|user|operation)-select-(\d+)", k)
        if m:
            prefix = m.group(1)
            num = int(m.group(2))
            cur[f"{prefix}{num:03d}"] = v.get("selectedValue") if isinstance(v, dict) else v

    # Build bgData dict: 0x8A → data0x8A value
    bg: dict[str, str | None] = {}
    for k, v in setting_background_data.items():
        bg[f"data{k}"] = v.get("value") if isinstance(v, dict) else v

    # Compute statusNo per setting and pick the right options set
    status_map: dict[str, int] = {
        "user008": _R(1, cur, bg),
        "user009": _R(2, cur, bg),
        "user010": _D(1, cur, bg),
        "user011": _D(2, cur, bg),
        "user013": _status_user013(cur),
        "user023": 0,
        "user024": 0,
    }

    ranges: dict[str, PlaceholderRange] = {}
    for user_key, status_no in status_map.items():
        opts_sets = _OPTIONS.get(user_key, {})
        # Fallback: if statusNo not in options, pick the first available set
        opts = opts_sets.get(status_no) or opts_sets.get(0) or {}
        if not opts:
            logger.warning("No options found for %s statusNo=%d", user_key, status_no)
            continue

        vals = sorted(opts.values())
        min_v, max_v = vals[0], vals[-1]
        # Detect step (usually 1 or 0.5)
        if len(vals) >= 2:
            step = vals[1] - vals[0]
        else:
            step = 1

        tr_key = f"function-setting-user-select-{user_key.removeprefix('user')}"
        ranges[tr_key] = PlaceholderRange(min=min_v, max=max_v, step=step)
        logger.debug(
            "Placeholder range %s [statusNo=%d]: min=%d, max=%d, step=%s",
            tr_key, status_no, min_v, max_v, step,
        )

    return ranges
