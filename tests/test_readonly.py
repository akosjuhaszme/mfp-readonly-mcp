"""Guards for the read-only guarantee of this fork. If one of these fails, a
change has re-introduced a way to write to the MyFitnessPal account."""

import asyncio
import re
import sys
from pathlib import Path

import pytest

from myfitnesspal_mcp import diary, mfp_client, server

SRC = Path(__file__).parent.parent / "src" / "myfitnesspal_mcp"

EXPECTED_TOOLS = {
    "fitness_get_day",
    "fitness_search_food",
    "fitness_get_exercise",
    "fitness_get_exercise_entries",
    "fitness_get_note",
    "fitness_get_trends",
    "fitness_bulk_export",
}


def test_only_the_expected_read_tools_are_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_no_http_write_verbs_anywhere_in_the_source():
    pattern = re.compile(r"\.(post|put|delete|patch)\(|[\"'](POST|PUT|DELETE|PATCH)[\"']")
    offenders = []
    for path in SRC.glob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert offenders == []


def test_no_subprocess_eval_or_pickle_in_the_source():
    pattern = re.compile(r"\b(subprocess|os\.system|eval\(|exec\(|pickle|playwright)\b")
    offenders = [
        path.name
        for path in SRC.glob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_browser_cookie_access_is_blocked():
    stub = sys.modules["browser_cookie3"]
    with pytest.raises(RuntimeError, match="disabled"):
        stub.load(domain_name="myfitnesspal.com")


def test_diary_page_signed_out_is_an_auth_error(client, make_response):
    client.session.route(
        "GET",
        "food/diary?date=",
        make_response(
            text="<html><head><meta name='csrf-token' content='T'></head>"
            "<body><form id='login'></form></body></html>"
        ),
    )
    import datetime

    with pytest.raises(diary.DiarySignedOut) as exc_info:
        diary.diary_page(client, datetime.date(2026, 7, 8))
    assert mfp_client.is_auth_error(exc_info.value)
