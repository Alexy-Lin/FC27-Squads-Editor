"""Bring players that exist in a source save but are missing from the loaded save.

Typical use: the 3DM legend roster (built on an older squad snapshot) is missing
a handful of official players.  This service copies them back into the loaded
save as **free agents** (the user's chosen policy), including their names and a
team link to the free-agent pool.

Classification (same rules as the comparison report):

* ``id_swapped`` — the player exists under another id (FC27 id offset); skipped,
  that belongs to ID-remapping/mod territory;
* ``placeholder`` — generated/placeholder records (``Player #…``, 5v5/manager
  pools, custom teams); skipped by default;
* ``real`` — genuinely missing players; these are imported.
"""
from __future__ import annotations

from pathlib import Path

from core.id_map import FREE_AGENT_TEAM_ID
from core.meta_parser import MetaDatabase
from core.name_resolver import NameResolver
from core.sav_file import SavFile
from services.changes import ChangeSet, RecordChange

PROJECT_ROOT = Path(__file__).resolve().parent.parent
META_PATH = PROJECT_ROOT / "data" / "fifa_ng_db-meta.xml"

_META: MetaDatabase | None = None


def _meta() -> MetaDatabase:
    global _META
    if _META is None:
        _META = MetaDatabase.from_file(META_PATH)
    return _META


def _normalize(name: str) -> str:
    return " ".join(str(name).lower().replace("  ", " ").split())


class MissingPlayersService:
    PLAYER_TABLE = "CZUM"
    LINK_TABLE = "RrqT"
    NAME_TABLE = "bneD"
    EDITED_TABLE = "nQVU"
    PLAYER_KEY = "playerid"
    LINK_KEY = "artificialkey"
    NAME_KEY = "nameid"
    FREE_AGENT_TEAM_ID = FREE_AGENT_TEAM_ID
    NAME_ID_FIELDS = ("firstnameid", "lastnameid", "playerjerseynameid", "commonnameid")

    def __init__(self, sav: SavFile):
        if not sav.db:
            raise ValueError("存档尚未加载")
        self.sav = sav
        self.players = sav.db.get_table(self.PLAYER_TABLE)
        self.links = sav.db.get_table(self.LINK_TABLE)
        self.names = sav.db.get_table(self.NAME_TABLE)
        self.edited = sav.db.get_table(self.EDITED_TABLE)
        if not self.players or not self.links:
            raise ValueError("存档缺少球员表 CZUM 或球队关系表 RrqT")
        self.resolver = NameResolver(sav.db)

    # ------------------------------------------------------------------
    # scan / preview
    # ------------------------------------------------------------------
    @staticmethod
    def _is_placeholder(name: str, club: str) -> bool:
        name = (name or "").strip().lower()
        club = (club or "").strip().lower()
        return (
            not name
            or name.startswith("player #")
            or "placeholder" in club
            or "custom team" in club
            or "5v5" in club
        )

    def _target_names(self) -> set[str]:
        return {_normalize(self.resolver.get_name(record)) for record in self.players.records}

    def scan(self, source_path) -> dict:
        source_path = Path(source_path)
        if not source_path.is_file():
            raise ValueError(f"找不到源存档：{source_path}")
        if self.sav.filepath and source_path.resolve() == Path(self.sav.filepath).resolve():
            raise ValueError("源存档不能是当前正在编辑的存档")
        source = SavFile()
        source.load(source_path, _meta())
        source_resolver = NameResolver(source.db)
        source_players = source.db.get_table(self.PLAYER_TABLE)
        if not source_players:
            raise ValueError("源存档缺少球员表 CZUM")

        target_ids = {
            record.get(self.PLAYER_KEY)
            for record in self.players.records
            if record.get(self.PLAYER_KEY)
        }
        target_names = self._target_names()

        real, swapped, placeholders = [], [], []
        for record in source_players.records:
            pid = record.get(self.PLAYER_KEY)
            if not isinstance(pid, int) or pid <= 0 or pid in target_ids:
                continue
            name = source_resolver.get_name(record)
            club, nat = source_resolver.get_player_team(pid)
            club_name = club or nat or ""
            item = {
                "playerid": pid,
                "name": name,
                "club": club_name,
                "nationality": nat or "",
                "position": self._position_name(record.get("preferredposition1")),
                "overallrating": record.get("overallrating", 0) or 0,
                "age": self._age(record.get("birthdate", 0)),
            }
            if self._is_placeholder(name, club_name):
                placeholders.append(item)
            elif _normalize(name) in target_names:
                swapped.append(item)
            else:
                real.append(item)

        return {
            "source": str(source_path),
            "source_players": len(source_players.records),
            "target_players": len(self.players.records),
            "real": real,
            "id_swapped": swapped,
            "placeholder": placeholders,
        }

    def preview(self, source_path) -> dict:
        scan = self.scan(source_path)
        real = sorted(scan["real"], key=lambda x: (-x["overallrating"], x["name"]))
        return {
            "source": scan["source"],
            "source_players": scan["source_players"],
            "target_players": scan["target_players"],
            "missing_count": len(real),
            "id_swapped_count": len(scan["id_swapped"]),
            "placeholder_count": len(scan["placeholder"]),
            "missing": real,
            "id_swapped": scan["id_swapped"],
            "placeholder": scan["placeholder"],
        }

    # ------------------------------------------------------------------
    # apply
    # ------------------------------------------------------------------
    def _position_name(self, code) -> str:
        from core.mappings import POSITION_NAMES
        return POSITION_NAMES.get(code, str(code))

    @staticmethod
    def _age(raw_birthdate) -> str:
        from services.birthdates import age_at_season_start
        age = age_at_season_start(raw_birthdate)
        return age if age is not None else ""

    def apply(self, source_path) -> tuple[ChangeSet, dict]:
        scan = self.scan(source_path)
        real = scan["real"]
        if not real:
            return ChangeSet(), {
                "added": 0, "names_added": 0, "links_added": 0,
                "id_swapped_count": len(scan["id_swapped"]),
                "placeholder_count": len(scan["placeholder"]),
            }

        source = SavFile()
        source.load(Path(source_path), _meta())
        source_players = {
            record.get(self.PLAYER_KEY): record
            for record in source.db.get_table(self.PLAYER_TABLE).records
            if record.get(self.PLAYER_KEY)
        }
        source_links: dict[int, list[dict]] = {}
        for record in source.db.get_table(self.LINK_TABLE).records:
            pid = record.get(self.PLAYER_KEY)
            if pid:
                source_links.setdefault(pid, []).append(record)
        source_names = {}
        if self.names is not None and source.db.get_table(self.NAME_TABLE):
            source_names = {
                record.get(self.NAME_KEY): record
                for record in source.db.get_table(self.NAME_TABLE).records
                if record.get(self.NAME_KEY) is not None
            }
        source_edited = {}
        if self.edited is not None and source.db.get_table(self.EDITED_TABLE):
            source_edited = {
                record.get(self.PLAYER_KEY): record
                for record in source.db.get_table(self.EDITED_TABLE).records
                if record.get(self.PLAYER_KEY)
            }

        player_capacity = self.players.n_records - len(self.players.records)
        if len(real) > player_capacity:
            raise ValueError(f"CZUM 没有足够空位，至少还需要 {len(real)} 个空位")
        link_capacity = self.links.n_records - len(self.links.records)
        if len(real) > link_capacity:
            raise ValueError(f"RrqT 没有足够空位，至少还需要 {len(real)} 个空位")

        changes = ChangeSet()
        player_additions = []
        link_additions = []
        name_additions = []
        edited_additions = []

        existing_name_ids = set()
        if self.names is not None:
            existing_name_ids = {
                record.get(self.NAME_KEY) for record in self.names.records
                if record.get(self.NAME_KEY) is not None
            }
        next_artificial_key = max(
            (record.get(self.LINK_KEY, 0) or 0 for record in self.links.records),
            default=0,
        )
        player_index = len(self.players.records)
        link_index = len(self.links.records)

        for item in real:
            pid = item["playerid"]
            source_record = source_players.get(pid)
            if source_record is None:
                continue
            record = {}
            for field in self.players.fields:
                key = field.field_name or field.short_name_str
                record[key] = source_record.get(key)
            record[self.PLAYER_KEY] = pid
            player_additions.append(record)
            changes.add(RecordChange(
                self.PLAYER_TABLE, self.PLAYER_KEY, pid, "add", dict(record), player_index,
            ))
            player_index += 1

            # Name rows the target may not have yet.
            if self.names is not None:
                for field in self.NAME_ID_FIELDS:
                    name_id = record.get(field)
                    if not isinstance(name_id, int) or name_id <= 0:
                        continue
                    if name_id in existing_name_ids:
                        continue
                    source_name = source_names.get(name_id)
                    if not source_name:
                        continue
                    row = {f.field_name or f.short_name_str: source_name.get(
                        f.field_name or f.short_name_str) for f in self.names.fields}
                    row[self.NAME_KEY] = name_id
                    name_additions.append(row)
                    existing_name_ids.add(name_id)

            if self.edited is not None and pid in source_edited:
                row = {f.field_name or f.short_name_str: source_edited[pid].get(
                    f.field_name or f.short_name_str) for f in self.edited.fields}
                edited_additions.append(row)

            # Free-agent link.
            next_artificial_key += 1
            base_link = (source_links.get(pid) or [{}])[0]
            link = {f.field_name or f.short_name_str: base_link.get(
                f.field_name or f.short_name_str, 0) for f in self.links.fields}
            link[self.LINK_KEY] = next_artificial_key
            link[self.PLAYER_KEY] = pid
            link["teamid"] = self.FREE_AGENT_TEAM_ID
            link_additions.append(link)
            changes.add(RecordChange(
                self.LINK_TABLE, self.LINK_KEY, next_artificial_key, "add", dict(link), link_index,
            ))
            link_index += 1

        if self.names is not None and name_additions:
            capacity = self.names.n_records - len(self.names.records)
            if len(name_additions) > capacity:
                raise ValueError(f"姓名表 bneD 没有足够空位，需要 {len(name_additions)} 个")
            base = len(self.names.records)
            for offset, row in enumerate(name_additions):
                changes.add(RecordChange(
                    self.NAME_TABLE, self.NAME_KEY, row[self.NAME_KEY], "add", dict(row), base + offset,
                ))
            self.names.records.extend(name_additions)
            self.names.n_valid_records = len(self.names.records)
            self.names.n_bit_records = self.names.n_records * self.names.record_size
        if self.edited is not None and edited_additions:
            self.edited.records.extend(edited_additions)
            self.edited.n_valid_records = len(self.edited.records)
            self.edited.n_bit_records = self.edited.n_records * self.edited.record_size

        self.players.records.extend(player_additions)
        self.links.records.extend(link_additions)
        for table in (self.players, self.links):
            table.n_valid_records = len(table.records)
            if table.n_valid_records > table.n_records:
                table.n_records = table.n_valid_records
            table.n_bit_records = table.n_records * table.record_size

        return changes, {
            "added": len(player_additions),
            "names_added": len(name_additions),
            "links_added": len(link_additions),
            "id_swapped_count": len(scan["id_swapped"]),
            "placeholder_count": len(scan["placeholder"]),
            "players": real,
        }
