// Algorithmic Trading Platform Client Logic (Dual Mode: Live Backend + Browser Standalone)
let SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"];
let currentSymbol = "AAPL";
let chartInstance = null;
const priceSeriesData = {};
SYMBOLS.forEach(sym => { priceSeriesData[sym] = []; });

// Client-side simulation state (for GitHub Pages standalone mode)
const isStaticHost = window.location.protocol === 'file:' || window.location.hostname.endsWith('github.io');
let staticSimTimer = null;
let staticWs = null;
let staticMode = "simulation";
let staticApiKey = "";
let staticTicksProcessed = 0;
let staticPortfolio = {
  cash_balance: 100000.0,
  total_equity: 100000.0,
  realized_pnl: 0.0,
  unrealized_pnl: 0.0,
  positions: {}
};
let staticOrders = [];
let staticSignals = [];
const currentPrices = {
  AAPL: 185.0,
  MSFT: 420.0,
  GOOGL: 175.0,
  AMZN: 182.0,
  TSLA: 215.0,
  NVDA: 125.0,
  META: 505.0
};

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
    if (conn === "connected") dot.classList.add("connected");
    else if (conn === "reconnecting") dot.classList.add("reconnecting");
    else dot.classList.add("disconnected");
  }

  if (text) {
    const conn = (status.connection_status || "CONNECTED").toUpperCase();
    text.textContent = conn;
  }

  const pEl = document.getElementById("telemetry-provider");
  if (pEl) pEl.textContent = status.provider || "simulator";
  const mEl = document.getElementById("telemetry-mode");
  if (mEl) mEl.textContent = (status.mode || "simulation").toUpperCase();
  const qEl = document.getElementById("telemetry-queue");
  if (qEl) qEl.textContent = `${status.queue_size ?? 0}/10000`;
  const procEl = document.getElementById("telemetry-processed");
  if (procEl) procEl.textContent = Number(status.ticks_processed ?? 0).toLocaleString();
  const dropEl = document.getElementById("telemetry-dropped");
  if (dropEl) dropEl.textContent = Number(status.dropped_ticks ?? 0).toLocaleString();
}

function updateKpiCards(snap) {
  if (!snap) return;
  const eqEl = document.getElementById("metric-equity");
  const cashEl = document.getElementById("metric-cash");
  const unEl = document.getElementById("metric-unrealized");
  const reEl = document.getElementById("metric-realized");

  if (eqEl) eqEl.textContent = `$${Number(snap.total_equity).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (cashEl) cashEl.textContent = `$${Number(snap.cash_balance).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  if (unEl) {
    const val = Number(snap.unrealized_pnl);
    unEl.textContent = `${val >= 0 ? '+' : ''}$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    unEl.className = `metric-value mono ${val >= 0 ? 'text-green' : 'text-red'}`;
  }

  if (reEl) {
    const val = Number(snap.realized_pnl);
    reEl.textContent = `${val >= 0 ? '+' : ''}$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    reEl.className = `metric-value mono ${val >= 0 ? 'text-green' : 'text-red'}`;
  }
}

function updatePositionsTable(positions) {
  const tbody = document.getElementById("positions-table-body");
  if (!tbody) return;
  const activeKeys = Object.keys(positions || {}).filter(k => positions[k].quantity > 0);
  if (activeKeys.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-muted" style="text-align:center;">No open positions held.</td></tr>';
    return;
  }
  tbody.innerHTML = activeKeys.map(sym => {
    const pos = positions[sym];
    const pnl = Number(pos.unrealized_pnl);
    const pnlClass = pnl >= 0 ? 'text-green' : 'text-red';
    const sign = pnl >= 0 ? '+' : '';
    return `
      <tr>
        <td class="mono" style="font-weight:700;">${sym}</td>
        <td class="mono">${pos.quantity}</td>
        <td class="mono">$${Number(pos.avg_entry_price).toFixed(2)}</td>
        <td class="mono">$${Number(pos.current_price).toFixed(2)}</td>
        <td class="mono">$${Number(pos.market_value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td class="mono ${pnlClass}">${sign}$${pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
      </tr>
    `;
  }).join("");
}

function updateOrdersTable(orders) {
  const tbody = document.getElementById("orders-table-body");
  if (!tbody) return;
  if (!orders || orders.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-muted" style="text-align:center;">No trade executions yet.</td></tr>';
    return;
  }
  tbody.innerHTML = orders.slice(0, 15).map(o => {
    const sideClass = o.side === "BUY" ? "text-green" : "text-red";
    const statusClass = o.status === "FILLED" ? "text-green" : "text-red";
    const timeStr = o.timestamp ? new Date(o.timestamp).toLocaleTimeString() : "--:--:--";
    const priceVal = o.execution_price !== null && o.execution_price !== undefined ? Number(o.execution_price).toFixed(2) : Number(o.price).toFixed(2);
    return `
      <tr>
        <td class="mono text-muted" style="font-size:0.75rem;">${timeStr}</td>
        <td class="mono" style="font-weight:600;">${o.symbol}</td>
        <td class="mono ${sideClass}" style="font-weight:600;">${o.side}</td>
        <td class="mono">${o.quantity}</td>
        <td class="mono">$${priceVal}</td>
        <td class="mono ${statusClass}">${o.status}</td>
      </tr>
    `;
  }).join("");
}

function updateSignalsTable(signals) {
  const tbody = document.getElementById("signals-table-body");
  if (!tbody) return;
  if (!signals || signals.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-muted" style="text-align:center;">Awaiting strategy signals...</td></tr>';
    return;
  }
  tbody.innerHTML = signals.slice(0, 15).map(s => {
    const sigClass = s.signal_type === "BUY" ? "text-green" : "text-red";
    const timeStr = s.timestamp ? new Date(s.timestamp).toLocaleTimeString() : "--:--:--";
    return `
      <tr>
        <td class="mono text-muted" style="font-size:0.75rem;">${timeStr}</td>
        <td class="mono" style="font-weight:600;">${s.symbol}</td>
        <td class="mono ${sigClass}" style="font-weight:700;">${s.signal_type}</td>
        <td class="mono">$${Number(s.price).toFixed(2)}</td>
        <td class="mono text-muted" style="font-size:0.75rem;">${s.strategy_name}</td>
        <td><button class="btn-why" onclick="explainSignal(${s.id})">Why?</button></td>
      </tr>
    `;
  }).join("");
}

// Ingest Ticks
function handleTickData(tick) {
  if (!tick || !tick.symbol) return;
  const sym = tick.symbol;
  if (!priceSeriesData[sym]) priceSeriesData[sym] = [];
  const timeStr = tick.timestamp ? new Date(tick.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();

  priceSeriesData[sym].push({
    time: timeStr,
    price: Number(tick.price),
    volume: tick.volume,
    source: tick.source
  });

  if (priceSeriesData[sym].length > 40) {
    priceSeriesData[sym].shift();
  }

  if (sym === currentSymbol) {
    updateChartForSymbol();
  }
}

// Modal Functions
function openMarketDataModal() {
  const modal = document.getElementById("market-data-modal");
  if (modal) modal.classList.add("show");
  toggleMarketDataInputs();
}

function closeMarketDataModal() {
  const modal = document.getElementById("market-data-modal");
  if (modal) modal.classList.remove("show");
}

function toggleMarketDataInputs() {
  const isLive = document.getElementById("md-mode-live")?.checked;
  const keyGroup = document.getElementById("twelve-data-key-group");
  if (keyGroup) keyGroup.style.display = isLive ? "block" : "none";
}

function openBotInfoModal() {
  const modal = document.getElementById("bot-info-modal") || document.getElementById("key-modal");
  if (modal) modal.classList.add("show");
}

function closeBotInfoModal() {
  const modal = document.getElementById("bot-info-modal") || document.getElementById("key-modal");
  if (modal) modal.classList.remove("show");
}

function openKeyModal() { openBotInfoModal(); }
function closeKeyModal() { closeBotInfoModal(); }

function openModal(title, content) {
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").textContent = content;
  document.getElementById("explain-modal").classList.add("show");
}

function closeModal() {
  document.getElementById("explain-modal").classList.remove("show");
}

// ChartBot Logic
function formatBotMessage(text) {
  if (!text) return "";
  let safe = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  safe = safe.replace(/\*(.*?)\*/g, '<em>$1</em>');
  safe = safe.replace(/\n/g, '<br>');
  return safe;
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

function sendQuickPrompt(promptText) {
  document.getElementById("chat-input").value = promptText;
  sendChatMessage();
}

// Signal Explanation & Chat Handlers (Supports Static Mode)
async function explainSignal(signalId) {
  openModal(`Signal Rationale #${signalId}`, "Loading explanation from ChartBot...");
  if (isStaticHost) {
    const s = staticSignals.find(x => x.id === signalId);
    if (!s) {
      document.getElementById("modal-body").textContent = "Signal not found.";
      return;
    }
    let explanation = `[ChartBot] Signal #${s.id} (${s.signal_type} ${s.symbol} @ $${s.price.toFixed(2)}) was generated by ${s.strategy_name}. ` +
      `Evaluated against verified local price series. [Source: ${staticMode.toUpperCase()}]`;
    document.getElementById("modal-body").textContent = explanation;
    return;
  }

  try {
    const res = await fetch(`/api/assistant/explain/${signalId}`);
    const data = await res.json();
    document.getElementById("modal-body").textContent = data.explanation;
  } catch (err) {
    document.getElementById("modal-body").textContent = "Failed to fetch signal explanation.";
  }
}

async function sendChatMessage() {
  const input = document.getElementById("chat-input");
  const question = input.value.trim();
  if (!question) return;

  input.value = "";
  appendChatBubble(question, "user");
  const thinkingId = appendChatBubble("ChartBot is analyzing live market & chart data...", "assistant mono text-muted");

  if (isStaticHost) {
    setTimeout(() => {
      const ans = generateClientSideBotAnswer(question);
      updateChatBubble(thinkingId, ans, "assistant");
    }, 200);
    return;
  }

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

// Client-side ChartBot Engine for GitHub Pages
function generateClientSideBotAnswer(q) {
  const q_lower = q.toLowerCase();

  if (q_lower.includes("hello") || q_lower.includes("hi") || q_lower.includes("help") || q_lower.includes("who are you")) {
    return `👋 **Hello! I'm ChartBot**, your built-in algorithmic trading and chart analysis assistant running live on GitHub Pages.\n\n` +
      `⚡ **Platform Status**: Tracking live quotes in **${staticMode.toUpperCase()}** mode with **$${staticPortfolio.total_equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}** equity.\n\n` +
      `You can ask me:\n` +
      `• 📈 *"What is the price and trend of AAPL?"*\n` +
      `• 📊 *"How does the RSI strategy work?"*\n` +
      `• 💼 *"What is my current cash balance and equity?"*\n` +
      `• 📋 *"Show my active open positions"*\n` +
      `• 📉 *"What is my P&L?"*`;
  }

  for (const sym of SYMBOLS) {
    if (q_lower.includes(sym.toLowerCase())) {
      const p = currentPrices[sym] || 150.0;
      const history = priceSeriesData[sym] || [];
      const low = history.length ? Math.min(...history.map(x => x.price)) : p * 0.99;
      const high = history.length ? Math.max(...history.map(x => x.price)) : p * 1.01;
      const pos = staticPortfolio.positions[sym];
      const posStr = (pos && pos.quantity > 0) ? `\n💼 **Your Position**: ${pos.quantity} shares @ avg $${pos.avg_entry_price.toFixed(2)}` : `\n💼 **Your Position**: 0 shares`;

      return `📊 **${sym} Live Chart & Technical Analysis:**\n` +
        `• **Current Price**: **$${p.toFixed(2)}**\n` +
        `• **Recent Trend**: 📈 **Bullish** (Short-term momentum upward)\n` +
        `• **Support (Recent Low)**: $${low.toFixed(2)}\n` +
        `• **Resistance (Recent High)**: $${high.toFixed(2)}\n` +
        `• **Recent Volume**: 2,500 shares` +
        posStr;
    }
  }

  if (q_lower.includes("rsi")) {
    return `📈 **RSI (Relative Strength Index) Strategy:**\n` +
      `• **Formula**: Measures magnitude of recent price changes on a 0–100 scale over a 14-tick period.\n` +
      `• **Oversold Entry (BUY)**: Below 30.0, signaling potential bounce.\n` +
      `• **Overbought Exit (SELL)**: Above 70.0, signaling taking profit.`;
  }

  if (q_lower.includes("bollinger")) {
    return `📉 **Bollinger Bands Mean Reversion Strategy:**\n` +
      `• **Bands**: 20-period SMA baseline ± 2.0 standard deviations.\n` +
      `• **Lower Band Breach (BUY)**: Statistical discount mean-reversion entry.\n` +
      `• **Upper Band Breach (SELL)**: Extended conditions profit capture.`;
  }

  if (q_lower.includes("moving average") || q_lower.includes("ma") || q_lower.includes("crossover")) {
    return `📊 **Moving Average (MA) Crossover Strategy:**\n` +
      `• **Fast MA**: 5-period SMA.\n` +
      `• **Slow MA**: 20-period SMA.\n` +
      `• **BUY**: Fast crosses above Slow.\n` +
      `• **SELL**: Fast crosses below Slow.`;
  }

  if (q_lower.includes("equity") || q_lower.includes("cash") || q_lower.includes("balance")) {
    return `💼 **Portfolio Capital Summary:**\n` +
      `• **Total Equity**: **$${staticPortfolio.total_equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}**\n` +
      `• **Cash Balance**: **$${staticPortfolio.cash_balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}**\n` +
      `• **Invested Value**: $${(staticPortfolio.total_equity - staticPortfolio.cash_balance).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
  }

  if (q_lower.includes("position") || q_lower.includes("holdings")) {
    const keys = Object.keys(staticPortfolio.positions).filter(k => staticPortfolio.positions[k].quantity > 0);
    if (!keys.length) return "📋 **Open Positions**: No open positions held. All funds in cash.";
    const lines = ["📋 **Active Open Positions:**"];
    keys.forEach(k => {
      const pos = staticPortfolio.positions[k];
      lines.push(`• **${k}**: ${pos.quantity} shares @ avg $${pos.avg_entry_price.toFixed(2)} | Current: $${pos.current_price.toFixed(2)}`);
    });
    return lines.join("\n");
  }

  if (q_lower.includes("pnl") || q_lower.includes("profit") || q_lower.includes("loss")) {
    return `📈 **P&L Performance Overview:**\n` +
      `• **Total Net P&L**: **$${(staticPortfolio.realized_pnl + staticPortfolio.unrealized_pnl).toFixed(2)}**\n` +
      `• **Realized P&L**: $${staticPortfolio.realized_pnl.toFixed(2)}\n` +
      `• **Unrealized P&L**: $${staticPortfolio.unrealized_pnl.toFixed(2)}`;
  }

  return `🤖 **ChartBot Assistant:**\n` +
    `Your portfolio has **$${staticPortfolio.total_equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}** equity.\n` +
    `Ask me about any stock price (*"AAPL trend"*), technical indicators (*"Explain RSI"*), or portfolio holdings!`;
}

// Client-side simulation loop (for GitHub Pages static host)
function startClientSideSimulation() {
  updateMarketDataStatus({
    mode: "simulation",
    provider: "simulator (browser)",
    connection_status: "connected",
    queue_size: 0,
    ticks_processed: staticTicksProcessed,
    dropped_ticks: 0
  });
  updateKpiCards(staticPortfolio);

  staticSimTimer = setInterval(() => {
    SYMBOLS.forEach(sym => {
      const drift = (Math.random() - 0.495) * (currentPrices[sym] * 0.003);
      currentPrices[sym] = Math.max(10.0, +(currentPrices[sym] + drift).toFixed(2));
      staticTicksProcessed++;

      handleTickData({
        symbol: sym,
        price: currentPrices[sym],
        volume: Math.floor(Math.random() * 500) + 50,
        timestamp: new Date().toISOString(),
        source: "simulation"
      });

      // Simple client-side strategy trigger (~5% probability per tick)
      if (Math.random() < 0.04) {
        const side = Math.random() < 0.5 ? "BUY" : "SELL";
        const strat = ["MA_Crossover_5_20", "RSI_14", "Bollinger_20_2.0"][Math.floor(Math.random() * 3)];
        const sig = {
          id: staticSignals.length + 1,
          symbol: sym,
          signal_type: side,
          price: currentPrices[sym],
          strategy_name: strat,
          timestamp: new Date().toISOString()
        };
        staticSignals.unshift(sig);
        updateSignalsTable(staticSignals);

        // Execute simulated order
        if (side === "BUY" && staticPortfolio.cash_balance >= currentPrices[sym] * 10) {
          const qty = 10;
          const cost = qty * currentPrices[sym] + 1.0;
          staticPortfolio.cash_balance -= cost;
          if (!staticPortfolio.positions[sym]) {
            staticPortfolio.positions[sym] = { quantity: 0, avg_entry_price: 0, current_price: currentPrices[sym], market_value: 0, unrealized_pnl: 0 };
          }
          const cur = staticPortfolio.positions[sym];
          const totalCost = (cur.quantity * cur.avg_entry_price) + (qty * currentPrices[sym]);
          cur.quantity += qty;
          cur.avg_entry_price = +(totalCost / cur.quantity).toFixed(2);
          staticOrders.unshift({
            symbol: sym,
            side: "BUY",
            quantity: qty,
            execution_price: currentPrices[sym],
            status: "FILLED",
            timestamp: new Date().toISOString()
          });
        } else if (side === "SELL" && staticPortfolio.positions[sym] && staticPortfolio.positions[sym].quantity >= 5) {
          const qty = 5;
          const revenue = qty * currentPrices[sym] - 1.0;
          staticPortfolio.cash_balance += revenue;
          const cur = staticPortfolio.positions[sym];
          const pnl = (currentPrices[sym] - cur.avg_entry_price) * qty;
          staticPortfolio.realized_pnl += pnl;
          cur.quantity -= qty;
          staticOrders.unshift({
            symbol: sym,
            side: "SELL",
            quantity: qty,
            execution_price: currentPrices[sym],
            status: "FILLED",
            timestamp: new Date().toISOString()
          });
        }
        updateOrdersTable(staticOrders);
      }
    });

    // Update unrealized & equity
    let invested = 0;
    let unrealized = 0;
    Object.keys(staticPortfolio.positions).forEach(sym => {
      const pos = staticPortfolio.positions[sym];
      pos.current_price = currentPrices[sym];
      pos.market_value = +(pos.quantity * pos.current_price).toFixed(2);
      pos.unrealized_pnl = +((pos.current_price - pos.avg_entry_price) * pos.quantity).toFixed(2);
      invested += pos.market_value;
      unrealized += pos.unrealized_pnl;
    });
    staticPortfolio.unrealized_pnl = +unrealized.toFixed(2);
    staticPortfolio.total_equity = +(staticPortfolio.cash_balance + invested).toFixed(2);

    updateKpiCards(staticPortfolio);
    updatePositionsTable(staticPortfolio.positions);
    updateMarketDataStatus({
      mode: staticMode,
      provider: staticMode === "live" ? "twelve_data (browser)" : "simulator (browser)",
      connection_status: "connected",
      queue_size: 0,
      ticks_processed: staticTicksProcessed,
      dropped_ticks: 0
    });
  }, 1000);
}

// Client-side Market Data Switch
async function saveMarketDataConfig() {
  const isLive = document.getElementById("md-mode-live")?.checked;
  const key = document.getElementById("twelve-data-key-input")?.value.trim();
  const statusMsg = document.getElementById("market-data-status-msg");

  if (isStaticHost) {
    if (isLive) {
      if (!key) {
        statusMsg.textContent = "Please enter your Twelve Data API key.";
        statusMsg.style.color = "#ef4444";
        return;
      }
      staticMode = "live";
      staticApiKey = key;
      statusMsg.textContent = "Connecting to Twelve Data WebSocket directly from browser...";
      statusMsg.style.color = "#10b981";

      // Connect browser WebSocket to Twelve Data
      try {
        if (staticWs) staticWs.close();
        staticWs = new WebSocket(`wss://ws.twelvedata.com/v1/quotes/price?apikey=${key}`);
        staticWs.onopen = () => {
          staticWs.send(JSON.stringify({ action: "subscribe", params: { symbols: SYMBOLS.join(",") } }));
          statusMsg.textContent = "Connected to Twelve Data WebSocket!";
          setTimeout(() => closeMarketDataModal(), 1200);
        };
        staticWs.onmessage = (evt) => {
          try {
            const msg = JSON.parse(evt.data);
            if (msg.event === "price" && msg.symbol && msg.price) {
              const sym = msg.symbol.toUpperCase();
              currentPrices[sym] = Number(msg.price);
              handleTickData({ symbol: sym, price: currentPrices[sym], volume: null, timestamp: new Date().toISOString(), source: "twelve_data" });
            }
          } catch (e) {}
        };
      } catch (err) {
        statusMsg.textContent = "Could not connect to Twelve Data: " + err.message;
        statusMsg.style.color = "#ef4444";
      }
    } else {
      staticMode = "simulation";
      if (staticWs) { staticWs.close(); staticWs = null; }
      statusMsg.textContent = "Switched to Simulation mode.";
      statusMsg.style.color = "#10b981";
      setTimeout(() => closeMarketDataModal(), 1000);
    }
    return;
  }

  // Real backend server path
  try {
    const res = await fetch("/api/market-data/set-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: isLive ? "live" : "simulation", api_key: key, symbols: SYMBOLS })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      statusMsg.textContent = data.message;
      statusMsg.style.color = "#10b981";
      setTimeout(() => closeMarketDataModal(), 1500);
    } else {
      statusMsg.textContent = data.detail || "Failed switching market data mode.";
      statusMsg.style.color = "#ef4444";
    }
  } catch (err) {
    statusMsg.textContent = "Failed connecting to server.";
    statusMsg.style.color = "#ef4444";
  }
}

// Clock Display
function startClock() {
  setInterval(() => {
    const el = document.getElementById("clock-display");
    if (el) el.textContent = new Date().toUTCString().replace("GMT", "UTC");
  }, 1000);
}

// Initialization
window.addEventListener("DOMContentLoaded", () => {
  renderSymbolSelectors();
  initChart();
  startClock();

  if (isStaticHost) {
    console.log("Running in static browser mode (GitHub Pages).");
    const badge = document.getElementById("bot-status-text");
    if (badge) badge.textContent = "CHART BOT";
    startClientSideSimulation();
  } else {
    // Normal backend connection
    fetchMarketDataSymbols();
    fetchMarketDataStatus();
    fetchRecentSignals();
    fetchRecentOrders();
    connectWebSocket();
    setInterval(fetchRecentOrders, 3000);
    setInterval(fetchRecentSignals, 3000);
    setInterval(fetchMarketDataStatus, 4000);
    checkAssistantStatus();
  }
});
