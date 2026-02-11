/* SSE client — routes events to DOM updates. */

(function () {
  "use strict";

  const form = document.getElementById("run-form");
  const queryInput = document.getElementById("query-input");
  const runBtn = document.getElementById("run-btn");
  const statusBar = document.getElementById("status-bar");
  const timeline = document.getElementById("timeline");
  const detailContent = document.getElementById("detail-content");
  const reportContent = document.getElementById("report-content");

  // Stores all events keyed by node name for the detail panel
  let nodeEvents = {};   // { nodeName: [event, ...] }
  let selectedNode = null;

  /* ---- Helpers ---- */

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function setStatus(text) {
    statusBar.textContent = text;
  }

  function setRunning(on) {
    runBtn.disabled = on;
    queryInput.disabled = on;
  }

  /* ---- Timeline ---- */

  function getOrCreateNodeEntry(nodeName) {
    let el = document.getElementById("tn-" + nodeName);
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
    const parentEl = document.getElementById("tn-" + parentName);
    if (!parentEl) return;
    const child = document.createElement("div");
    child.className = "timeline-tool";
    child.textContent = toolName;
    // Clicking a tool child also selects the parent node
    child.addEventListener("click", function (e) {
      e.stopPropagation();
      selectNode(parentName);
    });
    parentEl.after(child);
  }

  function selectNode(name) {
    selectedNode = name;
    // Highlight
    document.querySelectorAll(".timeline-node").forEach(function (el) {
      el.classList.toggle("selected", el.id === "tn-" + name);
    });
    renderDetail(name);
  }

  /* ---- Detail panel ---- */

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

  /* ---- Event routing ---- */

  function handleEvent(evt) {
    var type = evt.type;
    var node = evt.node;
    var data = evt.data;

    // Accumulate events per node
    if (!nodeEvents[node]) nodeEvents[node] = [];
    if (type !== "done") {
      nodeEvents[node].push(evt);
    }

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

      case "llm_response":
        // Already stored in nodeEvents — refresh detail if selected
        break;

      case "report": {
        var markdown = data.report || "";
        // Strip markdown code fences if the LLM wrapped the entire report
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

    // Auto-refresh the detail panel if the selected node got a new event
    if (selectedNode === node) {
      renderDetail(node);
    }
  }

  /* ---- SSE ---- */

  function startStream() {
    var source = new EventSource("/stream");
    source.onmessage = function (msg) {
      try {
        var evt = JSON.parse(msg.data);
        handleEvent(evt);
        if (evt.type === "done") {
          source.close();
        }
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

  /* ---- Form submit ---- */

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var query = queryInput.value.trim();
    if (!query) return;

    // Reset UI
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
