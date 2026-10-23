import contextlib
import io
import unittest
from unittest.mock import Mock, patch

from xmu_rollcall import verify, rollcall_handler


class TimetableCodeTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.session.headers = {}
        self.session.get.return_value.json.return_value = {
            "rollcalls": [{"id": 123, "number_code": "0037"}]
        }
        self.session.put.return_value.status_code = 200

    def code(self, timestamp="2026-10-12T11:06:00Z"):
        return verify.get_timetable_number_code(self.session, 123, 456, timestamp)

    def test_new_endpoint_uses_course_and_utc_date(self):
        self.assertEqual(self.code(), "0037")
        args, kwargs = self.session.get.call_args
        self.assertTrue(args[0].endswith("/api/timetable_rollcalls"))
        self.assertEqual(kwargs["params"], {"course_ids": [456], "rollcall_date": "2026-10-12"})

    def test_matches_rollcall_id_instead_of_first_code(self):
        self.session.get.return_value.json.return_value = {
            "rollcalls": [{"id": 999, "number_code": "9999"}, {"id": "123", "number_code": "0037"}]
        }
        self.assertEqual(self.code(), "0037")

    def test_no_matching_rollcall_does_not_use_other_code(self):
        self.session.get.return_value.json.return_value = {
            "rollcalls": [{"id": 999, "number_code": "9999"}]
        }
        self.assertIsNone(self.code())

    def test_late_utc_time_does_not_shift_to_next_campus_date(self):
        self.code("2026-10-12T16:06:00Z")
        self.assertEqual(self.session.get.call_args.kwargs["params"]["rollcall_date"], "2026-10-12")

    def test_early_morning_class_uses_previous_utc_date(self):
        # Live failure: 2026-10-23 07:53:57 in China is still Oct 22 in UTC.
        self.assertEqual(self.code("2026-10-22T23:53:57Z"), "0037")
        self.assertEqual(self.session.get.call_args.kwargs["params"]["rollcall_date"], "2026-10-22")

    def test_explicit_china_offset_converts_to_utc_date(self):
        self.code("2026-10-23T07:53:57+08:00")
        self.assertEqual(self.session.get.call_args.kwargs["params"]["rollcall_date"], "2026-10-22")

    def test_utc_midnight_stays_on_utc_day(self):
        self.code("2026-10-23T00:00:00Z")
        self.assertEqual(self.session.get.call_args.kwargs["params"]["rollcall_date"], "2026-10-23")

    def test_naive_server_timestamp_is_treated_as_utc(self):
        self.code("2026-10-22T23:53:57")
        self.assertEqual(self.session.get.call_args.kwargs["params"]["rollcall_date"], "2026-10-22")

    def test_null_code_does_not_submit(self):
        self.session.get.return_value.json.return_value = {
            "rollcalls": [{"id": 123, "number_code": None}]
        }
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(verify.send_code(self.session, 123, 456, "2026-10-12T11:06:00Z"))
        self.session.put.assert_not_called()

    def test_integer_code_keeps_leading_zeroes(self):
        self.session.get.return_value.json.return_value = {
            "rollcalls": [{"id": 123, "number_code": 37}]
        }
        self.assertEqual(self.code(), "0037")

    def test_two_argument_call_discovers_course_from_active_list(self):
        active_response = Mock()
        active_response.json.return_value = {"rollcalls": [
            {"rollcall_id": 123, "course_id": 456, "rollcall_time": "2026-10-12T11:06:00Z"}
        ]}
        timetable_response = self.session.get.return_value
        self.session.get.side_effect = [active_response, timetable_response]
        self.assertEqual(verify.get_timetable_number_code(self.session, 123), "0037")

    def test_read_failure_does_not_submit(self):
        self.session.get.side_effect = verify.requests.Timeout("timed out")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(verify.send_code(self.session, 123, 456))
        self.session.put.assert_not_called()

    def test_submission_uses_code_from_new_endpoint(self):
        with patch.object(verify.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(verify.send_code(self.session, 123, 456, "2026-10-12T11:06:00Z"))
        self.session.put.assert_called_once()
        self.assertTrue(self.session.put.call_args.args[0].endswith("/123/answer_number_rollcall"))
        self.assertEqual(self.session.put.call_args.kwargs["json"]["numberCode"], "0037")

    def test_monitor_passes_rollcall_course_and_time(self):
        rollcall = {
            "course_title": "Test", "created_by_name": "Teacher", "department_name": "Dept",
            "is_expired": False, "is_number": True, "is_radar": False, "rollcall_id": 123,
            "course_id": 456, "rollcall_time": "2026-10-12T11:06:00Z",
            "rollcall_status": "in_progress", "scored": False, "status": "absent",
        }
        with patch.object(rollcall_handler, "send_code", return_value=True) as submit, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rollcall_handler.handle_rollcalls({"rollcalls": [rollcall]}, self.session), [True])
        submit.assert_called_once_with(self.session, 123, course_id=456, rollcall_time=rollcall["rollcall_time"])

    def test_radar_still_uses_existing_handler(self):
        rollcall = {
            "course_title": "Test", "created_by_name": "Teacher", "department_name": "Dept",
            "is_expired": False, "is_number": False, "is_radar": True, "rollcall_id": 123,
            "rollcall_status": "in_progress", "scored": False, "status": "absent",
        }
        with patch.object(rollcall_handler, "send_radar", return_value=True) as radar, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rollcall_handler.handle_rollcalls({"rollcalls": [rollcall]}, self.session), [True])
        radar.assert_called_once_with(self.session, 123)

    def test_already_signed_rollcall_is_not_submitted(self):
        rollcall = {
            "course_title": "Test", "created_by_name": "Teacher", "department_name": "Dept",
            "is_expired": False, "is_number": True, "is_radar": False, "rollcall_id": 123,
            "rollcall_status": "in_progress", "scored": False, "status": "on_call_fine",
        }
        with patch.object(rollcall_handler, "send_code") as submit, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rollcall_handler.handle_rollcalls({"rollcalls": [rollcall]}, self.session), [True])
        submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
