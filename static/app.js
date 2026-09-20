// Algorithmic Trading Platform Client Logic
let SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"];
let currentSymbol = "AAPL";
let chartInstance = null;
const priceSeriesData = {};
SYMBOLS.forEach(sym => { priceSeriesData[sym] = []; });

// Initialize Chart.js
function initChart() {
  const ctx = document.getElementById("marketChart").getContext("2d");
  chartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: currentSymbol,
        data: [],
        borderColor: "#3b82f6",
        backgroundColor: "rgba(59, 130, 246, 0.08)",
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: "#3b82f6",
        fill: true,
        tension: 0.25,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: 'index',
          intersect: false,
          backgroundColor: '#1e293b',
          titleColor: '#94a3b8',
          bodyColor: '#f1f5f9',
          borderColor: '#334155',
          borderWidth: 1,
        }
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: { color: "#64748b", font: { family: 'JetBrains Mono', size: 10 }, maxTicksLimit: 8 }
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: {
            color: "#64748b",
            font: { family: 'JetBrains Mono', size: 10 },
            callback: value => `$${value.toFixed(2)}`
          }
        }
      }
    }
  });
}

async function fetchMarketDataSymbols() {
  try {
    const res = await fetch("/api/market-data/symbols");
    if (res.ok) {
      const data = await res.json();
      if (data.symbols && Array.isArray(data.symbols) && data.symbols.length > 0) {
        SYMBOLS = data.symbols;
        SYMBOLS.forEach(sym => {
          if (!priceSeriesData[sym]) priceSeriesData[sym] = [];
        });
        if (!SYMBOLS.includes(currentSymbol)) {
          currentSymbol = SYMBOLS[0];
        }
        renderSymbolSelectors();
        updateChartForSymbol();
      }
    }
  } catch (err) {
    console.debug("Could not fetch market data symbols:", err);
  }
}

function renderSymbolSelectors() {
  const container = document.getElementById("symbol-selectors");
  if (!container) return;
  container.innerHTML = "";
  SYMBOLS.forEach(sym => {
    const btn = document.createElement("button");
    btn.className = `symbol-pill ${sym === currentSymbol ? "active" : ""}`;
    btn.textContent = sym;
    btn.onclick = () => switchSymbol(sym);
    container.appendChild(btn);
  });
}

function switchSymbol(sym) {
  currentSymbol = sym;
  renderSymbolSelectors();
  updateChartForSymbol();
}

function updateChartForSymbol() {
  if (!chartInstance) return;
  const data = priceSeriesData[currentSymbol] || [];
  chartInstance.data.datasets[0].label = currentSymbol;
  chartInstance.data.labels = data.map(d => d.time);
  chartInstance.data.datasets[0].data = data.map(d => d.price);

  // Update selected symbol display
  const lastTick = data[data.length - 1];
  const priceDisplay = document.getElementById("selected-symbol-price");
  const volDisplay = document.getElementById("selected-symbol-vol");
  if (lastTick) {
    priceDisplay.textContent = `${currentSymbol}: $${lastTick.price.toFixed(2)}`;
    if (volDisplay) {
      if (lastTick.volume !== null && lastTick.volume !== undefined) {
        volDisplay.textContent = `| Vol: ${Number(lastTick.volume).toLocaleString()}`;
      } else {
        volDisplay.textContent = "";
      }
    }
  }
  chartInstance.update("none");
}

function updateMarketDataStatus(status) {
  if (!status) return;

  const badge = document.getElementById("market-data-badge");
  const dot = document.getElementById("market-data-dot");
  const text = document.getElementById("market-data-text");

  if (badge) {
    const mode = (status.mode || "").toLowerCase();
    if (mode === "live") {
      badge.className = "badge badge-live";
      badge.textContent = "LIVE — TWELVE DATA";
    } else if (mode === "replay") {
      badge.className = "badge badge-replay";
      badge.textContent = "HISTORICAL REPLAY";
    } else {
      badge.className = "badge badge-sim";
      badge.textContent = "SIMULATION";
    }
  }

  if (dot) {
    const conn = (status.connection_status || "").toLowerCase();
    dot.className = "status-dot";
    if (conn === "connected") {
      dot.classList.add("connected");
    } else if (conn === "reconnecting") {
      dot.classList.add("reconnecting");
    } else {
      dot.classList.add("disconnected");
    }
  }

  if (text) {
    const conn = (status.connection_status || "DISCONNECTED").toUpperCase();
    text.textContent = conn;
  }

  // Update Telemetry Bar
  const provEl = document.getElementById("telemetry-provider");
  const modeEl = document.getElementById("telemetry-mode");
  const queueEl = document.getElementById("telemetry-queue");
  const procEl = document.getElementById("telemetry-processed");
  const dropEl = document.getElementById("telemetry-dropped");

  if (provEl) provEl.textContent = status.provider || "--";
  if (modeEl) modeEl.textContent = (status.mode || "--").toUpperCase();
  if (queueEl) queueEl.textContent = `${status.queue_size ?? 0} / ${status.max_queue_size ?? 10000}`;
  if (procEl) procEl.textContent = Number(status.ticks_processed ?? 0).toLocaleString();
  if (dropEl) dropEl.textContent = Number(status.dropped_ticks ?? 0).toLocaleString();
}

async function fetchMarketDataStatus() {
  try {
    const res = await fetch("/api/market-data/status");
    if (res.ok) {
      const data = await res.json();
      if (data.market_data) {
        updateMarketDataStatus(data.market_data);
      }
    }
  } catch (err) {
    console.debug("Could not fetch market data status:", err);
  }
}

// WebSocket Connection
let ws = null;
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  const dot = document.getElementById("connection-dot");
  const text = document.getElementById("connection-text");

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    dot.classList.add("connected");
    text.textContent = "ENGINE LIVE";
  };

  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "market_update" || payload.type === "initial_state") {
        if (payload.portfolio) updatePortfolioMetrics(payload.portfolio);
        if (payload.ticks) handleIncomingTicks(payload.ticks);
        if (payload.signals) updateSignalsTable(payload.signals);
        if (payload.orders) updateOrdersTable(payload.orders);
        if (payload.market_data) updateMarketDataStatus(payload.market_data);
      }
    } catch (err) {
      console.error("Error parsing WS message", err);
    }
  };

  ws.onclose = () => {
    dot.classList.remove("connected");
    text.textContent = "RECONNECTING...";
    setTimeout(connectWebSocket, 2000);
  };

  ws.onerror = (err) => {
    console.warn("WebSocket error:", err);
    ws.close();
  };
}

function handleIncomingTicks(ticks) {
  const now = new Date().toLocaleTimeString();
  Object.keys(ticks).forEach(sym => {
    const tick = ticks[sym];
    if (!priceSeriesData[sym]) priceSeriesData[sym] = [];
    priceSeriesData[sym].push({ time: now, price: tick.price, volume: tick.volume });
    if (priceSeriesData[sym].length > 40) {
      priceSeriesData[sym].shift();
    }
  });
  updateChartForSymbol();
}

function updatePortfolioMetrics(portfolio) {
  document.getElementById("metric-equity").textContent = `$${portfolio.total_equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  document.getElementById("metric-cash").textContent = `$${portfolio.cash_balance.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

  const unrealizedEl = document.getElementById("metric-unrealized");
  const un = portfolio.unrealized_pnl || 0.0;
  unrealizedEl.textContent = `${un >= 0 ? "+" : ""}$${un.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  unrealizedEl.className = `metric-value mono ${un >= 0 ? "text-green" : "text-red"}`;

  const realizedEl = document.getElementById("metric-realized");
  const re = portfolio.realized_pnl || 0.0;
  realizedEl.textContent = `${re >= 0 ? "+" : ""}$${re.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  realizedEl.className = `metric-value mono ${re >= 0 ? "text-green" : "text-red"}`;

  updatePositionsTable(portfolio.positions || {});
}

function updatePositionsTable(positions) {
  const tbody = document.getElementById("positions-table-body");
  const keys = Object.keys(positions).filter(k => positions[k].quantity > 0);

  if (keys.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-muted" style="text-align:center;">No open positions held.</td></tr>`;
    return;
  }

  tbody.innerHTML = keys.map(sym => {
    const pos = positions[sym];
    const pnlClass = pos.unrealized_pnl >= 0 ? "text-green" : "text-red";
    const pnlSign = pos.unrealized_pnl >= 0 ? "+" : "";
    return `
      <tr>
        <td class="mono" style="font-weight:700;">${pos.symbol}</td>
        <td class="mono">${pos.quantity}</td>
        <td class="mono">$${pos.avg_entry_price.toFixed(2)}</td>
        <td class="mono">$${pos.current_price.toFixed(2)}</td>
        <td class="mono">$${pos.market_value.toFixed(2)}</td>
        <td class="mono ${pnlClass}">${pnlSign}$${pos.unrealized_pnl.toFixed(2)}</td>
      </tr>
    `;
  }).join("");
}

function updateSignalsTable(signals) {
  const tbody = document.getElementById("signals-table-body");
  if (!signals || signals.length === 0) return;

  tbody.innerHTML = signals.slice(0, 15).map(sig => {
    const timeStr = sig.timestamp ? new Date(sig.timestamp).toLocaleTimeString() : "--";
    const badgeClass = sig.signal_type === "BUY" ? "badge-buy" : "badge-sell";
    return `
      <tr>
        <td class="mono text-muted">${timeStr}</td>
        <td class="mono" style="font-weight:700;">${sig.symbol}</td>
        <td><span class="badge ${badgeClass}">${sig.signal_type}</span></td>
        <td class="mono">$${sig.price.toFixed(2)}</td>
        <td style="color:#94a3b8; font-size: 0.72rem;">${sig.strategy_name}</td>
        <td><button class="btn-why" onclick="explainSignal(${sig.id}, '${sig.symbol}', '${sig.signal_type}')">Why?</button></td>
      </tr>
    `;
  }).join("");
}

function updateOrdersTable(orders) {
  const tbody = document.getElementById("orders-table-body");
  if (!tbody || !orders || orders.length === 0) return;

  tbody.innerHTML = orders.map(ord => {
    const timeStr = ord.timestamp ? new Date(ord.timestamp).toLocaleTimeString() : "--";
    const statusColor = ord.status === "FILLED" ? "text-green" : "text-red";
    const sideColor = ord.side === "BUY" ? "text-green" : "text-red";
    const qty = Number(ord.quantity).toFixed(0);
    const price = Number(ord.price).toFixed(2);
    return `
      <tr>
        <td class="mono text-muted">${timeStr}</td>
        <td class="mono" style="font-weight:700;">${ord.symbol}</td>
        <td class="mono ${sideColor}" style="font-weight:700;">${ord.side}</td>
        <td class="mono">${qty}</td>
        <td class="mono">$${price}</td>
        <td class="mono ${statusColor}">${ord.status}</td>
      </tr>
    `;
  }).join("");
}

async function fetchRecentOrders() {
  try {
    const res = await fetch("/api/trades?limit=15");
    if (res.ok) {
      const orders = await res.json();
      updateOrdersTable(orders);
    }
  } catch (e) {
    console.error("Error fetching trades:", e);
  }
}

async function fetchRecentSignals() {
  try {
    const res = await fetch("/api/signals?limit=15");
    if (res.ok) {
      const signals = await res.json();
      updateSignalsTable(signals);
    }
  } catch (e) {
    console.error("Error fetching signals:", e);
  }
}

// AI Signal Explanation
async function explainSignal(signalId, symbol, action) {
  const modal = document.getElementById("explain-modal");
  const modalTitle = document.getElementById("modal-title");
  const modalBody = document.getElementById("modal-body");

  modalTitle.textContent = `Why did Signal #${signalId} (${action} ${symbol}) fire?`;
  modalBody.innerHTML = `<span class="mono text-muted">Consulting Gemini quantitative assistant...</span>`;
  modal.classList.add("show");

  try {
    const res = await fetch(`/api/assistant/explain/${signalId}`);
    const data = await res.json();
    modalBody.textContent = data.explanation;
  } catch (err) {
    modalBody.textContent = "Failed to fetch explanation from AI assistant.";
  }
}

function closeModal() {
  document.getElementById("explain-modal").classList.remove("show");
}

// Market Data Configuration Modal
function openMarketDataModal() {
  const modal = document.getElementById("market-data-modal");
  if (!modal) return;
  modal.classList.add("show");
  document.getElementById("market-data-status-msg").textContent = "";

  // Pre-fill existing symbols and mode
  fetch("/api/market-data/status")
    .then(r => r.json())
    .then(data => {
      if (data.market_data) {
        const mode = data.market_data.mode || "simulation";
        if (mode === "live") {
          document.getElementById("md-mode-live").checked = true;
        } else {
          document.getElementById("md-mode-sim").checked = true;
        }
        toggleMarketDataInputs();
      }
    })
    .catch(() => {});

  fetch("/api/market-data/symbols")
    .then(r => r.json())
    .then(data => {
      if (data.symbols && data.symbols.length > 0) {
        document.getElementById("market-data-symbols-input").value = data.symbols.join(", ");
      }
    })
    .catch(() => {});
}

function closeMarketDataModal() {
  const modal = document.getElementById("market-data-modal");
  if (modal) modal.classList.remove("show");
}

function toggleMarketDataInputs() {
  const isLive = document.getElementById("md-mode-live").checked;
  const keyGroup = document.getElementById("twelve-data-key-group");
  if (keyGroup) {
    keyGroup.style.display = isLive ? "block" : "none";
  }
}

async function saveMarketDataConfig() {
  const isLive = document.getElementById("md-mode-live").checked;
  const mode = isLive ? "live" : "simulation";
  const keyInput = document.getElementById("twelve-data-key-input");
  const apiKey = keyInput ? keyInput.value.trim() : "";
  const symsInput = document.getElementById("market-data-symbols-input");
  const symbols = symsInput ? symsInput.value.trim() : "";
  const statusMsg = document.getElementById("market-data-status-msg");

  if (isLive && !apiKey) {
    statusMsg.textContent = "Please enter your Twelve Data API key to activate LIVE mode.";
    statusMsg.style.color = "#ef4444";
    return;
  }

  statusMsg.textContent = "Switching market data provider...";
  statusMsg.style.color = "#94a3b8";

  try {
    const payload = {
      mode: mode,
      api_key: apiKey || null,
      symbols: symbols || null,
    };
    const res = await fetch("/api/market-data/set-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok && data.success) {
      statusMsg.textContent = data.message;
      statusMsg.style.color = "#10b981";
      if (data.status) updateMarketDataStatus(data.status);
      if (data.symbols) {
        SYMBOLS = data.symbols;
        renderSymbolSelectors();
      }
      setTimeout(() => closeMarketDataModal(), 1500);
    } else {
      statusMsg.textContent = data.detail || data.message || "Failed to switch market data mode.";
      statusMsg.style.color = "#ef4444";
    }
  } catch (err) {
    statusMsg.textContent = "Failed connecting to server.";
    statusMsg.style.color = "#ef4444";
  }
}

// ChartBot Modal & Information
function openBotInfoModal() {
  const modal = document.getElementById("bot-info-modal") || document.getElementById("key-modal");
  if (modal) modal.classList.add("show");
}

function closeBotInfoModal() {
  const modal = document.getElementById("bot-info-modal") || document.getElementById("key-modal");
  if (modal) modal.classList.remove("show");
}

// Backward-compatibility aliases
function openKeyModal() { openBotInfoModal(); }
function closeKeyModal() { closeBotInfoModal(); }
async function saveApiKey() { closeBotInfoModal(); }

async function checkAssistantStatus() {
  try {
    const res = await fetch("/api/assistant/status");
    const data = await res.json();
    updateBotStatusPill(data);
  } catch (e) {
    console.debug("Could not check Bot status:", e);
  }
}

function updateBotStatusPill(data) {
  const dot = document.getElementById("bot-status-dot") || document.getElementById("ai-status-dot");
  const text = document.getElementById("bot-status-text") || document.getElementById("ai-status-text");
  if (!dot || !text) return;

  dot.classList.add("connected");
  text.textContent = (data && data.bot_name) ? data.bot_name.toUpperCase() : "CHART BOT";
}

function formatBotMessage(text) {
  if (!text) return "";
  let safe = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  // Replace **bold** with <strong>bold</strong>
  safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // Replace *italic* with <em>italic</em>
  safe = safe.replace(/\*(.*?)\*/g, '<em>$1</em>');
  // Replace newlines with <br>
  safe = safe.replace(/\n/g, '<br>');
  return safe;
}

// Chat Assistant
async function sendChatMessage() {
  const input = document.getElementById("chat-input");
  const question = input.value.trim();
  if (!question) return;

  input.value = "";
  appendChatBubble(question, "user");

  // Show thinking indicator
  const thinkingId = appendChatBubble("ChartBot is analyzing live market & chart data...", "assistant mono text-muted");

  try {
    const res = await fetch("/api/assistant/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    updateChatBubble(thinkingId, data.answer, "assistant");
  } catch (err) {
    updateChatBubble(thinkingId, "Failed to communicate with ChartBot.", "assistant");
  }
}

function sendQuickPrompt(promptText) {
  document.getElementById("chat-input").value = promptText;
  sendChatMessage();
}

function appendChatBubble(text, className) {
  const container = document.getElementById("chat-messages");
  const bubble = document.createElement("div");
  const id = "bubble-" + Date.now() + Math.random().toString(36).substring(2, 6);
  bubble.id = id;
  bubble.className = `chat-bubble ${className}`;
  if (className.includes("assistant") && !className.includes("mono")) {
    bubble.innerHTML = formatBotMessage(text);
  } else {
    bubble.textContent = text;
  }
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
  return id;
}

function updateChatBubble(id, text, className) {
  const bubble = document.getElementById(id);
  if (bubble) {
    bubble.className = `chat-bubble ${className}`;
    if (className.includes("assistant")) {
      bubble.innerHTML = formatBotMessage(text);
    } else {
      bubble.textContent = text;
    }
    const container = document.getElementById("chat-messages");
    container.scrollTop = container.scrollHeight;
  }
}

// Clock Display
function startClock() {
  setInterval(() => {
    document.getElementById("clock-display").textContent = new Date().toUTCString().replace("GMT", "UTC");
  }, 1000);
}

// Initial Boot
window.addEventListener("DOMContentLoaded", () => {
  renderSymbolSelectors();
  initChart();
  fetchMarketDataSymbols();
  fetchMarketDataStatus();
  fetchRecentSignals();
  fetchRecentOrders();
  connectWebSocket();
  startClock();
  setInterval(fetchRecentOrders, 3000);
  setInterval(fetchRecentSignals, 3000);
  setInterval(fetchMarketDataStatus, 4000);
  checkAssistantStatus();
});
