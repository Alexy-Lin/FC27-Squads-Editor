"""Export real player birthdays for every FC27 player the editor knows.

Sources, in priority order:

1. ``Squads20261006`` (official squads) — real birthdays for all current players;
2. ``services.birthdates.REAL_BIRTHDAYS`` — legends whose imported rows carry
   placeholder values (public id keyed, converted to the FC27 save id).

The result (``data/fc27_real_birthdays.csv``) lets the age feature keep each
player's real month/day even when the loaded save was flattened to one value by
a roster mod.
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
from core.id_map import official_to_save
from services.birthdates import REAL_BIRTHDAYS, BIRTHDATE_MIN, describe

OFFICIAL = ROOT / "Squads20261006"
OUT = ROOT / "data" / "fc27_real_birthdays.csv"

meta = MetaDatabase.from_file(ROOT / "data" / "fifa_ng_db-meta.xml")
sav = SavFile()
sav.load(OFFICIAL, meta)
resolver = NameResolver(sav.db)

rows = {}
for rec in sav.db.get_table("CZUM").records:
    pid = rec.get("playerid")
    bd = rec.get("birthdate")
    if not isinstance(pid, int) or pid <= 0:
        continue
    if not isinstance(bd, int) or bd < BIRTHDATE_MIN:
        continue
    rows[pid] = {"save_playerid": pid, "birthdate": bd, "name": resolver.get_name(rec), "source": "official"}

for official_id, bd in REAL_BIRTHDAYS.items():
    pid = official_to_save(official_id)
    if pid in rows:
        continue
    try:
        name = resolver.get_name_by_player_id(pid)
    except Exception:
        name = f"Player #{pid}"
    rows[pid] = {"save_playerid": pid, "birthdate": bd, "name": name, "source": "legend_real"}

with OUT.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=["save_playerid", "birthdate", "name", "source"])
    writer.writeheader()
    for pid in sorted(rows):
        writer.writerow(rows[pid])

print("saved:", OUT)
print("rows:", len(rows), "size:", OUT.stat().st_size)
print("sample:", list(rows.items())[:2])
