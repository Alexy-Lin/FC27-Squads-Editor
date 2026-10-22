"""FC27 id conventions.

Findings verified against the FC27 save files in this project:

* player save id  = public/EA id + 1   (Cristiano Ronaldo: save 20802, public 20801)
* team  internal id = assetid + 2       (test_fc27_mapping asserts this)
* birthdate = days since 1582-10-14     (see services/birthdates.py)

``data/player_id_map.csv`` carries explicit high-confidence overrides for rows
where the raw +1 rule is not trusted; anything unknown keeps its literal save id.
"""
from __future__ import annotations

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAYER_ID_MAP = PROJECT_ROOT / "data" / "player_id_map.csv"

#: Difference between the FC27 save player id and the public/EA player id.
PLAYER_ID_OFFSET = 1

#: Difference between the FC27 internal team id and the public/EA asset id.
TEAM_ID_OFFSET = 2

#: Public asset id of the free-agent pool, and its FC27 internal team id.
FREE_AGENT_ASSET_ID = 111592
FREE_AGENT_TEAM_ID = FREE_AGENT_ASSET_ID + TEAM_ID_OFFSET  # 111594


def load_player_overrides() -> dict[int, int]:
    """Return ``{save_playerid: official_playerid}`` from the bundled CSV."""
    overrides: dict[int, int] = {}
    if not PLAYER_ID_MAP.is_file():
        return overrides
    with PLAYER_ID_MAP.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                save_id = int((row.get("save_playerid") or "").strip())
                official_id = int((row.get("official_playerid") or "").strip())
            except (TypeError, ValueError):
                continue
            if save_id > 0 and official_id > 0:
                overrides[save_id] = official_id
    return overrides


OVERRIDES = load_player_overrides()


def official_to_save(official_id: int) -> int:
    """Map a public/EA player id to the FC27 save id it is stored under."""
    return int(official_id) + PLAYER_ID_OFFSET


def save_to_official(save_id: int) -> int:
    """Map an FC27 save player id to the public id, honouring explicit overrides."""
    save_id = int(save_id)
    if save_id in OVERRIDES:
        return OVERRIDES[save_id]
    return save_id + PLAYER_ID_OFFSET


def team_official_to_internal(asset_id: int) -> int:
    return int(asset_id) + TEAM_ID_OFFSET


def team_internal_to_official(team_id: int) -> int:
    return int(team_id) - TEAM_ID_OFFSET
