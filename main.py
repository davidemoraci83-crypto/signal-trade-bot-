from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import os
import urllib.request
import json
import math
from datetime import datetime

app = FastAPI()
STATE_FILE = "bot_state.json"


def load_initial_state():
    default_state = {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "beps": 0,
        "consecutive_losses": 0,
        "shield_active": False,
        "signals_log": [],
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_state.update({k: v for k, v in data.items() if k in default_state})
        except Exception:
            pass
    return default_state


class SignalTrackerState:
    def __init__(self):
        state = load_initial_state()
        self.total_trades = state["total_trades"]
        self.wins = state["wins"]
        self.losses = state["losses"]
        self.beps = state["beps"]
        self.consecutive_losses = state["consecutive_losses"]
        self.shield_active = state["shield_active"]
        self.signals_log = state["signals_log"]

    def save(self):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "total_trades": self.total_trades,
                        "wins": self.wins,
                        "losses": self.losses,
                        "beps": self.beps,
                        "consecutive_losses": self.consecutive_losses,
                        "shield_active": self.shield_active,
                        "signals_log": self.signals_log[-300:],
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception:
            pass

    def record_signal(self, sig: dict):
        self.signals_log.append(sig)
        self.save()

    def update_signal_outcome(self, signal_id: int, outcome: str):
        for item in reversed(self.signals_log):
            if item.get("id") == signal_id:
                item["outcome"] = outcome
                break
        self.save()

    def process_result(self, result_type: str):
        self.total_trades += 1
        if result_type == "win":
            self.wins += 1
            self.consecutive_losses = 0
            self.shield_active = False
        elif result_type == "loss":
            self.losses += 1
            self.consecutive_losses += 1
            self.shield_active = True
        elif result_type == "bep":
            self.beps += 1

        if self.signals_log:
            for item in reversed(self.signals_log):
                if item.get("executed") and item.get("outcome") == "pending":
                    item["outcome"] = result_type
                    break
        self.save()

    def get_stats(self):
        active_trades = self.total_trades - self.beps
        std_wr = (self.wins / active_trades * 100) if active_trades > 0 else 0.0
        unexecuted_count = sum(1 for s in self.signals_log if not s.get("executed", False))
        buy_count = sum(1 for s in self.signals_log if s.get("direction") == "BUY")
        sell_count = sum(1 for s in self.signals_log if s.get("direction") == "SELL")
        total_spread_cost = round(
            sum(float(s.get("spread", 0.0) or 0.0) for s in self.signals_log if s.get("executed")), 4
        )
        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "beps": self.beps,
            "win_rate": round(std_wr, 2),
            "consecutive_losses": self.consecutive_losses,
            "shield_active": self.shield_active,
            "logged_signals": len(self.signals_log),
            "unexecuted_monitored": unexecuted_count,
            "buy_signals": buy_count,
            "sell_signals": sell_count,
            "logged_spread_cost": total_spread_cost,
            "recent_signals": self.signals_log[-15:],
        }


tracker = SignalTrackerState()


class TradeResultRequest(BaseModel):
    result_type: str  # "win", "loss", "bep"
    is_scalp: bool = False


class LogSignalRequest(BaseModel):
    asset: str
    timeframe: str
    direction: str
    entry: float
    sl: float
    tp: float
    spread: float = 0.0
    grade: str
    est_tp_prob: float
    ev_points: float = 0.0
    executed: bool = True
    notes: str = ""


class UpdateSignalOutcomeRequest(BaseModel):
    signal_id: int
    outcome: str


class TelegramSendRequest(BaseModel):
    bot_token: str
    chat_id: str
    message: str


class BacktestRequest(BaseModel):
    prices: list[float]
    spread: float = 0.25
    commission_per_trade: float = 0.0
    slippage_points: float = 0.0
    sl_points: float = 2.0
    tp_points: float = 3.0
    train_ratio: float = 0.7


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for p in values[1:]:
        out.append(p * k + out[-1] * (1.0 - k))
    return out


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains = []
    losses = []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


@app.get("/api/stats")
async def get_stats():
    return tracker.get_stats()


@app.post("/api/trade/result")
async def post_trade_result(payload: TradeResultRequest):
    tracker.process_result(payload.result_type)
    return tracker.get_stats()


@app.post("/api/signal/log")
async def post_signal_log(payload: LogSignalRequest):
    next_id = (tracker.signals_log[-1].get("id", 0) + 1) if tracker.signals_log else 1
    entry_obj = {
        "id": next_id,
        "mode_type": "manual_paper_log",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "asset": payload.asset,
        "timeframe": payload.timeframe,
        "direction": payload.direction,
        "entry": payload.entry,
        "sl": payload.sl,
        "tp": payload.tp,
        "spread": payload.spread,
        "grade": payload.grade,
        "est_tp_prob": payload.est_tp_prob,
        "ev_points": payload.ev_points,
        "executed": payload.executed,
        "outcome": "pending" if payload.executed else "unexecuted_monitored",
        "notes": payload.notes,
    }
    tracker.record_signal(entry_obj)
    return {"status": "ok", "stats": tracker.get_stats()}


@app.post("/api/signal/outcome")
async def post_signal_outcome(payload: UpdateSignalOutcomeRequest):
    tracker.update_signal_outcome(payload.signal_id, payload.outcome)
    return {"status": "ok", "stats": tracker.get_stats()}


@app.post("/api/backtest")
async def run_backtest(payload: BacktestRequest):
    prices = [x for x in payload.prices if isinstance(x, (int, float)) and math.isfinite(x) and x > 0]
    if len(prices) < 25:
        return {"status": "error", "message": "Servono almeno 25 prezzi validi per eseguire il backtest."}

    split_idx = max(15, min(len(prices) - 5, int(len(prices) * payload.train_ratio)))

    def simulate_slice(segment: list[float]):
        fast_ema = _ema(segment, 5)
        slow_ema = _ema(segment, 15)
        wins = 0
        losses = 0
        net_pnl = 0.0
        gross_profit = 0.0
        gross_loss = 0.0
        peak = 0.0
        max_dd = 0.0
        trades = 0

        i = 15
        while i < len(segment) - 1:
            pos = None
            if fast_ema[i - 1] <= slow_ema[i - 1] and fast_ema[i] > slow_ema[i]:
                pos = "BUY"
            elif fast_ema[i - 1] >= slow_ema[i - 1] and fast_ema[i] < slow_ema[i]:
                pos = "SELL"

            if pos:
                cost_half = (payload.spread / 2.0) + payload.slippage_points
                entry = segment[i] + (cost_half if pos == "BUY" else -cost_half)
                sl = entry - payload.sl_points if pos == "BUY" else entry + payload.sl_points
                tp = entry + payload.tp_points if pos == "BUY" else entry - payload.tp_points
                exit_price = segment[-1]
                outcome = "open_end"
                for j in range(i + 1, len(segment)):
                    px = segment[j]
                    if pos == "BUY":
                        if px <= sl:
                            exit_price = sl
                            outcome = "loss"
                            break
                        if px >= tp:
                            exit_price = tp
                            outcome = "win"
                            break
                    else:
                        if px >= sl:
                            exit_price = sl
                            outcome = "loss"
                            break
                        if px <= tp:
                            exit_price = tp
                            outcome = "win"
                            break

                raw_pnl = (exit_price - entry) if pos == "BUY" else (entry - exit_price)
                trade_pnl = raw_pnl - payload.commission_per_trade
                net_pnl += trade_pnl
                if trade_pnl > 0:
                    gross_profit += trade_pnl
                elif trade_pnl < 0:
                    gross_loss += abs(trade_pnl)
                trades += 1
                if outcome == "win":
                    wins += 1
                elif outcome == "loss":
                    losses += 1

                if net_pnl > peak:
                    peak = net_pnl
                dd = peak - net_pnl
                if dd > max_dd:
                    max_dd = dd
                i = j + 1 if outcome != "open_end" else len(segment)
            else:
                i += 1

        closed = wins + losses
        wr = round((wins / closed) * 100, 2) if closed > 0 else 0.0
        pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None
        avg_pnl = round(net_pnl / trades, 4) if trades > 0 else 0.0
        return {
            "bars": len(segment),
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "win_rate_closed": wr,
            "profit_factor": pf,
            "avg_pnl_points": avg_pnl,
            "net_pnl_points": round(net_pnl, 4),
            "max_drawdown_points": round(max_dd, 4),
        }

    train_res = simulate_slice(prices[:split_idx])
    test_res = simulate_slice(prices[split_idx:])
    return {
        "status": "ok",
        "source_type": "backtest_user_series",
        "spread_used": payload.spread,
        "slippage_used": payload.slippage_points,
        "commission_per_trade": payload.commission_per_trade,
        "train_in_sample": train_res,
        "test_out_of_sample": test_res,
    }


@app.post("/api/telegram/send")
async def send_telegram_signal(payload: TelegramSendRequest):
    if not payload.bot_token or not payload.chat_id:
        return {"status": "error", "message": "Token o Chat ID Telegram mancanti."}

    url = f"https://api.telegram.org/bot{payload.bot_token.strip()}/sendMessage"
    payload_data = {
        "chat_id": payload.chat_id.strip(),
        "text": payload.message,
        "parse_mode": "HTML",
    }

    try:
        data = json.dumps(payload_data).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res = json.loads(response.read().decode("utf-8"))
            if res.get("ok"):
                return {"status": "success", "message": "Segnale inviato con successo!"}
            else:
                return {"status": "error", "message": res.get("description", "Errore Telegram")}
    except Exception as e:
        return {"status": "error", "message": f"Errore di rete: {str(e)}"}


@app.get("/", response_class=HTMLResponse)
@app.get("/signals", response_class=HTMLResponse)
@app.get("/{full_path:path}", response_class=HTMLResponse)
def serve_home(full_path: str = ""):
    return """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Apex Lab - EV, Rischio & Backtest</title>
    <style>
        :root {
            --bg-body: #f8fafc;
            --bg-card: #ffffff;
            --border-subtle: #cbd5e1;
            --accent-primary: #0284c7;
            --accent-success: #059669;
            --accent-danger: #dc2626;
            --accent-warning: #d97706;
            --text-main: #0f172a;
            --text-muted: #475569;
            --shadow-card: 0 10px 30px -5px rgba(2, 132, 199, 0.08);
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --bg-body: #010409;
                --bg-card: #0d1117;
                --border-subtle: #30363d;
                --accent-primary: #38bdf8;
                --accent-success: #34d399;
                --accent-danger: #f87171;
                --accent-warning: #fbbf24;
                --text-main: #f0f6fc;
                --text-muted: #8b949e;
                --shadow-card: 0 20px 40px -10px rgba(0, 0, 0, 0.8);
            }
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-main);
            margin: 0;
            padding: 16px;
            -webkit-tap-highlight-color: transparent;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            background: var(--bg-card);
            padding: 16px 20px;
            border-radius: 20px;
            border: 1px solid var(--border-subtle);
            box-shadow: var(--shadow-card);
        }
        h1 {
            font-size: 1.2rem;
            margin: 0;
            color: var(--accent-primary);
            letter-spacing: -0.3px;
            font-weight: 900;
        }
        .badge {
            font-size: 0.7rem;
            background: rgba(52, 211, 153, 0.15);
            color: var(--accent-success);
            padding: 6px 12px;
            border-radius: 9999px;
            font-weight: 900;
            letter-spacing: 0.3px;
        }
        .badge-protection {
            background: rgba(248, 113, 113, 0.15) !important;
            color: var(--accent-danger) !important;
            animation: pulse 1s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        .card {
            background: var(--bg-card);
            border-radius: 20px;
            padding: 18px;
            margin-bottom: 16px;
            border: 1px solid var(--border-subtle);
            box-shadow: var(--shadow-card);
        }
        label {
            font-size: 0.72rem;
            color: var(--text-muted);
            display: block;
            margin-bottom: 8px;
            text-transform: uppercase;
            font-weight: 800;
            letter-spacing: 0.8px;
        }
        select, input[type="text"], input[type="number"], textarea {
            width: 100%;
            padding: 12px 14px;
            background-color: var(--bg-body);
            color: var(--text-main);
            border: 1px solid var(--border-subtle);
            border-radius: 14px;
            font-size: 0.9rem;
            font-weight: 700;
            outline: none;
            box-sizing: border-box;
            margin-bottom: 12px;
            transition: all 0.2s ease;
        }
        select:focus, input:focus, textarea:focus {
            border-color: var(--accent-primary);
            box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.25);
        }
        .tf-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-bottom: 14px;
        }
        .tf-btn {
            background-color: var(--bg-body);
            border: 1px solid var(--border-subtle);
            color: var(--text-muted);
            padding: 10px 0;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 700;
            cursor: pointer;
            text-align: center;
            transition: all 0.2s ease;
        }
        .tf-btn.active {
            background: var(--accent-primary);
            border-color: var(--accent-primary);
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(2, 132, 199, 0.4);
        }
        .chart-container {
            width: 100%;
            height: 240px;
            background-color: var(--bg-body);
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid var(--border-subtle);
            margin-bottom: 14px;
        }
        .btn-group {
            display: flex;
            gap: 8px;
        }
        .btn {
            flex: 1;
            background: var(--accent-primary);
            color: #ffffff;
            border: none;
            padding: 14px;
            border-radius: 14px;
            font-size: 0.9rem;
            font-weight: 900;
            cursor: pointer;
            box-shadow: 0 6px 16px rgba(2, 132, 199, 0.35);
            transition: all 0.2s ease;
        }
        .btn-secondary {
            background: var(--bg-body);
            border: 1px solid var(--border-subtle);
            color: var(--text-main);
            flex: 0.4;
            box-shadow: none;
        }
        .btn-success {
            background: var(--accent-success);
            color: white;
            box-shadow: 0 6px 16px rgba(5, 150, 105, 0.35);
            font-size: 0.85rem;
        }
        .btn-bep {
            background: var(--accent-warning);
            color: white;
            box-shadow: 0 6px 16px rgba(217, 119, 6, 0.35);
            font-size: 0.85rem;
        }
        .btn-danger {
            background: var(--accent-danger);
            color: white;
            box-shadow: 0 6px 16px rgba(220, 38, 38, 0.35);
            font-size: 0.85rem;
        }
        .btn-scalp {
            background: linear-gradient(135deg, #7c3aed, #4c1d95);
            color: white;
            box-shadow: 0 6px 16px rgba(124, 58, 237, 0.35);
        }
        .btn:active {
            transform: scale(0.98);
        }
        .signal-container {
            display: none;
            margin-top: 16px;
            background-color: var(--bg-body);
            padding: 18px;
            border-radius: 16px;
            border-left: 6px solid var(--accent-success);
            border: 1px solid var(--border-subtle);
        }
        .buy { color: var(--accent-success); font-weight: 900; font-size: 1.1rem; }
        .sell { color: var(--accent-danger); font-weight: 900; font-size: 1.1rem; }
        .data-row {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding: 8px 0;
            border-bottom: 1px solid var(--border-subtle);
            font-size: 0.86rem;
        }
        .data-row:last-child { border-bottom: none; }
        .history-box {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 8px;
            max-height: 150px;
            overflow-y: auto;
            font-family: monospace;
            background: var(--bg-body);
            padding: 12px;
            border-radius: 12px;
            border: 1px solid var(--border-subtle);
        }
        .toggle-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background-color: var(--bg-body);
            padding: 14px 16px;
            border-radius: 14px;
            border: 1px solid var(--border-subtle);
            margin-bottom: 14px;
        }
        .switch {
            position: relative;
            display: inline-block;
            width: 50px;
            height: 28px;
        }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
            background-color: #8b949e; transition: .3s; border-radius: 28px;
        }
        .slider:before {
            position: absolute; content: ""; height: 22px; width: 22px; left: 3px; bottom: 3px;
            background-color: white; transition: .3s; border-radius: 50%;
        }
        input:checked + .slider { background-color: var(--accent-success); }
        input:checked + .slider:before { transform: translateX(22px); }
    </style>
</head>
<body>

    <div class="header">
        <h1>APEX LAB</h1>
        <div id="header-badge" class="badge">EV + RISK + BACKTEST</div>
    </div>

    <!-- MONITOR PERSISTENTE -->
    <div class="card" style="border-left: 6px solid var(--accent-success);" id="monitor-card">
        <div style="font-size: 0.8rem; font-weight: 900; color: var(--accent-success); margin-bottom: 10px;">MONITOR STATO & REGISTRO (LOG MANUALE / PAPER)</div>
        <div class="data-row">
            <span>Fase / Stato Motore:</span>
            <strong id="ai-status-text" style="color: var(--accent-success);">In attesa di analisi</strong>
        </div>
        <div class="data-row">
            <span>Win Rate Registrato (Senza BEP):</span>
            <strong id="stat-winrate" style="color: var(--accent-primary);">0.00% (0 Win / 0 Loss / 0 BEP)</strong>
        </div>
        <div class="data-row">
            <span>Segnali Salvati / BUY-SELL / Non Eseguiti:</span>
            <strong id="stat-logged">0 / 0-0 / 0</strong>
        </div>
        <div class="data-row">
            <span>Costo Spread Sommato (Log Eseguiti):</span>
            <strong id="stat-spread">0</strong>
        </div>
    </div>

    <!-- CONTROLLO RISCHIO & DIMENSIONAMENTO -->
    <div class="card">
        <div style="font-size: 0.8rem; font-weight: 900; color: var(--accent-primary); margin-bottom: 10px;">CONTROLLO RISCHIO & SIZE INDICATIVA</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
            <div>
                <label for="risk-capital">Capitale Riferimento (€/$):</label>
                <input type="text" id="risk-capital" value="1000">
            </div>
            <div>
                <label for="risk-pct">Rischio Max Trade (%):</label>
                <input type="text" id="risk-pct" value="1.0">
            </div>
        </div>
        <div class="data-row">
            <span>Budget Rischio per Trade:</span>
            <strong id="risk-budget-val">10.00</strong>
        </div>
        <div class="data-row">
            <span>Nota Disciplina Rischio:</span>
            <strong id="risk-note-val" style="color: var(--text-muted); text-align: right; max-width: 65%;">Mai aumentare la size dopo una perdita</strong>
        </div>
    </div>

    <!-- CONFIGURAZIONE TELEGRAM -->
    <div class="card">
        <div class="toggle-container">
            <div>
                <span style="font-size: 0.8rem; font-weight: 900; color: var(--text-main);">INVIO ISTANTANEO TELEGRAM</span>
                <span style="font-size: 0.65rem; color: var(--text-muted); display: block;">Invia il segnale in chat privata</span>
            </div>
            <label class="switch">
                <input type="checkbox" id="telegram-toggle" checked>
                <span class="slider"></span>
            </label>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
            <div>
                <label>Telegram Bot Token:</label>
                <input type="text" id="tg-token" placeholder="Token bot..." style="font-size: 0.78rem;">
            </div>
            <div>
                <label>Telegram Chat ID:</label>
                <input type="text" id="tg-chatid" placeholder="Chat ID..." style="font-size: 0.78rem;">
            </div>
        </div>
    </div>

    <!-- MOTORE SEGNALI + CONTROLLI -->
    <div class="card">
        <label for="strategy-mode">Modalità Operativa:</label>
        <select id="strategy-mode" onchange="onModeChange()">
            <option value="standard">Trade Normale (Regole Trend + Controllo Rischio)</option>
            <option value="scalp">Scalp Veloce (Range Ridotto + Controllo Spread)</option>
        </select>

        <label for="asset-select">Seleziona Asset:</label>
        <select id="asset-select" onchange="updateChartSymbol()">
            <optgroup label="Mercati Principali">
                <option value="XAU/USD">Oro (XAU/USD)</option>
                <option value="NAS100">Nasdaq 100 (NAS100)</option>
                <option value="EUR/USD">Euro / Dollaro (EUR/USD)</option>
                <option value="GBP/USD">Sterlina / Dollaro (GBP/USD)</option>
            </optgroup>
            <optgroup label="Criptovalute (H24)">
                <option value="BTC/USD">Bitcoin (BTC/USD)</option>
                <option value="ETH/USD">Ethereum (ETH/USD)</option>
                <option value="SOL/USD">Solana (SOL/USD)</option>
                <option value="NEAR/USD">NEAR Protocol (NEAR/USD)</option>
                <option value="SUI/USD">Sui (SUI/USD)</option>
                <option value="DOGE/USD">Dogecoin (DOGE/USD)</option>
                <option value="SHIB/USD">Shiba Inu (SHIB/USD)</option>
                <option value="XRP/USD">Ripple (XRP/USD)</option>
            </optgroup>
        </select>

        <label>Grafico Live TradingView:</label>
        <div class="chart-container" id="tradingview_widget"></div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
            <div>
                <label for="live-price-input" style="color: var(--accent-primary);">Prezzo Corrente:</label>
                <input type="text" id="live-price-input" value="3934.50">
            </div>
            <div>
                <label for="spread-input">Spread Stimato:</label>
                <input type="text" id="spread-input" value="0.30">
            </div>
        </div>

        <label for="series-input">Serie Chiusure Recenti (Opzionale, virgola/spazio per EMA/RSI/Fase):</label>
        <input type="text" id="series-input" placeholder="Es: 3530.1, 3531.5, 3533.0, 3534.2, 3536.0, 3538.1">

        <label>Timeframe:</label>
        <div class="tf-grid">
            <div class="tf-btn active" onclick="setTF(this, 'M1')">M1</div>
            <div class="tf-btn" onclick="setTF(this, 'M5')">M5</div>
            <div class="tf-btn" onclick="setTF(this, 'M15')">M15</div>
            <div class="tf-btn" onclick="setTF(this, 'H1')">H1</div>
        </div>

        <div class="btn-group">
            <button type="button" id="gen-btn" class="btn btn-success" style="padding: 15px;" onclick="generaSegnale()">GENERA SEGNALE</button>
            <button type="button" class="btn btn-secondary" style="padding: 15px; font-size: 0.78rem;" onclick="logNonEseguito()">SALVA SOLO LOG</button>
        </div>
    </div>

    <!-- REGISTRAZIONE ESITO CON BEP -->
    <div class="card" style="border-left: 6px solid var(--accent-success);">
        <div style="font-size: 0.78rem; color: var(--accent-success); margin-bottom: 10px; font-weight: 900;">REGISTRA ESITO TRADE</div>
        <div class="btn-group">
            <button type="button" class="btn btn-success" onclick="registraEsito('win')">WIN</button>
            <button type="button" class="btn btn-bep" onclick="registraEsito('bep')">BEP</button>
            <button type="button" class="btn btn-danger" onclick="registraEsito('loss')">LOSS</button>
        </div>
    </div>

    <!-- BOX RISULTATO SEGNALE -->
    <div id="signal-box" class="card signal-container">
        <div id="signal-title-box" style="font-size: 0.78rem; color: var(--accent-success); margin-bottom: 10px; font-weight: 900;">SEGNALE GENERATO</div>
        <div class="data-row">
            <span>Asset & Timeframe:</span>
            <strong id="res-asset">--</strong>
        </div>
        <div class="data-row">
            <span>Direzione, Fase & Classe:</span>
            <span id="res-direction">--</span>
        </div>
        <div class="data-row">
            <span>Ingresso / SL / TP (R:R):</span>
            <strong id="res-levels">--</strong>
        </div>
        <div class="data-row">
            <span>Expected Value (Punti, Stima):</span>
            <strong id="res-ev" style="color: var(--accent-primary);">--</strong>
        </div>
        <div class="data-row">
            <span>Size Indicativa (da Rischio %):</span>
            <strong id="res-size">--</strong>
        </div>
        <div class="data-row">
            <span>Stima Probabilità TP vs SL (Indicativa):</span>
            <strong id="res-prob" style="color: var(--accent-primary);">--</strong>
        </div>
        <div class="data-row">
            <span>Motivo Tecnico & Durata Attesa:</span>
            <strong id="res-reason" style="text-align: right; max-width: 65%;">--</strong>
        </div>
        <div class="data-row">
            <span>Avvisi / Invalidazione:</span>
            <strong id="res-invalid" style="color: var(--accent-warning); text-align: right; max-width: 65%;">--</strong>
        </div>
        <div class="data-row">
            <span>Telegram:</span>
            <strong id="res-tg-status" style="color: var(--accent-primary);">--</strong>
        </div>
        <button type="button" id="copy-action-btn" class="btn btn-success" style="margin-top: 14px;" onclick="copiaSegnalePro()">COPIA SEGNALE PER TELEGRAM</button>
    </div>

    <!-- SIMULATORE BACKTEST SU DATI UTENTE -->
    <div class="card">
        <div style="font-size: 0.82rem; font-weight: 900; color: var(--accent-primary); margin-bottom: 10px;">BACKTEST SU TUA SERIE STORICA (TRAIN / OUT-OF-SAMPLE)</div>
        <textarea id="bt-prices" rows="3" placeholder="Incolla almeno 25 prezzi separati da virgola (es. 3520, 3522, 3521, 3525, ...)"></textarea>
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;">
            <div>
                <label>SL (punti):</label>
                <input type="text" id="bt-sl" value="2.5">
            </div>
            <div>
                <label>TP (punti):</label>
                <input type="text" id="bt-tp" value="3.5">
            </div>
            <div>
                <label>Slippage:</label>
                <input type="text" id="bt-slip" value="0.10">
            </div>
        </div>
        <button type="button" class="btn" style="width: 100%;" onclick="eseguiBacktest()">ESEGUI BACKTEST REALE</button>
        <div id="bt-output" class="history-box" style="margin-top: 12px;">Nessun backtest eseguito in questa sessione.</div>
    </div>

    <div class="card" style="padding: 12px 16px;">
        <label>Storico Sessione:</label>
        <div id="history-log" class="history-box">Pronto...</div>
    </div>

    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script>
        let currentTF = 'M1';
        let tvWidget = null;
        let lastSignalData = {};

        let localStats = {
            total: 0,
            wins: 0,
            losses: 0,
            beps: 0,
            consecutive_losses: 0,
            shield_active: false,
            logged_signals: 0,
            unexecuted_monitored: 0,
            buy_signals: 0,
            sell_signals: 0,
            logged_spread_cost: 0
        };

        function parseNum(val, fallback = NaN) {
            if (typeof val === 'number') return Number.isFinite(val) ? val : fallback;
            if (!val) return fallback;
            let cleaned = String(val).trim().replace(/\s+/g, '');
            if (cleaned.includes(',') && cleaned.includes('.')) {
                if (cleaned.lastIndexOf(',') > cleaned.lastIndexOf('.')) {
                    cleaned = cleaned.replace(/\./g, '').replace(',', '.');
                } else {
                    cleaned = cleaned.replace(/,/g, '');
                }
            } else if (cleaned.includes(',')) {
                cleaned = cleaned.replace(',', '.');
            }
            let n = Number(cleaned);
            return Number.isFinite(n) ? n : fallback;
        }

        function refreshRiskDisplay() {
            let cap = parseNum(document.getElementById('risk-capital').value, 1000);
            let pct = parseNum(document.getElementById('risk-pct').value, 1.0);
            if (cap < 0) cap = 0;
            if (pct < 0) pct = 0;
            if (pct > 5) pct = 5;
            let budget = (cap * pct) / 100;
            document.getElementById('risk-budget-val').innerText = budget.toFixed(2);
            document.getElementById('risk-note-val').innerText = localStats.shield_active
                ? `In cautela (${localStats.consecutive_losses} loss): mantieni size ridotta o invariata`
                : "Mai aumentare la size dopo una perdita";
        }

        document.getElementById('risk-capital').addEventListener('input', refreshRiskDisplay);
        document.getElementById('risk-pct').addEventListener('input', refreshRiskDisplay);

        function onModeChange() {
            let mode = document.getElementById('strategy-mode').value;
            let genBtn = document.getElementById('gen-btn');
            let copyBtn = document.getElementById('copy-action-btn');
            if (mode === 'scalp') {
                genBtn.className = 'btn btn-scalp';
                copyBtn.className = 'btn btn-scalp';
            } else {
                genBtn.className = 'btn btn-success';
                copyBtn.className = 'btn btn-success';
            }
        }

        function updateUIStats() {
            let activeTrades = localStats.total - localStats.beps;
            let wr = activeTrades > 0 ? ((localStats.wins / activeTrades) * 100).toFixed(2) : "0.00";
            document.getElementById('stat-winrate').innerText = `${wr}% (${localStats.wins} Win / ${localStats.losses} Loss / ${localStats.beps} BEP)`;
            document.getElementById('stat-logged').innerText = `${localStats.logged_signals} / ${localStats.buy_signals}-${localStats.sell_signals} / ${localStats.unexecuted_monitored}`;
            document.getElementById('stat-spread').innerText = String(localStats.logged_spread_cost);

            let badgeEl = document.getElementById('header-badge');
            let monitorCard = document.getElementById('monitor-card');
            if (localStats.shield_active) {
                badgeEl.className = "badge badge-protection";
                badgeEl.innerText = `CAUTELA (Loss: ${localStats.consecutive_losses})`;
                monitorCard.style.borderLeft = "6px solid var(--accent-danger)";
            } else {
                badgeEl.className = "badge";
                badgeEl.innerText = "EV + RISK + BACKTEST";
                monitorCard.style.borderLeft = "6px solid var(--accent-success)";
            }
            refreshRiskDisplay();
        }

        async function fetchStats() {
            try {
                let res = await fetch('/api/stats');
                let data = await res.json();
                if (data) {
                    localStats.total = data.total_trades || 0;
                    localStats.wins = data.wins || 0;
                    localStats.losses = data.losses || 0;
                    localStats.beps = data.beps || 0;
                    localStats.consecutive_losses = data.consecutive_losses || 0;
                    localStats.shield_active = Boolean(data.shield_active);
                    localStats.logged_signals = data.logged_signals || 0;
                    localStats.unexecuted_monitored = data.unexecuted_monitored || 0;
                    localStats.buy_signals = data.buy_signals || 0;
                    localStats.sell_signals = data.sell_signals || 0;
                    localStats.logged_spread_cost = data.logged_spread_cost || 0;
                    updateUIStats();
                }
            } catch (e) {}
        }

        function registraEsito(resultType) {
            let mode = document.getElementById('strategy-mode').value;
            let isScalp = mode === 'scalp';

            localStats.total++;
            if (resultType === 'win') {
                localStats.wins++;
                localStats.consecutive_losses = 0;
                localStats.shield_active = false;
            } else if (resultType === 'loss') {
                localStats.losses++;
                localStats.consecutive_losses++;
                localStats.shield_active = true;
            } else if (resultType === 'bep') {
                localStats.beps++;
            }

            updateUIStats();
            let logBox = document.getElementById('history-log');
            let nowStr = new Date().toTimeString().split(' ')[0];
            let msgText = `[${nowStr}] Esito registrato: ${resultType.toUpperCase()} (${isScalp ? 'SCALP' : 'NORMALE'})<br>`;
            logBox.innerHTML = msgText + logBox.innerHTML;

            fetch('/api/trade/result', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ result_type: resultType, is_scalp: isScalp })
            }).then(() => fetchStats()).catch(() => {});
        }

        fetchStats();
        refreshRiskDisplay();

        function initChart(symbolCode) {
            document.getElementById('tradingview_widget').innerHTML = "";
            tvWidget = new TradingView.widget({
                "autosize": true,
                "symbol": symbolCode,
                "interval": "1",
                "timezone": "Etc/UTC",
                "theme": "dark",
                "style": "1",
                "locale": "it",
                "toolbar_bg": "#0d1117",
                "enable_publishing": false,
                "hide_top_toolbar": false,
                "hide_legend": false,
                "save_image": false,
                "container_id": "tradingview_widget"
            });
        }

        function updateChartSymbol() {
            let asset = document.getElementById('asset-select').value;
            let tvSymbol = "OANDA:XAUUSD";
            let defaultP = "3934.50";
            let defaultSp = "0.30";
            if (asset.includes("NAS100")) { tvSymbol = "CAPITALCOM:US100"; defaultP = "20500.00"; defaultSp = "1.50"; }
            else if (asset.includes("EUR")) { tvSymbol = "FX:EURUSD"; defaultP = "1.0845"; defaultSp = "0.0002"; }
            else if (asset.includes("GBP")) { tvSymbol = "FX:GBPUSD"; defaultP = "1.3020"; defaultSp = "0.0003"; }
            else if (asset.includes("BTC")) { tvSymbol = "BITSTAMP:BTCUSD"; defaultP = "67500.00"; defaultSp = "12.00"; }
            else if (asset.includes("ETH")) { tvSymbol = "BITSTAMP:ETHUSD"; defaultP = "2650.00"; defaultSp = "1.50"; }
            else if (asset.includes("SOL")) { tvSymbol = "BITSTAMP:SOLUSD"; defaultP = "104.80"; defaultSp = "0.15"; }
            else if (asset.includes("NEAR")) { tvSymbol = "BINANCE:NEARUSD"; defaultP = "5.25"; defaultSp = "0.0100"; }
            else if (asset.includes("SUI")) { tvSymbol = "COINBASE:SUIUSD"; defaultP = "1.00"; defaultSp = "0.0050"; }
            else if (asset.includes("DOGE")) { tvSymbol = "BITSTAMP:DOGEUSD"; defaultP = "0.1450"; defaultSp = "0.0003"; }
            else if (asset.includes("SHIB")) { tvSymbol = "BITSTAMP:SHIBUSD"; defaultP = "0.00001850"; defaultSp = "0.00000005"; }
            else if (asset.includes("XRP")) { tvSymbol = "BITSTAMP:XRPUSD"; defaultP = "0.5500"; defaultSp = "0.0005"; }
            document.getElementById('live-price-input').value = defaultP;
            document.getElementById('spread-input').value = defaultSp;
            initChart(tvSymbol);
        }

        initChart("OANDA:XAUUSD");

        function setTF(element, tf) {
            document.querySelectorAll('.tf-btn').forEach(btn => btn.classList.remove('active'));
            element.classList.add('active');
            currentTF = tf;
        }

        function parseSeries() {
            let raw = document.getElementById('series-input').value.trim();
            if (!raw) return [];
            return raw.split(/[;\s]+/).map(tok => parseNum(tok)).filter(n => !isNaN(n) && n > 0);
        }

        function calcEMA(arr, period) {
            let k = 2 / (period + 1);
            let ema = [arr[0]];
            for (let i = 1; i < arr.length; i++) {
                ema.push(arr[i] * k + ema[i - 1] * (1 - k));
            }
            return ema;
        }

        function calcRSI(arr, period = 14) {
            if (arr.length <= period) return null;
            let gains = 0, losses = 0;
            for (let i = arr.length - period; i < arr.length; i++) {
                let d = arr[i] - arr[i - 1];
                if (d > 0) gains += d;
                else losses += Math.abs(d);
            }
            let avgG = gains / period;
            let avgL = losses / period;
            if (avgL === 0) return avgG > 0 ? 100 : 50;
            return 100 - (100 / (1 + avgG / avgL));
        }

        async function generaSegnale(executedFlag = true) {
            let asset = document.getElementById('asset-select').value;
            let livePrice = parseNum(document.getElementById('live-price-input').value);
            let spread = parseNum(document.getElementById('spread-input').value, 0);
            let mode = document.getElementById('strategy-mode').value;
            let isScalp = mode === 'scalp';
            let tgToggle = document.getElementById('telegram-toggle').checked;

            if (isNaN(livePrice) || livePrice <= 0) {
                alert("Inserisci un prezzo valido (es. 3538.185 o 3538,185)!");
                return;
            }
            if (spread < 0) spread = 0;

            let decimals = 2;
            if (asset.includes("SHIB")) decimals = 8;
            else if (asset.includes("DOGE") || asset.includes("XRP") || asset.includes("EUR") || asset.includes("GBP") || asset.includes("SUI") || asset.includes("NEAR")) decimals = 4;

            let series = parseSeries();
            let direction = "BUY";
            let reason = "Analisi sul solo prezzo corrente (nessuna serie storica inserita)";
            let regime = "Dati limitati";
            let scorePoints = 50;
            let warnings = [];

            let maxNormalSpread = asset.includes("XAU") ? 1.5 : (asset.includes("NAS100") ? 5.0 : (asset.includes("BTC") ? 35.0 : (decimals === 4 ? 0.0008 : 2.0)));
            if (spread > maxNormalSpread) {
                warnings.push(`Spread alto (${spread})`);
                scorePoints -= 15;
            }

            let baseUnit = decimals === 8 ? Math.max(livePrice * 0.008, 0.0000004)
                : (decimals === 4 ? Math.max(livePrice * 0.0012, 0.0008)
                : Math.max(livePrice * 0.0005, 0.8));

            if (series.length >= 6) {
                let diffs = [];
                for (let i = 1; i < series.length; i++) diffs.push(Math.abs(series[i] - series[i - 1]));
                let avgMove = diffs.reduce((a, b) => a + b, 0) / diffs.length;
                if (avgMove > 0) baseUnit = Math.max(avgMove, baseUnit * 0.4);

                let lastStep = diffs[diffs.length - 1] || 0;
                if (lastStep > avgMove * 3.5 && avgMove > 0) {
                    warnings.push("Spike/movimento improvviso rispetto alla media recente");
                    regime = "Alta volatilità / spike";
                    scorePoints -= 10;
                }

                let fast = calcEMA(series, Math.min(4, series.length));
                let slow = calcEMA(series, Math.min(12, series.length));
                let lastF = fast[fast.length - 1];
                let lastS = slow[slow.length - 1];
                let rsiVal = calcRSI(series, Math.min(14, series.length - 1));

                let minP = Math.min(...series);
                let maxP = Math.max(...series);
                let spanP = maxP - minP;
                let relRange = spanP > 0 ? (livePrice - minP) / spanP : 0.5;

                let netChange = series[series.length - 1] - series[0];
                if (spanP < baseUnit * 1.5) {
                    regime = "Compressione / laterale";
                    scorePoints -= 5;
                } else if (netChange > baseUnit * 2.0 && lastF >= lastS) {
                    regime = "Trend rialzista";
                    scorePoints += 15;
                } else if (netChange < -baseUnit * 2.0 && lastF <= lastS) {
                    regime = "Trend ribassista";
                    scorePoints += 15;
                } else if (regime === "Dati limitati") {
                    regime = "Fase mista / possibile inversione";
                }

                if (lastF >= lastS) {
                    direction = "BUY";
                    scorePoints += 10;
                    reason = `EMA veloce >= lenta (${lastF.toFixed(decimals)} vs ${lastS.toFixed(decimals)})`;
                } else {
                    direction = "SELL";
                    scorePoints += 10;
                    reason = `EMA veloce < lenta (${lastF.toFixed(decimals)} vs ${lastS.toFixed(decimals)})`;
                }

                if (rsiVal !== null) {
                    reason += ` | RSI ${rsiVal.toFixed(1)}`;
                    if (direction === "BUY" && rsiVal > 75) {
                        warnings.push("RSI elevato (>75): rischio ritracciamento");
                        scorePoints -= 10;
                    } else if (direction === "SELL" && rsiVal < 25) {
                        warnings.push("RSI basso (<25): rischio rimbalzo");
                        scorePoints -= 10;
                    } else if ((direction === "BUY" && rsiVal >= 45 && rsiVal <= 70) || (direction === "SELL" && rsiVal <= 55 && rsiVal >= 30)) {
                        scorePoints += 8;
                    }
                }

                if (direction === "BUY" && relRange > 0.85) warnings.push("Prezzo vicino ai massimi del campione");
                if (direction === "SELL" && relRange < 0.15) warnings.push("Prezzo vicino ai minimi del campione");
            } else {
                warnings.push("Poche chiusure recenti: inserisci almeno 6 valori per fase e EMA/RSI");
                direction = (Math.round(livePrice * 100) % 2 === 0) ? "BUY" : "SELL";
            }

            if (localStats.shield_active) {
                warnings.push(`Ultima operazione in LOSS (serie loss: ${localStats.consecutive_losses})`);
                scorePoints -= 10;
            }

            let slDist = isScalp ? baseUnit * 2.2 : baseUnit * 3.2;
            let tpDist = isScalp ? baseUnit * 3.0 : baseUnit * 4.5;

            let slNum = direction === "BUY" ? livePrice - slDist : livePrice + slDist;
            let tpNum = direction === "BUY" ? livePrice + tpDist : livePrice - tpDist;

            let netRewardPts = Math.max(0, tpDist - spread);
            let netRiskPts = Math.max(0.00000001, slDist + spread);
            let rrRatio = (netRewardPts / netRiskPts).toFixed(2);

            scorePoints = Math.max(20, Math.min(92, scorePoints));
            let grade = "C";
            if (scorePoints >= 82) grade = "A++";
            else if (scorePoints >= 72) grade = "A+";
            else if (scorePoints >= 60) grade = "A";
            else if (scorePoints >= 45) grade = "B";

            // Stima prudente e indicativa, non una certezza
            let estProb = Math.max(35, Math.min(65, Math.round(scorePoints * 0.68)));
            let pWin = estProb / 100;
            let pLoss = 1 - pWin;
            let evPoints = (pWin * netRewardPts) - (pLoss * netRiskPts);

            let cap = parseNum(document.getElementById('risk-capital').value, 1000);
            let pct = Math.min(5, Math.max(0, parseNum(document.getElementById('risk-pct').value, 1.0)));
            let budget = (cap * pct) / 100;
            let sizeUnits = slDist > 0 ? (budget / slDist) : 0;

            let durationHint = currentTF === 'M1' ? "Breve (pochi minuti, attenzione a rumore)"
                : (currentTF === 'M5' ? "Breve-medio (decine di minuti)"
                : (currentTF === 'M15' ? "Medio (1-3 ore)" : "Più esteso (diverse ore)"));

            let invalidation = direction === "BUY"
                ? `Chiusura sotto ${slNum.toFixed(decimals)} o rottura struttura rialzista`
                : `Chiusura sopra ${slNum.toFixed(decimals)} o rottura struttura ribassista`;

            document.getElementById('ai-status-text').innerText = `${regime} (${series.length} chiusure)`;

            let cleanSymbol = asset.replace("/", "");
            lastSignalData = {
                symbol: cleanSymbol,
                asset: asset,
                tf: currentTF,
                dir: direction,
                regime: regime,
                entry: livePrice.toFixed(decimals),
                sl: slNum.toFixed(decimals),
                tp: tpNum.toFixed(decimals),
                rr: rrRatio,
                ev: evPoints.toFixed(decimals),
                size: sizeUnits.toFixed(2),
                grade: grade,
                scorePoints: scorePoints,
                estProb: estProb,
                reason: `${reason} | Durata: ${durationHint}`,
                invalidation: invalidation,
                warnings: warnings.length ? warnings.join("; ") : "Nessuna criticità rilevata"
            };

            document.getElementById('signal-box').style.display = 'block';
            document.getElementById('res-asset').innerText = `${asset} (${currentTF})`;
            let dirEl = document.getElementById('res-direction');
            dirEl.innerText = `${direction} | ${regime} — Classe ${grade} (${scorePoints}/100)`;
            dirEl.className = direction === 'BUY' ? 'buy' : 'sell';

            document.getElementById('res-levels').innerText = `Entry ${livePrice.toFixed(decimals)} | SL ${slNum.toFixed(decimals)} | TP ${tpNum.toFixed(decimals)} (R:R netto 1:${rrRatio})`;
            document.getElementById('res-ev').innerText = `${evPoints >= 0 ? '+' : ''}${evPoints.toFixed(decimals)} pt (al netto spread ${spread}, stima)`;
            document.getElementById('res-size').innerText = `${sizeUnits.toFixed(2)} unità/pt (rischio ${budget.toFixed(2)})`;
            document.getElementById('res-prob').innerText = `~${estProb}% TP vs ~${100 - estProb}% SL (stima indicativa)`;
            document.getElementById('res-reason').innerText = lastSignalData.reason;
            document.getElementById('res-invalid').innerText = `${invalidation} | Note: ${lastSignalData.warnings}`;

            await fetch('/api/signal/log', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    asset: asset,
                    timeframe: currentTF,
                    direction: direction,
                    entry: Number(livePrice.toFixed(decimals)),
                    sl: Number(slNum.toFixed(decimals)),
                    tp: Number(tpNum.toFixed(decimals)),
                    spread: spread,
                    grade: grade,
                    est_tp_prob: estProb,
                    ev_points: Number(evPoints.toFixed(decimals)),
                    executed: executedFlag,
                    notes: `${regime} - ${reason}`
                })
            }).then(() => fetchStats()).catch(() => {});

            let tgStatusEl = document.getElementById('res-tg-status');
            if (executedFlag && tgToggle) {
                let tgToken = document.getElementById('tg-token').value.trim();
                let tgChatId = document.getElementById('tg-chatid').value.trim();
                if (tgToken && tgChatId) {
                    tgStatusEl.innerText = "Invio in corso...";
                    let msg = `<b>SEGNALE ${direction} (${grade})</b>\n<b>Asset:</b> ${cleanSymbol} (${currentTF})\n<b>Fase:</b> ${regime}\n<b>Entry:</b> ${livePrice.toFixed(decimals)}\n<b>SL:</b> ${slNum.toFixed(decimals)}\n<b>TP:</b> ${tpNum.toFixed(decimals)}\n<b>EV stimato:</b> ${evPoints >= 0 ? '+' : ''}${evPoints.toFixed(decimals)} pt\n<b>Stima TP (indicativa):</b> ~${estProb}%\n<b>Motivo:</b> ${reason}`;
                    try {
                        let tgRes = await fetch('/api/telegram/send', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ bot_token: tgToken, chat_id: tgChatId, message: msg })
                        });
                        let tgData = await tgRes.json();
                        tgStatusEl.innerText = tgData.status === "success" ? "Inviato su Telegram" : "Errore: " + tgData.message;
                    } catch (e) {
                        tgStatusEl.innerText = "Errore di rete Telegram";
                    }
                } else {
                    tgStatusEl.innerText = "Token o Chat ID mancanti";
                }
            } else {
                tgStatusEl.innerText = executedFlag ? "Disattivato" : "Salvato solo come non eseguito";
            }

            let nowStr = new Date().toTimeString().split(' ')[0];
            let logBox = document.getElementById('history-log');
            logBox.innerHTML = `[${nowStr}] ${asset} (${currentTF}) ${direction} [${grade}] EV:${evPoints >= 0 ? '+' : ''}${evPoints.toFixed(decimals)} ~${estProb}% (${executedFlag ? 'Eseguito' : 'Non eseguito'})<br>` + logBox.innerHTML;
        }

        function logNonEseguito() {
            generaSegnale(false);
        }

        function copiaSegnalePro() {
            if (!lastSignalData.symbol) {
                alert("Genera prima un segnale!");
                return;
            }
            let text = `${lastSignalData.symbol} (${lastSignalData.tf}) - ${lastSignalData.dir} [${lastSignalData.grade}]\nFase: ${lastSignalData.regime}\nEntry: ${lastSignalData.entry}\nSL: ${lastSignalData.sl}\nTP: ${lastSignalData.tp} (R:R netto 1:${lastSignalData.rr})\nEV stimato: ${lastSignalData.ev} pt | Size ind.: ${lastSignalData.size}\nStima TP (indicativa): ~${lastSignalData.estProb}%\nInvalidazione: ${lastSignalData.invalidation}`;
            navigator.clipboard.writeText(text).then(() => alert("Segnale copiato!"));
        }

        async function eseguiBacktest() {
            let raw = document.getElementById('bt-prices').value.trim();
            let prices = raw.split(/[;\s]+/).map(tok => parseNum(tok)).filter(n => !isNaN(n) && n > 0);
            let slPoints = parseNum(document.getElementById('bt-sl').value, 2.5);
            let tpPoints = parseNum(document.getElementById('bt-tp').value, 3.5);
            let slippage = parseNum(document.getElementById('bt-slip').value, 0);
            let spread = parseNum(document.getElementById('spread-input').value, 0);

            let outEl = document.getElementById('bt-output');
            outEl.innerText = "Esecuzione in corso...";

            try {
                let res = await fetch('/api/backtest', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        prices: prices,
                        spread: spread,
                        commission_per_trade: 0.0,
                        slippage_points: slippage,
                        sl_points: slPoints,
                        tp_points: tpPoints,
                        train_ratio: 0.7
                    })
                });
                let data = await res.json();
                if (data.status !== "ok") {
                    outEl.innerText = data.message || "Errore backtest";
                    return;
                }
                let tr = data.train_in_sample;
                let te = data.test_out_of_sample;
                outEl.innerHTML =
                    `<b>TRAIN (70%):</b> Trade ${tr.trades} | W/L ${tr.wins}/${tr.losses} (${tr.win_rate_closed}%) | PF ${tr.profit_factor ?? 'n/d'} | PnL netto ${tr.net_pnl_points} | MaxDD ${tr.max_drawdown_points}<br>` +
                    `<b>TEST OUT-OF-SAMPLE (30%):</b> Trade ${te.trades} | W/L ${te.wins}/${te.losses} (${te.win_rate_closed}%) | PF ${te.profit_factor ?? 'n/d'} | PnL netto ${te.net_pnl_points} | MaxDD ${te.max_drawdown_points}`;
            } catch (e) {
                outEl.innerText = "Errore di connessione durante il backtest.";
            }
        }
    </script>
</body>
</html>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
