"""Shared PHP session cookie store.

Imported by both web_app.py and tools/swedbank_tool.py so the agent's tool
calls carry the same authenticated PHPSESSID that the browser auth flow set.
"""

_cookie: dict = {}


def get() -> dict:
    """Return a copy of the current session cookie dict."""
    return _cookie.copy()


def update(cookies) -> None:
    """Persist PHPSESSID from a requests CookieJar or plain dict."""
    val = cookies.get("PHPSESSID") if hasattr(cookies, "get") else None
    if val:
        _cookie["PHPSESSID"] = val


def clear() -> None:
    _cookie.clear()
