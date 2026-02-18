# Agentic Personal Finance Advisor

A multi-agent AI system that connects to your Swedbank account and acts as a personal finance advisor. Authenticate with BankID, and the agent analyzes your transactions, categorizes spending, identifies patterns, and generates actionable financial recommendations — all powered by local LLMs via [LangGraph](https://github.com/langchain-ai/langgraph) and [Ollama](https://ollama.com).

## How It Works

```
User authenticates via BankID
  │
  ▼
┌────────────┐
│ Supervisor │  ← orchestrates all agents, loops until answer is ready
└─────┬──────┘
      │ routes to
      ├──▶ data_fetch  — fetches accounts + transactions from Swedbank
      ├──▶ analyze     — categorizes spending, calculates totals, finds patterns
      └──▶ advise      — writes the final Markdown response for the user
```

The supervisor reads the current state after each agent completes and decides the next step. It loops until it has enough information to answer the question, then routes to the advise agent which writes the final report.

**Example flow for "What did I spend on restaurants last month?":**
1. `supervisor` → route to `data_fetch` with instructions to fetch transactions for last month
2. `data_fetch` → calls `list_accounts`, then `get_transactions` for each account
3. `supervisor` → route to `analyze` to categorize and sum restaurant spending
4. `analyze` → categorizes all transactions, calculates totals per category
5. `supervisor` → route to `advise` with the analysis ready
6. `advise` → writes a clear, friendly Markdown answer with numbers and suggestions

## Features

- **Supervisor-driven orchestration** — smart routing between specialized agents using LangGraph
- **Swedbank integration** — connect to your real bank data via BankID authentication
- **Transaction categorization** — automatic keyword-based categorization into 8 spending categories
- **Time-period-aware fetching** — query any period: week, month, 3 months, 6 months, year, or custom range
- **Two interfaces** — CLI for quick queries, web UI with real-time streaming
- **Real-time web UI** — Server-Sent Events stream each agent step live to the browser
- **Fully local** — runs entirely on your machine via Ollama, no paid API keys required
- **BankID authentication** — Mobile BankID (QR code or same-device) and hardware security token support

## Spending Categories

Transactions are automatically categorized using keyword matching:

| Category | Examples |
|---|---|
| Groceries | ICA, Coop, Willys, Lidl, Hemköp |
| Restaurants & Cafés | McDonald's, Subway, Espresso House, Pizza/Kebab/Sushi |
| Transport | SL, SJ, Uber, Taxi, Ryanair, Parking |
| Shopping | H&M, Zalando, Amazon, IKEA, Elgiganten |
| Health & Fitness | Apotek, SATS, Friskis & Svettis |
| Entertainment | Spotify, Netflix, Steam, SF Bio |
| Bills & Utilities | Rent, Vattenfall, Telia, Insurance |
| Other | Everything else |

## Banking API (SwedbankJson)

The `SwedbankJson/` directory contains an unofficial PHP client for Swedbank's mobile banking REST API. It provides access to:

| Capability | Description |
|---|---|
| **Accounts** | List all accounts — checking, savings, loans, credit/debit cards |
| **Transactions** | Paginated transaction history with dates, amounts, descriptions |
| **Transaction details** | Detailed info for individual transactions |
| **Balances** | Quick balance check (no auth required for subscribed accounts) |
| **Transfers** | Register, confirm, list, and cancel money transfers |
| **Portfolios** | Investment savings account information |
| **Profiles** | Personal and corporate account profiles |
| **Reminders** | Rejected payments, unsigned transfers, e-invoices |

**Authentication methods:**
- **Mobile BankID** — scan QR code or autostart on same device
- **Security Token** — hardware token with one-time codes or challenge-response
- **No Auth** — quick balance only (requires prior subscription)

## Prerequisites

- **Python 3.11+**
- **PHP 8.1+** with `curl` and `json` extensions (for the Swedbank API bridge)
- **[Ollama](https://ollama.com)** installed and running
- **[Poetry](https://python-poetry.org/)** for dependency management
- **Swedish BankID** for Swedbank authentication

Pull the required models:

```bash
ollama pull llama3.1:8b
ollama pull deepseek-r1:8b
```

## Setup

```bash
# Clone the repo
git clone https://github.com/samuelribaric/agentic_prog.git
cd agentic_prog

# Install Python dependencies
poetry install

# Install PHP dependencies for the Swedbank API bridge
cd SwedbankJson && composer install && cd ..

# Configure environment
cp .env.example .env
# Edit .env if you need to change model names, Ollama URL, etc.
```

## Usage

### 1. Start the Swedbank PHP bridge

The agent needs the PHP microservice running to access banking data:

```bash
php -S localhost:8080 SwedbankJson/server.php
```

Verify it's running: `curl http://localhost:8080/` should return a JSON status response.

### 2. Run the agent

**CLI:**

```bash
python researcher.py "What did I spend on restaurants last month?"
python researcher.py "How much did I spend on groceries this year?"
python researcher.py "What are my account balances?"
```

**Web UI:**

```bash
python web_app.py
```

Open http://localhost:5000 in your browser. The web UI includes a built-in BankID authentication panel:

1. Click **Login with BankID** — a QR code appears and auto-refreshes
2. Scan the QR code with your BankID app on your phone
3. Once verified, the query form unlocks and you can start asking questions
4. Click **Sign out** when done to terminate the bank session

The Flask server proxies all auth requests to the PHP bridge, so the browser only talks to port 5000.

## Configuration

All settings are managed via `.env` (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `REASONING_MODEL` | `deepseek-r1:8b` | Model for analysis & report generation |
| `TOOL_MODEL` | `llama3.1:8b` | Model for tool-calling (supervisor + data_fetch) |
| `MAX_AGENT_TURNS` | `8` | Max supervisor loop iterations before stopping |
| `SWEDBANK_API_URL` | `http://localhost:8080` | Swedbank PHP bridge URL |
| `SWEDBANK_APP_TYPE` | `swedbank` | Bank app: `swedbank`, `swedbank_foretag`, `sparbanken`, `sparbanken_foretag` |

## Project Structure

```
agentic_prog/
├── researcher.py          # CLI entry point
├── web_app.py             # Flask web server with SSE streaming
├── state.py               # Shared graph state (FinanceState)
├── config.py              # Environment config loader
├── models.py              # Ollama model wrappers
├── prompts.py             # Prompt templates for each agent node
├── event_bus.py           # Thread-safe SSE event bus
├── node_wrappers.py       # Event-emitting node wrappers for web UI
├── nodes/
│   ├── supervisor_node.py # Orchestrator — routes between agents
│   ├── data_fetch_node.py # Tool-calling agent — fetches bank data
│   ├── analyze_node.py    # Reasoning agent — categorizes & calculates
│   └── advise_node.py     # Reasoning agent — writes final Markdown answer
├── tools/
│   ├── finance_tools.py   # Banking tools (list_accounts, get_transactions, search_web)
│   └── search_tool.py     # DuckDuckGo web search (used by finance_tools.search_web)
├── SwedbankJson/          # Swedbank API client (PHP)
│   ├── server.php         # PHP REST microservice (bridge)
│   ├── src/
│   │   ├── SwedbankJson.php       # Main API client
│   │   ├── AppData.php            # App metadata manager
│   │   └── Auth/                  # BankID & token authentication
│   └── docs/                      # API docs & response samples
├── templates/
│   └── index.html         # Web UI template
├── static/
│   ├── app.js             # SSE client & UI logic
│   └── style.css          # Styling
└── mcp_server/            # (Planned) MCP server for banking tools
```

## Tech Stack

| Component | Technology |
|---|---|
| Agent Orchestration | LangGraph (supervisor pattern) |
| LLM Framework | LangChain + LangChain-Ollama |
| Local Models | Ollama (deepseek-r1:8b, llama3.1:8b) |
| Banking API | SwedbankJson (PHP, unofficial) |
| Bank Authentication | Mobile BankID / Security Token |
| Web Search | DuckDuckGo (ddgs) |
| Web Server | Flask |
| Real-time Streaming | Server-Sent Events (SSE) |
| Frontend | Vanilla JavaScript + marked.js |
| Package Manager | Poetry (Python), Composer (PHP) |

## Roadmap

- [x] PHP microservice bridging Swedbank API to Python agent tools
- [x] BankID authentication flow in the web UI
- [x] Supervisor-driven multi-agent architecture
- [x] Transaction categorization and spending analysis
- [x] Time-period-aware transaction fetching
- [ ] Budget tracking and savings goal recommendations
- [ ] Historical spending trend visualization
- [ ] MCP server for banking tools

## License

This project is for educational and personal use.
