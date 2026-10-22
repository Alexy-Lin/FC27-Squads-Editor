import unittest
from pathlib import Path

from core.config import find_latest_save
from core.meta_parser import MetaDatabase
from core.sav_file import SavFile
from services.legend_service import LegendService
from web_app import EditorState, create_app


SAMPLE = find_latest_save()
ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "data" / "fifa_ng_db-meta.xml"
LEGEND_SAMPLE = ROOT / "Squads20261006"


def _save_with_missing_legends():
    """Find a save whose legend list is incomplete (the latest save may be complete)."""
    for candidate in (LEGEND_SAMPLE, SAMPLE):
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            sav = SavFile()
            sav.load(Path(candidate), MetaDatabase.from_file(META))
            preview = LegendService(sav).preview()
        except Exception:
            continue
        if preview["missing_count"]:
            return Path(candidate)
    return None


@unittest.skipUnless(SAMPLE and SAMPLE.is_file(), "本机没有 FC27 样本存档")
class QuickFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = EditorState(SAMPLE, remember_path=False)
        cls.client = create_app(cls.state).test_client()
        cls.headers = {"X-Editor-Token": cls.state.token}
        cls.meta = MetaDatabase.from_file(META)

    def tearDown(self):
        self.state.reset()

    def test_age_requires_token_and_uses_real_birthdays(self):
        self.assertEqual(
            self.client.post("/api/quick/age", json={"age": 18}).status_code,
            403,
        )
        preview = self.client.get("/api/quick/age/preview?age=18").get_json()
        self.assertGreater(preview["players"], 0)
        self.assertGreater(preview["changed"], 0)

        response = self.client.post(
            "/api/quick/age", headers=self.headers, json={"age": 18}
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        result = response.get_json()
        self.assertGreater(result["players_updated"], 0)
        # Real-birthday mode keeps month/day; only the year moves.
        birthdates = {record.get("birthdate") for record in self.state.players.table.records}
        self.assertNotIn(155123, birthdates)
        self.assertGreater(len(birthdates), 1)

    def test_birthday_snapshot_restore(self):
        self.client.post("/api/quick/age", headers=self.headers, json={"age": 18})
        status = self.client.get("/api/quick/age/status").get_json()
        self.assertTrue(status["snapshot"]["available"])
        response = self.client.post("/api/quick/age/restore", headers=self.headers, json={})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertGreater(response.get_json()["players_updated"], 0)

    def test_add_missing_legends_is_staged_and_idempotent(self):
        target = _save_with_missing_legends()
        if target is None:
            self.skipTest("本机没有缺失传奇的样本存档")
        state = EditorState(target, remember_path=False)
        client = create_app(state).test_client()
        headers = {"X-Editor-Token": state.token}
        try:
            preview = client.get("/api/quick/legends").get_json()
            self.assertGreater(preview["missing_count"], 0)
            # 默认只补男足：女足 ICON 会被跳过
            self.assertGreater(preview["women_skipped_count"], 0)
            self.assertEqual(
                {item["name"] for item in preview["extras"]},
                {"Mario Kempes", "Roberto Rivelino"},
            )
            response = client.post("/api/quick/add-legends", headers=headers, json={})
            self.assertEqual(response.status_code, 200, response.get_json())
            result = response.get_json()
            self.assertEqual(result["added"], preview["missing_count"])
            self.assertEqual(
                client.get("/api/quick/legends").get_json()["missing_count"], 0
            )
            self.assertEqual(
                client.post(
                    "/api/quick/add-legends", headers=headers, json={}
                ).get_json()["added"],
                0,
            )
        finally:
            state.reset()

    def test_legend_women_toggle_and_real_birthdays(self):
        target = _save_with_missing_legends()
        if target is None:
            self.skipTest("本机没有缺失传奇的样本存档")
        state = EditorState(target, remember_path=False)
        client = create_app(state).test_client()
        headers = {"X-Editor-Token": state.token}
        try:
            men = client.get("/api/quick/legends").get_json()
            women = client.get("/api/quick/legends?include_women=1").get_json()
            self.assertGreater(women["available_count"], men["available_count"])
            self.assertEqual(women["women_skipped_count"], 0)
            self.assertEqual(men["include_women"], False)

            extra = next(item for item in men["missing"] if item["playerid"] == 82092)
            self.assertTrue(extra["birthdate_fixed"])
            self.assertGreaterEqual(extra["birthdate"], 125812)
            response = client.post(
                "/api/quick/add-legends", headers=headers, json={}
            )
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertGreaterEqual(response.get_json()["names_added"], 2)
            players = {
                record.get("playerid"): record
                for record in state.players.table.records
            }
            self.assertIn(82092, players)
            self.assertGreaterEqual(players[82092]["birthdate"], 125812)
            names = {
                record.get("playerid")
                for record in state.sav.db.get_table("nQVU").records
            }
            self.assertIn(82092, names)
        finally:
            state.reset()

    def test_peak_preview_and_raise_only_apply(self):
        preview = self.client.get("/api/quick/peak").get_json()
        self.assertIn("count", preview)
        response = self.client.post(
            "/api/quick/restore-peak", headers=self.headers, json={}
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertGreaterEqual(response.get_json()["restored_count"], 0)


if __name__ == "__main__":
    unittest.main()
