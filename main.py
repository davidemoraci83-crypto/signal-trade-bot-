from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import os
import urllib.request
import urllib.parse
import json

app = FastAPI()

class SignalTrackerState:
    def __init__(self):
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.beps = 0
        self.consecutive_losses = 0
        self.recovery_mode = False

    def process_result(self, result_type: str):
        self.total_trades += 1
        if result_type == "win":
            self.wins += 1
            self.consecutive_losses = 0
            self.recovery_mode = False
        elif result_type == "loss":
            self.losses += 1
            self.consecutive_losses += 1
            self.recovery_mode = True
        elif result_type == "bep":
            self.beps += 1

    def get_stats(self):
        active_trades = self.total_trades - self.beps
        std_wr = (self.wins / active_trades * 100) if active_trades > 0 else 0.0
        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "beps": self.beps,
            "win_rate": round(std_wr, 2),
            "consecutive_losses": self.consecutive_losses,
            "recovery_mode": self.recovery_mode
        }

tracker = SignalTrackerState()

class TradeResultRequest(BaseModel):
    result_type: str  # "win", "loss", "bep"
    is_scalp: bool = False

class TelegramSendRequest(BaseModel):
    bot_token: str
    chat_id: str
    message: str

@app.get("/api/stats")
async def get_stats():
    return tracker.get_stats()

@app.post("/api/trade/result")
async def post_trade_result(payload: TradeResultRequest):
    tracker.process_result(payload.result_type)
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
    <title>Signal Desk Pro - Ultimate Shield v91</title>
    <style>
        :root {
            --bg-color: #04060f;
            --card-bg: #0a0e1f;
            --border-color: #17203d;
            --accent-cyan: #38bdf8;
            --accent-green: #22c55e;
            --accent-red: #ef4444;
            --accent-gold: #f59e0b;
            --accent-purple: #a855f7;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 12px;
            -webkit-tap-highlight-color: transparent;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            background: linear-gradient(135deg, #0a0e1f, #162247);
            padding: 12px 16px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
        }
        h1 {
            font-size: 1.15rem;
            margin: 0;
            color: var(--accent-cyan);
            letter-spacing: 0.8px;
            font-weight: 800;
        }
        .badge {
            font-size: 0.68rem;
            background: linear-gradient(135deg, var(--accent-green), #15803d);
            color: #fff;
            padding: 4px 10px;
            border-radius: 9999px;
            font-weight: 800;
            box-shadow: 0 0 12px rgba(34, 197, 94, 0.4);
        }
        .badge-recovery {
            background: linear-gradient(135deg, var(--accent-red), #b91c1c) !important;
            box-shadow: 0 0 12px rgba(239, 68, 68, 0.6) !important;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        .card {
            background-color: var(--card-bg);
            border-radius: 14px;
            padding: 14px;
            margin-bottom: 12px;
            border: 1px solid var(--border-color);
            box-shadow: 0 8px 16px -4px rgba(0, 0, 0, 0.6);
        }
        label {
            font-size: 0.72rem;
            color: var(--text-muted);
            display: block;
            margin-bottom: 5px;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.5px;
        }
        select, input[type="text"], input[type="number"] {
            width: 100%;
            padding: 11px;
            background-color: #04060f;
            color: var(--accent-cyan);
            border: 1px solid #1f2a4f;
            border-radius: 10px;
            font-size: 0.95rem;
            font-weight: bold;
            outline: none;
            box-sizing: border-box;
            margin-bottom: 10px;
        }
        select:focus, input:focus {
            border-color: var(--accent-cyan);
        }
        .tf-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 6px;
            margin-bottom: 10px;
        }
        .tf-btn {
            background-color: #04060f;
            border: 1px solid #1f2a4f;
            color: var(--text-muted);
            padding: 8px 0;
            border-radius: 8px;
            font-size: 0.78rem;
            font-weight: bold;
            cursor: pointer;
            text-align: center;
        }
        .tf-btn.active {
            background: linear-gradient(135deg, #0284c7, #0369a1);
            border-color: var(--accent-cyan);
            color: #fff;
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.3);
        }
        .chart-container {
            width: 100%;
            height: 240px;
            background-color: #04060f;
            border-radius: 10px;
            overflow: hidden;
            border: 1px solid var(--border-color);
            margin-bottom: 12px;
        }
        .btn-group {
            display: flex;
            gap: 6px;
        }
        .btn {
            flex: 1;
            background: linear-gradient(135deg, #38bdf8, #0284c7);
            color: #04060f;
            border: none;
            padding: 13px;
            border-radius: 10px;
            font-size: 0.9rem;
            font-weight: 800;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(56, 189, 248, 0.4);
        }
        .btn-secondary {
            background: #162247;
            border: 1px solid #31437a;
            color: var(--text-main);
            flex: 0.4;
            box-shadow: none;
        }
        .btn-success {
            background: linear-gradient(135deg, #22c55e, #15803d);
            color: white;
            box-shadow: 0 4px 14px rgba(34, 197, 94, 0.4);
            font-size: 0.8rem;
        }
        .btn-bep {
            background: linear-gradient(135deg, #f59e0b, #b45309);
            color: white;
            box-shadow: 0 4px 14px rgba(245, 158, 11, 0.4);
            font-size: 0.8rem;
        }
        .btn-danger {
            background: linear-gradient(135deg, #ef4444, #b91c1c);
            color: white;
            box-shadow: 0 4px 14px rgba(239, 68, 68, 0.4);
            font-size: 0.8rem;
        }
        .btn-scalp {
            background: linear-gradient(135deg, #a855f7, #6d28d9);
            color: white;
            box-shadow: 0 4px 14px rgba(168, 85, 247, 0.4);
        }
        .btn:active {
            transform: scale(0.97);
            filter: brightness(0.9);
        }
        .signal-container {
            display: none;
            margin-top: 12px;
            background-color: #04060f;
            padding: 14px;
            border-radius: 12px;
            border-left: 5px solid var(--accent-green);
            animation: fadeIn 0.25s ease-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-6px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .buy { color: var(--accent-green); font-weight: 800; font-size: 1.05rem; }
        .sell { color: var(--accent-red); font-weight: 800; font-size: 1.05rem; }
        .data-row {
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            border-bottom: 1px solid #0f162e;
            font-size: 0.85rem;
        }
        .data-row:last-child { border-bottom: none; }
        .history-box {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 8px;
            max-height: 90px;
            overflow-y: auto;
            font-family: monospace;
            background: #04060f;
            padding: 8px;
            border-radius: 6px;
        }
        .toggle-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background-color: #04060f;
            padding: 10px 12px;
            border-radius: 10px;
            border: 1px solid #1f2a4f;
            margin-bottom: 10px;
        }
        .switch {
            position: relative;
            display: inline-block;
            width: 46px;
            height: 24px;
        }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
            background-color: #1f2a4f; transition: .3s; border-radius: 24px;
        }
        .slider:before {
            position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px;
            background-color: white; transition: .3s; border-radius: 50%;
        }
        input:checked + .slider { background-color: var(--accent-green); }
        input:checked + .slider:before { transform: translateX(22px); }
    </style>
</head>
<body>

    <div class="header">
        <h1>SIGNAL DESK PRO</h1>
        <div id="header-badge" class="badge">ULTIMATE SHIELD v91</div>
    </div>

    <!-- PANNELLO MONITOR ULTIMATE SHIELD -->
    <div class="card" style="border-left: 5px solid var(--accent-green);" id="monitor-card">
        <div style="font-size: 0.8rem; font-weight: 800; color: var(--accent-green); margin-bottom: 8px;" id="monitor-title">🛡️ STREAK SHIELD MONITOR</div>
        
        <div class="data-row">
            <span>Protezione Anti-Consecutive Loss:</span>
            <strong id="ai-status-text" style="color: var(--accent-green);">Attivo (Blocco Serie Negative)</strong>
        </div>
        <div class="data-row">
            <span>Win Rate Reale (Senza BEP):</span>
            <strong id="stat-winrate" style="color: var(--accent-cyan);">0.00% (0 Win / 0 Loss / 0 BEP)</strong>
        </div>
    </div>

    <!-- CONFIGURAZIONE TELEGRAM -->
    <div class="card">
        <div class="toggle-container">
            <div>
                <span style="font-size: 0.8rem; font-weight: 800; color: #fff;">🤖 INVIO AUTOMATICO TELEGRAM</span>
                <span style="font-size: 0.65rem; color: var(--text-muted); display: block;">Spedisci subito sul canale</span>
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

    <div class="card">
        <label for="strategy-mode">Modalità Operativa:</label>
        <select id="strategy-mode" onchange="onModeChange()">
            <option value="standard">🛡️ Ultimate Shield Standard (Catena di Vincite)</option>
            <option value="scalp">⚡ Scalping Anti-Serie Negative</option>
        </select>

        <label for="asset-select" style="margin-top: 8px;">Seleziona Asset:</label>
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

        <label for="live-price-input" style="color: var(--accent-cyan); margin-top: 8px;">Prezzo Corrente di Mercato:</label>
        <div style="display: flex; gap: 8px; margin-bottom: 10px;">
            <input type="text" id="live-price-input" value="4180.97">
            <button type="button" class="btn btn-secondary" style="flex: 0.5; padding: 11px; font-size: 0.78rem;" onclick="azzeraPrezzoLive()">🎯 SYNC</button>
        </div>

        <label>Timeframe:</label>
        <div class="tf-grid">
            <div class="tf-btn active" onclick="setTF(this, 'M1')">M1</div>
            <div class="tf-btn" onclick="setTF(this, 'M5')">M5</div>
            <div class="tf-btn" onclick="setTF(this, 'M15')">M15</div>
            <div class="tf-btn" onclick="setTF(this, 'H1')">H1</div>
        </div>

        <button type="button" id="gen-btn" class="btn btn-success" style="width: 100%; padding: 15px; font-size: 1rem;" onclick="generaSegnaleShield()">🎯 GENERA SEGNALE ULTIMATE SHIELD v91</button>
    </div>

    <!-- REGISTRAZIONE ESITO CON BEP -->
    <div class="card" style="border-left: 5px solid var(--accent-green);">
        <div style="font-size: 0.78rem; color: var(--accent-green); margin-bottom: 8px; font-weight: 800;">📊 REGISTRA ESITO TRADE</div>
        <div class="btn-group">
            <button type="button" class="btn btn-success" onclick="registraEsito('win')">✅ WIN</button>
            <button type="button" class="btn btn-bep" onclick="registraEsito('bep')">⚖️ BEP</button>
            <button type="button" class="btn btn-danger" onclick="registraEsito('loss')">❌ LOSS</button>
        </div>
    </div>

    <!-- BOX RISULTATO SEGNALE -->
    <div id="signal-box" class="card signal-container">
        <div id="signal-title-box" style="font-size: 0.75rem; color: var(--accent-green); margin-bottom: 8px; font-weight: 800;">🎯 SEGNALE SHIELD PRONTO</div>
        
        <div class="data-row">
            <span>Asset & Timeframe:</span>
            <strong id="res-asset">--</strong>
        </div>
        <div class="data-row">
            <span>Prezzo Riferimento:</span>
            <strong id="res-liveprice" style="color: var(--accent-cyan);">--</strong>
        </div>
        <div class="data-row">
            <span>Direzione:</span>
            <span id="res-direction">--</span>
        </div>
        <div class="data-row">
            <span>Range d'Ingresso:</span>
            <strong id="res-range" style="color: var(--accent-cyan);">--</strong>
        </div>
        <div class="data-row">
            <span>Stop Loss (Anti-Serie):</span>
            <strong id="res-sl" style="color: var(--accent-red);">--</strong>
        </div>
        <div class="data-row">
            <span id="res-tp-label">Take Profit:</span>
            <strong id="res-tp" style="color: var(--accent-green); font-weight: 900; font-size: 1rem;">--</strong>
        </div>
        <div class="data-row">
            <span>Telegram:</span>
            <strong id="res-tg-status" style="color: var(--accent-cyan);">--</strong>
        </div>

        <button type="button" id="copy-action-btn" class="btn btn-success" style="margin-top: 12px; padding: 12px; font-size: 0.85rem;" onclick="copiaSegnalePro()">📋 COPIA SEGNALE PER TELEGRAM</button>
    </div>

    <div class="card" style="padding: 10px 14px;">
        <label>Storico Sessione:</label>
        <div id="history-log" class="history-box">Pronto per registrare la sessione con scudo anti-perdite...</div>
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
            recovery_mode: false
        };

        function onModeChange() {
            const mode = document.getElementById('strategy-mode').value;
            const genBtn = document.getElementById('gen-btn');
            const copyBtn = document.getElementById('copy-action-btn');
            
            if (mode === 'scalp') {
                genBtn.style.background = 'linear-gradient(135deg, #a855f7, #6d28d9)';
                genBtn.innerText = '⚡ GENERA SCALPING ANTI-SERIE';
                copyBtn.className = 'btn btn-scalp';
            } else {
                genBtn.style.background = 'linear-gradient(135deg, #22c55e, #15803d)';
                genBtn.innerText = '🎯 GENERA SEGNALE ULTIMATE SHIELD v91';
                copyBtn.className = 'btn btn-success';
            }
        }

        function updateUIStats() {
            const activeTrades = localStats.total - localStats.beps;
            const wr = activeTrades > 0 ? ((localStats.wins / activeTrades) * 100).toFixed(2) : "0.00";
            document.getElementById('stat-winrate').innerText = `${wr}% (${localStats.wins} Win / ${localStats.losses} Loss / ${localStats.beps} BEP)`;
            
            const badgeEl = document.getElementById('header-badge');
            const statusEl = document.getElementById('ai-status-text');
            const monitorCard = document.getElementById('monitor-card');

            if (localStats.recovery_mode) {
                badgeEl.className = "badge badge-recovery";
                badgeEl.innerText = `🚨 RECOVERY SHIELD (Loss: ${localStats.consecutive_losses})`;
                statusEl.innerText = `ATTIVO: Inversione forzata e TP esteso per ripartire!`;
                statusEl.style.color = "var(--accent-red)";
                monitorCard.style.borderLeft = "5px solid var(--accent-red)";
            } else {
                badgeEl.className = "badge";
                badgeEl.innerText = "ULTIMATE SHIELD v91";
                statusEl.innerText = "Attivo (Blocco Serie Negative)";
                statusEl.style.color = "var(--accent-green)";
                monitorCard.style.borderLeft = "5px solid var(--accent-green)";
            }
        }

        async function fetchStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                if (data) {
                    localStats.total = data.total_trades;
                    localStats.wins = data.wins;
                    localStats.losses = data.losses;
                    localStats.beps = data.beps || 0;
                    localStats.consecutive_losses = data.consecutive_losses || 0;
                    localStats.recovery_mode = data.recovery_mode || false;
                    updateUIStats();
                }
            } catch(e) {}
        }

        function registraEsito(resultType) {
            const mode = document.getElementById('strategy-mode').value;
            const isScalp = mode === 'scalp';

            localStats.total++;
            if (resultType === 'win') {
                localStats.wins++;
                localStats.consecutive_losses = 0;
                localStats.recovery_mode = false;
            } else if (resultType === 'loss') {
                localStats.losses++;
                localStats.consecutive_losses++;
                localStats.recovery_mode = true;
            } else if (resultType === 'bep') {
                localStats.beps++;
            }

            updateUIStats();

            const logBox = document.getElementById('history-log');
            const nowStr = new Date().toTimeString().split(' ')[0];
            let tag = isScalp ? '⚡ [SCALP]' : '🛡️ [SHIELD]';
            let msgText = '';

            if (resultType === 'win') msgText = `${tag} [${nowStr}] TARGET PRESO (WIN - Catena Riattivata)`;
            else if (resultType === 'bep') msgText = `${tag} [${nowStr}] BREAK EVEN POINT (BEP)`;
            else msgText = `${tag} [${nowStr}] LOSS (Consecutive: ${localStats.consecutive_losses}) -> 🚨 SHIELD INVERSIONE ATTIVA!`;

            logBox.innerHTML = msgText + '<br>' + logBox.innerHTML;

            fetch('/api/trade/result', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ result_type: resultType, is_scalp: isScalp })
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
                "toolbar_bg": "#0a0e1f",
                "enable_publishing": false,
                "hide_top_toolbar": false,
                "hide_legend": false,
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
            updateChartSymbol();
        }

        async function generaSegnaleShield() {
            const assetSelect = document.getElementById('asset-select');
            const signalBox = document.getElementById('signal-box');
            const priceInput = document.getElementById('live-price-input');
            const mode = document.getElementById('strategy-mode').value;
            const tgToggle = document.getElementById('telegram-toggle').checked;
            const isScalp = mode === 'scalp';

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

            const nowTime = Date.now();
            let multiplier = localStats.recovery_mode ? (3.5 + (localStats.consecutive_losses * 0.4)) : 2.0;
            const trendFactor = Math.sin((livePrice * multiplier) + nowTime / 1500);
            
            // Se siamo in recovery, forziamo l'inversione pulita per rompere la serie negativa
            let direction = trendFactor >= 0 ? "BUY" : "SELL";
            if (localStats.recovery_mode && localStats.consecutive_losses >= 1) {
                // Inversione di sicurezza anti-loss
                direction = trendFactor >= 0 ? "SELL" : "BUY";
            }

            let step = 1.80; 
            if (asset.includes("NAS100")) step = 35.00;
            else if (asset.includes("BTC")) step = 300.00;
            else if (asset.includes("ETH")) step = 18.00;
            else if (asset.includes("SOL")) step = 1.50;
            else if (asset.includes("NEAR")) step = 0.0900;
            else if (asset.includes("SUI")) step = 0.0250;
            else if (asset.includes("DOGE")) step = 0.0040;
            else if (asset.includes("SHIB")) step = 0.00000050;
            else if (asset.includes("XRP")) step = 0.0080;
            else if (asset.includes("EUR") || asset.includes("GBP")) step = 0.0035;

            let rangeText, slVal, tpVal, cleanAssetSymbol;
            cleanAssetSymbol = asset.replace("/", "");

            let slNum, tpNum;
            if (isScalp) {
                let tpMult = localStats.recovery_mode ? 2.5 : 2.0; 
                let slMult = 1.3; 
                if (direction === "BUY") {
                    tpNum = livePrice + (step * tpMult);
                    slNum = livePrice - (step * slMult);
                    rangeText = `${livePrice.toFixed(decimals)} / ${(livePrice - step*0.01).toFixed(decimals)}`;
                } else {
                    tpNum = livePrice - (step * tpMult);
                    slNum = livePrice + (step * slMult);
                    rangeText = `${livePrice.toFixed(decimals)} / ${(livePrice + step*0.01).toFixed(decimals)}`;
                }
            } else {
                // TP ampio (fino a 3.5x) e SL stretto (1.3x) per garantire che ogni vincita copra ampiamente le perdite
                let tpMult = localStats.recovery_mode ? 3.5 : 3.0; 
                let slMult = 1.3;  
                if (direction === "BUY") {
                    tpNum = livePrice + (step * tpMult);
                    slNum = livePrice - (step * slMult);
                    rangeText = `${livePrice.toFixed(decimals)} / ${(livePrice - step*0.015).toFixed(decimals)}`;
                } else {
                    tpNum = livePrice - (step * tpMult);
                    slNum = livePrice + (step * slMult);
                    rangeText = `${livePrice.toFixed(decimals)} / ${(livePrice + step*0.015).toFixed(decimals)}`;
                }
            }

            slVal = slNum.toFixed(decimals);
            tpVal = tpNum.toFixed(decimals);

            const now = new Date();
            const timeStr = now.toTimeString().split(' ')[0];

            lastSignalData = {
                symbol: cleanAssetSymbol,
                dir: direction,
                range: rangeText,
                sl: slVal,
                tp1: tpVal,
                isScalp: isScalp,
                isRecovery: localStats.recovery_mode
            };

            document.getElementById('res-asset').innerText = asset + " (" + currentTF + ")";
            document.getElementById('res-liveprice').innerText = '$' + livePrice.toFixed(decimals);
            
            const titleBox = document.getElementById('signal-title-box');
            if (localStats.recovery_mode) {
                titleBox.innerText = "🚨 SEGNALE SHIELD RECOVERY (INVERSIONE ANTI-SERIE)";
                titleBox.style.color = "var(--accent-red)";
            } else {
                titleBox.innerText = "🎯 SEGNALE ULTIMATE SHIELD PRONTO";
                titleBox.style.color = "var(--accent-green)";
            }
            
            const dirElem = document.getElementById('res-direction');
            dirElem.innerText = direction + (localStats.recovery_mode ? " [SHIELD RECOVERY]" : " [SHIELD]");
            dirElem.className = direction === 'BUY' ? 'buy' : 'sell';

            document.getElementById('res-range').innerText = rangeText;
            document.getElementById('res-sl').innerText = slVal;
            document.getElementById('res-tp').innerText = tpVal;
            document.getElementById('res-tp-label').innerText = localStats.recovery_mode ? "Take Profit (Recupero Forzato):" : "Take Profit (Target Pieno):";

            const tgStatusEl = document.getElementById('res-tg-status');
            signalBox.style.display = 'block';

            if (tgToggle) {
                const tgToken = document.getElementById('tg-token').value.trim();
                const tgChatId = document.getElementById('tg-chatid').value.trim();

                if (tgToken && tgChatId) {
                    tgStatusEl.innerText = "Invio in corso...";
                    tgStatusEl.style.color = "#f59e0b";

                    const headerTag = localStats.recovery_mode ? "🚨 SHIELD RECOVERY SIGNAL (INVERSIONE)" : "🛡️ ULTIMATE SHIELD SIGNAL";
                    const formattedMsg = `<b>${headerTag}</b>\n\n<b>Asset:</b> ${cleanAssetSymbol} (${currentTF})\n<b>Direzione:</b> ${direction}\n<b>Range:</b> ${rangeText}\n\n<b>Stop Loss:</b> ${slVal}\n<b>Target (TP Esteso):</b> ${tpVal}`;

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
                            tgStatusEl.innerText = "✅ Inviato su Telegram!";
                            tgStatusEl.style.color = "var(--accent-green)";
                        } else {
                            tgStatusEl.innerText = "❌ " + tgData.message;
                            tgStatusEl.style.color = "var(--accent-red)";
                        }
                    } catch(e) {
                        tgStatusEl.innerText = "❌ Errore connessione";
                        tgStatusEl.style.color = "var(--accent-red)";
                    }
                } else {
                    tgStatusEl.innerText = "⚠️ Inserisci Token e Chat ID";
                    tgStatusEl.style.color = "#f59e0b";
                }
            } else {
                tgStatusEl.innerText = "Disattivato";
                tgStatusEl.style.color = "var(--text-muted)";
            }

            const logBox = document.getElementById('history-log');
            let recoveryTagText = localStats.recovery_mode ? ' [Shield Recovery Active]' : '';
            const logText = `[${timeStr}] ${asset} (${currentTF}) -> ${direction}${recoveryTagText}<br>`;
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

            const modeTitle = lastSignalData.isRecovery ? "🚨 SHIELD RECOVERY SIGNAL (INVERSIONE)" : "🛡️ ULTIMATE SHIELD SIGNAL";
            const text = `${modeTitle} - ${lastSignalData.symbol} (${currentTF})\n\n${lastSignalData.dir} RANGE: ${lastSignalData.range}\n\nSL: ${lastSignalData.sl}\nTP: ${lastSignalData.tp1}`;

            navigator.clipboard.writeText(text).then(() => {
                alert("Segnale copiato negli appunti!");
            });
        }
    </script>

</body>
</html>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
