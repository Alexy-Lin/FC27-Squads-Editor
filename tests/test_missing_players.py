import unittest
from pathlib import Path

from core.config import find_latest_save
from web_app import EditorState, create_app

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "downloads" / "Squads20261003145848779"
SOURCE = ROOT / "Squads20261006"
SAMPLE = find_latest_save()


@unittest.skipUnless(
    TARGET.is_file() and SOURCE.is_file(), "本机没有 3DM 传奇档或官方档样本"
)
class MissingPlayersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = EditorState(TARGET, remember_path=False)
        cls.client = create_app(cls.state).test_client()
        cls.headers = {"X-Editor-Token": cls.state.token}

    @classmethod
    def tearDownClass(cls):
        pass

    def test_preview_reports_real_players_only(self):
        # A previous test in this class may have applied the import in memory.
        self.state.load(TARGET)
        response = self.client.post(
            "/api/quick/missing-players/preview",
            headers=self.headers,
            json={"source": str(SOURCE)},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        data = response.get_json()
        self.assertGreater(data["missing_count"], 0)
        self.assertGreater(data["id_swapped_count"], 0)
        self.assertGreater(data["placeholder_count"], 0)
        self.assertEqual(
            data["missing_count"] + data["id_swapped_count"] + data["placeholder_count"], 262
        )
        # Nothing with an empty/placeholder name may end up in the import list.
        self.assertTrue(all(not str(item["name"]).startswith("Player #") for item in data["missing"]))

    def test_apply_is_idempotent_and_adds_free_agents(self):
        before = self.client.post(
            "/api/quick/missing-players/preview",
            headers=self.headers,
            json={"source": str(SOURCE)},
        ).get_json()["missing_count"]
        response = self.client.post(
            "/api/quick/missing-players/apply",
            headers=self.headers,
            json={"source": str(SOURCE)},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["added"], before)
        after = self.client.post(
            "/api/quick/missing-players/preview",
            headers=self.headers,
            json={"source": str(SOURCE)},
        ).get_json()
        self.assertEqual(after["missing_count"], 0)


if __name__ == "__main__":
    unittest.main()
