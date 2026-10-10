# mfp-readonly-mcp

A **read-only** local fork of [Mason-Levyy/myfitnesspal-mcp](https://github.com/Mason-Levyy/myfitnesspal-mcp)
(`mfp-mcp` 0.4.1, upstream commit `1bb92c63cb291d57fd3ce7733b207a841d4ec13c`, MIT).
It lets an MCP client (the Garmin coach session) *read* the MyFitnessPal food
diary - meals, calories, macros, exercise, notes, trends - and nothing else.
This copy is for personal use and is not published.

MyFitnessPal's official partner API (OAuth, documented at myfitnesspalapi.com) is
not accepting new access requests, so this reverse-engineers the website with a
session cookie. It is unofficial and can break whenever MyFitnessPal changes the
site.

## What was changed from upstream

- **All write paths removed**: logging, modifying and deleting food, weight, water,
  exercise and notes; food drafts, remembered food choices and the local "feel"
  note. `diary.py` lost every `POST` call; `tests/conftest.py`'s fake session now
  fails any `POST/PUT/DELETE/PATCH`, and `tests/test_readonly.py` checks that only
  the 7 read tools are registered and that no HTTP write verb appears in the source.
- **No headless-browser auto-refresh** (Playwright removed), **no HTTP transport**
  (stdio only), no publish workflow.
- **`browser_cookie3` is stubbed and uninstalled.** The upstream library can read
  the browser's saved cookies; this build refuses to. Authentication is only the
  cookie you paste yourself.
- The cookie file is created owner-only from the start.

## Tools (all read-only)

`fitness_get_day`, `fitness_search_food`, `fitness_get_exercise`,
`fitness_get_exercise_entries`, `fitness_get_note`, `fitness_get_trends`
(weight | calories_in | protein | carbs | fat | sodium | sugar), `fitness_bulk_export`.

What a free MyFitnessPal account exposes in the diary (verified live): per food
entry and per day calories, protein, carbohydrates, fat, sodium (mg) and sugar (g),
plus the day's goals for the same six values. The goals are the day's *adjusted* budget: with the account's "Exercise Calories" switch on, calories burned in synced exercise are added to the base goal (verified: base 2000 + 505 burned = 2505 kcal), and the macro goals scale with it. Other nutrients (fibre, saturated fat,
cholesterol, vitamins, minerals) were not in the data; they are probably premium-only.
Water is read from MyFitnessPal's own tracker.

## Connect or renew your account (you do this, not the assistant)

**Easiest:** double-click the *MyFitnessPal megujitas* shortcut on the Desktop
(`renew-mfp-session.bat`). It opens MyFitnessPal, walks through copying the cookie,
asks for it at a hidden prompt and checks the result. Nothing needs restarting
afterwards. From the 25th day on, every tool result carries a `session_notice`
asking the user to renew.

**Manually:**

1. Log in at https://www.myfitnesspal.com in your browser.
2. DevTools (F12) -> Application -> Cookies -> copy the value of
   `__Secure-next-auth.session-token`.
3. In your own terminal, run `.venv\Scripts\myfitnesspal-mcp.exe auth` and paste it
   at the hidden prompt. The cookie grants full access to the account: never paste
   it into a chat, a file in a repo, or an issue.
4. `.venv\Scripts\myfitnesspal-mcp.exe auth --check` reports whether it works.

The session lasts about 30 days; run `auth` again when it expires.

Files stay on this machine: the cookie in the user config directory
(`%LOCALAPPDATA%\myfitnesspal-mcp`) and a SQLite cache of the diary
(`MFP_MCP_DATA_DIR`, same place by default). Network traffic goes only to
`www.myfitnesspal.com` / `api.myfitnesspal.com`.

## Development

```
python -m venv .venv
.venv\Scripts\python -m pip install "mcp>=1.10,<2" "myfitnesspal==2.1.2" "curl-cffi>=0.15,<0.16" "lxml>=5,<7" "platformdirs>=4" pytest
.venv\Scripts\python -m pip uninstall -y browser-cookie3
.venv\Scripts\python -m pip install --no-deps -e .
.venv\Scripts\python -m pytest
```

Note: do not run this server's Python with `-X utf8` / `PYTHONUTF8=1` on a Windows
path containing non-ASCII characters (e.g. `Felhasználó`): the TLS library then
cannot open its CA bundle and every request fails.

Record-keeping and trend data only - not medical or dietary advice.
