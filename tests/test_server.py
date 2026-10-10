import asyncio

import pytest
from myfitnesspal.exceptions import MyfitnesspalLoginError

from myfitnesspal_mcp import mfp_client, server
from myfitnesspal_mcp.store import Store


class FakeContext:
    def __init__(self):
        self.messages = []

    async def info(self, message):
        self.messages.append(message)


def test_is_auth_error_patterns():
    assert mfp_client.is_auth_error(MyfitnesspalLoginError("bad"))
    assert mfp_client.is_auth_error(mfp_client.NotConnectedError("x"))
    assert mfp_client.is_auth_error(RuntimeError("HTTP 403 returned"))
    assert mfp_client.is_auth_error(RuntimeError("couldn't read the csrf token"))
    assert not mfp_client.is_auth_error(RuntimeError("no food found for 'kale'"))
    assert not mfp_client.is_auth_error(ValueError("bad date"))


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    test_store = Store(tmp_path / "server.db")
    monkeypatch.setattr(server, "_store", test_store)
    return test_store


def test_day_record_includes_note(local_store):
    local_store.set_note("2026-07-08", "long run, felt strong")
    assert local_store.day_record("2026-07-08")["note"] == "long run, felt strong"


def test_bulk_export_includes_note(local_store):
    local_store.set_note("2026-07-05", "rest day")
    result = asyncio.run(
        server.fitness_bulk_export(start="2026-07-01", end="2026-07-08")
    )
    assert result["count"] == 1
    assert result["days"][0]["note"] == "rest day"


def test_trends_rejects_unknown_metric(local_store):
    with pytest.raises(ValueError, match="unknown metric"):
        asyncio.run(server.fitness_get_trends(metric="steps"))


def test_bulk_export_validates_range(local_store):
    with pytest.raises(ValueError, match="start must be on or before end"):
        asyncio.run(server.fitness_bulk_export(start="2026-07-08", end="2026-07-01"))


@pytest.fixture
def connected(local_store, client, monkeypatch):
    monkeypatch.setattr(server.mfp_client, "get_client", lambda: client)
    monkeypatch.setattr(server.sync, "refresh_day", lambda store, client, day: None)
    return client


def posts_to(client, fragment):
    return [
        url
        for method, url, _ in client.session.calls
        if method == "POST" and fragment in url
    ]


@pytest.fixture
def refresh_expires_once(connected, monkeypatch):
    monkeypatch.setattr(server.refresh, "refresh_session", lambda: None)
    refresh_calls = []

    def flaky_refresh(store, client, day):
        refresh_calls.append(day)
        if len(refresh_calls) == 1:
            raise MyfitnesspalLoginError("session expired")

    monkeypatch.setattr(server.sync, "refresh_day", flaky_refresh)
    return refresh_calls


def test_bulk_export_reads_cache_without_client(local_store):
    local_store.upsert_nutrition("2026-07-05", calories=1500.0)
    result = asyncio.run(
        server.fitness_bulk_export(start="2026-07-01", end="2026-07-08")
    )
    assert result["count"] == 1
    assert result["days"][0]["nutrition"]["calories"] == 1500.0


