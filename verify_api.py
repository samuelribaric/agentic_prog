"""Standalone diagnostic script for the Swedbank PHP bridge integration.

Usage:
    python verify_api.py [--url http://localhost:8080] [--same-device]

Walks through the full auth + data flow step-by-step, printing raw JSON at
each stage with PASS/FAIL/WARN/SKIP verdicts and a final summary table.

By default uses the QR code flow (suitable for desktop).
Pass --same-device to use the autoStartToken flow instead.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time

import requests

# ---------------------------------------------------------------------------
# Config — import only SWEDBANK_API_URL; avoid pulling in LangChain deps
# ---------------------------------------------------------------------------
try:
    from config import SWEDBANK_API_URL as _DEFAULT_URL
except Exception:
    _DEFAULT_URL = "http://localhost:8080"

# ---------------------------------------------------------------------------
# ANSI colours
# ---------------------------------------------------------------------------
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def _green(s):  return f"{GREEN}{s}{RESET}"
def _red(s):    return f"{RED}{s}{RESET}"
def _yellow(s): return f"{YELLOW}{s}{RESET}"
def _cyan(s):   return f"{CYAN}{s}{RESET}"
def _bold(s):   return f"{BOLD}{s}{RESET}"

PASS = _green("PASS")
FAIL = _red("FAIL")
WARN = _yellow("WARN")
SKIP = _cyan("SKIP")

# ---------------------------------------------------------------------------
# Helpers duplicated from finance_tools.py (no LangChain dep here)
# ---------------------------------------------------------------------------

def _parse_amount(val) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if not val:
        return 0.0
    s = str(val).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _iter_accounts(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("accounts", "transactionAccounts", "savingAccounts",
                    "loanAccounts", "cardAccounts"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    return []


def _extract_transactions(data) -> list:
    if isinstance(data, dict):
        for key in ("transactions", "reservedTransactions"):
            if key in data and isinstance(data[key], list):
                return data[key]
    if isinstance(data, list):
        return data
    return []


# ---------------------------------------------------------------------------
# Step runner
# ---------------------------------------------------------------------------

_results: list[tuple[str, str, str]] = []  # (step_label, verdict, note)


def _pp(data, max_list: int = 5) -> str:
    """Pretty-print JSON, truncating top-level lists to max_list items."""
    if isinstance(data, dict):
        # Truncate any list values inside the dict for readability
        trimmed = {}
        for k, v in data.items():
            if isinstance(v, list) and len(v) > max_list:
                trimmed[k] = v[:max_list] + [f"… ({len(v) - max_list} more)"]
            else:
                trimmed[k] = v
        return json.dumps(trimmed, indent=2, ensure_ascii=False)
    if isinstance(data, list) and len(data) > max_list:
        return json.dumps(
            data[:max_list] + [f"… ({len(data) - max_list} more)"],
            indent=2, ensure_ascii=False,
        )
    return json.dumps(data, indent=2, ensure_ascii=False)


def _print_response(label: str, verdict: str, note: str,
                    elapsed: float, body=None) -> None:
    print(f"\n{'─' * 60}")
    print(f"{_bold(label)}  {verdict}  {_cyan(f'({elapsed:.2f}s)')}")
    if note:
        print(f"  {note}")
    if body is not None:
        print(_pp(body))
    _results.append((label, verdict, note))


def _step(label: str, fn, *args, **kwargs):
    """Execute fn(*args, **kwargs), catch errors, print result."""
    t0 = time.time()
    try:
        verdict, note, body = fn(*args, **kwargs)
    except requests.exceptions.ConnectionError:
        elapsed = time.time() - t0
        msg = "PHP bridge not running — start with: php -S localhost:8080 SwedbankJson/server.php"
        _print_response(label, FAIL, msg, elapsed)
        return None
    except Exception as exc:
        elapsed = time.time() - t0
        _print_response(label, FAIL, str(exc), elapsed)
        return None
    elapsed = time.time() - t0
    _print_response(label, verdict, note, elapsed, body)
    return body


# ---------------------------------------------------------------------------
# Individual step functions
# ---------------------------------------------------------------------------

def _check_bridge(sess: requests.Session, base: str):
    resp = sess.get(f"{base}/", timeout=10)
    try:
        data = resp.json()
    except Exception:
        return FAIL, f"Non-JSON response: {resp.text[:200]}", None
    if resp.ok:
        auth_status = data.get("data", {}).get("authed", "?")
        return PASS, f"Bridge responding; authed={auth_status}", data
    return FAIL, f"HTTP {resp.status_code}", data


def _bankid_init(sess: requests.Session, base: str, same_device: bool = False):
    resp = sess.post(f"{base}/auth/bankid/init",
                     json={"sameDevice": same_device}, timeout=15)
    try:
        data = resp.json()
    except Exception:
        return FAIL, f"Non-JSON: {resp.text[:200]}", None
    if not resp.ok:
        return FAIL, f"HTTP {resp.status_code}", data
    if not data.get("ok"):
        return FAIL, data.get("error", "Unknown error"), data
    mode = "same-device (autoStartToken)" if same_device else "QR code"
    return PASS, f"BankID init successful ({mode})", data


def _show_qr(sess: requests.Session, base: str) -> None:
    """Fetch the QR image and open it with the system viewer."""
    try:
        resp = sess.get(f"{base}/auth/bankid/qr", timeout=10)
        data = resp.json()
        qr_b64 = data.get("data", {}).get("qr_image")
        if not qr_b64:
            print(f"  {_yellow('WARN')} QR endpoint returned no image data")
            return
        img_bytes = base64.b64decode(qr_b64)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        tmp.write(img_bytes)
        tmp.close()
        print(f"  {_cyan('QR')} Saved to: {tmp.name}")
        # Try to open with default viewer
        try:
            if sys.platform == "win32":
                os.startfile(tmp.name)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", tmp.name])
            else:
                subprocess.Popen(["xdg-open", tmp.name])
            print(f"  {_cyan('QR')} Opening image viewer — scan the QR code with your BankID app")
        except Exception:
            print(f"  {_yellow('WARN')} Could not auto-open image — open it manually: {tmp.name}")
    except Exception as exc:
        print(f"  {_yellow('WARN')} Could not fetch QR image: {exc}")


def _bankid_poll(sess: requests.Session, base: str,
                 same_device: bool = False, timeout_s: int = 90):
    if same_device:
        print(f"\n  {_yellow('>>>')} Open your BankID app on this device and confirm…")
    else:
        _show_qr(sess, base)
        print(f"\n  {_yellow('>>>')} Scan the QR code with your BankID app.")

    input(f"  {_yellow('>>>')} Press Enter once you have opened/scanned BankID to start polling… ")

    deadline = time.time() + timeout_s
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        time.sleep(2)
        resp = sess.get(f"{base}/auth/bankid/verify", timeout=15)
        try:
            data = resp.json()
        except Exception:
            continue
        verified = data.get("data", {}).get("verified", False)
        print(f"  [{attempt}] verified={verified}")
        if verified is True:
            return PASS, f"Verified after ~{attempt * 2}s", data
        # A non-ok response signals a hard failure
        if not data.get("ok"):
            return FAIL, data.get("error", "Verify failed"), data
    return FAIL, f"Timed out after {timeout_s}s — user did not confirm in BankID app", None


def _bankid_login(sess: requests.Session, base: str):
    resp = sess.post(f"{base}/auth/bankid/login", timeout=15)
    try:
        data = resp.json()
    except Exception:
        return FAIL, f"Non-JSON: {resp.text[:200]}", None
    if not resp.ok:
        if resp.status_code == 401:
            return FAIL, "Not authenticated (401) — BankID verify may not have completed", data
        return FAIL, f"HTTP {resp.status_code}", data
    if not data.get("ok"):
        return FAIL, data.get("error", "Unknown error"), data
    return PASS, "Login succeeded", data


def _check_auth_status(sess: requests.Session, base: str):
    resp = sess.get(f"{base}/", timeout=10)
    try:
        data = resp.json()
    except Exception:
        return FAIL, f"Non-JSON: {resp.text[:200]}", None
    authed = data.get("data", {}).get("authed")
    if authed:
        return PASS, "Confirmed authed=true", data
    return WARN, f"authed={authed} — session may not have persisted", data


def _get_profiles(sess: requests.Session, base: str):
    resp = sess.get(f"{base}/profiles", timeout=15)
    try:
        data = resp.json()
    except Exception:
        return FAIL, f"Non-JSON: {resp.text[:200]}", None
    if not resp.ok:
        if resp.status_code == 401:
            return FAIL, "Not authenticated (401)", data
        return FAIL, f"HTTP {resp.status_code}", data
    if not data.get("ok"):
        return FAIL, data.get("error", "Unknown error"), data
    profiles = data.get("data", [])
    if isinstance(profiles, list):
        count = len(profiles)
    else:
        count = 1
    return PASS, f"{count} profile(s) returned", data


def _get_accounts(sess: requests.Session, base: str, profile_id: str):
    resp = sess.get(f"{base}/accounts",
                    params={"profileId": profile_id}, timeout=15)
    try:
        data = resp.json()
    except Exception:
        return FAIL, f"Non-JSON: {resp.text[:200]}", None
    if not resp.ok:
        if resp.status_code == 401:
            return FAIL, "Not authenticated (401)", data
        return FAIL, f"HTTP {resp.status_code}", data
    if not data.get("ok"):
        return FAIL, data.get("error", "Unknown error"), data
    accounts = _iter_accounts(data.get("data", []))
    return PASS, f"{len(accounts)} account(s) found", data


def _get_transactions(sess: requests.Session, base: str, account_id: str):
    resp = sess.get(
        f"{base}/accounts/{account_id}/transactions",
        params={"perPage": "20", "page": "1"},
        timeout=15,
    )
    try:
        data = resp.json()
    except Exception:
        return FAIL, f"Non-JSON: {resp.text[:200]}", None
    if not resp.ok:
        if resp.status_code == 401:
            return FAIL, "Not authenticated (401)", data
        return FAIL, f"HTTP {resp.status_code}", data
    if not data.get("ok"):
        return FAIL, data.get("error", "Unknown error"), data
    txs = _extract_transactions(data.get("data", {}))
    return PASS, f"{len(txs)} transaction(s) returned", data


def _get_transaction_detail(sess: requests.Session, base: str, tx_id: str):
    resp = sess.get(f"{base}/transactions/{tx_id}", timeout=15)
    try:
        data = resp.json()
    except Exception:
        return FAIL, f"Non-JSON: {resp.text[:200]}", None
    if not resp.ok:
        return FAIL, f"HTTP {resp.status_code}", data
    if not data.get("ok"):
        return WARN, data.get("error", "Unknown error"), data
    return PASS, "Transaction detail returned", data


def _terminate(sess: requests.Session, base: str):
    resp = sess.post(f"{base}/terminate", timeout=10)
    try:
        data = resp.json()
    except Exception:
        return WARN, f"Non-JSON response: {resp.text[:100]}", None
    if resp.ok and data.get("ok"):
        return PASS, "Session terminated", data
    return WARN, f"Terminate returned ok=false (HTTP {resp.status_code})", data


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def _print_summary() -> None:
    print(f"\n{'═' * 60}")
    print(_bold("SUMMARY"))
    print(f"{'═' * 60}")
    width_label = max(len(r[0]) for r in _results) + 2
    for label, verdict, note in _results:
        pad = " " * (width_label - len(label))
        trunc_note = (note[:60] + "…") if len(note) > 63 else note
        print(f"  {label}{pad}{verdict}  {trunc_note}")
    print(f"{'═' * 60}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnostic script for the Swedbank PHP bridge"
    )
    parser.add_argument(
        "--url", default=_DEFAULT_URL,
        help=f"Base URL of the PHP bridge (default: {_DEFAULT_URL})"
    )
    parser.add_argument(
        "--same-device", action="store_true",
        help="Use autoStartToken flow instead of QR code (if BankID is installed on this machine)"
    )
    args = parser.parse_args()
    base = args.url.rstrip("/")
    same_device = args.same_device

    print(_bold(f"\nSwedbank PHP Bridge Diagnostic  —  {base}\n"))

    sess = requests.Session()

    # ── Step 1: Bridge reachable ─────────────────────────────────────────────
    body = _step("1. GET /  (bridge health)", _check_bridge, sess, base)
    if body is None:
        _print_summary()
        sys.exit(1)

    # If already authenticated, skip auth steps
    already_authed = body.get("data", {}).get("authed") or body.get("authenticated")

    if already_authed:
        print(f"\n  {_green('Already authenticated')} — skipping BankID steps")
        _results.append(("2. POST /auth/bankid/init",  SKIP, "already authenticated"))
        _results.append(("3. GET  /auth/bankid/verify", SKIP, "already authenticated"))
        _results.append(("4. POST /auth/bankid/login",  SKIP, "already authenticated"))
        _results.append(("5. GET /  (confirm auth)",    SKIP, "already authenticated"))
    else:
        # ── Step 2: BankID init ──────────────────────────────────────────────
        body = _step("2. POST /auth/bankid/init", _bankid_init, sess, base, same_device)
        if body is None:
            _print_summary()
            sys.exit(1)

        # ── Step 3: BankID poll ──────────────────────────────────────────────
        body = _step("3. GET  /auth/bankid/verify  (poll)", _bankid_poll, sess, base, same_device)
        if body is None:
            _print_summary()
            sys.exit(1)

        # ── Step 4: Login ────────────────────────────────────────────────────
        body = _step("4. POST /auth/bankid/login", _bankid_login, sess, base)
        if body is None:
            _print_summary()
            sys.exit(1)

        # ── Step 5: Confirm auth status ──────────────────────────────────────
        _step("5. GET /  (confirm auth)", _check_auth_status, sess, base)

    # ── Step 6: Profiles ──────────────────────────────────────────────────────
    body = _step("6. GET /profiles", _get_profiles, sess, base)
    if body is None:
        _print_summary()
        sys.exit(1)

    profile_id = ""
    profiles_data = body.get("data", [])
    if isinstance(profiles_data, list) and profiles_data:
        profile_id = profiles_data[0].get("id", "")
    elif isinstance(profiles_data, dict):
        profile_id = profiles_data.get("id", "")
    if not profile_id:
        print(f"  {_yellow('WARN')} Could not extract profile ID — trying accounts without profileId")

    # ── Step 7: Accounts ──────────────────────────────────────────────────────
    body = _step("7. GET /accounts", _get_accounts, sess, base, profile_id)
    if body is None:
        _print_summary()
        sys.exit(1)

    accounts = _iter_accounts(body.get("data", []))
    # Pick first transaction account, fall back to first account
    target_account = None
    for acct in accounts:
        acct_type = acct.get("accountType", "").lower()
        if "transaction" in acct_type or "checking" in acct_type:
            target_account = acct
            break
    if target_account is None and accounts:
        target_account = accounts[0]

    account_id = ""
    if target_account:
        account_id = (target_account.get("id")
                      or target_account.get("fullyFormattedNumber", ""))

    if not account_id:
        print(f"  {_red('FAIL')} No account ID found — cannot fetch transactions")
        _results.append(("8. GET /accounts/{id}/transactions", FAIL, "no account ID"))
        _results.append(("9. GET /transactions/{id}", SKIP, "no account ID"))
        _print_summary()
        _terminate_quietly(sess, base)
        sys.exit(1)

    # ── Step 8: Transactions ──────────────────────────────────────────────────
    body = _step(f"8. GET /accounts/…/transactions", _get_transactions,
                 sess, base, account_id)
    if body is None:
        _results.append(("9. GET /transactions/{id}", SKIP, "no transactions"))
        _terminate_step(sess, base)
        _print_summary()
        sys.exit(1)

    txs = _extract_transactions(body.get("data", {}))
    tx_id = ""
    for tx in txs:
        if tx.get("id"):
            tx_id = tx["id"]
            break

    # ── Step 9: Transaction detail ────────────────────────────────────────────
    if tx_id:
        _step("9. GET /transactions/{id}", _get_transaction_detail, sess, base, tx_id)
    else:
        print(f"\n  {_cyan('SKIP')} Step 9 — no transaction IDs found")
        _results.append(("9. GET /transactions/{id}", SKIP, "no transaction IDs in response"))

    # ── Step 10: Terminate (always) ───────────────────────────────────────────
    _terminate_step(sess, base)

    _print_summary()


def _terminate_step(sess: requests.Session, base: str) -> None:
    _step("10. POST /terminate", _terminate, sess, base)


def _terminate_quietly(sess: requests.Session, base: str) -> None:
    try:
        sess.post(f"{base}/terminate", timeout=10)
    except Exception:
        pass
    _results.append(("10. POST /terminate", SKIP, "called quietly during early exit"))


if __name__ == "__main__":
    main()
