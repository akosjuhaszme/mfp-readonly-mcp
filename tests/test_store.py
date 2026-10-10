import datetime
import sqlite3
import threading
from pathlib import Path

import pytest


def test_reads_never_see_a_half_replaced_diary():
    from myfitnesspal_mcp.store import Store

    store = Store(Path(":memory:"))
    day = "2026-07-01"
    entries = [{"meal": "Lunch", "name": f"Item {index}"} for index in range(3)]
    store.replace_diary(day, entries)
    writing = threading.Event()
    writing.set()

    def rewrite_repeatedly():
        while writing.is_set():
            store.replace_diary(day, entries)

    writer = threading.Thread(target=rewrite_repeatedly)
    writer.start()
    try:
        observed_sizes = {len(store.diary(day)) for _ in range(500)}
    finally:
        writing.clear()
        writer.join(5)

    assert observed_sizes == {3}


def test_upsert_nutrition_partial_updates(store):
    store.upsert_nutrition("2026-07-01", calories=1800.0, protein=120.0)
    store.upsert_nutrition("2026-07-01", weight=80.5)
    row = store.nutrition("2026-07-01")
    assert row["calories"] == 1800.0
    assert row["protein"] == 120.0
    assert row["weight"] == 80.5


def test_upsert_nutrition_rejects_unknown_fields(store):
    with pytest.raises(ValueError, match="unknown nutrition fields"):
        store.upsert_nutrition("2026-07-01", steps=10000)


def test_replace_diary(store):
    store.replace_diary(
        "2026-07-01", [{"meal": "Breakfast", "name": "Egg", "calories": 70}]
    )
    store.replace_diary(
        "2026-07-01",
        [
            {"meal": "Breakfast", "name": "Oats", "calories": 300},
            {"meal": "Lunch", "name": "Salad", "calories": 250},
        ],
    )
    entries = store.diary("2026-07-01")
    assert [e["name"] for e in entries] == ["Oats", "Salad"]


def test_note_upsert(store):
    store.set_note("2026-07-01", "first draft")
    store.set_note("2026-07-01", "final note")
    assert store.note("2026-07-01") == "final note"
    assert store.note("2026-07-02") is None


def test_trend_filters_nulls_and_orders(store):
    store.upsert_nutrition("2026-07-02", weight=81.0)
    store.upsert_nutrition("2026-07-01", weight=80.0)
    store.upsert_nutrition("2026-07-03", calories=2000.0)
    points = store.trend("weight", "2026-07-01", "2026-07-31")
    assert points == [
        {"day": "2026-07-01", "value": 80.0},
        {"day": "2026-07-02", "value": 81.0},
    ]


def test_trend_unknown_metric(store):
    with pytest.raises(ValueError, match="unknown metric"):
        store.trend("steps", "2026-07-01", "2026-07-31")


def test_days_with_synced_diary(store):
    store.mark_diary_synced("2026-07-01")
    store.mark_diary_synced("2026-07-05")
    assert store.days_with_synced_diary("2026-07-01", "2026-07-04") == {"2026-07-01"}


def test_partial_row_is_not_a_synced_diary(store):
    """A weigh-in creates a row before the diary is ever fetched; that row must
    not hide the day from gap-fill."""
    store.upsert_nutrition("2026-07-01", weight=80.0)
    assert store.days_with_synced_diary("2026-07-01", "2026-07-01") == set()

    store.mark_diary_synced("2026-07-01")
    store.upsert_nutrition("2026-07-01", weight=79.5)
    assert store.days_with_synced_diary("2026-07-01", "2026-07-01") == {"2026-07-01"}


def test_nutrition_hides_sync_bookkeeping(store):
    store.upsert_nutrition("2026-07-01", calories=1800.0)
    store.mark_diary_synced("2026-07-01")
    assert "diary_synced" not in store.nutrition("2026-07-01")


def test_export_range_ignores_empty_notes(store):
    store.set_note("2026-07-05", None)
    store.set_note("2026-07-06", "")
    assert store.export_range("2026-07-01", "2026-07-31") == []


def test_mark_synced_roundtrip(store):
    assert store.last_synced_on() is None
    store.mark_synced()
    assert store.last_synced_on() is not None


