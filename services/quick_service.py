import sqlite3
from datetime import date, timedelta
from pathlib import Path

from core.sav_file import SavFile
from .changes import ChangeSet, FieldChange


class QuickFeatureService:
    """Implement small, reversible bulk edits for the currently loaded save."""

    TABLE = "CZUM"
    KEY = "playerid"
    BIRTHDATE_FIELD = "birthdate"

    # FC stores birthdate as days since 1582-10-14.
    BIRTHDATE_AGE18 = 155123
    BIRTHDATE_AGE17 = 155854  # 2009-07-01, age 17 during the FC27 season
    BIRTHDATE_BASE = date(1582, 10, 14)
    SEASON_START = date(2026, 7, 1)
    PEAK_DATABASE = Path(__file__).resolve().parent.parent / "data" / "legend_database.db"
    # These two active stars are intentionally included even if the age test
    # is unavailable in a partial or edited squad file.
    PEAK_PLAYER_IDS = {20801, 158023}  # Cristiano Ronaldo, Lionel Messi

    def __init__(self, sav: SavFile):
        if not sav.db:
            raise ValueError("存档尚未加载")
        table = sav.db.get_table(self.TABLE)
        if not table:
            raise ValueError("存档中没有球员表 CZUM")
        if not table.get_field_by_name(self.BIRTHDATE_FIELD) and not table.get_field(self.BIRTHDATE_FIELD):
            raise ValueError("球员表没有 birthdate 字段")
        self.table = table

    def set_all_players_age18(self) -> ChangeSet:
        """Set every valid player's birthdate to the legacy age-18 value."""
        changes = ChangeSet()
        for record in self.table.records:
            player_id = record.get(self.KEY, 0)
            if not isinstance(player_id, int) or player_id <= 0:
                continue
            old_value = record.get(self.BIRTHDATE_FIELD, 0)
            if old_value == self.BIRTHDATE_AGE18:
                continue
            record[self.BIRTHDATE_FIELD] = self.BIRTHDATE_AGE18
            changes.add(FieldChange(
                self.TABLE,
                self.KEY,
                player_id,
                self.BIRTHDATE_FIELD,
                old_value,
                self.BIRTHDATE_AGE18,
            ))
        return changes

    def set_all_players_age17_and_restore_peak(self):
        """Age everyone to 17 and restore bundled peak profiles for older stars.

        The bundled database contains peak snapshots for legends and selected
        veteran stars. Only players already present in the current squad file
        are changed; no records are created by this feature.
        """
        changes = ChangeSet()
        peak_records = self._load_peak_records()
        peak_players = 0
        players_updated = set()

        for record in self.table.records:
            player_id = record.get(self.KEY, 0)
            if not isinstance(player_id, int) or player_id <= 0:
                continue
            old_birthdate = record.get(self.BIRTHDATE_FIELD, 0)
            old_age = self._age_at_season_start(old_birthdate)
            peak = peak_records.get(player_id)
            if peak and (old_age is None or old_age >= 30 or player_id in self.PEAK_PLAYER_IDS):
                changed_peak = False
                for field, new_value in peak.items():
                    if field in {self.KEY, self.BIRTHDATE_FIELD} or field not in record:
                        continue
                    old_value = record.get(field)
                    if old_value == new_value:
                        continue
                    record[field] = new_value
                    changes.add(FieldChange(self.TABLE, self.KEY, player_id, field, old_value, new_value))
                    changed_peak = True
                if changed_peak:
                    peak_players += 1
                    players_updated.add(player_id)

            if old_birthdate != self.BIRTHDATE_AGE17:
                record[self.BIRTHDATE_FIELD] = self.BIRTHDATE_AGE17
                changes.add(FieldChange(
                    self.TABLE, self.KEY, player_id, self.BIRTHDATE_FIELD,
                    old_birthdate, self.BIRTHDATE_AGE17,
                ))
                players_updated.add(player_id)

        return changes, {
            "players_updated": len(players_updated),
            "peak_players": peak_players,
        }

    @classmethod
    def _age_at_season_start(cls, raw_birthdate):
        if not isinstance(raw_birthdate, int) or raw_birthdate <= 0:
            return None
        try:
            born = cls.BIRTHDATE_BASE + timedelta(days=raw_birthdate)
        except OverflowError:
            return None
        return cls.SEASON_START.year - born.year - (
            (cls.SEASON_START.month, cls.SEASON_START.day) < (born.month, born.day)
        )

    @classmethod
    def _load_peak_records(cls):
        if not cls.PEAK_DATABASE.is_file():
            return {}
        try:
            with sqlite3.connect(cls.PEAK_DATABASE) as connection:
                connection.row_factory = sqlite3.Row
                return {
                    int(row[cls.KEY]): dict(row)
                    for row in connection.execute("SELECT * FROM czum")
                    if row[cls.KEY] is not None
                }
        except sqlite3.Error:
            return {}
