"""Bulk age editing with real birthdays and a reversible snapshot.

The age feature keeps each player's real month/day and only moves the year, so a
squad is never flattened onto one arbitrary date (that is what the 3DM roster mod
does with ``154774``).  Real birthdays come from, in order:

1. ``data/fc27_real_birthdays.csv`` (exported from the official squads);
2. the real-birthday table for legends in :mod:`services.birthdates`;
3. the loaded save's current value, when it is a plausible birthday.

Every run stores a snapshot first, so "恢复原始生日" can undo the change.
"""
from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path

from core.sav_file import SavFile
from services.birthdates import (
    BIRTHDATE_MIN,
    age_at_season_start,
    describe,
    is_valid,
    shift_birthdate_to_age,
)
from services.changes import ChangeSet, FieldChange

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REAL_BIRTHDAYS_CSV = PROJECT_ROOT / "data" / "fc27_real_birthdays.csv"
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "birthdate_snapshots"

#: Acceptable range for the global age feature (the game hides younger values).
MIN_AGE = 3
MAX_AGE = 60


class AgeService:
    """Stage global age edits for the currently loaded save."""

    TABLE = "CZUM"
    KEY = "playerid"
    BIRTHDATE_FIELD = "birthdate"

    def __init__(self, sav: SavFile):
        if not sav.db:
            raise ValueError("存档尚未加载")
        self.sav = sav
        self.table = sav.db.get_table(self.TABLE)
        if not self.table:
            raise ValueError("存档中没有球员表 CZUM")
        self._real_birthdays = None

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def players(self):
        for record in self.table.records:
            player_id = record.get(self.KEY, 0)
            if isinstance(player_id, int) and player_id > 0:
                yield player_id, record

    def real_birthdays(self) -> dict[int, int]:
        if self._real_birthdays is not None:
            return self._real_birthdays
        data: dict[int, int] = {}
        if REAL_BIRTHDAYS_CSV.is_file():
            with REAL_BIRTHDAYS_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    try:
                        pid = int((row.get("save_playerid") or "").strip())
                        value = int((row.get("birthdate") or "").strip())
                    except (TypeError, ValueError):
                        continue
                    if pid > 0 and is_valid(value):
                        data[pid] = value
        self._real_birthdays = data
        return data

    def birthdate_of(self, player_id: int, record: dict) -> int:
        real = self.real_birthdays().get(player_id)
        if real is not None:
            return real
        value = record.get(self.BIRTHDATE_FIELD, 0)
        return value if is_valid(value) else 0

    # ------------------------------------------------------------------
    # snapshots
    # ------------------------------------------------------------------
    def snapshot_paths(self):
        stem = self.sav.filepath.stem if self.sav.filepath else "unsaved"
        return SNAPSHOT_DIR / f"{stem}.json", SNAPSHOT_DIR / "latest.json"

    @staticmethod
    def _read_snapshot(path: Path):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        birthdates = payload.get("birthdates")
        if not isinstance(birthdates, dict):
            return None
        cleaned = {}
        for key, value in birthdates.items():
            try:
                pid, raw = int(key), int(value)
            except (TypeError, ValueError):
                continue
            if pid > 0:
                cleaned[pid] = raw
        if not cleaned:
            return None
        payload["birthdates"] = cleaned
        return payload

    def load_snapshot(self):
        per_save, latest = self.snapshot_paths()
        for path in (per_save, latest):
            if path.is_file():
                payload = self._read_snapshot(path)
                if payload:
                    payload["path"] = str(path)
                    return payload
        return None

    def save_snapshot(self, force: bool = False):
        if not self.sav.filepath:
            return None
        per_save, latest = self.snapshot_paths()
        payload = {
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "save": str(self.sav.filepath),
            "birthdates": {
                str(pid): record.get(self.BIRTHDATE_FIELD, 0)
                for pid, record in self.players()
            },
        }
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        for path in {per_save, latest}:
            if force or not path.is_file():
                path.write_text(text, encoding="utf-8")
        return per_save

    # ------------------------------------------------------------------
    # preview
    # ------------------------------------------------------------------
    def preview(self, age: int):
        age = int(age)
        if not MIN_AGE <= age <= MAX_AGE:
            raise ValueError(f"年龄必须在 {MIN_AGE}-{MAX_AGE} 之间，收到 {age}")
        distribution = {}
        changed = 0
        samples = []
        for pid, record in self.players():
            current = record.get(self.BIRTHDATE_FIELD, 0)
            current_age = age_at_season_start(current) if isinstance(current, int) else None
            bucket = str(current_age) if current_age is not None else "?"
            distribution[bucket] = distribution.get(bucket, 0) + 1
            target = shift_birthdate_to_age(self.birthdate_of(pid, record), age)
            if target != current:
                changed += 1
                if len(samples) < 8:
                    samples.append({
                        "playerid": pid,
                        "from": describe(current) if current else "?",
                        "to": describe(target),
                    })
        snapshot = self.load_snapshot()
        return {
            "age": age,
            "players": sum(1 for _ in self.players()),
            "changed": changed,
            "current_years": dict(sorted(distribution.items(), key=lambda kv: str(kv[0]))),
            "samples": samples,
            "snapshot": {
                "available": bool(snapshot),
                "path": snapshot.get("path", "") if snapshot else "",
                "save": snapshot.get("save", "") if snapshot else "",
                "created": snapshot.get("created", "") if snapshot else "",
                "saved_players": len(snapshot["birthdates"]) if snapshot else 0,
            },
        }

    def status(self):
        snapshot = self.load_snapshot()
        invalid = 0
        for _pid, record in self.players():
            value = record.get(self.BIRTHDATE_FIELD, 0)
            if isinstance(value, int) and value and value < BIRTHDATE_MIN:
                invalid += 1
        return {
            "snapshot": {
                "available": bool(snapshot),
                "path": snapshot.get("path", "") if snapshot else "",
                "save": snapshot.get("save", "") if snapshot else "",
                "created": snapshot.get("created", "") if snapshot else "",
                "saved_players": len(snapshot["birthdates"]) if snapshot else 0,
            },
            "invalid_birthdates": invalid,
        }

    # ------------------------------------------------------------------
    # apply
    # ------------------------------------------------------------------
    def set_all_players_age(self, age: int) -> ChangeSet:
        age = int(age)
        if not MIN_AGE <= age <= MAX_AGE:
            raise ValueError(f"年龄必须在 {MIN_AGE}-{MAX_AGE} 之间，收到 {age}")
        self.save_snapshot()
        changes = ChangeSet()
        for pid, record in self.players():
            old_value = record.get(self.BIRTHDATE_FIELD, 0)
            target = shift_birthdate_to_age(self.birthdate_of(pid, record), age)
            if old_value == target:
                continue
            record[self.BIRTHDATE_FIELD] = target
            changes.add(FieldChange(
                self.TABLE, self.KEY, pid, self.BIRTHDATE_FIELD, old_value, target,
            ))
        return changes

    def restore_original_birthdays(self) -> ChangeSet:
        payload = self.load_snapshot()
        if not payload:
            raise ValueError("还没有生日快照：请先执行一次全员年龄调整，编辑器会自动记录原始生日。")
        birthdates = payload["birthdates"]
        changes = ChangeSet()
        for pid, record in self.players():
            original = birthdates.get(pid)
            if original is None:
                continue
            current = record.get(self.BIRTHDATE_FIELD, 0)
            if current == original:
                continue
            record[self.BIRTHDATE_FIELD] = original
            changes.add(FieldChange(
                self.TABLE, self.KEY, pid, self.BIRTHDATE_FIELD, current, original,
            ))
        return changes

    def restore_real_birthdays(self) -> ChangeSet:
        """Write the bundled real birthdays back (no age change)."""
        changes = ChangeSet()
        for pid, record in self.players():
            real = self.real_birthdays().get(pid)
            if real is None:
                continue
            current = record.get(self.BIRTHDATE_FIELD, 0)
            if current == real:
                continue
            record[self.BIRTHDATE_FIELD] = real
            changes.add(FieldChange(
                self.TABLE, self.KEY, pid, self.BIRTHDATE_FIELD, current, real,
            ))
        return changes
