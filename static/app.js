/* SSE client — routes events to DOM updates + dashboard rendering. */

(function () {
  "use strict";

  const form = document.getElementById("run-form");
  const queryInput = document.getElementById("query-input");
  const runBtn = document.getElementById("run-btn");
  const statusBar = document.getElementById("status-bar");
  const timeline = document.getElementById("timeline");
  const detailContent = document.getElementById("detail-content");
  const reportContent = document.getElementById("report-content");

  // Auth elements
  const authIndicator = document.getElementById("auth-indicator");
  const authStatusText = document.getElementById("auth-status-text");
  const bankidLoginBtn = document.getElementById("bankid-login-btn");
  const signOutBtn = document.getElementById("sign-out-btn");
  const bankidFlow = document.getElementById("bankid-flow");
  const bankidQr = document.getElementById("bankid-qr");
  const bankidMsg = document.getElementById("bankid-msg");
  const authGateMsg = document.getElementById("auth-gate-msg");

  // Dashboard elements
  const dashboardSection = document.getElementById("dashboard");
  const dashboardLoading = document.getElementById("dashboard-loading");
  const dashboardError = document.getElementById("dashboard-error");
  const accountsRow = document.getElementById("accounts-row");
  const recentTxBody = document.getElementById("recent-tx-body");
  const spendingChartTitle = document.getElementById("spending-chart-title");
  const spendingTotal = document.getElementById("spending-total");
  const spendingLegend = document.getElementById("spending-legend");
  const dashboardRefreshBtn = document.getElementById("dashboard-refresh-btn");

  let nodeEvents = {};
  let selectedNode = null;
  let qrInterval = null;
  let verifyInterval = null;
  let spendingChart = null;

  // Chart.js colour palette
  const CHART_COLORS = [
    "#4CAF50", "#FF9800", "#2196F3", "#9C27B0",
    "#00BCD4", "#F44336", "#607D8B", "#FF5722",
    "#8BC34A", "#FFC107",
  ];

  /* ================================================================
     Auth
  ================================================================ */

  function setAuthUI(authed, message) {
    if (authed) {
      authIndicator.className = "auth-authed";
      authStatusText.textContent = message || "Authenticated";
      bankidLoginBtn.style.display = "none";
      signOutBtn.style.display = "";
      bankidFlow.style.display = "none";
      queryInput.disabled = false;
      runBtn.disabled = false;
      authGateMsg.style.display = "none";
      loadDashboard();
    } else {
      authIndicator.className = "auth-not-authed";
      authStatusText.textContent = message || "Not authenticated";
      bankidLoginBtn.style.display = "";
      signOutBtn.style.display = "none";
      bankidFlow.style.display = "none";
      queryInput.disabled = true;
      runBtn.disabled = true;
      authGateMsg.style.display = "";
      hideDashboard();
    }
    stopAuthPolling();
  }

  function stopAuthPolling() {
    if (qrInterval)  { clearInterval(qrInterval);  qrInterval  = null; }
    if (verifyInterval) { clearInterval(verifyInterval); verifyInterval = null; }
  }

  function checkAuthStatus() {
    fetch("/api/auth/status")
      .then(function (r) { return r.json(); })
      .then(function (resp) {
        if (resp.ok && resp.data && resp.data.authed) {
          setAuthUI(true, "Authenticated (" + resp.data.appType + ")");
        } else {
          setAuthUI(false);
        }
      })
      .catch(function () {
        setAuthUI(false, "Bank bridge unavailable");
      });
  }

  function startBankIdAuth() {
    bankidLoginBtn.disabled = true;
    bankidMsg.textContent = "Initiating BankID...";
    bankidFlow.style.display = "";
    authIndicator.className = "auth-pending";
    authStatusText.textContent = "Waiting for BankID...";

    fetch("/api/auth/bankid/init", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sameDevice: false }),
    })
      .then(function (r) { return r.json(); })
      .then(function (resp) {
        if (!resp.ok) {
          bankidMsg.textContent = "Error: " + (resp.error || "Init failed");
          bankidLoginBtn.disabled = false;
          return;
        }
        bankidMsg.textContent = "Scan the QR code with your BankID app...";
        pollQrCode();
        pollVerify();
      })
      .catch(function (err) {
        bankidMsg.textContent = "Failed to start BankID: " + err;
        bankidLoginBtn.disabled = false;
      });
  }

  function pollQrCode() {
    function fetchQr() {
      fetch("/api/auth/bankid/qr")
        .then(function (r) { return r.json(); })
        .then(function (resp) {
          if (resp.ok && resp.data && resp.data.qr_image) {
            var img = resp.data.qr_image;
            if (img.indexOf("data:") !== 0) {
              img = "data:image/png;base64," + img;
            }
            bankidQr.src = img;
          }
        })
        .catch(function () {});
    }
    fetchQr();
    qrInterval = setInterval(fetchQr, 1500);
  }

  function pollVerify() {
    verifyInterval = setInterval(function () {
      fetch("/api/auth/bankid/verify")
        .then(function (r) { return r.json(); })
        .then(function (resp) {
          if (resp.ok && resp.data && resp.data.verified) {
            stopAuthPolling();
            bankidMsg.textContent = "Verified! Logging in...";
            completeBankIdLogin();
          }
        })
        .catch(function () {});
    }, 2000);
  }

  function completeBankIdLogin() {
    fetch("/api/auth/bankid/login", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (resp) {
        if (resp.ok && resp.data && resp.data.loggedIn) {
          setAuthUI(true, "Authenticated via BankID");
        } else {
          bankidMsg.textContent = "Login failed: " + (resp.error || "unknown error");
          bankidLoginBtn.disabled = false;
        }
      })
      .catch(function (err) {
        bankidMsg.textContent = "Login error: " + err;
        bankidLoginBtn.disabled = false;
      });
  }

  function signOut() {
    signOutBtn.disabled = true;
    fetch("/api/auth/terminate", { method: "POST" })
      .then(function () {
        setAuthUI(false, "Signed out");
        signOutBtn.disabled = false;
      })
      .catch(function () {
        setAuthUI(false, "Signed out (bridge error)");
        signOutBtn.disabled = false;
      });
  }

  bankidLoginBtn.addEventListener("click", startBankIdAuth);
  signOutBtn.addEventListener("click", signOut);
  if (dashboardRefreshBtn) dashboardRefreshBtn.addEventListener("click", loadDashboard);
  checkAuthStatus();

  /* ================================================================
     Dashboard
  ================================================================ */

  function hideDashboard() {
    dashboardSection.style.display = "none";
    if (spendingChart) { spendingChart.destroy(); spendingChart = null; }
  }

  function loadDashboard() {
    dashboardSection.style.display = "";
    dashboardLoading.style.display = "";
    dashboardError.style.display = "none";
    accountsRow.innerHTML = "";
    recentTxBody.innerHTML = '<tr><td colspan="3" class="placeholder">Loading...</td></tr>';
    spendingTotal.textContent = "";
    spendingLegend.innerHTML = "";
    if (spendingChart) { spendingChart.destroy(); spendingChart = null; }

    Promise.all([
      fetch("/api/dashboard").then(function (r) { return r.json(); }),
      fetch("/api/spending/monthly").then(function (r) { return r.json(); }),
    ])
      .then(function (results) {
        var dashResp = results[0];
        var spendResp = results[1];
        dashboardLoading.style.display = "none";

        if (!dashResp.ok) {
          showDashboardError(dashResp.error || "Failed to load account data.");
          return;
        }

        renderAccounts(dashResp.data.accounts);
        renderRecentTransactions(dashResp.data.accounts);

        if (spendResp.ok && spendResp.data) {
          renderSpendingChart(spendResp.data);
        }
      })
      .catch(function (err) {
        dashboardLoading.style.display = "none";
        showDashboardError("Could not reach the bank bridge: " + err);
      });
  }

  function showDashboardError(msg) {
    dashboardError.style.display = "";
    dashboardError.querySelector(".dashboard-error-msg").textContent = msg;
  }

  function renderAccounts(accounts) {
    accountsRow.innerHTML = "";
    if (!accounts || accounts.length === 0) {
      accountsRow.innerHTML = '<p class="placeholder">No accounts found.</p>';
      return;
    }
    accounts.forEach(function (acct) {
      var balance = parseFloat(acct.balance) || 0;
      var isNegative = balance < 0;
      var card = document.createElement("div");
      card.className = "account-card";
      card.innerHTML =
        '<div class="account-name">' + escapeHtml(acct.name) + '</div>' +
        '<div class="account-type">' + escapeHtml(acct.accountType || "") + '</div>' +
        '<div class="account-balance' + (isNegative ? " negative" : "") + '">' +
          formatAmount(balance) + " " + escapeHtml(acct.currency || "SEK") +
        '</div>';
      accountsRow.appendChild(card);
    });
  }

  function renderRecentTransactions(accounts) {
    // Collect and merge all recent transactions, sort by date desc, take 10
    var all = [];
    (accounts || []).forEach(function (acct) {
      (acct.recent_transactions || []).forEach(function (tx) {
        all.push(tx);
      });
    });
    all.sort(function (a, b) {
      return (b.date || "").localeCompare(a.date || "");
    });
    var top = all.slice(0, 10);

    if (top.length === 0) {
      recentTxBody.innerHTML = '<tr><td colspan="3" class="placeholder">No recent transactions.</td></tr>';
      return;
    }
    recentTxBody.innerHTML = "";
    top.forEach(function (tx) {
      var amount = parseFloat(tx.amount) || 0;
      var row = document.createElement("tr");
      row.innerHTML =
        '<td class="tx-date">' + escapeHtml(tx.date || "") + '</td>' +
        '<td class="tx-desc">' + escapeHtml(tx.description || "") + '</td>' +
        '<td class="tx-amount' + (amount < 0 ? " negative" : " positive") + '">' +
          formatAmount(amount) + " " + escapeHtml(tx.currency || "SEK") +
        '</td>';
      recentTxBody.appendChild(row);
    });
  }

  function renderSpendingChart(data) {
    var cats = (data.categories || []).filter(function (c) { return c.amount > 0; });

    // Period label
    spendingChartTitle.textContent = "Spending — " + (data.period || "this month");
    spendingTotal.textContent = "Total: " + formatAmount(data.total_spent || 0) + " SEK";

    if (cats.length === 0) {
      document.getElementById("chart-wrapper").innerHTML =
        '<p class="placeholder" style="padding:24px;">No spending data for this period.</p>';
      return;
    }

    var ctx = document.getElementById("spending-chart").getContext("2d");
    spendingChart = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: cats.map(function (c) { return c.name; }),
        datasets: [{
          data: cats.map(function (c) { return c.amount; }),
          backgroundColor: cats.map(function (_, i) { return CHART_COLORS[i % CHART_COLORS.length]; }),
          borderWidth: 2,
          borderColor: "#fff",
        }],
      },
      options: {
        cutout: "60%",
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return ctx.label + ": " + formatAmount(ctx.parsed) + " SEK";
              },
            },
          },
        },
      },
    });

    // Custom legend
    spendingLegend.innerHTML = "";
    cats.forEach(function (cat, i) {
      var pct = data.total_spent > 0 ? ((cat.amount / data.total_spent) * 100).toFixed(1) : "0";
      var row = document.createElement("div");
      row.className = "legend-row";
      row.innerHTML =
        '<span class="legend-dot" style="background:' + CHART_COLORS[i % CHART_COLORS.length] + '"></span>' +
        '<span class="legend-label">' + escapeHtml(cat.name) + '</span>' +
        '<span class="legend-pct">' + pct + '%</span>' +
        '<span class="legend-amount">' + formatAmount(cat.amount) + ' SEK</span>';
      spendingLegend.appendChild(row);
    });
  }

  /* ================================================================
     Helpers
  ================================================================ */

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }

  function formatAmount(val) {
    return parseFloat(val).toLocaleString("sv-SE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function setStatus(text) {
    statusBar.textContent = text;
  }

  function setRunning(on) {
    runBtn.disabled = on;
    queryInput.disabled = on;
  }

  /* ================================================================
     Timeline
  ================================================================ */

  function getOrCreateNodeEntry(nodeName) {
    var el = document.getElementById("tn-" + nodeName);
    if (!el) {
      el = document.createElement("div");
      el.id = "tn-" + nodeName;
      el.className = "timeline-node";
      el.innerHTML =
        '<div class="node-name">' + escapeHtml(nodeName) + "</div>" +
        '<div class="node-meta"></div>';
      el.addEventListener("click", function () { selectNode(nodeName); });
      timeline.appendChild(el);
    }
    return el;
  }

  function addToolChild(parentName, toolName) {
    var parentEl = document.getElementById("tn-" + parentName);
    if (!parentEl) return;
    var child = document.createElement("div");
    child.className = "timeline-tool";
    child.textContent = toolName;
    child.addEventListener("click", function (e) {
      e.stopPropagation();
      selectNode(parentName);
    });
    parentEl.after(child);
  }

  function selectNode(name) {
    selectedNode = name;
    document.querySelectorAll(".timeline-node").forEach(function (el) {
      el.classList.toggle("selected", el.id === "tn-" + name);
    });
    renderDetail(name);
  }

  /* ================================================================
     Detail panel
  ================================================================ */

  function renderDetail(name) {
    var events = nodeEvents[name];
    if (!events || events.length === 0) {
      detailContent.innerHTML = '<p class="placeholder">No data yet.</p>';
      return;
    }
    var html = "";
    events.forEach(function (evt) {
      html += '<div class="detail-section">';
      html += "<h3>" + escapeHtml(evt.type) + "</h3>";
      html += '<pre class="raw-output">' + escapeHtml(JSON.stringify(evt.data, null, 2)) + "</pre>";
      html += "</div>";
    });
    detailContent.innerHTML = html;
  }

  /* ================================================================
     Event routing (SSE)
  ================================================================ */

  function handleEvent(evt) {
    var type = evt.type;
    var node = evt.node;
    var data = evt.data;

    if (!nodeEvents[node]) nodeEvents[node] = [];
    if (type !== "done") nodeEvents[node].push(evt);

    switch (type) {
      case "node_start": {
        var el = getOrCreateNodeEntry(node);
        el.classList.add("running");
        el.classList.remove("done", "error");
        el.querySelector(".node-meta").textContent =
          "iteration " + (data.iteration || 0) + " — running...";
        setStatus("Running: " + node + "...");
        break;
      }
      case "node_end": {
        var el = getOrCreateNodeEntry(node);
        el.classList.remove("running");
        el.classList.add("done");
        var meta = Object.keys(data).map(function (k) { return k + "=" + data[k]; }).join(", ");
        el.querySelector(".node-meta").textContent = meta || "done";
        break;
      }
      case "tool_result": {
        addToolChild(node, data.tool || "tool");
        break;
      }
      case "report": {
        var markdown = data.report || "";
        markdown = markdown.replace(/^```(?:markdown)?\s*\n?/i, "").replace(/\n?```\s*$/i, "");
        if (typeof marked !== "undefined" && marked.parse) {
          reportContent.innerHTML = marked.parse(markdown);
        } else {
          reportContent.innerHTML = '<pre class="raw-output">' + escapeHtml(markdown) + "</pre>";
        }
        break;
      }
      case "error": {
        var el = getOrCreateNodeEntry(node);
        el.classList.remove("running");
        el.classList.add("error");
        el.querySelector(".node-meta").textContent = "ERROR: " + (data.error || "unknown");
        setStatus("Error in " + node + ": " + (data.error || ""));
        break;
      }
      case "done": {
        setStatus("Run complete.");
        setRunning(false);
        return;
      }
    }

    if (selectedNode === node) renderDetail(node);
  }

  function startStream() {
    var source = new EventSource("/stream");
    source.onmessage = function (msg) {
      try {
        var evt = JSON.parse(msg.data);
        handleEvent(evt);
        if (evt.type === "done") source.close();
      } catch (e) {
        console.error("SSE parse error:", e, msg.data);
      }
    };
    source.onerror = function () {
      source.close();
      setStatus("Stream connection lost.");
      setRunning(false);
    };
  }

  /* ================================================================
     Form submit
  ================================================================ */

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var query = queryInput.value.trim();
    if (!query) return;

    nodeEvents = {};
    selectedNode = null;
    timeline.innerHTML = "";
    detailContent.innerHTML = '<p class="placeholder">Waiting for events...</p>';
    reportContent.innerHTML = '<p class="placeholder">Report will appear here after the run completes.</p>';

    setRunning(true);
    setStatus("Starting...");

    fetch("/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query }),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.error) {
          setStatus("Error: " + data.error);
          setRunning(false);
        } else {
          setStatus("Run started. Streaming events...");
          startStream();
        }
      })
      .catch(function (err) {
        setStatus("Failed to start run: " + err);
        setRunning(false);
      });
  });
})();
