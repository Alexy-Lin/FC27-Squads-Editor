"""Birthdate knowledge for the FC27 editor.

FC stores ``birthdate`` as *days since 1582-10-14* (Gregorian epoch).

Facts encoded here (verified on the real saves used by this project):

* The game silently hides players whose birthdate is below ``125812``
  (1927-04-01, Ferenc Puskás, the oldest player in the shipped squad data).
* FC27 covers the 2026/27 season.  A player born on ``2026-age``-07-01 is
  exactly ``age`` years old on the season start (2026-07-01).
* The 3DM legend save uses the single value ``154774`` (2006-07-17) for every
  player; that is *not* a real birthday, which is why the editor's age feature
  keeps each player's real month/day instead.
* EA's ICON/Hero rows in older snapshots occasionally carry placeholder
  values, so ``REAL_BIRTHDAYS`` restores the true month/day for the legends the
  editor can import.
"""
from __future__ import annotations

import datetime
import re
from typing import Optional

EPOCH = datetime.date(1582, 10, 14)

#: Field that stores the day counter inside ``CZUM``.
FIELD_NAME = "birthdate"

#: Fields the editor shows as calendar dates instead of raw day counters.
DATE_FIELDS = frozenset({FIELD_NAME})

#: Season year used for age calculations (FC27 = 2026/27).
SEASON_YEAR = 2026

#: First day of the FC27 season.
SEASON_START = datetime.date(SEASON_YEAR, 7, 1)

#: Birthdates below this are rejected by the game (player becomes invisible).
BIRTHDATE_MIN = 125812

#: The 3DM save's "everyone is 20" placeholder value (2006-07-17).
BIRTHDATE_3DM_AGE20 = 154774

_ISO_DATE = re.compile(r"^(\d{1,4})-(\d{1,2})-(\d{1,2})$")


def to_date(value: int) -> datetime.date:
    return EPOCH + datetime.timedelta(days=int(value))


def describe(value: int) -> str:
    try:
        return to_date(value).isoformat()
    except (TypeError, ValueError, OverflowError):
        return "?"


def from_text(text: str) -> int:
    """Parse ``YYYY-MM-DD`` (or a raw day counter) into a stored birthdate."""
    value = str(text if text is not None else "").strip()
    if not value:
        raise ValueError("出生日期不能为空")
    if value.lstrip("+-").isdigit():
        return int(value)
    match = _ISO_DATE.match(value)
    if not match:
        raise ValueError(f"出生日期格式必须是 YYYY-MM-DD，例如 1954-07-15：{value}")
    year, month, day = (int(part) for part in match.groups())
    try:
        calendar_date = datetime.date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"出生日期不是有效日期：{value}") from exc
    return (calendar_date - EPOCH).days


def is_valid(value: int) -> bool:
    try:
        return int(value) >= BIRTHDATE_MIN
    except (TypeError, ValueError):
        return False


def birthdate_for_age(age: int) -> int:
    """July 1 of ``SEASON_YEAR - age`` — the uniform birthday for a target age."""
    age = int(age)
    if age < 1 or age > 60:
        raise ValueError(f"年龄超出支持范围（1-60）：{age}")
    return (datetime.date(SEASON_YEAR - age, 7, 1) - EPOCH).days


def age_at_season_start(raw_birthdate: int) -> Optional[int]:
    if not isinstance(raw_birthdate, int) or raw_birthdate <= 0:
        return None
    try:
        born = to_date(raw_birthdate)
    except (OverflowError, ValueError):
        return None
    return SEASON_START.year - born.year - (
        (SEASON_START.month, SEASON_START.day) < (born.month, born.day)
    )


def shift_birthdate_to_age(raw_birthdate: int, age: int) -> int:
    """Keep the real month/day and move the year so the player is ``age``.

    This is the "real birthday" mode used by the age feature: a player born on
    1998-03-15 becomes 2008-03-15 when the target age is 18, instead of all
    players collapsing onto July 1.  Records without a usable real birthday
    (placeholder values, 0, Feb 29 issues) fall back to the uniform July 1.
    """
    age = int(age)
    target_year = SEASON_YEAR - age
    try:
        born = to_date(raw_birthdate)
    except (TypeError, ValueError, OverflowError):
        return birthdate_for_age(age)
    try:
        shifted = datetime.date(target_year, born.month, born.day)
    except ValueError:
        shifted = datetime.date(target_year, 7, 1)
    value = (shifted - EPOCH).days
    if value < BIRTHDATE_MIN:
        return birthdate_for_age(age)
    return value


#: Real birthdays (public/EA ids) for legends whose save rows carry placeholders.
REAL_BIRTHDAYS = {
    5679: 143832,    # Nwankwo Kanu        1976-08-01
    8348: 143548,    # Míchel Salgado      1975-10-22
    10959: 145021,   # Pablo Aimar         1979-11-03
    20775: 146444,   # Quaresma            1983-09-26
    23174: 144524,   # Juan Román Riquelme 1978-06-24
    39386: 145954,   # D. Beasley          1982-05-24
    50752: 145365,   # Ledley King         1980-10-12
    51412: 145054,   # Tim Cahill          1979-12-06
    155897: 146243,  # Clint Dempsey       1983-03-09
    156353: 141053,  # Luis Hernández      1968-12-22
    168880: 144406,  # Mohammed Noor       1978-02-26
    168886: 142503,  # Sami Al Jaber       1972-12-11
    170733: 147783,  # Gervinho            1987-05-27
    188428: 148001,  # S. Doumbia          1987-12-31
    191694: 140254,  # Jorge Campos        1966-10-15
    204550: 148871,  # V. Ibarbo           1990-05-19
    214267: 138109,  # Gary Lineker        1960-11-30
    242625: 144006,  # Hidetoshi Nakata    1977-01-22
    243030: 144358,  # Gennaro Gattuso     1978-01-09
    266694: 140562,  # Saeed Al Owairan    1967-08-19
    266695: 141395,  # Tomas Brolin        1969-11-29
    82092: 135779,   # Mario Kempes        1954-07-15
    191190: 132662,  # Roberto Rivellino   1946-01-01
}
