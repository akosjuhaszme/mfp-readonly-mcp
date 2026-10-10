import asyncio
import datetime
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from . import auth, diary, mfp_client, sync
from .store import Store, trend_column

# The MyFitnessPal session cookie lasts about 30 days; warn from this age on so
# the user can renew it before tools start failing.
SESSION_WARN_DAYS = 25

mcp = FastMCP(
    "myfitnesspal-readonly",
    instructions=(
        "Read-only access to the user's MyFitnessPal food diary. Nothing here can "
        "log, change or delete diary data. The numbers are the user's own "
        "record-keeping for trend analysis, not medical or dietary advice."
    ),
)

_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def parse_day(value: str | None) -> datetime.date:
    if value is None:
        return datetime.date.today()
    return datetime.date.fromisoformat(value)


def parse_range(
    start: str | None, end: str | None, span_days: int = 30
) -> tuple[datetime.date, datetime.date]:
    end_day = parse_day(end)
    if start is None:
        start_day = end_day - datetime.timedelta(days=span_days)
    else:
        start_day = parse_day(start)
    if start_day > end_day:
        raise ValueError("start must be on or before end")
    return start_day, end_day


def session_notice() -> str | None:
    age = auth.session_age_days()
    if age is None or age < SESSION_WARN_DAYS:
        return None
    return (
        f"The MyFitnessPal session is {age} days old and lasts about "
        f"{auth.SESSION_LIFETIME_DAYS}. Ask the user to double-click the "
        "'MyFitnessPal megujitas' shortcut (or run 'myfitnesspal-mcp auth') soon; "
        "nothing needs restarting afterwards."
    )


def with_notice(result: Any) -> Any:
    notice = session_notice()
    if notice and isinstance(result, dict):
        return {**result, "session_notice": notice}
    return result


async def run_with_retry(ctx: Context, op: Callable[[], Any]) -> Any:
    """Runs a blocking MFP operation; on an auth-shaped failure, drops the cached
    client (so a re-pasted cookie or an updated MFP_COOKIE is picked up) and
    retries once. Adds a session_notice when the session is nearly expired."""
    return with_notice(await _run_with_retry(ctx, op))


async def _run_with_retry(ctx: Context, op: Callable[[], Any]) -> Any:
    try:
        return await asyncio.to_thread(op)
    except Exception as exc:
        if not mfp_client.is_auth_error(exc):
            raise
        await ctx.info("MyFitnessPal rejected the session - retrying once.")
        mfp_client.reset()
        try:
            return await asyncio.to_thread(op)
        except Exception as retry_exc:
            raise RuntimeError(
                f"{mfp_client.RECONNECT_HINT} (retry failed: {retry_exc})"
            ) from retry_exc


async def with_session(ctx: Context, op: Callable[[Store, Any], Any]) -> Any:
    """Runs `op` against the store and a live MFP client, re-resolving both on
    the retry."""
    return await run_with_retry(ctx, lambda: op(get_store(), mfp_client.get_client()))


@mcp.tool()
async def fitness_get_day(date: str | None = None, ctx: Context = None) -> dict:
    """Nutrition summary and diary entries (with macros) for a day, plus the
    MyFitnessPal daily note. Read-only.

    date: YYYY-MM-DD (default: today).
    """
    day = parse_day(date)

    def op(store, client):
        sync.poll(store, client)
        sync.refresh_day(store, client, day)
        return store.day_record(day.isoformat())

    return await with_session(ctx, op)


@mcp.tool()
async def fitness_search_food(
    query: str, limit: int = 5, with_macros: bool = True, ctx: Context = None
) -> dict:
    """Search MyFitnessPal's food database and return candidate matches with
    name, brand, calories, macros and serving. Read-only lookup - nothing is
    logged.
    """

    def op(store, client):
        return {
            "query": query,
            "results": diary.search_food(client, query, limit, with_macros),
        }

    return await with_session(ctx, op)


@mcp.tool()
async def fitness_get_exercise(date: str | None = None, ctx: Context = None) -> dict:
    """Read the MyFitnessPal exercise diary (cardio + strength) for a day.

    date: YYYY-MM-DD (default: today).
    """
    day = parse_day(date)

    def op(store, client):
        return diary.get_exercise(client, day)

    return await with_session(ctx, op)


@mcp.tool()
async def fitness_get_exercise_entries(
    date: str | None = None, ctx: Context = None
) -> dict:
    """List a day's cardio and strength exercise-diary entries.

    Each entry has its section, name, and that section's columns (cardio:
    minutes, calories_burned; strength: sets, reps_set, weight_set).
    date: YYYY-MM-DD (default: today).
    """
    day = parse_day(date)

    def op(store, client):
        doc, _ = diary.exercise_page(client, day)
        return {"day": day.isoformat(), "entries": diary.exercise_entries(doc)}

    return await with_session(ctx, op)


@mcp.tool()
async def fitness_get_note(date: str | None = None, ctx: Context = None) -> dict:
    """Read the MyFitnessPal daily diary note (the free-text 'Notes' box at the
    bottom of the day) straight from the account. Read-only.

    date: YYYY-MM-DD (default: today).
    """
    day = parse_day(date)

    def op(store, client):
        body = diary.get_note(client, day)
        store.set_note(day.isoformat(), body)
        return {"day": day.isoformat(), "note": body}

    return await with_session(ctx, op)


@mcp.tool()
async def fitness_get_trends(
    metric: str, start: str | None = None, end: str | None = None, ctx: Context = None
) -> dict:
    """A single metric over a date range, for charts/analysis.

    metric: weight | calories_in | protein | carbs | fat.
    start/end: YYYY-MM-DD (default: last 30 days).
    Returns {metric, points: [{day, value}, ...]} with nulls omitted.
    """
    trend_column(metric)
    start_day, end_day = parse_range(start, end)

    def op(store, client):
        sync.poll(store, client)
        return {
            "metric": metric,
            "points": store.trend(metric, start_day.isoformat(), end_day.isoformat()),
        }

    return await with_session(ctx, op)


@mcp.tool()
async def fitness_bulk_export(
    start: str | None = None,
    end: str | None = None,
    sync_first: bool = False,
    ctx: Context = None,
) -> dict:
    """Export a whole date range at once for analysis: per-day nutrition
    totals, food entries with macros, and the MyFitnessPal daily note.
    Read-only.

    start/end: YYYY-MM-DD (default: last 30 days ending today).
    sync_first: gap-fill from MyFitnessPal before exporting. Off by default so
    large historical exports stay fast on cached data.
    """
    start_day, end_day = parse_range(start, end)

    def op():
        store = get_store()
        if sync_first:
            span = (end_day - start_day).days + 1
            sync.poll(store, mfp_client.get_client(), days=span, force=True)
        days = store.export_range(start_day.isoformat(), end_day.isoformat())
        return {
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "count": len(days),
            "days": days,
        }

    return await run_with_retry(ctx, op)
