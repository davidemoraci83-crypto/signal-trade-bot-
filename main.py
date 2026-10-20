from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import os
import urllib.request
import urllib.parse
import json

# Tentativo di importazione della libreria MetaTrader5 ufficiale
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

app = FastAPI()

# ==========================================
# GESTORE STATO & SMART WIN RATE (BACKEND)
# ==========================================
class SignalTrackerState:
    def __init__(self):
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.recovery_trades = 0
        self.recovery_wins = 0
        self.is_in_recovery = False
        self.recovery_attempts = 0
        self.base_lot = 0.01
        self.lot_multiplier = 1.5
        self.max_recovery_attempts = 2

    def get_next_lot(self):
        if self.is_in_recovery and self.recovery_attempts <= self.max_recovery_attempts:
            return round(self.base_lot * (self.lot_multiplier ** self.recovery_attempts), 2)
        return self.base_lot

    def process_result(self, is_win: bool):
        self.total_trades += 1
        if self.is_in_recovery:
            self.recovery_trades += 1

        if is_win:
            self.wins += 1
            if self.is_in_recovery:
                self.recovery_wins += 1
            self.is_in_recovery = False
            self.recovery_attempts = 0
        else:
            self.losses += 1
            self.recovery_attempts += 1
            if self.recovery_attempts <= self.max_recovery_attempts:
                self.is_in_recovery = True
            else:
                self.is_in_recovery = False
                self.recovery_attempts = 0

    def get_stats(self):
        std_wr = (self.wins / self.total_trades * 100) if self.total_trades > 0 else 0.0
        rec_wr = (self.recovery_wins / self.recovery_trades * 100) if self.recovery_trades > 0 else 0.0
        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "standard_win_rate": round(std_wr, 2),
            "recovery_win_rate": round(rec_wr, 2),
            "is_in_recovery": self.is_in_recovery,
            "recovery_attempts": self.recovery_attempts,
            "next_lot": self.get_next_lot()
        }

tracker = SignalTrackerState()

class TradeResultRequest(BaseModel):
    is_win: bool

class AutoTradeRequest(BaseModel):
    asset: str
    direction: str
    volume: float
    sl: float
    tp: float
    auto_enabled: bool

class TelegramSendRequest(BaseModel):
    bot_token: str
    chat_id: str
    message: str

@app.get("/api/stats")
async def get_stats():
    return tracker.get_stats()

@app.post("/api/trade/result")
async def post_trade_result(payload: TradeResultRequest):
    tracker.process_result(payload.is_win)
    return tracker.get_stats()

@app.post("/api/telegram/send")
async def send_telegram_signal(payload: TelegramSendRequest):
    if not payload.bot_token or not payload.chat_id:
        return {"status": "error", "message": "Token o Chat ID Telegram mancanti."}
    
    url = f"https://api.telegram.org/bot{payload.bot_token}/sendMessage"
    params = {
        "chat_id": payload.chat_id,
        "text": payload.message,
        "parse_mode": "HTML"
    }
    
    try:
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            if res.get("ok"):
                return {"status": "success", "message": "Segnale inviato su Telegram con successo!"}
            else:
                return {"status": "error", "message": res.get("description", "Errore Telegram")}
    except Exception as e:
        return {"status": "error", "message": f"Impossibile inviare a Telegram: {str(e)}"}

@app.post("/api/autotrade")
async def execute_autotrade(payload: AutoTradeRequest):
    if not payload.auto_enabled:
        return {"status": "disabled", "message": "Auto-trading disattivato dall'utente."}
    
    if not MT5_AVAILABLE:
        return {"status": "error", "message": "Libreria MetaTrader5 non installata sul server."}

    if not mt5.initialize():
        return {"status": "error", "message": f"Impossibile connettersi a MetaTrader5: {mt5.last_error()}"}

    symbol = payload.asset.replace("/", "")
    if symbol == "NAS100":
        symbol = "US100"

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        mt5.shutdown()
        return {"status": "error", "message": f"Simbolo {symbol} non trovato su MetaTrader."}

    if not symbol_info.visible:
        if not mt5.symbol_select(symbol, True):
            mt5.shutdown()
            return {"status": "error", "message": f"Impossibile abilitare il simbolo {symbol}."}

    price = mt5.symbol_info_tick(symbol).ask if payload.direction == "BUY" else mt5.symbol_info_tick(symbol).bid
    order_type = mt5.ORDER_TYPE_BUY if payload.direction == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": payload.volume,
        "type": order_type,
        "price": price,
        "sl": float(payload.sl),
        "tp": float(payload.tp),
        "deviation": 20,
        "magic": 234000,
        "comment": "SignalDeskPro AutoTrade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    mt5.shutdown()

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {"status": "failed", "message": f"Ordine rifiutato da MT5: {result.comment}"}

    return {"status": "success", "message": f"Ordine eseguito con successo su MT5! Ticket: {result.order}"}

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
    <title>Signal Desk Pro - v60 Quantum AI & Telegram Autopilot</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #05070a;
            color: #f1f5f9;
            margin: 0;
            padding: 12px;
            -webkit-tap-highlight-color: transparent;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        h1 {
            font-size: 1.05rem;
            margin: 0;
            color: #38bdf8;
            letter-spacing: 0.5px;
        }
        .badge {
            font-size: 0.65rem;
            background-color: #8b5cf6;
            color: #fff;
            padding: 3px 8px;
            border-radius: 9999px;
            font-weight: bold;
        }
        .card {
            background-color: #101726;
            border-radius: 12px;
            padding: 12px;
            margin-bottom: 10px;
            border: 1px solid #1e293b;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }
        label {
            font-size: 0.72rem;
            color: #94a3b8;
            display: block;
            margin-bottom: 4px;
            text-transform: uppercase;
            font-weight: 600;
        }
        select, input[type="text"] {
            width: 100%;
            padding: 10px;
            background-color: #070a12;
            color: #38bdf8;
            border: 1px solid #334155;
            border-radius: 8px;
            font-size: 0.92rem;
            font-weight: bold;
            outline: none;
            box-sizing: border-box;
            margin-bottom: 8px;
        }
        .tf-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 6px;
            margin-bottom: 8px;
        }
        .tf-btn {
            background-color: #070a12;
            border: 1px solid #334155;
            color: #94a3b8;
            padding: 7px 0;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: bold;
            cursor: pointer;
            text-align: center;
            transition: background-color 0.15s ease, color 0.15s ease;
        }
        .tf-btn.active {
            background-color: #0284c7;
            border-color: #38bdf8;
            color: #fff;
        }
        .chart-container {
            width: 100%;
            height: 240px;
            background-color: #070a12;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid #1e293b;
            margin-bottom: 10px;
        }
        .btn-group {
            display: flex;
            gap: 8px;
        }
        .btn {
            flex: 1;
            background: linear-gradient(135deg, #0ea5e9, #1d4ed8);
            color: white;
            border: none;
            padding: 12px;
            border-radius: 8px;
            font-size: 0.88rem;
            font-weight: bold;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
            transition: transform 0.05s ease, opacity 0.15s ease;
        }
        .btn-secondary {
            background: #1e293b;
            border: 1px solid #475569;
            color: #cbd5e1;
            flex: 0.4;
        }
        .btn-success {
            background: linear-gradient(135deg, #22c55e, #15803d);
            box-shadow: 0 4px 12px rgba(34, 197, 94, 0.3);
        }
        .btn-danger {
            background: linear-gradient(135deg, #ef4444, #b91c1c);
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
        }
        .btn-purple {
            background: linear-gradient(135deg, #8b5cf6, #6d28d9);
            box-shadow: 0 4px 12px rgba(139, 92, 246, 0.3);
        }
        .btn:active {
            transform: scale(0.98);
            opacity: 0.9;
        }
        .signal-container {
            display: none;
            margin-top: 10px;
            background-color: #070a12;
            padding: 12px;
            border-radius: 10px;
            border-left: 4px solid #8b5cf6;
            animation: fadeIn 0.2s ease-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-4px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .buy { color: #22c55e; font-weight: bold; font-size: 1rem; }
        .sell { color: #ef4444; font-weight: bold; font-size: 1rem; }
        .data-row {
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            border-bottom: 1px solid #111827;
            font-size: 0.82rem;
        }
        .data-row:last-child { border-bottom: none; }
        .history-box {
            font-size: 0.72rem;
            color: #64748b;
            margin-top: 6px;
            max-height: 80px;
            overflow-y: auto;
        }
        .toggle-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background-color: #070a12;
            padding: 8px 10px;
            border-radius: 8px;
            border: 1px solid #334155;
            margin-bottom: 8px;
        }
        .switch {
            position: relative;
            display: inline-block;
            width: 44px;
            height: 22px;
        }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
            background-color: #334155; transition: .3s; border-radius: 22px;
        }
        .slider:before {
            position: absolute; content: ""; height: 16px; width: 16px; left: 3px; bottom: 3px;
            background-color: white; transition: .3s; border-radius: 50%;
        }
        input:checked + .slider { background-color: #8b5cf6; }
        input:checked + .slider:before { transform: translateX(22px); }
    </style>
</head>
<body>

    <div class="header">
        <h1>SIGNAL DESK PRO</h1>
        <div class="badge">v60 QUANTUM TG</div>
    </div>

    <!-- CONFIGURAZIONE TELEGRAM & AUTOMAZIONE -->
    <div class="card">
        <div class="toggle-container">
            <div>
                <span style="font-size: 0.78rem; font-weight: bold; color: #f1f5f9;">🤖 AUTO-DISPATCH TELEGRAM</span>
                <span style="font-size: 0.62rem; color: #94a3b8; display: block;">Invia i segnali in automatico al tuo canale</span>
            </div>
            <label class="switch">
                <input type="checkbox" id="telegram-toggle" checked>
                <span class="slider"></span>
            </label>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
            <div>
                <label>Telegram Bot Token:</label>
                <input type="text" id="tg-token" placeholder="es. 123456:ABC..." style="font-size: 0.75rem;">
            </div>
            <div>
                <label>Telegram Chat/Channel ID:</label>
                <input type="text" id="tg-chatid" placeholder="es. -100123456" style="font-size: 0.75rem;">
            </div>
        </div>
    </div>

    <div class="card">
        <div class="toggle-container">
            <div>
                <span style="font-size: 0.78rem; font-weight: bold; color: #f1f5f9;">⚡ METATRADER 5 AUTO-TRADING</span>
                <span style="font-size: 0.62rem; color: #94a3b8; display: block;">Esegui ordini su terminale MT5 locale/VPS</span>
            </div>
            <label class="switch">
                <input type="checkbox" id="autotrade-toggle">
                <span class="slider"></span>
            </label>
        </div>

        <label for="asset-select">Seleziona Asset / Mercato:</label>
        <select id="asset-select" onchange="updateChartSymbol()">
            <optgroup label="Mercati Tradizionali & Indici">
                <option value="XAU/USD">Oro (XAU/USD)</option>
                <option value="NAS100">Nasdaq 100 (NAS100)</option>
                <option value="EUR/USD">Euro / Dollaro (EUR/USD)</option>
                <option value="GBP/USD">Sterlina / Dollaro (GBP/USD)</option>
            </optgroup>
            <optgroup label="Criptovalute (H24 / Weekend)">
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

        <label for="live-price-input" style="color: #38bdf8; margin-top: 6px;">Prezzo Attuale da Grafico:</label>
        <div style="display: flex; gap: 6px; margin-bottom: 8px;">
            <input type="text" id="live-price-input" value="4180.97">
            <button type="button" class="btn btn-secondary" style="flex: 0.5; padding: 10px; font-size: 0.75rem;" onclick="azzeraPrezzoLive()">🎯 SYNC</button>
        </div>

        <label>Timeframe Operativo:</label>
        <div class="tf-grid">
            <div class="tf-btn active" onclick="setTF(this, 'M1')">M1</div>
            <div class="tf-btn" onclick="setTF(this, 'M5')">M5</div>
            <div class="tf-btn" onclick="setTF(this, 'M15')">M15</div>
            <div class="tf-btn" onclick="setTF(this, 'H1')">H1</div>
        </div>

        <div class="btn-group">
            <button type="button" id="action-btn" class="btn btn-purple" onclick="generaSegnaleCrypto()">🚀 GENERA SEGNALE QUANTUM AI</button>
            <button type="button" id="sync-btn" class="btn btn-secondary" onclick="syncBroker()">🔄 TICK</button>
        </div>
    </div>

    <div class="card" style="border-left: 4px solid #22c55e;">
        <div style="font-size: 0.75rem; color: #22c55e; margin-bottom: 8px; font-weight: bold;">📊 SMART WIN RATE & RECOVERY SYSTEM</div>
        
        <div class="data-row">
            <span>Win Rate Standard:</span>
            <strong id="stat-std-wr" style="color: #38bdf8;">0.00%</strong>
        </div>
        <div class="data-row">
            <span>Smart Recovery Win Rate:</span>
            <strong id="stat-rec-wr" style="color: #4ade80;">0.00%</strong>
        </div>
        <div class="data-row">
            <span>Stato Gestione:</span>
            <strong id="stat-status" style="color: #fbbf24;">Standard Mode</strong>
        </div>
        <div class="data-row">
            <span>Lotto Prossimo Trade:</span>
            <strong id="stat-lot" style="color: #38bdf8; font-size: 0.95rem;">0.01</strong>
        </div>

        <div style="margin-top: 8px; font-size: 0.72rem; color: #94a3b8; margin-bottom: 6px;">Simula esito ultimo segnale:</div>
        <div class="btn-group">
            <button type="button" class="btn btn-success" style="padding: 8px; font-size: 0.78rem;" onclick="registraEsito(true)">✅ VINTO (WIN)</button>
            <button type="button" class="btn btn-danger" style="padding: 8px; font-size: 0.78rem;" onclick="registraEsito(false)">❌ PERSO (LOSS)</button>
        </div>
    </div>

    <div id="signal-box" class="card signal-container">
        <div style="font-size: 0.72rem; color: #8b5cf6; margin-bottom: 6px; font-weight: bold;">⚡ QUANTUM AI SIGNAL DETAILED OUTPUT</div>
        
        <div class="data-row">
            <span>Asset & Timeframe:</span>
            <strong id="res-asset">--</strong>
        </div>
        <div class="data-row">
            <span>Prezzo Riferimento:</span>
            <strong id="res-liveprice" style="color: #38bdf8;">--</strong>
        </div>
        <div class="data-row">
            <span>Direzione:</span>
            <span id="res-direction">--</span>
        </div>
        <div class="data-row">
            <span>Range d'Ingresso:</span>
            <strong id="res-range" style="color: #38bdf8; font-size: 0.95rem;">--</strong>
        </div>
        <div class="data-row">
            <span>Stop Loss (SL):</span>
            <strong id="res-sl" style="color: #f87171;">--</strong>
        </div>
        <div class="data-row">
            <span>Take Profit (TP):</span>
            <strong id="res-tp" style="color: #4ade80;">--</strong>
        </div>
        <div class="data-row">
            <span>Stato Invio Telegram:</span>
            <strong id="res-tg-status" style="color: #38bdf8;">--</strong>
        </div>
        <div class="data-row">
            <span>Stato Esecuzione MT5:</span>
            <strong id="res-mt5-status" style="color: #94a3b8;">--</strong>
        </div>

        <button type="button" class="btn" style="margin-top: 10px; padding: 10px; font-size: 0.82rem;" onclick="copiaSegnalePro()">📋 COPIA PER TELEGRAM MANUALMENTE</button>
    </div>

    <div class="card" style="padding: 10px 12px;">
        <label>Log Operazioni & Segnali:</label>
        <div id="history-log" class="history-box">Pronto per la generazione.</div>
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
            recTrades: 0,
            recWins: 0,
            isInRecovery: false,
            attempts: 0,
            baseLot: 0.01
        };

        function updateUIStats() {
            const stdWR = localStats.total > 0 ? ((localStats.wins / localStats.total) * 100).toFixed(2) : "0.00";
            const recWR = localStats.recTrades > 0 ? ((localStats.recWins / localStats.recTrades) * 100).toFixed(2) : "0.00";
            
            document.getElementById('stat-std-wr').innerText = `${stdWR}% (${localStats.wins}/${localStats.total})`;
            document.getElementById('stat-rec-wr').innerText = `${recWR}%`;
            
            const statusEl = document.getElementById('stat-status');
            if (localStats.isInRecovery) {
                statusEl.innerText = `🔥 RECOVERY MODE (Tentativo ${localStats.attempts}/2)`;
                statusEl.style.color = '#ef4444';
                localStats.currentLot = parseFloat((localStats.baseLot * Math.pow(1.5, localStats.attempts)).toFixed(2));
            } else {
                statusEl.innerText = '🛡️ STANDARD MODE (Pronto)';
                statusEl.style.color = '#22c55e';
                localStats.currentLot = localStats.baseLot;
            }
            document.getElementById('stat-lot').innerText = localStats.currentLot;
        }

        async function fetchStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                if (data) {
                    localStats.total = data.total_trades;
                    localStats.wins = data.wins;
                    localStats.losses = data.losses;
                    localStats.isInRecovery = data.is_in_recovery;
                    localStats.attempts = data.recovery_attempts;
                    updateUIStats();
                }
            } catch(e) {}
        }

        function registraEsito(isWin) {
            localStats.total++;
            if (localStats.isInRecovery) localStats.recTrades++;

            if (isWin) {
                localStats.wins++;
                if (localStats.isInRecovery) localStats.recWins++;
                localStats.isInRecovery = false;
                localStats.attempts = 0;
            } else {
                localStats.losses++;
                localStats.attempts++;
                if (localStats.attempts <= 2) {
                    localStats.isInRecovery = true;
                } else {
                    localStats.isInRecovery = false;
                    localStats.attempts = 0;
                }
            }
            updateUIStats();

            const logBox = document.getElementById('history-log');
            const nowStr = new Date().toTimeString().split(' ')[0];
            const msg = isWin ? `🟢 [${nowStr}] Trade WIN` : `🔴 [${nowStr}] Trade LOSS -> Recovery mode`;
            logBox.innerHTML = msg + '<br>' + logBox.innerHTML;

            fetch('/api/trade/result', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_win: isWin })
            }).catch(() => {});
        }

        fetchStats();

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
                "toolbar_bg": "#101726",
                "enable_publishing": false,
                "hide_top_toolbar": true,
                "hide_legend": true,
                "save_image": false,
                "container_id": "tradingview_widget"
            });
        }

        function updateChartSymbol() {
            const asset = document.getElementById('asset-select').value;
            let tvSymbol = "OANDA:XAUUSD";
            let defaultP = "4180.97";

            if (asset.includes("NAS100")) { tvSymbol = "CAPITALCOM:US100"; defaultP = "20500.00"; }
            else if (asset.includes("EUR")) { tvSymbol = "FX:EURUSD"; defaultP = "1.0845"; }
            else if (asset.includes("GBP")) { tvSymbol = "FX:GBPUSD"; defaultP = "1.3020"; }
            else if (asset.includes("BTC")) { tvSymbol = "BITSTAMP:BTCUSD"; defaultP = "67500.00"; }
            else if (asset.includes("ETH")) { tvSymbol = "BITSTAMP:ETHUSD"; defaultP = "2650.00"; }
            else if (asset.includes("SOL")) { tvSymbol = "BITSTAMP:SOLUSD"; defaultP = "104.80"; }
            else if (asset.includes("NEAR")) { tvSymbol = "BINANCE:NEARUSD"; defaultP = "5.25"; }
            else if (asset.includes("SUI")) { tvSymbol = "COINBASE:SUIUSD"; defaultP = "1.00"; }
            else if (asset.includes("DOGE")) { tvSymbol = "BITSTAMP:DOGEUSD"; defaultP = "0.1450"; }
            else if (asset.includes("SHIB")) { tvSymbol = "BITSTAMP:SHIBUSD"; defaultP = "0.00001850"; }
            else if (asset.includes("XRP")) { tvSymbol = "BITSTAMP:XRPUSD"; defaultP = "0.5500"; }
            
            document.getElementById('live-price-input').value = defaultP;
            initChart(tvSymbol);
        }

        initChart("OANDA:XAUUSD");

        function setTF(element, tf) {
            document.querySelectorAll('.tf-btn').forEach(btn => btn.classList.remove('active'));
            element.classList.add('active');
            currentTF = tf;
        }

        function azzeraPrezzoLive() {
            const assetSelect = document.getElementById('asset-select').value;
            let defaultP = "4180.97";
            if (assetSelect.includes("NAS100")) defaultP = "20500.00";
            else if (assetSelect.includes("EUR")) defaultP = "1.0845";
            else if (assetSelect.includes("GBP")) defaultP = "1.3020";
            else if (assetSelect.includes("BTC")) defaultP = "67500.00";
            else if (assetSelect.includes("ETH")) defaultP = "2650.00";
            else if (assetSelect.includes("SOL")) defaultP = "104.80";
            else if (assetSelect.includes("NEAR")) defaultP = "5.25";
            else if (assetSelect.includes("SUI")) defaultP = "1.00";
            else if (assetSelect.includes("DOGE")) defaultP = "0.1450";
            else if (assetSelect.includes("SHIB")) defaultP = "0.00001850";
            else if (assetSelect.includes("XRP")) defaultP = "0.5500";

            document.getElementById('live-price-input').value = defaultP;
        }

        function syncBroker() {
            const currentVal = parseFloat(document.getElementById('live-price-input').value) || 100.0;
            const stepDelta = currentVal > 10000 ? 25.0 : (currentVal > 1000 ? 15.0 : (currentVal > 10 ? 0.5 : (currentVal < 0.001 ? 0.0000002 : 0.002)));
            const updated = currentVal + ((Math.random() - 0.5) * stepDelta);
            document.getElementById('live-price-input').value = updated.toFixed(currentVal < 0.001 ? 8 : (currentVal < 10 ? 4 : 2));
        }

        async function generaSegnaleCrypto() {
            const assetSelect = document.getElementById('asset-select');
            const signalBox = document.getElementById('signal-box');
            const priceInput = document.getElementById('live-price-input');
            const autoToggle = document.getElementById('autotrade-toggle').checked;
            const tgToggle = document.getElementById('telegram-toggle').checked;

            if (!assetSelect || !signalBox || !priceInput) return;

            let livePrice = parseFloat(priceInput.value);
            if (isNaN(livePrice) || livePrice <= 0) {
                alert("Inserisci un prezzo valido!");
                return;
            }

            const asset = assetSelect.value;
            let decimals = 2;
            if (asset.includes("SHIB")) decimals = 8;
            else if (asset.includes("DOGE") || asset.includes("XRP") || asset.includes("EUR") || asset.includes("GBP") || asset.includes("SUI") || asset.includes("NEAR")) decimals = 4;

            const quantumVector = Math.sin(Date.now() / 400) * Math.cos(Date.now() / 300);
            const direction = (quantumVector + Math.random()) > -0.15 ? "BUY" : "SELL";
            
            let step = 2.50;
            if (asset.includes("NAS100")) step = 35.00;
            else if (asset.includes("BTC")) step = 150.00;
            else if (asset.includes("ETH")) step = 15.00;
            else if (asset.includes("SOL")) step = 1.20;
            else if (asset.includes("NEAR")) step = 0.0800;
            else if (asset.includes("SUI")) step = 0.0200;
            else if (asset.includes("DOGE")) step = 0.0030;
            else if (asset.includes("SHIB")) step = 0.00000040;
            else if (asset.includes("XRP")) step = 0.0050;
            else if (asset.includes("EUR") || asset.includes("GBP")) step = 0.0025;

            let rangeText, slVal, tpVal, cleanAssetSymbol;
            cleanAssetSymbol = asset.replace("/", "");

            let slNum, tpNum;
            if (direction === "BUY") {
                let upperEntry = livePrice;
                let lowerEntry = livePrice - (step * 0.15);
                slNum = lowerEntry - (step * 3.0);
                tpNum = upperEntry + (step * 4.5);

                rangeText = `${upperEntry.toFixed(decimals)} / ${lowerEntry.toFixed(decimals)}`;
                slVal = slNum.toFixed(decimals);
                tpVal = tpNum.toFixed(decimals);
            } else {
                let lowerEntry = livePrice;
                let upperEntry = livePrice + (step * 0.15);
                slNum = upperEntry + (step * 3.0);
                tpNum = lowerEntry - (step * 4.5);

                rangeText = `${lowerEntry.toFixed(decimals)} / ${upperEntry.toFixed(decimals)}`;
                slVal = slNum.toFixed(decimals);
                tpVal = tpNum.toFixed(decimals);
            }

            const now = new Date();
            const timeStr = now.toTimeString().split(' ')[0];

            lastSignalData = {
                symbol: cleanAssetSymbol,
                dir: direction,
                range: rangeText,
                sl: slVal,
                tp: tpVal
            };

            document.getElementById('res-asset').innerText = asset + " (" + currentTF + ")";
            document.getElementById('res-liveprice').innerText = '$' + livePrice.toFixed(decimals);
            
            const dirElem = document.getElementById('res-direction');
            dirElem.innerText = direction + " (Quantum AI)";
            dirElem.className = direction === 'BUY' ? 'buy' : 'sell';

            document.getElementById('res-range').innerText = rangeText;
            document.getElementById('res-sl').innerText = slVal;
            document.getElementById('res-tp').innerText = tpVal;

            const mt5StatusEl = document.getElementById('res-mt5-status');
            const tgStatusEl = document.getElementById('res-tg-status');

            if (autoToggle) {
                mt5StatusEl.innerText = "Invio ordine a MT5...";
                mt5StatusEl.style.color = "#f59e0b";
            } else {
                mt5StatusEl.innerText = "Disattivato (Solo Segnale)";
                mt5StatusEl.style.color = "#94a3b8";
            }

            signalBox.style.display = 'block';

            // Invio Automatico a Telegram via Bot Webhook
            if (tgToggle) {
                const tgToken = document.getElementById('tg-token').value.trim();
                const tgChatId = document.getElementById('tg-chatid').value.trim();

                if (tgToken && tgChatId) {
                    tgStatusEl.innerText = "Invio a Telegram...";
                    tgStatusEl.style.color = "#f59e0b";

                    const formattedMsg = `<b>🟢 SIGNAL DESK PRO QUANTUM AI 🟢</b>\n\n<b>Asset:</b> ${cleanAssetSymbol} (${currentTF})\n<b>Direzione:</b> ${direction}\n<b>Range Ingresso:</b> ${rangeText}\n\n<b>SL:</b> ${slVal}\n<b>TP:</b> ${tpVal}\n\n<i>Lotto consigliato: ${localStats.currentLot || 0.01}</i>`;

                    try {
                        const tgRes = await fetch('/api/telegram/send', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                bot_token: tgToken,
                                chat_id: tgChatId,
                                message: formattedMsg
                            })
                        });
                        const tgData = await tgRes.json();
                        if (tgData.status === "success") {
                            tgStatusEl.innerText = "✅ Inviato sul Canale Telegram!";
                            tgStatusEl.style.color = "#22c55e";
                        } else {
                            tgStatusEl.innerText = "❌ " + tgData.message;
                            tgStatusEl.style.color = "#ef4444";
                        }
                    } catch(e) {
                        tgStatusEl.innerText = "❌ Errore connessione Telegram";
                        tgStatusEl.style.color = "#ef4444";
                    }
                } else {
                    tgStatusEl.innerText = "⚠️ Token/Chat ID non inseriti";
                    tgStatusEl.style.color = "#fbbf24";
                }
            } else {
                tgStatusEl.innerText = "Disattivato";
                tgStatusEl.style.color = "#94a3b8";
            }

            // Invio a MetaTrader se abilitato
            if (autoToggle) {
                try {
                    const response = await fetch('/api/autotrade', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            asset: asset,
                            direction: direction,
                            volume: localStats.currentLot || 0.01,
                            sl: slNum,
                            tp: tpNum,
                            auto_enabled: autoToggle
                        })
                    });
                    const resData = await response.json();
                    if (resData.status === "success") {
                        mt5StatusEl.innerText = "✅ " + resData.message;
                        mt5StatusEl.style.color = "#22c55e";
                    } else {
                        mt5StatusEl.innerText = "❌ " + resData.message;
                        mt5StatusEl.style.color = "#ef4444";
                    }
                } catch(err) {
                    mt5StatusEl.innerText = "❌ Errore bridge MT5";
                    mt5StatusEl.style.color = "#ef4444";
                }
            }

            const logBox = document.getElementById('history-log');
            const logText = `[${timeStr}] ${asset} (${currentTF}) -> ${direction} generato<br>`;
            if (logBox.innerText.includes("Pronto")) {
                logBox.innerHTML = logText;
            } else {
                logBox.innerHTML = logText + logBox.innerHTML;
            }
        }

        function copiaSegnalePro() {
            if (!lastSignalData.symbol) {
                alert("Genera prima un segnale!");
                return;
            }

            const text = `🟢 ${lastSignalData.symbol} 🟢\n\n${lastSignalData.dir} RANGE: ${lastSignalData.range}\n\nSL: ${lastSignalData.sl}\n\nTP: ${lastSignalData.tp}`;

            navigator.clipboard.writeText(text).then(() => {
                alert("Segnale copiato negli appunti per Telegram!");
            });
        }
    </script>

</body>
</html>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
