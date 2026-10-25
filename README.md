# mfp-readonly-mcp

A **read-only** fork of [Mason-Levyy/myfitnesspal-mcp](https://github.com/Mason-Levyy/myfitnesspal-mcp)
(`mfp-mcp` 0.4.1, upstream commit `1bb92c63cb291d57fd3ce7733b207a841d4ec13c`, MIT, all credit
for the original work to its author). It lets an MCP client (for example a Claude
coaching or analysis session) *read* your MyFitnessPal food diary - meals, calories,
macros, exercise, notes, trends - and nothing else: nothing here can log, change or
delete diary data. The upstream server exposes 7 write/delete tools with no read-only
switch, which is why this variant exists.

> **Unofficial, use at your own risk.** This project is not affiliated with or endorsed
> by MyFitnessPal (Under Armour) or by the upstream author. MyFitnessPal's official
> partner API is not accepting new access requests, so this reads the website with
> your own logged-in session cookie. That can stop working whenever the site changes,
> and automated access may be against MyFitnessPal's terms of service - check them
> before using this. The cookie gives full access to your account: keep it secret.

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

**Easiest (Windows):** double-click `renew-mfp-session.bat` (create a Desktop shortcut
named *MyFitnessPal megujitas* to it; the tool's expiry notices refer to that name).
It opens MyFitnessPal, walks you through copying the cookie (the on-screen text is in
Hungarian), asks for it at a hidden prompt and checks the result. Nothing needs
restarting afterwards. From the 25th day on, every tool result carries a
`session_notice` asking the user to renew.

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

## Known behaviours (verified on a real account)

- **Profile lookup can return HTTP 500** for accounts that log in with an e-mail address.
  `auth` then asks for your MyFitnessPal *username* (not the e-mail) and stores it.
- **Anonymous access does not work.** A Public or "Locked with a key" diary answers
  scripts with a bot-protection challenge (HTTP 403); only the logged-in session cookie
  gets through. Keep the diary Private.
- **The day's goals are the adjusted budget:** with "Exercise Calories" on, calories
  burned in synced exercise are added to the base goal, and the macro goals scale with it.
- **The first call fills a local cache** with the last `MFP_SYNC_DAYS` days (default 30).
  Use a small value (for example 2) for the first run. The cache (`data.db` in the data
  directory) can be deleted at any time; it is refetched.
- **The `.bat` file needs CRLF line endings** (kept by `.gitattributes`), otherwise `cmd`
  garbles the Hungarian text.

## Using it together with a Garmin coach

This server pairs with [garmin-firefighter-coach](https://github.com/akosjuhaszme/garmin-firefighter-coach)
(the Garmin Connect MCP server of the same author's coaching setup). Register both in
your MCP client's config and the assistant sees training and food side by side:

```json
{
  "mcpServers": {
    "garmin-workouts": { "command": "C:\path\to\garmin-workouts-mcp\.venv\Scripts\garmin-workouts-mcp.exe", "args": [] },
    "mfp-readonly":    { "command": "C:\path\to\mfp-readonly-mcp\.venv\Scripts\myfitnesspal-mcp.exe", "args": [] }
  }
}
```

With MyFitnessPal and Garmin Connect linked to each other, data flows both ways
(checked on a real account):

- **MyFitnessPal -> Garmin:** calories eaten show up in Garmin's daily summary
  (`consumed_kcal`), and a weight logged in MyFitnessPal appears in Garmin tagged
  with the source `MFP`.
  **Water is not synced:** water logged in MyFitnessPal (`water_ml` here) does not reach
  Garmin's hydration tracker (checked live). Garmin's calorie goal (`net_goal_kcal`)
  follows the MyFitnessPal goal.
- **Garmin -> MyFitnessPal:** synced workouts appear in MyFitnessPal's exercise diary
  (plus a "Garmin Connect calorie adjustment" entry) and, with "Exercise Calories" on,
  raise that day's calorie goal.
- The assistant reads meals and macros through this server and everything else
  (training, sleep, HRV, weight, hydration) through the Garmin server.
- Ready-made prompts that use both servers (first-run setup, weekly review, nutrition check)
  are in the Garmin repository: [docs/PROMPTS.md](https://github.com/akosjuhaszme/garmin-firefighter-coach/blob/main/docs/PROMPTS.md).

## Lessons learned (October 2026)

- **(both) The Garmin link copies weigh-ins to MyFitnessPal within seconds.** A test weigh-in written to Garmin for a weight that differed from the day's weight reached MyFitnessPal at once, and an entry with the source MFP came back into Garmin (dated at the test moment, the newest of the day) even though the Garmin test entry had been deleted. This server cannot write, so the copy in MyFitnessPal has to be removed by hand in the app. While the link is on, never test a weigh-in with a value that differs from the real one.
- **(MFP) Windows Smart App Control can block the unsigned `myfitnesspal-mcp.exe` launcher.** Start the server as `python.exe -m myfitnesspal_mcp.cli` (the signed interpreter is allowed); `renew-mfp-session.bat` calls the module the same way.
- **(both) Deleting the copy in MyFitnessPal changes nothing in Garmin:** after the echo entry in Garmin and the copy in MyFitnessPal had both been removed, nothing came back and the real Garmin entry stayed.
- **(MFP) An expired session shows up as "MyFitnessPal session expired or not connected"** and is renewed with the shortcut or `auth`; nothing needs a restart afterwards.

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
