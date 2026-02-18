"""Finance-specific tools for the data_fetch agent."""

from __future__ import annotations

import json
from datetime import date, timedelta

import requests
from langchain_core.tools import tool

import php_session
from config import SWEDBANK_API_URL


# ---------------------------------------------------------------------------
# Shared category definitions (also used in web_app.py)
# ---------------------------------------------------------------------------

CATEGORIES: list[tuple[str, list[str]]] = [
    ("Groceries",           ["ica", "coop", "willys", "lidl", "hemköp", "netto",
                              "citygross", "mathem", "matsmart"]),
    ("Restaurants & Cafés", ["espresso house", "waynes", "wayne's", "starbucks",
                              "mcdonalds", "mcdonald's", "max hamburgare", "burger king",
                              "subway", "pizza", "kebab", "sushi", "restaurang"]),
    ("Transport",           ["sl ", "sj ", "uber", "bolt ", "taxi", "vy ", "flixbus",
                              "ryanair", "norwegian ", "sas ", "parkering", "biljett"]),
    ("Shopping",            ["h&m", "zara", "asos", "zalando", "amazon", "ikea",
                              "elgiganten", "webhallen", "mediamarkt"]),
    ("Health & Fitness",    ["apoteket", "apotek hjärtat", "kronans apotek", "apotek",
                              "sats ", "friskis", "gym "]),
    ("Entertainment",       ["spotify", "netflix", "hbo", "disney", "steam",
                              "playstation", "sf bio", "filmstaden"]),
    ("Bills & Utilities",   ["hyra", "vattenfall", "telia", "tele2", "comhem",
                              "tre ", "telenor", "försäkring", "elnät"]),
]


def _parse_amount(val) -> float:
    """Parse a Swedbank amount to float.

    Swedbank returns amounts as Swedish-locale strings, e.g. '7 615,90' or
    '-150,44' (space/NBSP as thousands separator, comma as decimal).
    """
    if isinstance(val, (int, float)):
        return float(val)
    if not val:
        return 0.0
    s = str(val).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def categorize_transaction(description: str) -> str:
    """Categorize a transaction based on its description text."""
    desc = description.lower()
    for category, keywords in CATEGORIES:
        if any(kw in desc for kw in keywords):
            return category
    return "Other"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(path: str, params: dict | None = None) -> dict:
    resp = requests.get(
        f"{SWEDBANK_API_URL}{path}",
        params=params,
        cookies=php_session.get(),
        timeout=15,
    )
    php_session.update(resp.cookies)
    return resp.json()


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


def _period_to_dates(period: str) -> tuple[date, date]:
    """Convert a period string to (start_date, end_date)."""
    today = date.today()
    if ":" in period:
        parts = period.split(":")
        return date.fromisoformat(parts[0]), date.fromisoformat(parts[1])
    if period == "week":
        return today - timedelta(days=7), today
    if period == "month":
        return date(today.year, today.month, 1), today
    if period == "3months":
        return today - timedelta(days=90), today
    if period == "6months":
        return today - timedelta(days=180), today
    if period == "year":
        return date(today.year, 1, 1), today
    # Default: current month
    return date(today.year, today.month, 1), today


# ---------------------------------------------------------------------------
# LangChain tools (return JSON strings for structured parsing in data_fetch_node)
# ---------------------------------------------------------------------------

@tool
def list_accounts() -> str:
    """List all Swedbank bank accounts with balances.

    Returns a JSON array of account objects, each with:
    id, name, balance, currency, accountType.
    Use the id field with get_transactions to fetch transaction history.
    """
    try:
        data = _get("/accounts")
        if not data.get("ok"):
            return json.dumps({"error": data.get("error", "Unknown error")})

        accounts = _iter_accounts(data["data"])
        if not accounts:
            return json.dumps([])

        # Return normalized account objects
        result = []
        for acct in accounts:
            result.append({
                "id":          acct.get("id", acct.get("fullyFormattedNumber", "")),
                "name":        acct.get("name", "Unknown"),
                "balance":     _parse_amount(acct.get("balance", 0)),
                "currency":    acct.get("currency", "SEK"),
                "accountType": acct.get("accountType", ""),
            })
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": f"Bank API error: {e}"})


@tool
def get_transactions(account_id: str, period: str = "month") -> str:
    """Get transactions for a bank account within a time period.

    Args:
        account_id: The account ID from list_accounts.
        period: Time period — "week", "month", "3months", "6months", "year",
                or a custom range "YYYY-MM-DD:YYYY-MM-DD".

    Returns a JSON array of transaction objects with:
    date, description, amount (negative = expense), currency.
    """
    try:
        start, end = _period_to_dates(period)
        data = _get(
            f"/accounts/{account_id}/transactions",
            params={"perPage": "100", "page": "1"},
        )
        if not data.get("ok"):
            return json.dumps({"error": data.get("error", "Unknown error")})

        transactions = _extract_transactions(data["data"])
        if not transactions:
            return json.dumps([])

        # Filter to date range and normalize fields
        filtered = []
        for tx in transactions:
            raw_date = (
                tx.get("date")
                or tx.get("accountingDate")
                or tx.get("bookingDate")
                or ""
            )
            try:
                tx_date = date.fromisoformat(str(raw_date)[:10])
                if not (start <= tx_date <= end):
                    continue
            except (ValueError, TypeError):
                pass  # include transactions with unparseable dates

            filtered.append({
                "date":        raw_date,
                "description": tx.get("description") or tx.get("narrative", ""),
                "amount":      _parse_amount(tx.get("amount", 0)),
                "currency":    tx.get("currency", "SEK"),
                "id":          tx.get("id", ""),
            })

        return json.dumps(filtered)
    except Exception as e:
        return json.dumps({"error": f"Bank API error: {e}"})


@tool
def search_web(query: str) -> str:
    """Search the web using DuckDuckGo. Use only when bank data is insufficient.

    Args:
        query: The search query string.
    """
    from tools.search_tool import ddg_search
    return ddg_search.invoke({"query": query})
