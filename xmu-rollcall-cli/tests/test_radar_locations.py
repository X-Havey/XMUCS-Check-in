import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from xmu_rollcall import radar, verify, rollcall_handler


def response(status=200, data=None):
    result = Mock(status_code=status)
    result.json.return_value = data
    return result


def activity(status="absent", **fields):
    return {"rollcall_id": 123, "is_radar": True, "is_expired": False,
            "rollcall_status": "in_progress", "status": status, **fields}


class RadarLocationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "radar_locations.json"
        self.config = {"coordinate_system": "gcj02", "device_id": "test-device", "locations": [
            {"name": f"Building {i}", "latitude": 24.6 + i / 1000, "longitude": 118.3}
            for i in range(3)]}
        self.save()
        environment = patch.dict(os.environ, {"XMU_RADAR_LOCATIONS_FILE": str(self.path)})
        environment.start()
        self.addCleanup(environment.stop)
        sleeper = patch.object(radar.time, "sleep")
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)
        self.session = Mock(headers={})
        self.preflight()
        self.output = io.StringIO()

    def save(self):
        self.path.write_text(json.dumps(self.config), encoding="utf-8")

    def preflight(self, beacon=False, confirmed="on_call_fine"):
        self.session.get.side_effect = [response(data={"rollcalls": [activity()]}),
                                       response(data={"use_beacon": beacon}),
                                       response(data={"rollcalls": [activity(confirmed)]})]

    def run_radar(self):
        with contextlib.redirect_stdout(self.output):
            return verify.send_radar(self.session, 123)

    def test_missing_distance_does_not_prevent_next_location(self):
        self.session.put.side_effect = [response(400, {"error_code": radar.OUT_OF_SCOPE}), response(200, {})]
        self.assertTrue(self.run_radar())
        calls = self.session.put.call_args_list
        self.assertEqual(len(calls), 2)
        for call, location in zip(calls, self.config["locations"]):
            self.assertEqual(call.kwargs["json"]["latitude"], location["latitude"])
            self.assertEqual(call.kwargs["json"]["deviceId"], "test-device")
            self.assertEqual(call.kwargs["params"], {"api_version": "1.76"})
            self.assertFalse(call.kwargs["allow_redirects"])

    def test_first_success_stops_at_one_location(self):
        self.session.put.return_value = response(200, {})
        self.assertTrue(self.run_radar())
        self.session.put.assert_called_once()
        self.sleep.assert_not_called()

    def test_three_rejections_are_not_repeated_on_next_poll(self):
        self.session.put.return_value = response(400, {"error_code": radar.OUT_OF_SCOPE})
        self.assertFalse(self.run_radar())
        self.assertFalse(self.run_radar())
        self.assertEqual(self.session.put.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_auth_device_bluetooth_unknown_and_rate_limit_errors_stop(self):
        for status, code in [(401, None), (403, "radar_device_id_invalid"),
                             (400, "radar_signal_invalid_no_signal"), (400, None),
                             (429, radar.OUT_OF_SCOPE), (503, radar.OUT_OF_SCOPE)]:
            with self.subTest(status=status, code=code):
                self.session.__dict__.pop("_xmu_radar_location_attempts", None)
                self.preflight()
                self.session.put.reset_mock()
                self.session.put.return_value = response(status, {"error_code": code})
                self.assertFalse(self.run_radar())
                self.session.put.assert_called_once()

    def test_beacon_or_unknown_setting_prevents_location_submissions(self):
        for settings in [{"use_beacon": True}, {}, {"use_beacon": "false"}]:
            with self.subTest(settings=settings):
                self.session.__dict__.pop("_xmu_radar_location_attempts", None)
                self.session.get.side_effect = [response(data={"rollcalls": [activity()]}), response(data=settings)]
                self.assertFalse(self.run_radar())
                self.session.put.assert_not_called()

    def test_already_signed_activity_is_skipped(self):
        self.session.get.side_effect = [response(data={"rollcalls": [activity("on_call_fine")]})]
        self.assertTrue(self.run_radar())
        self.session.put.assert_not_called()

    def test_closed_expired_missing_or_leave_activity_is_skipped(self):
        for rows in [[], [activity(is_expired=True)], [activity(rollcall_status="closed")], [activity("on_leave")]]:
            with self.subTest(rows=rows):
                self.session.__dict__.pop("_xmu_radar_location_attempts", None)
                self.session.get.side_effect = [response(data={"rollcalls": rows})]
                self.assertFalse(self.run_radar())
                self.session.put.assert_not_called()

    def test_timeout_stops_without_resubmission(self):
        self.session.put.side_effect = radar.requests.Timeout("timed out")
        self.assertFalse(self.run_radar())
        self.assertFalse(self.run_radar())
        self.session.put.assert_called_once()
        self.assertEqual(self.session.put.call_args.kwargs["timeout"], (5, 15))

    def test_http_200_requires_confirmed_signed_status(self):
        self.preflight(confirmed="absent")
        self.session.put.return_value = response(200, {})
        self.assertFalse(self.run_radar())
        self.session.put.assert_called_once()

    def test_confirmation_failure_does_not_try_more_locations(self):
        self.session.get.side_effect = [response(data={"rollcalls": [activity()]}), response(data={"use_beacon": False}), radar.requests.Timeout()]
        self.session.put.return_value = response(200, {})
        self.assertFalse(self.run_radar())
        self.session.put.assert_called_once()

    def test_redirect_or_html_does_not_try_another_location(self):
        self.session.put.return_value = response(302)
        self.session.put.return_value.json.side_effect = ValueError("HTML")
        self.assertFalse(self.run_radar())
        self.session.put.assert_called_once()

    def test_disabled_locations_are_not_submitted(self):
        self.config["locations"][0].update(enabled=False, latitude=None, longitude=None)
        self.save()
        self.session.put.return_value = response(200, {})
        self.assertTrue(self.run_radar())
        self.assertEqual(self.session.put.call_args.kwargs["json"]["latitude"], self.config["locations"][1]["latitude"])

    def test_invalid_config_prevents_requests(self):
        for change in [lambda c: c["locations"][0].update(latitude=float("nan")),
                       lambda c: c["locations"].extend([c["locations"][0]] * 3),
                       lambda c: c.update(coordinate_system="bd09")]:
            with self.subTest(change=change):
                baseline = json.loads(json.dumps(self.config))
                change(self.config)
                self.save()
                self.assertFalse(self.run_radar())
                self.session.get.assert_not_called()
                self.session.put.assert_not_called()
                self.config = baseline

    def test_generated_device_is_stable_between_locations(self):
        self.config.pop("device_id")
        self.save()
        self.session.put.side_effect = [response(400, {"error_code": radar.OUT_OF_SCOPE}), response(200, {})]
        self.assertTrue(self.run_radar())
        ids = [call.kwargs["json"]["deviceId"] for call in self.session.put.call_args_list]
        self.assertEqual(ids[0], ids[1])

    def test_log_keeps_error_without_authentication_or_payload(self):
        self.session.put.return_value = response(400, {"error_code": "radar_device_id_invalid", "token": "secret"})
        self.assertFalse(self.run_radar())
        content = self.path.with_name("radar_attempts.jsonl").read_text(encoding="utf-8")
        self.assertIn("radar_device_id_invalid", content)
        self.assertNotIn("secret", content)
        self.assertNotIn("test-device", content)

    def test_gcj_coordinates_are_not_transformed_twice(self):
        lat, lon = radar.to_gcj02(24.3, 118)
        self.assertAlmostEqual(lat, 24.297212346298068, places=10)
        self.assertAlmostEqual(lon, 118.00480514795184, places=10)
        locations, _ = radar.load_locations(self.path)
        self.assertEqual(locations[0]["latitude"], 24.6)
        self.config["coordinate_system"] = "wgs84"
        self.save()
        converted, _ = radar.load_locations(self.path)
        self.assertEqual((converted[0]["latitude"], converted[0]["longitude"]), radar.to_gcj02(24.6, 118.3))
        self.assertEqual(radar.to_gcj02(51.5, -0.1), (51.5, -0.1))

    def test_five_locations_are_tried_at_most_once_each(self):
        self.config["locations"].extend([
            {"name": "Building 3", "latitude": 24.603, "longitude": 118.3},
            {"name": "Building 4", "latitude": 24.604, "longitude": 118.3},
        ])
        self.save()
        self.session.put.return_value = response(400, {"error_code": radar.OUT_OF_SCOPE})
        self.assertFalse(self.run_radar())
        self.assertFalse(self.run_radar())
        self.assertEqual(self.session.put.call_count, 5)
        self.assertEqual(self.sleep.call_count, 4)
        self.assertEqual(
            [call.kwargs["json"]["latitude"] for call in self.session.put.call_args_list],
            [location["latitude"] for location in self.config["locations"]],
        )

    def test_monitor_stops_repeating_radar_but_preserves_numeric_retry(self):
        radar_data = {"rollcalls": [activity()]}
        numeric_data = {"rollcalls": [activity(is_radar=False)]}
        with patch.object(rollcall_handler, "handle_rollcalls", return_value=[False]):
            self.assertEqual(rollcall_handler.process_rollcalls(radar_data, self.session), radar_data)
            self.assertEqual(rollcall_handler.process_rollcalls(numeric_data, self.session), {"rollcalls": []})


if __name__ == "__main__":
    unittest.main()
