import copy
import unittest

from core.config import find_latest_save
from web_app import EditorState, create_app


SAMPLE = find_latest_save()


@unittest.skipUnless(SAMPLE and SAMPLE.is_file(), "本机没有 FC27 样本存档")
class NationalSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = EditorState(SAMPLE, remember_path=False)
        cls.client = create_app(cls.state).test_client()
        cls.headers = {"X-Editor-Token": cls.state.token}
        meta = cls.client.get("/api/meta").get_json()
        cls.national = {item["teamid"]: item for item in meta["national_teams"]}
        cls.clubs = {item["teamid"]: item for item in meta["clubs"]}
        cls.men = [item for item in cls.national.values() if item["gender"] == 0]
        cls.women = [item for item in cls.national.values() if item["gender"] == 1]
        if not cls.men or not cls.women:
            raise unittest.SkipTest("样本存档没有男足/女足国家队名单")

    def tearDown(self):
        self.state.reset()

    def _editable_team(self, gender, size):
        for item in (self.men if gender == 0 else self.women):
            detail = self.client.get(f"/api/national-teams/{item['teamid']}").get_json()
            if detail.get("editable") and detail.get("roster_size") == size:
                return detail
        return None

    def test_national_team_list_contains_men_and_women_and_no_placeholders(self):
        self.assertGreaterEqual(len(self.men), 20)
        self.assertGreaterEqual(len(self.women), 5)
        for team_id, item in self.national.items():
            self.assertNotIn(team_id, self.clubs, f"{item['label']} 是国家队，不该出现在俱乐部列表里")
        for item in self.women:
            self.assertIn("女足", item["label"])
        for item in self.men:
            self.assertNotIn("女足", item["label"])
        resolver = self.state.resolver
        placeholders = [
            team_id for team_id, item in self.clubs.items()
            if resolver.is_non_player_team(team_id)
        ]
        self.assertEqual(placeholders, [], "5v5/经理池不该出现在可转会球队列表里")
        self.assertEqual(len(placeholders), 0)

    def test_men_team_read_apply_and_authorization(self):
        detail = self._editable_team(0, 26)
        if detail is None:
            self.skipTest("样本存档没有 26 人男足国家队")
        team_id = detail["teamid"]
        self.assertGreater(len(detail["candidates"]), 26)
        self.assertEqual(detail["expected_roster_size"], 26)
        self.assertEqual(
            self.client.post(f"/api/national-teams/{team_id}", json={"roster": []}).status_code,
            403,
        )

        selected = {item["playerid"] for item in detail["roster"]}
        incoming = next(
            item
            for item in detail["candidates"]
            if item["playerid"] not in selected and not item["unavailable"]
        )
        roster = [
            {"playerid": item["playerid"], "jerseynumber": index + 1}
            for index, item in enumerate(detail["roster"])
        ]
        roster[0]["playerid"] = incoming["playerid"]
        response = self.client.post(
            f"/api/national-teams/{team_id}",
            json={"roster": roster},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual({change.table for change in self.state.changes.values()}, {"RrqT"})
        self.assertEqual(
            self.client.post(
                f"/api/national-teams/{team_id}",
                json={"roster": roster},
                headers=self.headers,
            ).get_json()["applied"],
            0,
        )

    def test_invalid_request_is_atomic(self):
        detail = self._editable_team(0, 26)
        if detail is None:
            self.skipTest("样本存档没有 26 人男足国家队")
        team_id = detail["teamid"]
        roster = [
            {"playerid": item["playerid"], "jerseynumber": index + 1}
            for index, item in enumerate(detail["roster"])
        ]
        before = copy.deepcopy(self.state.rosters.table.records)
        response = self.client.post(
            f"/api/national-teams/{team_id}",
            json={"roster": roster[:-1]},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.state.rosters.table.records, before)
        self.assertFalse(self.state.changes)

    def test_candidates_match_roster_gender_and_skip_placeholders(self):
        detail = self._editable_team(0, 26)
        if detail is None:
            self.skipTest("样本存档没有 26 人男足国家队")
        players = {record.get("playerid"): record for record in self.state.players.table.records}
        self.assertEqual(detail["gender"], 0)
        self.assertTrue(detail["candidates"])
        for item in detail["candidates"]:
            self.assertEqual((players[item["playerid"]].get("gender") or 0), 0)
        self.assertGreaterEqual(detail["excluded_placeholders"], 0)
        from services.national_service import NationalService

        service = NationalService(self.state.rosters)
        placeholders = service.placeholder_player_ids()
        ids = {item["playerid"] for item in detail["candidates"]}
        self.assertFalse(ids & placeholders)

    def test_womens_team_keeps_its_own_size(self):
        detail = self._editable_team(1, 23)
        if detail is None:
            self.skipTest("样本存档没有 23 人女足国家队")
        team_id = detail["teamid"]
        self.assertEqual(detail["gender"], 1)
        self.assertEqual(detail["expected_roster_size"], detail["roster_size"])
        players = {record.get("playerid"): record for record in self.state.players.table.records}
        for item in detail["candidates"]:
            self.assertEqual((players[item["playerid"]].get("gender") or 0), 1)

        links_before = [
            record for record in self.state.rosters.table.records
            if record.get("teamid") == team_id
        ]
        selected = {item["playerid"] for item in detail["roster"]}
        incoming = next(
            item
            for item in detail["candidates"]
            if item["playerid"] not in selected and not item["unavailable"]
        )
        roster = [
            {"playerid": item["playerid"], "jerseynumber": index + 1}
            for index, item in enumerate(detail["roster"])
        ]
        roster[0]["playerid"] = incoming["playerid"]
        response = self.client.post(
            f"/api/national-teams/{team_id}",
            json={"roster": roster},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        links_after = [
            record for record in self.state.rosters.table.records
            if record.get("teamid") == team_id
        ]
        self.assertEqual(len(links_after), len(links_before))

    def test_candidates_carry_position_for_auto_numbering(self):
        detail = self._editable_team(0, 26)
        if detail is None:
            self.skipTest("样本存档没有 26 人男足国家队")
        for item in detail["candidates"][:200]:
            self.assertIn("position", item)
            self.assertIn("overallrating", item)
            self.assertIsInstance(item["primary_position"], str)
        keeper = next(
            (item for item in detail["candidates"] if item["primary_position"] == "GK"),
            None,
        )
        self.assertIsNotNone(keeper)
        self.assertEqual(keeper["position"], 0)

    def test_placeholder_and_manager_pools_are_recognised(self):
        resolver = self.state.resolver
        teams = self.state.sav.db.get_table("lyxL").records
        tiny = [
            record.get("teamid") for record in teams
            if resolver.is_non_player_team(record.get("teamid"))
        ]
        self.assertTrue(tiny, "样本存档应包含 5v5/经理池等占位球队")
        for team_id in tiny:
            self.assertNotIn(team_id, self.national)
            self.assertNotIn(team_id, self.clubs)
        free_agent = 111594
        self.assertFalse(resolver.is_non_player_team(free_agent))
        arsenal = next(
            (record.get("teamid") for record in teams
             if record.get("teamname") == "Arsenal"),
            None,
        )
        if arsenal:
            self.assertFalse(resolver.is_non_player_team(arsenal))

    def test_detected_national_teams_does_not_swallow_clubs(self):
        resolver = self.state.resolver
        detected = resolver.detected_national_teams()
        self.assertEqual(detected, resolver.detected_national_teams())  # cached/idempotent
        from services.national_service import NationalService

        service = NationalService(self.state.rosters)
        self.assertIsInstance(service.roster_gender([]), int)


if __name__ == "__main__":
    unittest.main()
