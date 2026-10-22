"""Restore active veterans to their peak attributes.

Peak data sources, in priority order:

1. ``data/fifa19_peak.csv`` — FIFA19 peak rows, keyed by the *public* player id
   (same convention as the FC26 editor);
2. ``data/fc27_peak_fallback.csv`` — exported from the 3DM legend save for
   players who do not exist in FIFA19 (post-2019 debuts), keyed by FC27 save id.

Selection rules (ported from the FC26 editor and adapted to FC27):

* active players only (age >= ``min_age``), male, not part of the legend/ICON set;
* only when the peak OVR is meaningfully high (``min_peak``), and only raise
  attributes — a player is never weakened;
* nationality and height must match the peak row, which keeps same-name players
  from being mistaken for the star;
* players whose club disappeared from the current data version still count as
  active when ``include_clubless`` is on;
* goalkeeper attributes are only written to goalkeepers.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from core.id_map import FREE_AGENT_TEAM_ID
from core.name_resolver import NameResolver
from core.sav_file import SavFile
from services.birthdates import age_at_season_start
from services.changes import ChangeSet, FieldChange

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Highest regular FIFA19 rating; above this is an ICON/promo row.
PEAK_MAX = 94

#: FC27 legend/ICON source list (public/EA ids).
ICON_LIST = PROJECT_ROOT / "data" / "icon_hero_list.csv"

FIELDS = [
    "overallrating", "potential", "finishing", "dribbling", "ballcontrol", "sprintspeed",
    "acceleration", "shotpower", "shortpassing", "longpassing", "vision", "composure",
    "agility", "balance", "jumping", "strength", "headingaccuracy", "standingtackle",
    "slidingtackle", "interceptions", "curve", "freekickaccuracy", "penalties", "volleys",
    "positioning", "crossing", "longshots", "stamina", "reactions", "aggression",
    "defensiveawareness", "gkdiving", "gkhandling", "gkkicking", "gkpositioning", "gkreflexes",
    "weakfootabilitytypecode", "skillmoves", "skillmoveslikelihood", "preferredfoot",
    "internationalrep",
]

GK_FIELDS = ("gkdiving", "gkhandling", "gkkicking", "gkpositioning", "gkreflexes")

#: Same-name players that a pure data match would mistake for the star
#: (public ids, taken from the FC26 editor's findings).
SAME_NAME_IDS = {193080, 192387}


class PeakRestoreService:
    """Stage "restore veterans to peak" edits for the loaded save."""

    TABLE = "CZUM"
    KEY = "playerid"
    LINK_TABLE = "RrqT"
    FREE_AGENT_TEAM_ID = FREE_AGENT_TEAM_ID
    FIFA19_PEAK = PROJECT_ROOT / "data" / "fifa19_peak.csv"
    FC27_PEAK = PROJECT_ROOT / "data" / "fc27_peak_fallback.csv"

    def __init__(self, sav: SavFile):
        if not sav.db:
            raise ValueError("存档尚未加载")
        self.sav = sav
        self.players = sav.db.get_table(self.TABLE)
        if not self.players:
            raise ValueError("存档中没有球员表 CZUM")
        self.resolver = NameResolver(sav.db)
        self._fifa19: Optional[dict] = None
        self._fc27: Optional[dict] = None
        self._legend_ids: Optional[set] = None
        self._player_teams: dict[int, list[int]] = {}
        links = sav.db.get_table(self.LINK_TABLE)
        if links:
            for record in links.records:
                player_id = record.get(self.KEY, 0)
                team_id = record.get("teamid", 0)
                if player_id and team_id:
                    self._player_teams.setdefault(player_id, []).append(team_id)

    # ------------------------------------------------------------------
    # data
    # ------------------------------------------------------------------
    @staticmethod
    def _as_int(value) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return 0

    def _load_fifa19(self) -> dict:
        if self._fifa19 is not None:
            return self._fifa19
        if not self.FIFA19_PEAK.is_file():
            raise ValueError("缺少 FIFA19 巅峰数据 data/fifa19_peak.csv")
        data = {}
        with self.FIFA19_PEAK.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                player_id = self._as_int(row.get("playerid"))
                if not player_id:
                    continue
                values = {field: self._as_int(row.get(field)) for field in FIELDS}
                data[player_id] = {
                    "values": values,
                    "nationality": self._as_int(row.get("nationality")),
                    "height": self._as_int(row.get("height")),
                    "position": self._as_int(row.get("preferredposition1")),
                    "peak": values.get("overallrating", 0),
                    "name": (row.get("name") or "").strip(),
                    "source": "FIFA19",
                }
        self._fifa19 = data
        return data

    def _load_fc27(self) -> dict:
        if self._fc27 is not None:
            return self._fc27
        data = {}
        if self.FC27_PEAK.is_file():
            with self.FC27_PEAK.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    player_id = self._as_int(row.get("save_playerid"))
                    if not player_id:
                        continue
                    values = {field: self._as_int(row.get(field)) for field in FIELDS}
                    data[player_id] = {
                        "values": values,
                        "nationality": self._as_int(row.get("nationality")),
                        "height": self._as_int(row.get("height")),
                        "position": self._as_int(row.get("preferredposition1")),
                        "peak": values.get("overallrating", 0),
                        "source": "3DM",
                    }
        self._fc27 = data
        return data

    def legend_ids(self) -> set:
        if self._legend_ids is not None:
            return self._legend_ids
        ids = set()
        if ICON_LIST.is_file():
            with ICON_LIST.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    raw = (row.get("IDs") or "").strip()
                    if raw.isdigit():
                        ids.add(int(raw))
        self._legend_ids = ids
        return ids

    def _official_id(self, record: dict) -> int:
        return int(self.resolver.get_official_player_id(record))

    def _lookup_peak(self, record: dict, official: int):
        """Return the best verified peak entry for a player, or ``None``."""
        fifa19 = self._load_fifa19()
        player_id = record.get(self.KEY, 0)
        # When the resolver could not remap the player (low rating / new player)
        # the save id is still ``public id + 1``; try that id first.
        order = [official, official - 1] if official != player_id else [official - 1, official]
        entry = None
        for candidate in order:
            row = fifa19.get(candidate)
            if not row:
                continue
            if row.get("peak", 0) > PEAK_MAX:
                continue
            if not self._verified(record, row):
                continue
            entry = row
            break
        fallback = self._load_fc27().get(player_id)
        if fallback is not None and fallback["peak"] > 0:
            if entry is not None and entry["peak"] >= fallback["peak"]:
                return entry
            return fallback
        return entry

    @staticmethod
    def _name_tokens(name: str) -> set[str]:
        import unicodedata
        text = unicodedata.normalize("NFKD", str(name or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
        for char in ".-'":
            text = text.replace(char, " ")
        return {token for token in text.split() if len(token) >= 2}

    def _verified(self, record: dict, row: dict) -> bool:
        """Reject FIFA19 rows whose name does not match the save player."""
        row_name = row.get("name") or ""
        if not row_name.strip():
            return False
        save_name = self.resolver.get_name(record) or ""
        row_tokens = self._name_tokens(row_name)
        save_tokens = self._name_tokens(save_name)
        if not row_tokens or not save_tokens:
            return False
        return bool(row_tokens & save_tokens)

    def club_teams(self, player_id: int):
        teams = []
        for team_id in self._player_teams.get(player_id, []):
            if team_id == self.FREE_AGENT_TEAM_ID:
                continue
            if self.resolver.is_national_team(team_id):
                continue
            teams.append(team_id)
        return teams

    def is_classic_only(self, clubs: list[int]) -> bool:
        """Retired players only appear in the all-time/classic squads."""
        if not clubs:
            return False
        for team_id in clubs:
            english, chinese = self.resolver.get_team_names(team_id)
            text = f"{english} {chinese}".lower()
            if "classic" not in text and "经典" not in text:
                return False
        return True

    # ------------------------------------------------------------------
    # selection
    # ------------------------------------------------------------------
    def raiseable_fields(self, record: dict, entry: dict):
        is_gk = entry.get("position") == 0 or (record.get("preferredposition1") or 0) == 0
        values = entry["values"]
        result = []
        for field in FIELDS:
            if field in GK_FIELDS and not is_gk:
                continue
            target = values.get(field) or 0
            if target and target > (record.get(field, 0) or 0):
                result.append(field)
        return result

    def candidates(self, min_peak: int = 85, min_age: int = 30, include_clubless: bool = True,
                   skip_same_name: bool = True, include_done: bool = False):
        legends = self.legend_ids()
        found = []
        for record in self.players.records:
            player_id = record.get(self.KEY, 0)
            if not isinstance(player_id, int) or player_id <= 0:
                continue
            official = self._official_id(record)
            if official in legends or player_id in legends or (player_id - 1) in legends:
                continue
            if skip_same_name and (official in SAME_NAME_IDS or player_id in SAME_NAME_IDS):
                continue
            if (record.get("gender", 0) or 0) != 0:
                continue
            entry = self._lookup_peak(record, official)
            if not entry:
                continue
            target_ovr = entry["peak"]
            if target_ovr < min_peak:
                continue
            if entry.get("source") == "FIFA19" and target_ovr > PEAK_MAX:
                continue
            if entry.get("nationality") and entry["nationality"] != (record.get("nationality") or 0):
                continue
            if entry.get("height") and abs(entry["height"] - (record.get("height") or 0)) > 3:
                continue
            age = age_at_season_start(record.get("birthdate", 0) or 0)
            if age is None or age < min_age:
                continue
            clubs = self.club_teams(player_id)
            if self.is_classic_only(clubs):
                continue
            if entry.get("source") == "3DM" and not clubs:
                # The 3DM fallback free agents are mostly legends the mod added;
                # restoring them to "peak" would just re-import legend ratings.
                continue
            if not clubs and not include_clubless:
                continue
            raiseable = self.raiseable_fields(record, entry)
            if not raiseable and not include_done:
                continue
            found.append({
                "playerid": player_id,
                "official_id": official,
                "name": self.resolver.get_name(record),
                "age": age,
                "overallrating": record.get("overallrating", 0) or 0,
                "peak": target_ovr,
                "gain": max(0, target_ovr - (record.get("overallrating", 0) or 0)),
                "raiseable": len(raiseable),
                "done": not raiseable,
                "gk": entry.get("position") == 0 or (record.get("preferredposition1") or 0) == 0,
                "club": ", ".join(self.resolver.get_team_name(team) for team in clubs),
                "clubless": not clubs,
                "source": entry.get("source", ""),
            })
        if include_done:
            found.sort(key=lambda item: (item["done"], -item["peak"], -item["raiseable"], item["name"]))
        else:
            found.sort(key=lambda item: (-item["peak"], -item["raiseable"], item["name"]))
        return found

    def preview(self, min_peak: int = 85, min_age: int = 30, include_clubless: bool = True,
                skip_same_name: bool = True, include_done: bool = False):
        candidates = self.candidates(
            min_peak=min_peak, min_age=min_age, include_clubless=include_clubless,
            skip_same_name=skip_same_name, include_done=include_done,
        )
        return {
            "count": sum(1 for item in candidates if not item["done"]),
            "roster_count": len(candidates),
            "min_peak": min_peak,
            "min_age": min_age,
            "include_clubless": include_clubless,
            "skip_same_name": skip_same_name,
            "clubless_count": sum(1 for item in candidates if item["clubless"]),
            "gk_count": sum(1 for item in candidates if item["gk"] and not item["done"]),
            "fifa19_count": sum(1 for item in candidates if item["source"] == "FIFA19"),
            "fc27_count": sum(1 for item in candidates if item["source"] == "3DM"),
            "include_done": include_done,
            "candidates": candidates,
        }

    # ------------------------------------------------------------------
    # apply
    # ------------------------------------------------------------------
    def apply(self, min_peak: int = 85, min_age: int = 30, include_clubless: bool = True,
              only_raise: bool = True, skip_same_name: bool = True):
        candidates = self.candidates(
            min_peak=min_peak, min_age=min_age, include_clubless=include_clubless,
            skip_same_name=skip_same_name,
        )
        by_id = {record.get(self.KEY): record for record in self.players.records}
        changes = ChangeSet()
        restored = []
        field_total = 0
        for item in candidates:
            record = by_id.get(item["playerid"])
            if record is None:
                continue
            entry = self._lookup_peak(record, item["official_id"])
            if not entry:
                continue
            values = entry["values"]
            is_gk = entry.get("position") == 0 or (record.get("preferredposition1") or 0) == 0
            touched = 0
            for field in FIELDS:
                if field in GK_FIELDS and not is_gk:
                    continue
                target = values.get(field) or 0
                if not target:
                    continue
                current = record.get(field, 0) or 0
                if target == current or (only_raise and target < current):
                    continue
                record[field] = target
                changes.add(FieldChange(
                    self.TABLE, self.KEY, item["playerid"], field, current, target,
                ))
                touched += 1
            if touched:
                field_total += touched
                restored.append({
                    **item,
                    "fields": touched,
                    "overallrating_after": record.get("overallrating", 0),
                })
        return changes, {
            "candidate_count": len(candidates),
            "restored_count": len(restored),
            "field_count": field_total,
            "only_raise": only_raise,
            "restored": restored,
        }
