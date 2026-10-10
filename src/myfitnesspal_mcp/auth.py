import getpass
import json
import os
import sys

from . import config

SESSION_COOKIE = "__Secure-next-auth.session-token"

INSTRUCTIONS = """\
Connect your MyFitnessPal account
---------------------------------
1. Log in at https://www.myfitnesspal.com in your browser.
2. Open DevTools (F12) -> Application (Chrome) or Storage (Firefox) -> Cookies.
3. Copy the value of the '__Secure-next-auth.session-token' cookie.
   (Pasting the entire Cookie header from any request also works.)
"""


def parse_cookie_input(text: str) -> dict[str, str]:
    text = text.strip()
    if text.lower().startswith("cookie:"):
        text = text[len("cookie:") :].strip()
    if "=" not in text:
        return {SESSION_COOKIE: text}
    cookies = {}
    for part in text.split(";"):
        if "=" in part:
            name, value = part.strip().split("=", 1)
            cookies[name.strip()] = value.strip()
    return cookies


def _read_saved() -> dict:
    path = config.cookies_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def load_cookies() -> dict[str, str] | None:
    env = config.cookie_env()
    if env:
        return parse_cookie_input(env)
    saved = _read_saved().get("cookies")
    if saved:
        return saved
    return None


def saved_username() -> str | None:
    if config.username_env():
        return config.username_env()
    return _read_saved().get("username")


def save_cookies(cookies: dict[str, str], username: str | None = None) -> None:
    saved = _read_saved()
    saved["cookies"] = cookies
    if username:
        saved["username"] = username
    path = config.cookies_path()
    # Create the file owner-only from the start (no window where it is world
    # readable). On Windows the mode is ignored and the profile ACL applies.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(json.dumps(saved, indent=2))
    path.chmod(0o600)


def read_cookie_paste() -> str:
    if sys.stdin.isatty():
        return getpass.getpass("Paste cookie (input hidden): ")
    print("(no terminal detected - reading the cookie from stdin)", file=sys.stderr)
    return sys.stdin.readline()


def _validate(cookies: dict[str, str]):
    """Builds a client from the cookies; when only the profile lookup fails (a
    known MFP issue for accounts that log in by email), asks for the username
    and retries instead of failing the whole flow."""
    from myfitnesspal.exceptions import MyfitnesspalLoginError

    from . import mfp_client

    try:
        return mfp_client.build_client(cookies)
    except MyfitnesspalLoginError as exc:
        if "profile" not in str(exc):
            raise
        if not sys.stdin.isatty():
            raise
        print(
            "\nYour cookie works, but MyFitnessPal couldn't return your profile "
            "(a known issue for some accounts)."
        )
        username = input("Your MyFitnessPal username (not email): ").strip()
        if not username:
            raise
        save_cookies(cookies, username=username)
        return mfp_client.build_client(cookies)


def session_source() -> str | None:
    if config.cookie_env():
        return "the MFP_COOKIE environment variable"
    if _read_saved().get("cookies"):
        return str(config.cookies_path())
    return None


def run_check() -> int:
    from . import mfp_client

    source = session_source()
    if source is None:
        print("Session:      none saved")
        print("Fix: run 'myfitnesspal-mcp auth' to connect your account.")
        return 1

    print(f"Session:      from {source}")
    try:
        client = mfp_client.build_client(load_cookies())
    except Exception as exc:
        print(f"Status:       rejected ({exc})")
        print("Fix: run 'myfitnesspal-mcp auth' with a fresh cookie.")
        return 1

    print(f"Status:       valid, connected as {client.effective_username}")
    return 0


def run_auth_flow() -> int:
    from . import mfp_client

    print(INSTRUCTIONS, flush=True)
    try:
        pasted = read_cookie_paste()
    except EOFError:
        pasted = ""
    if not pasted.strip():
        print(
            "No cookie received. Run this in an interactive terminal, or pipe "
            "the token in: myfitnesspal-mcp auth < token.txt",
            file=sys.stderr,
        )
        return 1

    cookies = parse_cookie_input(pasted)
    print("Validating with MyFitnessPal...")
    try:
        client = _validate(cookies)
    except Exception as exc:
        print(f"Those cookies didn't authenticate: {exc}", file=sys.stderr)
        print(
            "If this mentions Cloudflare or a 403, try MFP_IMPERSONATE=chrome124 "
            "or run from a residential IP.",
            file=sys.stderr,
        )
        return 1

    save_cookies(cookies, username=client.effective_username)
    mfp_client.reset()
    print(
        f"Connected as {client.effective_username}. Cookies saved to {config.cookies_path()}"
    )
    print("The session lasts about 30 days; re-run 'myfitnesspal-mcp auth' when it expires.")
    return 0
