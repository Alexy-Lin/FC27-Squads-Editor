import unittest
from pathlib import Path

from core.meta_parser import MetaDatabase
from core.name_resolver import NameResolver
from core.sav_file import SavFile
from services.team_service import TeamService


ROOT = Path(__file__).resolve().parents[1]
SAVE = ROOT / "Squads20260918100256149"
META = ROOT / "data" / "fifa_ng_db-meta.xml"


@unittest.skipUnless(SAVE.is_file(), "本机没有 FC27 基准存档")
class FC27MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = MetaDatabase.from_file(META)
        cls.sav = SavFile()
        cls.sav.load(SAVE, cls.meta)
        cls.resolver = NameResolver(cls.sav.db)

    def test_team_public_and_internal_ids_are_distinct_but_consistent(self):
        teams = self.sav.db.get_table("lyxL").records
        self.assertEqual({r["teamid"] - r["assetid"] for r in teams}, {2})
        self.assertEqual(self.resolver.get_team_official_id(112141), 112139)
        self.assertEqual(self.resolver.get_team_internal_id(112139), 112141)

    def test_official_team_id_can_be_used_for_lookup(self):
        team = TeamService(self.sav).get_team(112139)
        self.assertEqual(team["teamid"], 112141)
        self.assertEqual(team["teamname"], "Al Nassr")

    def test_first_high_rating_player_id_corrections(self):
        players = {
            r["playerid"]: r
            for r in self.sav.db.get_table("CZUM").records
        }
        expected = {
            20802: (20801, "Cristiano Ronaldo"),
            158024: (158023, "Lionel Messi"),
            242445: (242444, "João Félix"),
            239086: (239085, "Erling Haaland"),
            252372: (252371, "Jude Bellingham"),
            231748: (231747, "Kylian Mbappé"),
        }
        for save_id, (official_id, name) in expected.items():
            self.assertEqual(self.resolver.get_official_player_id(players[save_id]), official_id)
            self.assertEqual(self.resolver.get_name(players[save_id]), name)

    def test_85_plus_alignment_uses_legend_and_fc27_reference_data(self):
        players = self.sav.db.get_table("CZUM").records
        high = [record for record in players if (record.get("overallrating") or 0) >= 85]
        aligned = [
            record for record in high
            if self.resolver.get_official_player_id(record) == record.get("playerid") - 1
        ]
        self.assertEqual(len(high), 338)
        self.assertGreaterEqual(len(aligned), 250)
        pele = next(record for record in players if record.get("playerid") == 237068)
        self.assertEqual(self.resolver.get_official_player_id(pele), 237067)
        self.assertEqual(self.resolver.get_name(pele), "Pelé")


if __name__ == "__main__":
    unittest.main()
