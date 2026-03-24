"""Flask web app — submit queries, stream execution events, view reports."""

from __future__ import annotations

import threading
from datetime import date

import requests as http_requests
from flask import Flask, Response, jsonify, render_template, request
from langgraph.graph import StateGraph, START, END

import config
import event_bus
import php_session
from event_bus import Event, EventType
from state import FinanceState
from node_wrappers import supervisor_node, data_fetch_node, analyze_node, advise_node

app = Flask(__name__)

# ---------------------------------------------------------------------------
# PHP bridge proxy — stores PHPSESSID via php_session so auth persists
# ---------------------------------------------------------------------------

def _php_proxy(method: str, path: str, json_body=None, params=None):
    """Forward a request to the PHP microservice and return its JSON response."""
    url = f"{config.SWEDBANK_API_URL}{path}"
    cookies = php_session.get()

    try:
        if method == "GET":
            resp = http_requests.get(url, cookies=cookies, params=params, timeout=15)
        else:
            resp = http_requests.post(url, json=json_body or {}, cookies=cookies, timeout=15)
    except http_requests.exceptions.ConnectionError:
        return {
            "ok": False,
            "error": f"PHP bridge is not running. Start it with: php -S localhost:8080 SwedbankJson/server.php",
        }, 503

    php_session.update(resp.cookies)
    return resp.json(), resp.status_code


# ---------------------------------------------------------------------------
# Finance helpers (used by dashboard routes)
# ---------------------------------------------------------------------------

_CATEGORIES = [
    ("Groceries",          ["ica", "coop", "willys", "lidl", "hemköp", "netto", "citygross", "mathem", "matsmart"]),
    ("Restaurants & Cafés",["espresso house", "waynes", "wayne's", "starbucks", "mcdonalds", "mcdonald's",
                             "max hamburgare", "burger king", "subway", "pizza", "kebab", "sushi", "restaurang"]),
    ("Transport",          ["sl ", "sj ", "uber", "bolt ", "taxi", "vy ", "flixbus", "ryanair",
                             "norwegian ", "sas ", "parkering", "biljett"]),
    ("Shopping",           ["h&m", "zara", "asos", "zalando", "amazon", "ikea",
                             "elgiganten", "webhallen", "mediamarkt"]),
    ("Health & Fitness",   ["apoteket", "apotek hjärtat", "kronans apotek", "apotek", "sats ", "friskis", "gym "]),
    ("Entertainment",      ["spotify", "netflix", "hbo", "disney", "steam", "playstation", "sf bio", "filmstaden"]),
    ("Bills & Utilities",  ["hyra", "vattenfall", "telia", "tele2", "comhem", "tre ", "telenor",
                             "försäkring", "elnät"]),
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


def _categorize(description: str) -> str:
    desc = description.lower()
    for category, keywords in _CATEGORIES:
        if any(kw in desc for kw in keywords):
            return category
    return "Other"


def _iter_accounts(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("accounts", "transactionAccounts", "savingAccounts", "loanAccounts", "cardAccounts"):
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


def _parse_date(tx: dict) -> date | None:
    raw = tx.get("date") or tx.get("accountingDate") or tx.get("bookingDate") or ""
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

_run_lock = threading.Lock()
_running = False


def _route_supervisor(state: FinanceState) -> str:
    """Read next_agent from state and route accordingly."""
    return state.get("next_agent", "done")


def _build_web_graph():
    graph = StateGraph(FinanceState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("data_fetch", data_fetch_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("advise", advise_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_supervisor,
        {
            "data_fetch": "data_fetch",
            "analyze":    "analyze",
            "advise":     "advise",
            "done":       END,
        },
    )
    # All agents route back to supervisor after completing
    graph.add_edge("data_fetch", "supervisor")
    graph.add_edge("analyze",    "supervisor")
    graph.add_edge("advise",     END)

    return graph.compile()


def _run_graph(query: str) -> None:
    global _running
    try:
        app_graph = _build_web_graph()
        initial_state: FinanceState = {
            "query":            query,
            "messages":         [],
            "accounts":         [],
            "transactions":     [],
            "analysis":         "",
            "next_agent":       "",
            "supervisor_notes": "",
            "report":           "",
            "turn":             0,
        }
        app_graph.invoke(initial_state)
        event_bus.emit(Event(type=EventType.DONE, node="system", data={}))
    except Exception as e:
        event_bus.emit(Event(type=EventType.ERROR, node="system", data={"error": str(e)}))
        event_bus.emit(Event(type=EventType.DONE, node="system", data={}))
    finally:
        with _run_lock:
            _running = False


# ---------------------------------------------------------------------------
# Routes — main UI
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        tool_model=config.TOOL_MODEL,
        reasoning_model=config.REASONING_MODEL,
        max_turns=config.MAX_AGENT_TURNS,
    )


@app.route("/run", methods=["POST"])
def run():
    global _running
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400

    with _run_lock:
        if _running:
            return jsonify({"error": "A run is already in progress"}), 409
        _running = True

    event_bus.clear()
    thread = threading.Thread(target=_run_graph, args=(query,), daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/stream")
def stream():
    def generate():
        for event in event_bus.consume(timeout=2.0):
            if event is None:
                yield ": keepalive\n\n"
            else:
                yield event.to_sse()
    return Response(generate(), mimetype="text/event-stream")


# ---------------------------------------------------------------------------
# Routes — dashboard data
# ---------------------------------------------------------------------------

@app.route("/api/dashboard")
def dashboard():
    """Return all accounts with balances and the last 5 transactions each."""
    accounts_resp, status = _php_proxy("GET", "/accounts")
    if not accounts_resp.get("ok"):
        return jsonify({"ok": False, "error": accounts_resp.get("error", "Could not fetch accounts")}), status

    accounts = _iter_accounts(accounts_resp["data"])
    result = []

    for acct in accounts:
        acct_id = acct.get("id") or acct.get("fullyFormattedNumber", "")
        name = acct.get("name", "Unknown Account")
        balance = _parse_amount(acct.get("balance", 0))
        currency = acct.get("currency", "SEK")
        acct_type = acct.get("accountType", "")

        recent = []
        if acct_id:
            txn_resp, _ = _php_proxy(
                "GET",
                f"/accounts/{acct_id}/transactions",
                params={"perPage": "5", "page": "1"},
            )
            if txn_resp.get("ok"):
                for tx in _extract_transactions(txn_resp["data"])[:5]:
                    recent.append({
                        "date":        tx.get("date") or tx.get("accountingDate", ""),
                        "description": tx.get("description") or tx.get("narrative", ""),
                        "amount":      tx.get("amount", 0),
                        "currency":    tx.get("currency", currency),
                    })

        result.append({
            "id":                  acct_id,
            "name":                name,
            "balance":             balance,
            "currency":            currency,
            "accountType":         acct_type,
            "recent_transactions": recent,
        })

    return jsonify({"ok": True, "data": {"accounts": result}})


@app.route("/api/spending/monthly")
def spending_monthly():
    """Return categorized spending totals for the current calendar month."""
    today = date.today()
    month_start = date(today.year, today.month, 1)

    accounts_resp, status = _php_proxy("GET", "/accounts")
    if not accounts_resp.get("ok"):
        return jsonify({"ok": False, "error": "Could not fetch accounts"}), status

    accounts = _iter_accounts(accounts_resp["data"])
    category_totals: dict[str, dict] = {}
    total_spent = 0.0

    for acct in accounts:
        acct_id = acct.get("id") or acct.get("fullyFormattedNumber", "")
        if not acct_id:
            continue

        txn_resp, _ = _php_proxy(
            "GET",
            f"/accounts/{acct_id}/transactions",
            params={"perPage": "50", "page": "1"},
        )
        if not txn_resp.get("ok"):
            continue

        for tx in _extract_transactions(txn_resp["data"]):
            tx_date = _parse_date(tx)
            if tx_date is None or tx_date < month_start:
                continue
            amount = _parse_amount(tx.get("amount", 0))
            if amount >= 0:
                continue  # skip income / deposits
            amount = abs(amount)
            desc = tx.get("description") or tx.get("narrative") or ""
            cat = _categorize(desc)
            if cat not in category_totals:
                category_totals[cat] = {"amount": 0.0, "count": 0}
            category_totals[cat]["amount"] += amount
            category_totals[cat]["count"] += 1
            total_spent += amount

    categories = [
        {"name": k, "amount": round(v["amount"], 2), "count": v["count"]}
        for k, v in sorted(category_totals.items(), key=lambda x: -x[1]["amount"])
    ]

    return jsonify({
        "ok": True,
        "data": {
            "period":      f"{month_start.isoformat()} to {today.isoformat()}",
            "total_spent": round(total_spent, 2),
            "categories":  categories,
        },
    })


# ---------------------------------------------------------------------------
# Routes — auth proxy
# ---------------------------------------------------------------------------

@app.route("/api/auth/status")
def auth_status():
    data, status = _php_proxy("GET", "/")
    return jsonify(data), status


@app.route("/api/auth/bankid/init", methods=["POST"])
def auth_bankid_init():
    body = request.get_json(silent=True) or {}
    data, status = _php_proxy("POST", "/auth/bankid/init", json_body=body)
    return jsonify(data), status


@app.route("/api/auth/bankid/qr")
def auth_bankid_qr():
    data, status = _php_proxy("GET", "/auth/bankid/qr")
    return jsonify(data), status


@app.route("/api/auth/bankid/verify")
def auth_bankid_verify():
    data, status = _php_proxy("GET", "/auth/bankid/verify")
    return jsonify(data), status


@app.route("/api/auth/bankid/login", methods=["POST"])
def auth_bankid_login():
    data, status = _php_proxy("POST", "/auth/bankid/login")
    return jsonify(data), status


@app.route("/api/auth/terminate", methods=["POST"])
def auth_terminate():
    data, status = _php_proxy("POST", "/terminate")
    if status == 200:
        php_session.clear()
    return jsonify(data), status


if __name__ == "__main__":
    print("Finance Agent Web UI")
    print(f"  Tool model:      {config.TOOL_MODEL}")
    print(f"  Reasoning model: {config.REASONING_MODEL}")
    print(f"  Max agent turns: {config.MAX_AGENT_TURNS}")
    print(f"  PHP bridge:      {config.SWEDBANK_API_URL}")
    print("  http://localhost:5000")
    app.run(debug=False, port=5000, threaded=True)
