"""Try a bounded list of configured radar locations without distance inference."""
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://lnt.xmu.edu.cn"
TIMEOUT = (5, 15)
SIGNED_STATUSES = {"on_call", "on_call_fine"}
OUT_OF_SCOPE = "radar_out_of_rollcall_scope"


def locations_path():
    override = os.environ.get("XMU_RADAR_LOCATIONS_FILE")
    if override:
        return Path(override).expanduser()
    config_dir = os.environ.get("XMU_ROLLCALL_CONFIG_DIR")
    return (Path(config_dir).expanduser() if config_dir else Path.home() / ".xmu_rollcall") / "radar_locations.json"


def to_gcj02(latitude, longitude):
    """Apply the same China coordinate transformation as the official client."""
    if longitude < 72.004 or longitude > 137.8347 or latitude < 0.8293 or latitude > 55.8271:
        return latitude, longitude
    x, y = longitude - 105, latitude - 35
    common = 20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)
    lat_delta = (common + 20 * math.sin(y * math.pi) + 40 * math.sin(y * math.pi / 3)
                 + 160 * math.sin(y * math.pi / 12) + 320 * math.sin(y * math.pi / 30)) * 2 / 3
    lon_delta = (common + 20 * math.sin(x * math.pi) + 40 * math.sin(x * math.pi / 3)
                 + 150 * math.sin(x * math.pi / 12) + 300 * math.sin(x * math.pi / 30)) * 2 / 3
    lat_delta += 2 * x - 100 + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    lon_delta += 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    rad_lat = math.radians(latitude)
    magic = 1 - 0.006693421622965943 * math.sin(rad_lat) ** 2
    root = math.sqrt(magic)
    lat_delta = math.degrees(lat_delta / (6378137 * (1 - 0.006693421622965943) / (magic * root)))
    lon_delta = math.degrees(lon_delta / (6378137 / root * math.cos(rad_lat)))
    return latitude + lat_delta, longitude + lon_delta


def load_locations(path):
    with path.open(encoding="utf-8-sig") as stream:
        config = json.load(stream)
    if not isinstance(config, dict):
        raise ValueError("Radar configuration must be an object.")
    rows = config.get("locations")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5:
        raise ValueError("Configure between one and five radar locations.")
    locations = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Location {index} must be an object.")
        if row.get("enabled", True) is False:
            continue
        name = row.get("name") or f"Location {index}"
        lat, lon = row.get("latitude"), row.get("longitude")
        if (type(lat) not in (int, float) or type(lon) not in (int, float)
                or not -90 <= lat <= 90 or not -180 <= lon <= 180):
            raise ValueError(f"Invalid coordinates for {name}.")
        system = row.get("coordinate_system", config.get("coordinate_system"))
        if system not in {"gcj02", "wgs84"}:
            raise ValueError(f"Specify gcj02 or wgs84 for {name}; do not guess the coordinate system.")
        if system == "wgs84":
            lat, lon = to_gcj02(lat, lon)
        accuracy = row.get("accuracy", 35)
        if type(accuracy) not in (int, float) or not 0 <= accuracy <= 1000:
            raise ValueError(f"Invalid accuracy for {name}.")
        locations.append({"name": name, "latitude": lat, "longitude": lon, "accuracy": accuracy})
    if not locations:
        raise ValueError("No enabled radar locations.")
    device_id = config.get("device_id")
    if device_id is not None and (not isinstance(device_id, str) or not device_id.strip()):
        raise ValueError("device_id must be a nonempty string.")
    return locations, device_id


def _current_rollcall(session, rollcall_id, headers):
    response = session.get(f"{BASE_URL}/api/radar/rollcalls", headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("rollcalls"), list):
        raise ValueError("Invalid rollcall list response.")
    return next((row for row in data["rollcalls"]
                 if isinstance(row, dict) and str(row.get("rollcall_id")) == str(rollcall_id)), None)


def _record(path, rollcall_id, **fields):
    entry = {"time": datetime.now(timezone.utc).isoformat(), "rollcall_id": rollcall_id, **fields}
    try:
        with path.with_name("radar_attempts.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as error:
        print(f"Could not write radar log: {type(error).__name__}.")


def send_radar_locations(session, rollcall_id):
    path = locations_path()
    try:
        locations, configured_device = load_locations(path)
    except (OSError, ValueError) as error:
        print(f"Radar locations unavailable: {error}")
        return False

    # Each activity gets one bounded pass per monitor session, including timeouts.
    # Editing the locations file permits a new pass with the changed configuration.
    signature = json.dumps([locations, configured_device], sort_keys=True)
    attempts = session.__dict__.setdefault("_xmu_radar_location_attempts", {})
    key = (str(rollcall_id), signature)
    if key in attempts:
        return attempts[key]
    attempts[key] = False
    if len(attempts) > 256:
        attempts.pop(next(iter(attempts)))

    headers = {**getattr(session, "headers", {}), "Accept": "application/json, text/plain, */*",
               "Referer": f"{BASE_URL}/", "X-Requested-With": "XMLHttpRequest"}
    try:
        row = _current_rollcall(session, rollcall_id, headers)
        if row is None or not row.get("is_radar"):
            print("Radar activity is no longer available.")
            return False
        if row.get("status") in SIGNED_STATUSES:
            attempts[key] = True
            print("Radar rollcall already answered.")
            return True
        if row.get("is_expired") or row.get("rollcall_status") != "in_progress" or row.get("status") != "absent":
            print("Radar activity is not available for answering.")
            return False
        response = session.get(f"{BASE_URL}/api/rollcall/{rollcall_id}/lite", headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        settings = response.json()
        if not isinstance(settings, dict) or type(settings.get("use_beacon")) is not bool:
            raise ValueError("Could not determine whether this radar activity requires Bluetooth.")
        if settings["use_beacon"]:
            print("This radar activity requires a live Bluetooth signal; locations alone cannot answer it.")
            _record(path, rollcall_id, event="bluetooth_required")
            return False
    except (requests.RequestException, ValueError) as error:
        print(f"Radar preflight failed: {error}")
        _record(path, rollcall_id, event="preflight_failed", error_type=type(error).__name__)
        return False

    device_id = configured_device or session.__dict__.setdefault("_xmu_radar_device_id", str(uuid.uuid4()))
    url = f"{BASE_URL}/api/rollcall/{rollcall_id}/answer"
    for index, location in enumerate(locations, 1):
        print(f"Trying radar location {index}/{len(locations)}: {location['name']}")
        payload = {"accuracy": location["accuracy"], "altitude": 0, "altitudeAccuracy": None,
                   "deviceId": device_id, "heading": None, "latitude": location["latitude"],
                   "longitude": location["longitude"], "speed": None}
        try:
            response = session.put(url, params={"api_version": "1.76"}, json=payload,
                                   headers=headers, timeout=TIMEOUT, allow_redirects=False)
        except requests.RequestException as error:
            print(f"Radar request failed: {type(error).__name__}; outcome unknown, stopping this activity.")
            _record(path, rollcall_id, event="request_failed", location=location["name"], error_type=type(error).__name__)
            return False
        try:
            body = response.json()
        except ValueError:
            body = None
        code = body.get("error_code") if isinstance(body, dict) else None
        safe_code = code if isinstance(code, (str, int)) and not isinstance(code, bool) else None
        _record(path, rollcall_id, event="response", location=location["name"],
                http_status=response.status_code, error_code=safe_code)
        if response.status_code == 200:
            try:
                updated = _current_rollcall(session, rollcall_id, headers)
                confirmed = updated is not None and updated.get("status") in SIGNED_STATUSES
            except (requests.RequestException, ValueError):
                confirmed = False
            _record(path, rollcall_id, event="confirmation", location=location["name"], confirmed=confirmed)
            if confirmed:
                attempts[key] = True
                print(f"Radar rollcall answered and confirmed: {location['name']}")
                return True
            print("Radar API returned HTTP 200, but signed status could not be confirmed; stopping this activity.")
            return False
        print(f"Radar request failed: HTTP {response.status_code}; error_code={safe_code!r}.")
        if response.status_code not in {400, 403, 422} or code != OUT_OF_SCOPE:
            print("Changing locations cannot resolve this response; stopping this activity.")
            return False
        if index < len(locations):
            time.sleep(1)

    print("All configured locations are outside the permitted range; stopping this activity.")
    return False
