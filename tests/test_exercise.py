import datetime

import pytest
from lxml import html as lh

from myfitnesspal_mcp import diary

TODAY = datetime.date(2026, 9, 10)


@pytest.fixture
def exercise_doc(exercise_html):
    return lh.fromstring(exercise_html)


def _posts(client):
    return [call for call in client.session.calls if call[0] == "POST"]


def test_exercise_page_uses_username_url_and_reads_token(exercise_client):
    _, token = diary.exercise_page(exercise_client, TODAY)
    assert token == "EXERCISETOKEN"
    _, url, _ = exercise_client.session.calls[-1]
    assert url.endswith("exercise/diary/tester?date=2026-09-10")


def test_exercise_entries_parse_cardio_rows(exercise_doc):
    cardio = [
        e
        for e in diary.exercise_entries(exercise_doc)
        if e["section"] == "cardiovascular"
    ]
    assert cardio == [
        {
            "entry_id": "111",
            "section": "cardiovascular",
            "name": "Aerobics, general",
            "minutes": 1.0,
            "calories_burned": 13.0,
        },
        {
            "entry_id": "222",
            "section": "cardiovascular",
            "name": "Running (jogging), 8 kph",
            "minutes": 20.0,
            "calories_burned": 1201.0,
        },
        {
            "entry_id": "333",
            "section": "cardiovascular",
            "name": "Aerobics, general",
            "minutes": 4.0,
            "calories_burned": 25.0,
        },
    ]


def test_exercise_entries_parse_strength_rows_with_their_own_columns(exercise_doc):
    strength = [
        e
        for e in diary.exercise_entries(exercise_doc)
        if e["section"] == "strength training"
    ]
    assert strength == [
        {
            "entry_id": "444",
            "section": "strength training",
            "name": "Bench Press, Barbell",
            "sets": 3.0,
            "reps_set": 8.0,
            "weight_set": 135.0,
        },
        {
            "entry_id": "555",
            "section": "strength training",
            "name": "Pull Up",
            "sets": 4.0,
            "reps_set": 10.0,
            "weight_set": None,
        },
    ]


def test_exercise_entries_skip_total_rows(exercise_doc):
    names = [e["name"] for e in diary.exercise_entries(exercise_doc)]
    assert not any("Total" in name for name in names)


