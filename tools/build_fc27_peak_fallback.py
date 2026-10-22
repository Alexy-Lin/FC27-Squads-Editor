"""Build the 3DM-based peak fallback dataset.

FIFA19 has no rows for players who debuted after 2019. For those, the 3DM
legend save (Squads20261003145848779) carries boosted/peak values, so we export
its full attribute set as ``data/fc27_peak_fallback.csv``.

The file is keyed by the FC27 *save* player id, because it is used against FC27
saves that share the same id space.
"""
import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r"D:\Software\FC27 Editor")
sys.path.insert(0, str(ROOT))

from core.meta_parser import MetaDatabase
from core.name_resolver import NameResolver
from core.sav_file import SavFile

SAVE = ROOT / "downloads" / "Squads20261003145848779"
OUT = ROOT / "data" / "fc27_peak_fallback.csv"

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

meta = MetaDatabase.from_file(ROOT / "data" / "fifa_ng_db-meta.xml")
sav = SavFile()
sav.load(SAVE, meta)
resolver = NameResolver(sav.db)
players = sav.db.get_table("CZUM").records

rows = []
for rec in players:
    pid = rec.get("playerid")
    if not isinstance(pid, int) or pid <= 0:
        continue
    row = {"save_playerid": pid}
    for field in FIELDS:
        row[field] = rec.get(field, 0)
    row["nationality"] = rec.get("nationality", 0)
    row["height"] = rec.get("height", 0)
    row["preferredposition1"] = rec.get("preferredposition1", 0)
    row["gender"] = rec.get("gender", 0)
    row["name"] = resolver.get_name(rec)
    rows.append(row)

with OUT.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

print("saved:", OUT, "rows:", len(rows), "size:", OUT.stat().st_size)
