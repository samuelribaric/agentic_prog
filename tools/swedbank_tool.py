"""Swedbank banking tools — call the PHP microservice to fetch account data."""

import requests
from langchain_core.tools import tool
from config import SWEDBANK_API_URL
import php_session


def _get(path: str, params: dict | None = None) -> dict:
    """Send GET request to the Swedbank PHP bridge and return parsed JSON."""
    resp = requests.get(
        f"{SWEDBANK_API_URL}{path}",
        params=params,
        cookies=php_session.get(),
        timeout=15,
    )
    php_session.update(resp.cookies)
    return resp.json()


@tool
def swedbank_list_accounts(profile_id: str = "") -> str:
    """List all Swedbank bank accounts with balances.

    Returns account names, types, balances, and IDs. Optionally filter by
    profile ID (leave empty for default profile).
    """
    try:
        params = {}
        if profile_id:
            params["profileId"] = profile_id
        data = _get("/accounts", params)
        if not data.get("ok"):
            return f"Error: {data.get('error', 'Unknown error')}"

        accounts = data["data"]
        if not accounts:
            return "No accounts found."

        # Format for LLM consumption
        lines = []
        for acct in _iter_accounts(accounts):
            name = acct.get("name", "Unknown")
            balance = acct.get("balance", "N/A")
            currency = acct.get("currency", "SEK")
            acct_id = acct.get("id", acct.get("fullyFormattedNumber", ""))
            lines.append(f"- {name}: {balance} {currency} (ID: {acct_id})")
        return "\n".join(lines) if lines else "No accounts found."
    except Exception as e:
        return f"Swedbank API error: {e}"


@tool
def swedbank_get_transactions(
    account_id: str, per_page: int = 20, page: int = 1
) -> str:
    """Get transaction history for a Swedbank account.

    Args:
        account_id: The account ID to fetch transactions for.
        per_page: Number of transactions per page (default 20).
        page: Page number (default 1).
    """
    try:
        params = {"perPage": str(per_page), "page": str(page)}
        data = _get(f"/accounts/{account_id}/transactions", params)
        if not data.get("ok"):
            return f"Error: {data.get('error', 'Unknown error')}"

        details = data["data"]
        transactions = _extract_transactions(details)
        if not transactions:
            return "No transactions found."

        lines = []
        for tx in transactions:
            date = tx.get("date", tx.get("accountingDate", ""))
            desc = tx.get("description", tx.get("narrative", ""))
            amount = tx.get("amount", "")
            currency = tx.get("currency", "SEK")
            lines.append(f"- [{date}] {desc}: {amount} {currency}")
        return "\n".join(lines)
    except Exception as e:
        return f"Swedbank API error: {e}"


@tool
def swedbank_transaction_detail(transaction_id: str) -> str:
    """Get detailed info for a single Swedbank transaction.

    Args:
        transaction_id: The transaction ID to look up.
    """
    try:
        data = _get(f"/transactions/{transaction_id}")
        if not data.get("ok"):
            return f"Error: {data.get('error', 'Unknown error')}"
        # Return the raw detail as formatted text
        detail = data["data"]
        if isinstance(detail, dict):
            lines = [f"{k}: {v}" for k, v in detail.items()]
            return "\n".join(lines)
        return str(detail)
    except Exception as e:
        return f"Swedbank API error: {e}"


@tool
def swedbank_list_portfolios(profile_id: str = "") -> str:
    """List Swedbank investment portfolios.

    Returns investment savings accounts. Optionally filter by profile ID.
    """
    try:
        params = {}
        if profile_id:
            params["profileId"] = profile_id
        data = _get("/portfolios", params)
        if not data.get("ok"):
            return f"Error: {data.get('error', 'Unknown error')}"

        portfolios = data["data"]
        if not portfolios:
            return "No portfolios found."

        if isinstance(portfolios, dict):
            lines = [f"{k}: {v}" for k, v in portfolios.items()]
            return "\n".join(lines)
        return str(portfolios)
    except Exception as e:
        return f"Swedbank API error: {e}"


@tool
def swedbank_quick_balance(subscription_id: str) -> str:
    """Get quick balance for a Swedbank subscription (no auth required).

    Args:
        subscription_id: The quick-balance subscription ID.
    """
    try:
        data = _get(f"/quick-balance/{subscription_id}")
        if not data.get("ok"):
            return f"Error: {data.get('error', 'Unknown error')}"

        balance = data["data"]
        if isinstance(balance, dict):
            lines = [f"{k}: {v}" for k, v in balance.items()]
            return "\n".join(lines)
        return str(balance)
    except Exception as e:
        return f"Swedbank API error: {e}"


# ---------------------------------------------------------------------------
# Helpers for navigating the Swedbank API response structure
# ---------------------------------------------------------------------------

def _iter_accounts(data) -> list:
    """Extract a flat list of account dicts from the API response."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Swedbank may nest accounts under various keys
        for key in ("accounts", "transactionAccounts", "savingAccounts",
                     "loanAccounts", "cardAccounts"):
            if key in data:
                items = data[key]
                if isinstance(items, list):
                    return items
        # If none of those keys, return values that look like accounts
        return [data]
    return []


def _extract_transactions(data) -> list:
    """Pull the transactions list from an accountDetails response."""
    if isinstance(data, dict):
        for key in ("transactions", "reservedTransactions"):
            if key in data and isinstance(data[key], list):
                return data[key]
    if isinstance(data, list):
        return data
    return []
