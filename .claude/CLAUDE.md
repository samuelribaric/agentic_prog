# CLAUDE.md — Project Context & Instructions

## Project Overview

**Name:** agentic-prog
**Description:** A multi-agent AI system built with LangGraph and Ollama, acting as a **personal finance advisor** that connects to Swedbank via BankID authentication. A supervisor agent orchestrates specialized sub-agents that fetch real bank data, categorize and analyze transactions, and generate actionable financial recommendations. It features a CLI and a real-time web UI powered by Server-Sent Events.

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (StateGraph, supervisor pattern) |
| LLM Framework | LangChain + LangChain-Ollama |
| Local Models | Ollama — deepseek-r1:8b (reasoning), llama3.1:8b (tool-calling + supervisor) |
| Web Search | DuckDuckGo (ddgs library, no API key needed) |
| Web Server | Flask with SSE streaming |
| Frontend | Vanilla JS + CSS3 + marked.js for Markdown rendering |
| Config | python-dotenv (.env file) |
| Package Manager | Poetry |
| Python | 3.11+ |
| Banking API | SwedbankJson (PHP) — unofficial Swedbank/Sparbanken REST client |
| Bank Auth | Mobile BankID / Security Token |

## Project Structure

```
agentic_prog/
├── researcher.py          # CLI entry point
├── web_app.py             # Flask web server with SSE
├── state.py               # LangGraph shared state (FinanceState TypedDict)
├── config.py              # .env config loader
├── models.py              # Ollama model wrappers
├── prompts.py             # Prompt templates for each node
├── event_bus.py           # Thread-safe SSE event bus
├── node_wrappers.py       # Web-event-emitting node wrappers
├── nodes/
│   ├── __init__.py
│   ├── supervisor_node.py # Orchestrator — routes between agents
│   ├── data_fetch_node.py # Tool-calling agent — fetches bank data
│   ├── analyze_node.py    # Reasoning agent — categorizes & calculates
│   └── advise_node.py     # Reasoning agent — writes final Markdown answer
├── tools/
│   ├── __init__.py
│   ├── finance_tools.py   # Banking tools (list_accounts, get_transactions, search_web)
│   └── search_tool.py     # DuckDuckGo search (used by finance_tools.search_web)
├── templates/
│   └── index.html         # Flask web UI template
├── static/
│   ├── app.js             # SSE client + DOM management
│   └── style.css          # UI styling
├── SwedbankJson/          # Swedbank API client (PHP) — bank data access
│   ├── server.php                 # PHP REST microservice (bridge for Python tools)
│   ├── cache/                     # AppData cache directory
│   ├── src/
│   │   ├── SwedbankJson.php       # Main API client class
│   │   ├── AppData.php            # App metadata manager
│   │   ├── Auth/
│   │   │   ├── MobileBankID.php   # Mobile BankID authentication
│   │   │   ├── SecurityToken.php  # Hardware token authentication
│   │   │   └── UnAuth.php         # No-auth (quick balance only)
│   │   └── Exception/             # Custom exceptions
│   └── docs/                      # API reference & response samples
├── mcp_server/            # (Planned) MCP server integrations
├── pyproject.toml         # Poetry dependencies
├── .env.example           # Environment variable template
└── README.md              # Project documentation
```

## Graph Architecture

```
START → supervisor → data_fetch → supervisor
                   → analyze   → supervisor
                   → advise    → END
                   → END (done)
```

- **supervisor**: Routes between agents based on current state; loops until answer is ready
- **data_fetch**: Tool-calling agent (llama3.1:8b) — calls list_accounts + get_transactions
- **analyze**: Reasoning agent (deepseek-r1:8b) — categorizes transactions, calculates totals
- **advise**: Reasoning agent (deepseek-r1:8b) — writes final Markdown answer for the user

Max turns controlled by `MAX_AGENT_TURNS` (default: 8).

## Entry Points

- **CLI:** `python researcher.py "<query>"`
- **Web:** `python web_app.py` → http://localhost:5000

## Environment Variables

See `.env.example` for all available settings:
- `OLLAMA_BASE_URL` — Ollama server URL
- `REASONING_MODEL` / `TOOL_MODEL` — model names
- `MAX_AGENT_TURNS` — max supervisor loop iterations (default: 8)
- `SWEDBANK_API_URL` — PHP bridge URL (default: `http://localhost:8080`)
- `SWEDBANK_APP_TYPE` — Bank app type: `swedbank`, `swedbank_foretag`, `sparbanken`, `sparbanken_foretag`

## SwedbankJson API Reference

The `SwedbankJson/` directory contains an unofficial PHP client for Swedbank's mobile banking API, exposed to the Python agent via a PHP REST microservice (`server.php`).

### PHP Microservice

Run with: `php -S localhost:8080 SwedbankJson/server.php`

The microservice wraps SwedbankJson methods as JSON endpoints. Python tools in `tools/finance_tools.py` call these endpoints via `requests`. Auth is handled by the user before the agent runs; the agent only uses data-fetching tools.

**Authentication methods:**
- **Mobile BankID** — user authenticates via BankID app (QR code or same-device autostart)
- **Security Token** — hardware token with one-time codes or challenge-response
- **UnAuth** — no login required (quick balance only)

**Available API methods:**

| Method | Returns |
|---|---|
| `profileList()` | User profiles (personal + corporate) |
| `accountList($profileID)` | All accounts (checking, savings, loans, cards) |
| `accountDetails($accountID, $perPage, $page)` | Account info + paginated transactions |
| `transactionDetails($transactionID)` | Single transaction detail |
| `portfolioList($profileID)` | Investment savings accounts |
| `transferBaseInfo()` | Accounts eligible for transfers |
| `transferRegisterPayment()` | Register a pending transfer |
| `transferConfirmPayments()` | Execute registered transfers |
| `quickBalance($subscriptionId)` | Balance check (no auth needed) |
| `reminders()` | Notifications (rejected payments, unsigned transfers) |

**API base:** `https://auth.api.swedbank.se/TDE_DAP_Portal_REST_WEB/api/v5/`

## Key Patterns & Conventions

- **State accumulation:** `messages` and `transactions` use `Annotated[list, operator.add]` for append-only accumulation across nodes. `accounts` is a plain list (replaced on each fetch).
- **Supervisor routing:** `supervisor_node` outputs `next_agent` (string) into state. A conditional edge in the graph reads this field to route to the correct agent.
- **Finance tools return JSON:** `list_accounts` and `get_transactions` return JSON strings so `data_fetch_node` can parse the raw dicts and populate `state["accounts"]` / `state["transactions"]`.
- **Tool argument normalization:** `search_web` accepts both `query` and `q` parameter names since LLMs are inconsistent.
- **Node wrappers:** `node_wrappers.py` wraps each node function to emit events via `event_bus.py` for the web UI, keeping node logic clean.
- **Threading:** Web app runs the graph in a background thread with a lock to prevent concurrent runs.
- **PHP bridge:** `SwedbankJson/server.php` is a single-file PHP router using PHP sessions for auth state. Python tools call it via `requests`. Auth endpoints are for user interaction; agent tools only use data endpoints.
- **Auth proxy:** Flask proxies `/api/auth/*` routes to the PHP bridge so the browser only talks to port 5000. The PHP session cookie (`PHPSESSID`) is stored in a module-level dict (`_php_session_cookie`) and forwarded on every proxy call to maintain auth state. The web UI gates the query form behind BankID authentication.

---

## Standing Instructions

### README Maintenance
Every time we update any major functionality for the app or repo, the README.md must be updated accordingly, so that the README is always up to date with the current state of the app. This includes but is not limited to:
- Adding, removing, or renaming features or nodes
- Changing the tech stack or dependencies
- Modifying the graph architecture or workflow
- Adding new entry points, tools, or MCP integrations
- Changing setup/installation steps

### CLAUDE.md Maintenance
This file itself should be updated when:
- The project structure changes significantly
- New conventions or patterns are established
- The tech stack changes
- The user provides new standing instructions
