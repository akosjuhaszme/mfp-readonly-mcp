import sys
import types
from importlib.metadata import version

# Defence in depth: python-myfitnesspal imports browser_cookie3, which can read
# the user's saved browser cookies. This server authenticates only with the
# cookie the user pasted via `auth`, so that path is neutralised here, before
# anything imports the library (the package is also uninstalled from the venv).
_blocked_browser_cookies = types.ModuleType("browser_cookie3")


def _refuse_browser_cookies(*args, **kwargs):
    raise RuntimeError("reading browser cookies is disabled in this build")


_blocked_browser_cookies.load = _refuse_browser_cookies
sys.modules["browser_cookie3"] = _blocked_browser_cookies

__version__ = version("mfp-readonly-mcp")
