import functools
import sqlite3
import threading
from datetime import date
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS day_nutrition (
    day TEXT PRIMARY KEY,
    calories REAL,
    protein REAL,
    carbs REAL,
    fat REAL,
    water_ml REAL,
    weight REAL,
    goal_calories REAL,
    diary_synced INTEGER NOT NULL DEFAULT 0,
    sodium REAL,
    sugar REAL,
    goal_protein REAL,
    goal_carbs REAL,
    goal_fat REAL,
    goal_sodium REAL,
    goal_sugar REAL
);
CREATE TABLE IF NOT EXISTS diary_entry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    meal TEXT,
    name TEXT,
    calories REAL,
    protein REAL,
    carbs REAL,
    fat REAL,
    sodium REAL,
    sugar REAL
);
CREATE INDEX IF NOT EXISTS diary_entry_day ON diary_entry(day);
CREATE TABLE IF NOT EXISTS day_note (
    day TEXT PRIMARY KEY,
    body TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

NUTRITION_FIELDS = (
    "calories",
    "protein",
    "carbs",
    "fat",
    "water_ml",
    "weight",
    "goal_calories",
    "sodium",
    "sugar",
    "goal_protein",
    "goal_carbs",
    "goal_fat",
    "goal_sodium",
    "goal_sugar",
)

# Columns added after the first release; older cache databases get them on open.
ADDED_COLUMNS = {
    "day_nutrition": (
        "sodium",
        "sugar",
        "goal_protein",
        "goal_carbs",
        "goal_fat",
        "goal_sodium",
        "goal_sugar",
    ),
    "diary_entry": ("sodium", "sugar"),
}

TREND_COLUMNS = {
    "weight": "weight",
    "calories_in": "calories",
    "protein": "protein",
    "carbs": "carbs",
    "fat": "fat",
    "sodium": "sodium",
    "sugar": "sugar",
}


POPULATED_DAY_QUERIES = (
    "SELECT day FROM day_nutrition WHERE day >= ? AND day <= ?",
    "SELECT DISTINCT day FROM diary_entry WHERE day >= ? AND day <= ?",
    "SELECT day FROM day_note WHERE day >= ? AND day <= ? "
    "AND body IS NOT NULL AND body != ''",
)


def trend_column(metric: str) -> str:
    column = TREND_COLUMNS.get(metric)
    if column is None:
        raise ValueError(f"unknown metric (use {' | '.join(TREND_COLUMNS)})")
    return column


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


def _serialized(method):
    @functools.wraps(method)
    def locked(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return locked


class Store:
    """Local SQLite cache of the diary data read from MyFitnessPal. Nothing in
    here is ever sent back to MyFitnessPal."""

    def __init__(self, path: Path | None = None):
        if path is None:
            path = config.database_path()
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """Add columns introduced after the first release to an existing cache
        database, and mark its days as not yet synced so they are fetched again
        with the new fields. The cache only mirrors MyFitnessPal, so a refetch
        loses nothing."""
        added = False
        for table, columns in ADDED_COLUMNS.items():
            present = {
                row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")
            }
            for column in columns:
                if column not in present:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} REAL")
                    added = True
        if added:
            self.conn.execute("UPDATE day_nutrition SET diary_synced = 0")
            self.conn.commit()

    @_serialized
    def upsert_nutrition(self, day: str, **fields) -> None:
        unknown = set(fields) - set(NUTRITION_FIELDS)
        if unknown:
            raise ValueError(f"unknown nutrition fields: {sorted(unknown)}")
        columns = ", ".join(fields)
        placeholders = ", ".join("?" for _ in fields)
        updates = ", ".join(f"{name} = excluded.{name}" for name in fields)
        self.conn.execute(
            f"INSERT INTO day_nutrition (day, {columns}) VALUES (?, {placeholders}) "
            f"ON CONFLICT(day) DO UPDATE SET {updates}",
            [day, *fields.values()],
        )
        self.conn.commit()

    @_serialized
    def mark_diary_synced(self, day: str) -> None:
        """Record that the day's MyFitnessPal diary has been fetched in full.

        A row can exist with only a weigh-in (the measurement backfill in
        sync.poll); gap-fill keys off this flag, not off row existence, so such
        days still get their calories and macros.
        """
        self.conn.execute(
            "INSERT INTO day_nutrition (day, diary_synced) VALUES (?, 1) "
            "ON CONFLICT(day) DO UPDATE SET diary_synced = 1",
            (day,),
        )
        self.conn.commit()

    @_serialized
    def nutrition(self, day: str) -> dict | None:
        row = self.conn.execute(
            "SELECT day, calories, protein, carbs, fat, sodium, sugar, water_ml, "
            "weight, goal_calories, goal_protein, goal_carbs, goal_fat, "
            "goal_sodium, goal_sugar FROM day_nutrition WHERE day = ?",
            (day,),
        ).fetchone()
        return _row_to_dict(row)

    @_serialized
    def replace_diary(self, day: str, entries: list[dict]) -> None:
        self.conn.execute("DELETE FROM diary_entry WHERE day = ?", (day,))
        self.conn.executemany(
            "INSERT INTO diary_entry "
            "(day, meal, name, calories, protein, carbs, fat, sodium, sugar) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    day,
                    e.get("meal"),
                    e.get("name"),
                    e.get("calories"),
                    e.get("protein"),
                    e.get("carbs"),
                    e.get("fat"),
                    e.get("sodium"),
                    e.get("sugar"),
                )
                for e in entries
            ],
        )
        self.conn.commit()

    @_serialized
    def diary(self, day: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT meal, name, calories, protein, carbs, fat, sodium, sugar "
            "FROM diary_entry "
            "WHERE day = ? ORDER BY id",
            (day,),
        ).fetchall()
        return [dict(r) for r in rows]

    @_serialized
    def set_note(self, day: str, body: str | None) -> None:
        """Cache of the MyFitnessPal daily diary note read from MFP."""
        self.conn.execute(
            "INSERT INTO day_note (day, body) VALUES (?, ?) "
            "ON CONFLICT(day) DO UPDATE SET body = excluded.body",
            (day, body),
        )
        self.conn.commit()

    @_serialized
    def note(self, day: str) -> str | None:
        row = self.conn.execute(
            "SELECT body FROM day_note WHERE day = ?", (day,)
        ).fetchone()
        if row is None:
            return None
        return row["body"]

    @_serialized
    def days_with_synced_diary(self, start: str, end: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT day FROM day_nutrition "
            "WHERE day >= ? AND day <= ? AND diary_synced = 1",
            (start, end),
        ).fetchall()
        return {r["day"] for r in rows}

    @_serialized
    def trend(self, metric: str, start: str, end: str) -> list[dict]:
        rows = self.conn.execute(
            f"SELECT day, {trend_column(metric)} AS value FROM day_nutrition "
            "WHERE day >= ? AND day <= ? AND value IS NOT NULL ORDER BY day",
            (start, end),
        ).fetchall()
        return [dict(r) for r in rows]

    @_serialized
    def day_record(self, day: str) -> dict:
        return {
            "day": day,
            "nutrition": self.nutrition(day),
            "diary": self.diary(day),
            "note": self.note(day),
        }

    @_serialized
    def export_range(self, start: str, end: str) -> list[dict]:
        days: set[str] = set()
        for query in POPULATED_DAY_QUERIES:
            days |= {row["day"] for row in self.conn.execute(query, (start, end))}
        return [self.day_record(day) for day in sorted(days)]

    @_serialized
    def last_synced_on(self) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = 'last_synced_on'"
        ).fetchone()
        if row is None:
            return None
        return row["value"]

    @_serialized
    def mark_synced(self, day: date | None = None) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES ('last_synced_on', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ((day or date.today()).isoformat(),),
        )
        self.conn.commit()
