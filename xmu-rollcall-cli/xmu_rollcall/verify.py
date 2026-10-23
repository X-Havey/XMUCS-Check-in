import uuid
import time
import requests
from datetime import datetime, timezone

base_url = "https://lnt.xmu.edu.cn"
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://ids.xmu.edu.cn/authserver/login",
}

def find_number_code(data, depth=0, max_depth=10):
    """Extract number_code from nested dict/list API responses.

    Args:
        data: Parsed JSON payload from Tronclass APIs.
        depth: Current recursive depth when traversing nested structures.
        max_depth: Maximum depth allowed for traversal to avoid pathological recursion.

    Returns:
        str or None: The first discovered number_code value, or None if not found.
    """
    if depth > max_depth:
        return None
    if isinstance(data, dict):
        number_code = data.get("number_code")
        if number_code is not None:
            return str(number_code)
        for value in data.values():
            nested_code = find_number_code(value, depth + 1, max_depth)
            if nested_code:
                return nested_code
    elif isinstance(data, list):
        for item in data:
            nested_code = find_number_code(item, depth + 1, max_depth)
            if nested_code:
                return nested_code
    return None

def get_timetable_number_code(in_session, rollcall_id, course_id=None, rollcall_time=None):
    """Read the code for this rollcall from the student timetable API."""
    if course_id is None:
        response = in_session.get(f"{base_url}/api/radar/rollcalls", timeout=(5, 15))
        response.raise_for_status()
        for rollcall in response.json().get("rollcalls", []):
            if str(rollcall.get("rollcall_id")) == str(rollcall_id):
                course_id = rollcall.get("course_id")
                rollcall_time = rollcall_time or rollcall.get("rollcall_time")
                break
    if course_id is None:
        return None

    # This endpoint indexes rollcalls by UTC creation date, not campus date.
    # A 07:53 China-time rollcall belongs to the previous UTC calendar day.
    rollcall_date = datetime.now(timezone.utc).date()
    if rollcall_time:
        try:
            timestamp = datetime.fromisoformat(rollcall_time.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            rollcall_date = timestamp.astimezone(timezone.utc).date()
        except (ValueError, AttributeError):
            pass

    response = in_session.get(
        f"{base_url}/api/timetable_rollcalls",
        params={"course_ids": [course_id], "rollcall_date": rollcall_date.isoformat()},
        timeout=(5, 15),
    )
    response.raise_for_status()
    for rollcall in response.json().get("rollcalls", []):
        if str(rollcall.get("id")) != str(rollcall_id):
            continue
        number_code = rollcall.get("number_code")
        if number_code is None:
            return None
        code = str(number_code)
        if 1 <= len(code) <= 4 and all("0" <= digit <= "9" for digit in code):
            return code.zfill(4)
        return None
    return None


def send_code(in_session, rollcall_id, course_id=None, rollcall_time=None):
    answer_url = f"{base_url}/api/rollcall/{rollcall_id}/answer_number_rollcall"
    print("Trying number code from timetable API...")
    t00 = time.time()
    request_headers = in_session.headers
    try:
        number_code = get_timetable_number_code(in_session, rollcall_id, course_id, rollcall_time)
    except requests.RequestException as e:
        t01 = time.time()
        print(f"Failed to request number code API: {e}\nTime: {t01 - t00:.2f} s.")
        return False
    except ValueError as e:
        t01 = time.time()
        print(f"Failed to parse number code API response: {e}\nTime: {t01 - t00:.2f} s.")
        return False

    if not number_code:
        t01 = time.time()
        print(f"Failed to get number code for this rollcall from timetable API.\nTime: {t01 - t00:.2f} s.")
        return False

    payload = {
        "deviceId": str(uuid.uuid4()),
        "numberCode": number_code
    }
    try:
        response = in_session.put(answer_url, json=payload, headers=request_headers, timeout=(5, 15))
        if response.status_code == 200:
            print("Number code rollcall answered successfully.\nNumber code: ", number_code)
            time.sleep(5)
            t01 = time.time()
            print(f"Time: {t01 - t00:.2f} s.")
            return True
        t01 = time.time()
        print(f"Failed to submit number code. Status: {response.status_code}\nTime: {t01 - t00:.2f} s.")
        return False
    except requests.RequestException as e:
        t01 = time.time()
        print(f"Failed to submit number code: {e}\nTime: {t01 - t00:.2f} s.")
        return False

def send_radar(in_session, rollcall_id):
    from .radar import send_radar_locations
    return send_radar_locations(in_session, rollcall_id)
