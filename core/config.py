"""Application settings and FC27 save discovery."""

import json
import os
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / ".fc27-editor.json"
#: Previous config filename, still read so an existing install keeps its last save.
LEGACY_CONFIG_FILE = PROJECT_ROOT / ".fc26-editor.json"

#: Game folders searched for Squads saves.  FC27 is the target; the FC26 folder
#: is kept as a compatibility fallback for installs that still use the old name.
GAME_DIRS = ("EA SPORTS FC 27", "EA SPORTS FC 26")


def save_dirs() -> list[Path]:
    """Return existing FC27 settings directories for the current user."""
    home = Path.home()
    candidates = []
    for game in GAME_DIRS:
        candidates.extend([
            home / "AppData" / "Local" / game / "settings",
            home / "Documents" / game / "settings",
            home / "文档" / game / "settings",
        ])
    for env_name in ("LOCALAPPDATA", "APPDATA"):
        value = os.environ.get(env_name)
        if value:
            for game in GAME_DIRS:
                candidates.append(Path(value) / game / "settings")
    result = []
    seen = set()
    for path in candidates:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key not in seen and path.is_dir():
            seen.add(key)
            result.append(path)
    return result


def find_save_candidates(*extra_dirs) -> list[Path]:
    result = []
    seen = set()
    for directory in (*extra_dirs, *save_dirs()):
        path = Path(directory)
        try:
            entries = path.iterdir()
        except OSError:
            continue
        for entry in entries:
            if not entry.is_file() or not entry.name.startswith("Squads"):
                continue
            if entry.suffix.lower() not in ("", ".sav") or entry.name.endswith(".bak"):
                continue
            try:
                key = str(entry.resolve())
            except OSError:
                key = str(entry)
            if key not in seen:
                seen.add(key)
                result.append(entry)
    return result


def find_latest_save(*extra_dirs) -> Optional[Path]:
    candidates = find_save_candidates(*extra_dirs)
    return max(candidates, key=lambda item: (item.stat().st_mtime_ns, item.name)) if candidates else None


def choose_startup_save(last_save_path=None, fallback_dir=None) -> tuple[Optional[Path], str]:
    latest = find_latest_save()
    if latest:
        return latest, "game"
    if last_save_path:
        last = Path(last_save_path)
        if last.is_file():
            return last, "last"
    if fallback_dir:
        fallback = find_latest_save(fallback_dir)
        if fallback:
            return fallback, "fallback"
    return None, "none"


def load() -> dict:
    for path in (CONFIG_FILE, LEGACY_CONFIG_FILE):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        return data if isinstance(data, dict) else {}
    return {}


def save(values: dict) -> None:
    current = load()
    current.update(values)
    temporary = CONFIG_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(CONFIG_FILE)
