import datetime
import unittest

from core.config import find_latest_save
from services.birthdates import EPOCH, describe, from_text
from web_app import EditorState, create_app


SAMPLE = find_latest_save()


class BirthdateConversionTests(unittest.TestCase):
    """Pure conversion helpers shared by the web editor and the CLI."""

    def test_iso_date_maps_to_the_stored_day_counter(self):
        self.assertEqual(from_text("1987-05-27"), 147783)
        self.assertEqual(from_text("1927-04-01"), 125812)
        self.assertEqual(from_text("1582-10-14"), 0)

    def test_raw_day_counter_is_still_accepted(self):
        self.assertEqual(from_text("147783"), 147783)
        self.assertEqual(describe(from_text("147783")), "1987-05-27")

    def test_invalid_values_are_rejected(self):
        for value in ("", None, "1990-02-30", "1990-13-01", "27/05/1987", "abc"):
            with self.assertRaises(ValueError, msg=repr(value)):
                from_text(value)

    def test_iso_date_round_trip(self):
        day = from_text("1954-07-15")
        self.assertEqual(day, (datetime.date(1954, 7, 15) - EPOCH).days)
        self.assertEqual(describe(day), "1954-07-15")


@unittest.skipUnless(SAMPLE and SAMPLE.is_file(), "本机没有 FC27 样本存档")
class PlayerBirthdateEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = EditorState(SAMPLE, remember_path=False)
        cls.client = create_app(cls.state).test_client()
        cls.headers = {"X-Editor-Token": cls.state.token}
        cls.player_id = next(
            record.get("playerid")
            for record in cls.state.players.table.records
            if record.get("birthdate")
        )

    def tearDown(self):
        self.state.reset()

    def _record(self):
        return self.state.players.get_player(self.player_id)

    def _birthdate_field(self):
        detail = self.client.get(f"/api/players/{self.player_id}").get_json()
        group = next(
            item for item in detail["fields"]
            if any(field["name"] == "birthdate" for field in item["fields"])
        )
        return next(field for field in group["fields"] if field["name"] == "birthdate")

    def _post_birthdate(self, value):
        return self.client.post(
            f"/api/players/{self.player_id}",
            headers=self.headers,
            json={"fields": {"birthdate": value}},
        )

    def test_detail_shows_a_calendar_date_instead_of_six_digits(self):
        field = self._birthdate_field()
        self.assertEqual(field["format"], "date")
        self.assertEqual(field["value"], describe(self._record()["birthdate"]))
        # 值必须是真正的日期，而不是 143832 这样的天数
        datetime.date.fromisoformat(field["value"])
        self.assertEqual(field["min"], "1582-10-14")

    def test_update_accepts_iso_date_and_reads_back_as_date(self):
        response = self._post_birthdate("1990-01-02")
        self.assertEqual(response.status_code, 200, response.get_json())
        expected = (datetime.date(1990, 1, 2) - EPOCH).days
        self.assertEqual(self._record()["birthdate"], expected)
        self.assertEqual(self._birthdate_field()["value"], "1990-01-02")

    def test_update_still_accepts_the_raw_day_counter(self):
        expected = (datetime.date(1976, 8, 1) - EPOCH).days
        response = self._post_birthdate(str(expected))
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self._record()["birthdate"], expected)
        self.assertEqual(self._birthdate_field()["value"], "1976-08-01")

    def test_invalid_date_is_rejected_without_touching_the_record(self):
        before = self._record()["birthdate"]
        for value in ("1990-02-30", "not-a-date", ""):
            response = self._post_birthdate(value)
            self.assertEqual(response.status_code, 400, f"{value!r} -> {response.get_json()}")
        self.assertEqual(self._record()["birthdate"], before)


if __name__ == "__main__":
    unittest.main()
