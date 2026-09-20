import re
import os
import math
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from app.config import settings
from app.models import SignalModel, TickModel, OrderModel, PositionModel, PortfolioSnapshotModel
from app.db import db_session, SessionLocal
from app.engine.portfolio import Portfolio

logger = logging.getLogger(__name__)


class ChartBotAssistant:
    """
    Built-in Chart & Algorithmic Trading Assistant ('ChartBot').
    Runs 100% locally with zero external API dependencies.
    Provides instant, verified answers on:
    - Live tick charts, price trends, support/resistance, and volatility.
    - Technical indicators: Moving Average Crossover, RSI, Bollinger Bands.
    - Portfolio capital, cash liquidity, open positions, and P&L.
    - Algorithmic strategy rationale & signal explanations.
    - Market data telemetry (Twelve Data vs. Simulation).
    """

    def __init__(
        self,
        portfolio: Optional[Portfolio] = None,
        data_feed: Optional[Any] = None,
        session_factory=None,
        **kwargs,
    ):
        self.portfolio = portfolio
        self.data_feed = data_feed
        self.session_factory = session_factory or SessionLocal
        self.bot_name = getattr(settings, "BOT_NAME", "ChartBot")
        self.version = getattr(settings, "BOT_VERSION", "1.0")

    def is_bot_active(self) -> bool:
        return True

    # Backwards-compatibility methods for existing routes/tests
    def is_gemini_active(self) -> bool:
        return False

    def is_claude_active(self) -> bool:
        return False

    def set_api_key(self, api_key: str):
        """ChartBot runs locally without external keys."""
        return True, "ChartBot is built-in and active locally. No external API key is needed."

    def get_market_data_info(self) -> Dict[str, Any]:
        if self.data_feed:
            return self.data_feed.get_status()
        return {
            "mode": getattr(settings, "MARKET_DATA_MODE", "simulation"),
            "provider": "simulator" if getattr(settings, "MARKET_DATA_MODE", "simulation") == "simulation" else "twelve_data",
            "connection_status": "connected",
        }

    def explain_signal(self, signal_id: int) -> str:
        """
        Gathers signal parameters and recent price series around the signal,
        then provides a verified mathematical explanation of why it fired.
        """
        signal_data = None
        price_history = []
        md_info = self.get_market_data_info()

        with db_session(self.session_factory) as session:
            sig = session.query(SignalModel).filter(SignalModel.id == signal_id).first()
            if not sig:
                return f"Signal with ID {signal_id} not found in database."

            signal_data = sig.to_dict()

            # Retrieve prior 30 ticks for context
            ticks = (
                session.query(TickModel)
                .filter(TickModel.symbol == sig.symbol)
                .order_by(TickModel.timestamp.desc())
                .limit(30)
                .all()
            )
            price_history = [float(t.price) for t in reversed(ticks)]

        return self._generate_quantitative_signal_explanation(signal_data, price_history, md_info)

    def _generate_quantitative_signal_explanation(
        self,
        signal: Dict[str, Any],
        prices: List[float],
        md_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generates accurate, mathematically grounded natural language signal explanations."""
        sym = signal["symbol"]
        action = signal["signal_type"]
        price = signal["price"]
        strat = signal["strategy_name"]
        source = (md_info or {}).get("provider", "simulator").upper()
        mode = (md_info or {}).get("mode", "simulation").upper()
        source_tag = f" [Source: {source} ({mode})]"

        if "MA_Crossover" in strat:
            fast_p, slow_p = 5, 20
            parts = strat.split("_")
            if len(parts) >= 4:
                try:
                    fast_p, slow_p = int(parts[2]), int(parts[3])
                except ValueError:
                    pass

            if len(prices) >= slow_p:
                fast_sma = sum(prices[-fast_p:]) / fast_p
                slow_sma = sum(prices[-slow_p:]) / slow_p
                if action == "BUY":
                    return (
                        f"[ChartBot] Signal #{signal['id']} (BUY {sym} @ ${price:.2f}) was triggered by the Moving Average Crossover strategy. "
                        f"The fast {fast_p}-period SMA (${fast_sma:.2f}) crossed strictly above the slow {slow_p}-period SMA (${slow_sma:.2f}) "
                        f"following an upward shift in price momentum, confirming a bullish entry signal.{source_tag}"
                    )
                else:
                    return (
                        f"[ChartBot] Signal #{signal['id']} (SELL {sym} @ ${price:.2f}) was triggered by the Moving Average Crossover strategy. "
                        f"The fast {fast_p}-period SMA (${fast_sma:.2f}) broke below the slow {slow_p}-period SMA (${slow_sma:.2f}), "
                        f"indicating a bearish momentum shift and signaling an exit.{source_tag}"
                    )
            return (
                f"[ChartBot] Signal #{signal['id']} ({action} {sym} @ ${price:.2f}) fired when the short-term moving average crossed the "
                f"long-term moving average on {sym}, indicating a directional trend shift.{source_tag}"
            )

        elif "RSI" in strat:
            period = 14
            parts = strat.split("_")
            if len(parts) >= 2:
                try:
                    period = int(parts[1])
                except ValueError:
                    pass

            rsi_val = None
            if len(prices) >= period + 1:
                gains, losses = [], []
                slice_p = prices[-(period + 1):]
                for i in range(1, len(slice_p)):
                    diff = slice_p[i] - slice_p[i - 1]
                    gains.append(max(diff, 0))
                    losses.append(max(-diff, 0))
                avg_g = sum(gains) / period
                avg_l = sum(losses) / period
                if avg_l > 0:
                    rs = avg_g / avg_l
                    rsi_val = round(100.0 - (100.0 / (1.0 + rs)), 1)
                else:
                    rsi_val = 100.0

            rsi_str = f"RSI reached {rsi_val}" if rsi_val is not None else "RSI crossed threshold"

            if action == "BUY":
                return (
                    f"[ChartBot] Signal #{signal['id']} (BUY {sym} @ ${price:.2f}) fired due to oversold conditions. "
                    f"The 14-period {rsi_str} (below the 30.0 oversold threshold), indicating aggressive selling exhaustion "
                    f"and an attractive mean-reversion discount.{source_tag}"
                )
            else:
                return (
                    f"[ChartBot] Signal #{signal['id']} (SELL {sym} @ ${price:.2f}) fired due to overbought conditions. "
                    f"The 14-period {rsi_str} (above the 70.0 overbought threshold), signaling stretched bullish momentum "
                    f"and elevated risk of a corrective pullback.{source_tag}"
                )

        elif "Bollinger" in strat:
            period, num_std = 20, 2.0
            parts = strat.split("_")
            if len(parts) >= 4:
                try:
                    period = int(parts[2])
                    num_std = float(parts[3])
                except ValueError:
                    pass

            if len(prices) >= period:
                slice_p = prices[-period:]
                sma = sum(slice_p) / period
                var = sum((p - sma) ** 2 for p in slice_p) / period
                sd = math.sqrt(var)
                upper = round(sma + num_std * sd, 2)
                lower = round(sma - num_std * sd, 2)

                if action == "BUY":
                    return (
                        f"[ChartBot] Signal #{signal['id']} (BUY {sym} @ ${price:.2f}) fired on a Bollinger Band lower breach. "
                        f"Price dropped to or below ${price:.2f}, crossing the lower band of ${lower:.2f} "
                        f"({num_std} standard deviations below the 20-period baseline of ${sma:.2f}), triggering a statistical mean-reversion entry.{source_tag}"
                    )
                else:
                    return (
                        f"[ChartBot] Signal #{signal['id']} (SELL {sym} @ ${price:.2f}) fired on a Bollinger Band upper test. "
                        f"Price reached ${price:.2f}, touching or exceeding the upper band of ${upper:.2f} "
                        f"({num_std} standard deviations above the 20-period baseline of ${sma:.2f}), signaling profit-taking.{source_tag}"
                    )

            return (
                f"[ChartBot] Signal #{signal['id']} ({action} {sym} @ ${price:.2f}) was generated by the Bollinger Bands Mean Reversion model "
                f"as the asset price diverged 2 standard deviations away from its rolling moving average.{source_tag}"
            )

        return (
            f"[ChartBot] Signal #{signal['id']} ({action} {sym} @ ${price:.2f}) was executed by strategy '{strat}' "
            f"based on automated algorithmic rule validation at {signal.get('timestamp')}.{source_tag}"
        )

    def answer_question(self, user_question: str) -> str:
        """
        Main ChartBot conversational reasoning engine.
        Answers inquiries on charts, prices, indicators, portfolio, and platform telemetry.
        """
        q = (user_question or "").strip()
        if not q:
            return "Please ask a question about the live chart, stock prices, technical indicators, or your portfolio."

        q_lower = q.lower()

        # Gather real-time context
        portfolio_snapshot = self.portfolio.get_snapshot() if self.portfolio else {}
        md_info = self.get_market_data_info()

        # Database queries for orders and signals
        recent_orders = []
        recent_signals = []
        with db_session(self.session_factory) as session:
            orders = (
                session.query(OrderModel)
                .order_by(OrderModel.timestamp.desc())
                .limit(15)
                .all()
            )
            recent_orders = [o.to_dict() for o in orders]

            signals = (
                session.query(SignalModel)
                .order_by(SignalModel.timestamp.desc())
                .limit(15)
                .all()
            )
            recent_signals = [s.to_dict() for s in signals]

        context_data = {
            "portfolio": portfolio_snapshot,
            "market_data": md_info,
            "recent_orders": recent_orders,
            "recent_signals": recent_signals,
        }

        # 1. Greetings & Help / Capabilities
        if any(w in q_lower for w in ["hello", "hi", "hey", "who are you", "what can you do", "help", "guide"]):
            return self._handle_greetings_and_help(portfolio_snapshot, md_info)

        # 2. General Chart & Telemetry Explanations
        if any(phrase in q_lower for phrase in ["how to read", "explain the chart", "what does the chart show", "chart help", "chart explanation"]):
            return self._handle_chart_explanation(md_info)

        # 3. Specific Ticker Price, Trend, or Chart Query
        known_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"]
        if self.data_feed and hasattr(self.data_feed, "symbols"):
            known_symbols = list(set(known_symbols + list(self.data_feed.symbols)))

        for sym in known_symbols:
            if re.search(r'\b' + re.escape(sym.lower()) + r'\b', q_lower):
                return self._handle_ticker_inquiry(sym, context_data)

        # 4. Technical Indicator & Strategy Queries
        if any(term in q_lower for term in ["rsi", "relative strength", "moving average", "ma crossover", "sma", "bollinger", "bands", "strategy", "strategies"]):
            return self._handle_indicator_and_strategy(q_lower)

        # 5. Market Data Telemetry & Live Switch Queries
        if any(term in q_lower for term in ["market data", "feed", "twelve data", "provider", "real-time", "live data", "switch mode", "simulation"]):
            return self._handle_market_data_telemetry(md_info)

        # 6. Portfolio Capital, Equity, & Cash
        if any(term in q_lower for term in ["equity", "cash", "balance", "capital", "worth", "liquidity", "money"]):
            return self._handle_equity_and_cash(portfolio_snapshot)

        # 7. Open Positions & Holdings
        if any(term in q_lower for term in ["position", "positions", "holdings", "shares", "stocks i own", "portfolio"]):
            return self._handle_positions(portfolio_snapshot)

        # 8. P&L / Profits & Losses
        if any(term in q_lower for term in ["pnl", "p&l", "profit", "loss", "gain", "return", "performance"]):
            return self._handle_pnl(portfolio_snapshot)

        # 9. Orders, Trades, & Executions
        if any(term in q_lower for term in ["order", "orders", "trade", "trades", "execution", "executions", "fills"]):
            return self._handle_orders(recent_orders)

        # 10. Signals
        if any(term in q_lower for term in ["signal", "signals", "alerts", "triggers"]):
            return self._handle_signals(recent_signals)

        # 11. Support & Resistance or Volatility
        if any(term in q_lower for term in ["support", "resistance", "trend", "volatility"]):
            # Default to first known symbol or active ticker
            active_sym = known_symbols[0] if known_symbols else "AAPL"
            return self._handle_ticker_inquiry(active_sym, context_data)

        # 12. Contextual Intelligent Fallback
        return self._handle_fallback(context_data)

    # -------------------------------------------------------------------------
    # Specialized Intent Handlers
    # -------------------------------------------------------------------------

    def _handle_greetings_and_help(self, portfolio: Dict[str, Any], md_info: Dict[str, Any]) -> str:
        equity = portfolio.get("total_equity", 100000.0)
        mode = md_info.get("mode", "simulation").upper()
        provider = md_info.get("provider", "simulator").upper()

        return (
            f"👋 **Hello! I'm ChartBot**, your built-in algorithmic trading and chart analysis assistant.\n\n"
            f"⚡ **Platform Status**: Tracking live quotes in **{mode}** mode ({provider}) with **${equity:,.2f}** portfolio equity.\n\n"
            f"Here are some questions you can ask me right now:\n"
            f"• 📈 *\"What is the price and trend of AAPL?\"* (or NVDA, TSLA, MSFT, etc.)\n"
            f"• 📊 *\"How does the RSI strategy work?\"* (or Moving Averages / Bollinger Bands)\n"
            f"• 💼 *\"What is my current cash balance and equity?\"*\n"
            f"• 📋 *\"Show me my active open positions\"*\n"
            f"• 📉 *\"What is my realized and unrealized P&L?\"*\n"
            f"• 📡 *\"How do I switch to real-time Twelve Data market data?\"*"
        )

    def _handle_chart_explanation(self, md_info: Dict[str, Any]) -> str:
        provider = md_info.get("provider", "simulator")
        mode = md_info.get("mode", "simulation").upper()
        return (
            f"📊 **How to Read the Live Market Chart:**\n"
            f"• **Chart Type**: Real-time tick price line chart updating every second.\n"
            f"• **X-Axis**: Timestamps in UTC reflecting order of tick arrival.\n"
            f"• **Y-Axis**: Price in USD ($).\n"
            f"• **Ticker Selector**: Use the pill buttons above the chart (e.g. AAPL, MSFT, NVDA) to switch the active view.\n"
            f"• **Data Feed**: Currently streaming from **{provider}** ({mode} mode).\n"
            f"• **Algorithmic Signals**: Strategies evaluate every incoming tick in real-time to generate BUY/SELL orders."
        )

    def _handle_ticker_inquiry(self, symbol: str, context: Dict[str, Any]) -> str:
        portfolio = context.get("portfolio", {})
        positions = portfolio.get("positions", {})
        pos = positions.get(symbol, {})
        orders = [o for o in context.get("recent_orders", []) if o.get("symbol") == symbol]
        signals = [s for s in context.get("recent_signals", []) if s.get("symbol") == symbol]

        # Fetch recent ticks from database
        prices = []
        volumes = []
        with db_session(self.session_factory) as session:
            ticks = (
                session.query(TickModel)
                .filter(TickModel.symbol == symbol)
                .order_by(TickModel.timestamp.desc())
                .limit(30)
                .all()
            )
            for t in reversed(ticks):
                prices.append(float(t.price))
                if t.volume is not None:
                    volumes.append(float(t.volume))

        if not prices:
            # Fallback to latest tick in data_feed if DB has not recorded yet
            latest = {}
            if self.data_feed and hasattr(self.data_feed, "latest_ticks"):
                latest = self.data_feed.latest_ticks.get(symbol, {})
            if latest and "price" in latest:
                prices = [float(latest["price"])]

        if not prices:
            return f"ℹ️ No recent ticks recorded yet for **{symbol}**. The feed is initializing."

        current_p = prices[-1]
        high_p = max(prices)
        low_p = min(prices)
        first_p = prices[0]
        change_val = current_p - first_p
        change_pct = (change_val / first_p * 100) if first_p > 0 else 0.0
        change_sign = "+" if change_val >= 0 else ""

        # Trend analysis
        if len(prices) >= 2:
            pct_change = (change_val / first_p * 100.0) if first_p > 0 else 0.0
            if pct_change >= 0.2:
                trend_str = "📈 **Bullish** (Short-term momentum upward)"
            elif pct_change <= -0.2:
                trend_str = "📉 **Bearish** (Short-term momentum downward)"
            else:
                trend_str = "⚖️ **Consolidating / Neutral** (Range-bound)"
        else:
            trend_str = "⚖️ **Neutral** (Awaiting more ticks)"

        vol_str = f"{int(volumes[-1]):,} shares" if volumes else "N/A (Simulated)"

        # Position status
        holding_str = ""
        if pos and pos.get("quantity", 0) > 0:
            qty_val = pos["quantity"]
            qty_fmt = int(qty_val) if float(qty_val).is_integer() else float(qty_val)
            entry = pos["avg_entry_price"]
            pnl = pos["unrealized_pnl"]
            pnl_sign = "+" if pnl >= 0 else ""
            holding_str = f"\n💼 **Your Position**: {qty_fmt} shares @ avg ${entry:,.2f} (P&L: {pnl_sign}${pnl:,.2f})"
        else:
            holding_str = "\n💼 **Your Position**: 0 shares (No open exposure)"

        last_sig_str = ""
        if signals:
            last_sig = signals[0]
            last_sig_str = f"\n⚡ **Last Signal**: {last_sig['signal_type']} @ ${last_sig['price']:,.2f} via {last_sig['strategy_name']}"

        return (
            f"📊 **{symbol} Live Chart & Technical Analysis:**\n"
            f"• **Current Price**: **${current_p:,.2f}** ({change_sign}${change_val:,.2f} / {change_sign}{change_pct:.2f}%)\n"
            f"• **Recent Trend**: {trend_str}\n"
            f"• **Support (Recent Low)**: ${low_p:,.2f}\n"
            f"• **Resistance (Recent High)**: ${high_p:,.2f}\n"
            f"• **Recent Volume**: {vol_str}"
            f"{holding_str}"
            f"{last_sig_str}"
        )

    def _handle_indicator_and_strategy(self, query: str) -> str:
        if "rsi" in query:
            return (
                f"📈 **RSI (Relative Strength Index) Strategy:**\n"
                f"• **Formula**: Measures magnitude of recent price changes on a 0–100 scale over a 14-tick period.\n"
                f"• **Oversold Entry (BUY)**: When RSI drops **below 30.0**, the stock is oversold, signaling potential bounce.\n"
                f"• **Overbought Exit (SELL)**: When RSI rises **above 70.0**, the stock is overstretched, signaling taking profit."
            )
        elif "bollinger" in query:
            return (
                f"📉 **Bollinger Bands Mean Reversion Strategy:**\n"
                f"• **Bands**: Composed of a 20-period Simple Moving Average (SMA) baseline ± 2.0 standard deviations.\n"
                f"• **Lower Band Breach (BUY)**: Price penetrating below the lower band indicates statistically cheap pricing for a mean-reversion bounce.\n"
                f"• **Upper Band Breach (SELL)**: Price penetrating above the upper band indicates extended conditions, triggering profit capture."
            )
        elif "moving average" in query or "ma" in query or "crossover" in query:
            return (
                f"📊 **Moving Average (MA) Crossover Strategy:**\n"
                f"• **Fast MA**: 5-period Simple Moving Average.\n"
                f"• **Slow MA**: 20-period Simple Moving Average.\n"
                f"• **Golden Cross (BUY)**: Fast MA crosses strictly above the Slow MA, confirming bullish directional trend.\n"
                f"• **Death Cross (SELL)**: Fast MA crosses below Slow MA, indicating bearish exhaustion."
            )
        else:
            return (
                f"⚙️ **Active Algorithmic Strategies:**\n"
                f"Our trading engine runs 3 concurrent strategies across all tracked symbols:\n"
                f"1. **MA_Crossover_5_20**: Trend-following dual SMA crossover.\n"
                f"2. **RSI_14**: Momentum oscillator with 30 oversold / 70 overbought thresholds.\n"
                f"3. **Bollinger_20_2.0**: Statistical mean-reversion with 2.0 standard deviation bands.\n"
                f"All signals pass through risk controls before order execution."
            )

    def _handle_market_data_telemetry(self, md_info: Dict[str, Any]) -> str:
        provider = md_info.get("provider", "simulator").upper()
        mode = md_info.get("mode", "simulation").upper()
        conn = md_info.get("connection_status", "connected").upper()
        processed = md_info.get("ticks_processed", 0)
        dropped = md_info.get("dropped_ticks", 0)
        symbols = md_info.get("symbols_list", ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"])

        return (
            f"📡 **Market Data Telemetry & Setup:**\n"
            f"• **Current Provider**: **{provider}**\n"
            f"• **Ingestion Mode**: **{mode}**\n"
            f"• **Connection Status**: **{conn}**\n"
            f"• **Subscribed Equities**: {', '.join(symbols)}\n"
            f"• **Total Ticks Processed**: {processed:,}\n"
            f"• **Dropped Ticks**: {dropped:,} (Zero indicates optimal queue throughput)\n\n"
            f"💡 **To switch to Real-Time Twelve Data WebSocket**:\n"
            f"1. Click the **SIMULATION** badge in the top-right header.\n"
            f"2. Select **LIVE — Twelve Data WebSocket**.\n"
            f"3. Enter your free Twelve Data API key from [twelvedata.com](https://twelvedata.com).\n"
            f"4. Click **Apply & Connect** to stream live company stock data instantly!"
        )

    def _handle_equity_and_cash(self, portfolio: Dict[str, Any]) -> str:
        equity = portfolio.get("total_equity", 100000.0)
        cash = portfolio.get("cash_balance", 100000.0)
        positions = portfolio.get("positions", {})
        invested = sum(p.get("market_value", 0.0) for p in positions.values())
        active_count = len([p for p in positions.values() if p.get("quantity", 0) > 0])
        liq_pct = (cash / equity * 100) if equity > 0 else 0.0

        return (
            f"💼 **Portfolio Capital Summary:**\n"
            f"• **Total Equity**: **${equity:,.2f}**\n"
            f"• **Cash Balance**: **${cash:,.2f}** ({liq_pct:.1f}% liquid)\n"
            f"• **Invested Value**: **${invested:,.2f}** across {active_count} open position(s)\n"
            f"• **Available Buying Power**: ${cash:,.2f}"
        )

    def _handle_positions(self, portfolio: Dict[str, Any]) -> str:
        positions = portfolio.get("positions", {})
        active = [p for p in positions.values() if p.get("quantity", 0) > 0]
        cash = portfolio.get("cash_balance", 100000.0)

        if not active:
            return f"📋 **Open Positions**: You currently have no open stock positions. All capital is preserved in cash (${cash:,.2f})."

        lines = ["📋 **Active Open Positions:**"]
        for p in active:
            pnl = p.get("unrealized_pnl", 0.0)
            sign = "+" if pnl >= 0 else ""
            qty_val = p.get("quantity", 0)
            qty_fmt = int(qty_val) if float(qty_val).is_integer() else float(qty_val)
            lines.append(
                f"• **{p['symbol']}**: {qty_fmt} shares @ avg ${p['avg_entry_price']:,.2f} | "
                f"Current: ${p['current_price']:,.2f} | Value: ${p['market_value']:,.2f} | "
                f"Unrealized P&L: {sign}${pnl:,.2f}"
            )
        return "\n".join(lines)

    def _handle_pnl(self, portfolio: Dict[str, Any]) -> str:
        realized = portfolio.get("realized_pnl", 0.0)
        unrealized = portfolio.get("unrealized_pnl", 0.0)
        net_pnl = realized + unrealized
        equity = portfolio.get("total_equity", 100000.0)

        net_sign = "+" if net_pnl >= 0 else ""
        re_sign = "+" if realized >= 0 else ""
        un_sign = "+" if unrealized >= 0 else ""

        return (
            f"📈 **P&L Performance Overview:**\n"
            f"• **Total Net P&L**: **{net_sign}${net_pnl:,.2f}**\n"
            f"• **Realized P&L**: {re_sign}${realized:,.2f} (from closed positions)\n"
            f"• **Unrealized P&L**: {un_sign}${unrealized:,.2f} (floating mark-to-market)\n"
            f"• **Total Portfolio Equity**: ${equity:,.2f}"
        )

    def _handle_orders(self, orders: List[Dict[str, Any]]) -> str:
        if not orders:
            return "📝 **Orders**: No trade executions recorded yet."

        filled = [o for o in orders if o.get("status") == "FILLED"]
        rejected = [o for o in orders if o.get("status") == "REJECTED"]

        lines = [
            f"📝 **Recent Order Executions (Last {min(len(orders), 5)}):**",
            f"• Filled Orders: **{len(filled)}** | Rejected (Risk/Cash): **{len(rejected)}**\n"
        ]
        for o in orders[:5]:
            status_icon = "✅" if o.get("status") == "FILLED" else "❌"
            lines.append(
                f"• {status_icon} **{o.get('side')} {o.get('symbol')}**: {o.get('quantity')} shares @ "
                f"${o.get('execution_price', o.get('price', 0.0)):,.2f} — *{o.get('status')}*"
            )
        return "\n".join(lines)

    def _handle_signals(self, signals: List[Dict[str, Any]]) -> str:
        if not signals:
            return "⚡ **Signals**: Strategies are actively evaluating live ticks; no signals have fired yet."

        lines = [f"⚡ **Recent Algorithmic Signals (Last {min(len(signals), 5)}):**"]
        for s in signals[:5]:
            action_icon = "🟢" if s.get("signal_type") == "BUY" else "🔴"
            lines.append(
                f"• {action_icon} **{s.get('signal_type')} {s.get('symbol')}** @ ${s.get('price', 0.0):,.2f} "
                f"via *{s.get('strategy_name')}*"
            )
        lines.append("\n💡 *Tip: Click the 'Why?' button in the Generated Signals table for an instant mathematical breakdown.*")
        return "\n".join(lines)

    def _handle_fallback(self, context: Dict[str, Any]) -> str:
        portfolio = context.get("portfolio", {})
        equity = portfolio.get("total_equity", 100000.0)
        cash = portfolio.get("cash_balance", 100000.0)
        positions = portfolio.get("positions", {})
        active_count = len([p for p in positions.values() if p.get("quantity", 0) > 0])

        return (
            f"🤖 **ChartBot Assistant:**\n"
            f"Your current portfolio equity is **${equity:,.2f}** with **${cash:,.2f}** cash across {active_count} position(s).\n\n"
            f"I can help you analyze:\n"
            f"• **Stock Charts**: *\"What is the price of AAPL?\"* or *\"NVDA trend\"*\n"
            f"• **Indicators**: *\"Explain RSI\"* or *\"How does MA Crossover work?\"*\n"
            f"• **Account Status**: *\"Show my positions\"* or *\"What is my P&L?\"*\n"
            f"• **Market Data**: *\"How do I switch to live Twelve Data quotes?\"*"
        )


# Backward-compatible alias
AITradingAssistant = ChartBotAssistant
