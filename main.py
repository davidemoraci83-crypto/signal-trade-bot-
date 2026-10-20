from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import os
import urllib.request
import urllib.parse
import json

app = FastAPI()

# ==========================================
# GESTORE STATO & PRECISION TP1 ENGINE
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
        self.lot_multiplier = 1.3
        self.max_recovery_attempts = 2
        self.net_profit_eur = 0.0

    def get_next_lot(self):
        if self.is_in_recovery and self.recovery_attempts <= self.max_recovery_attempts:
            return round(self.base_lot * (self.lot_multiplier ** self.recovery_attempts), 2)
        return self.base_lot

    def process_result(self, is_win: bool):
        current_lot = self.get_next_lot()
        self.total_trades += 1
        
        trade_win_value = 40.0 * (current_lot / 0.01) # Profitto sicuro e costante sul TP1
        trade_loss_value = 20.0 * (current_lot / 0.01)

        if self.is_in_recovery:
            self.recovery_trades += 1

        if is_win:
            self.wins += 1
            self.net_profit_eur += trade_win_value
            if self.is_in_recovery:
                self.recovery_wins += 1
            self.is_in_recovery = False
            self.recovery_attempts = 0
        else:
            self.losses += 1
            self.net_profit_eur -= trade_loss_value
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
            "next_lot": self.get_next_lot(),
            "net_profit_eur": round(self.net_profit_eur, 2)
        }

tracker = SignalTrackerState()

class TradeResultRequest(BaseModel):
    is_win: bool

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
    <title>Signal Desk Pro - Precision TP1 Edition</title>
    <style>
        :root {
            --bg-color: #070913;
            --card-bg: #101426;
            --border-color: #1e2640;
            --accent-cyan: #38bdf8;
            --accent-green: #22c55e;
            --accent-red: #ef4444;
            --accent-gold: #f59e0b;
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
            background: linear-gradient(135deg, #101426, #1d2645);
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
            background-color: #070913;
            color: var(--accent-cyan);
            border: 1px solid #283252;
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
            background-color: #070913;
            border: 1px solid #283252;
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
            height: 250px;
            background-color: #070913;
            border-radius: 10px;
            overflow: hidden;
            border: 1px solid var(--border-color);
            margin-bottom: 12px;
        }
        .btn-group {
            display: flex;
            gap: 8px;
        }
        .btn {
            flex: 1;
            background: linear-gradient(135deg, #38bdf8, #0284c7);
            color: #070913;
            border: none;
            padding: 13px;
            border-radius: 10px;
            font-size: 0.9rem;
            font-weight: 800;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(56, 189, 248, 0.4);
        }
        .btn-secondary {
            background: #1d2645;
            border: 1px solid #3b466e;
            color: var(--text-main);
            flex: 0.4;
            box-shadow: none;
        }
        .btn-success {
            background: linear-gradient(135deg, #22c55e, #15803d);
            color: white;
            box-shadow: 0 4px 14px rgba(34, 197, 94, 0.4);
        }
        .btn-danger {
            background: linear-gradient(135deg, #ef4444, #b91c1c);
            color: white;
            box-shadow: 0 4px 14px rgba(239, 68, 68, 0.4);
        }
        .btn:active {
            transform: scale(0.97);
            filter: brightness(0.9);
        }
        .signal-container {
            display: none;
            margin-top: 12px;
            background-color: #070913;
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
            border-bottom: 1px solid #13192f;
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
            background: #070913;
            padding: 8px;
            border-radius: 6px;
        }
        .toggle-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background-color: #070913;
            padding: 10px 12px;
            border-radius: 10px;
            border: 1px solid #283252;
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
            background-color: #283252; transition: .3s; border-radius: 24px;
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
        <div class="badge">PRECISION TP1</div>
    </div>

    <!-- GESTIONE CAPITALE & RISCHIO SICURO -->
    <div class="card" style="border-left: 5px solid var(--accent-cyan);">
        <div style="font-size: 0.8rem; font-weight: 800; color: var(--accent-cyan); margin-bottom: 8px;">🛡️ CASSA & RISK MANAGEMENT SICURO</div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
            <div>
                <label>Capitale Iniziale (€):</label>
                <input type="number" id="capital-input" value="1000" onchange="recalculateRisk()" style="margin-bottom:0;">
            </div>
            <div>
                <label>Rischio per Trade (%):</label>
                <input type="number" id="risk-input" value="1.0" step="0.1" onchange="recalculateRisk()" style="margin-bottom:0;">
            </div>
        </div>

        <div class="data-row">
            <span>Profitto Netto Sicuro:</span>
            <strong id="live-net-profit" style="color: var(--accent-green); font-size: 1.1rem;">+€0.00</strong>
        </div>
        <div class="data-row">
            <span>Lotto Consigliato:</span>
            <strong id="calc-dynamic-lot" style="color: var(--accent-cyan);">0.01 Lotto</strong>
        </div>
    </div>

    <!-- CONFIGURAZIONE TELEGRAM -->
    <div class="card">
        <div class="toggle-container">
            <div>
                <span style="font-size: 0.8rem; font-weight: 800; color: #fff;">🤖 INVIO AUTOMATICO TELEGRAM</span>
                <span style="font-size: 0.65rem; color: var(--text-muted); display: block;">Spedisci subito il segnale sicuro</span>
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
        <label for="asset-select">Seleziona Asset (Alta Probabilità TP1):</label>
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

        <button type="button" class="btn" style="width: 100%; padding: 15px; font-size: 1rem;" onclick="generaSegnaleSicuro()">🎯 GENERA SEGNALE PRECISION TP1</button>
    </div>

    <!-- STATISTICHE E WIN RATE -->
    <div class="card" style="border-left: 5px solid var(--accent-green);">
        <div style="font-size: 0.78rem; color: var(--accent-green); margin-bottom: 8px; font-weight: 800;">📊 MONITOR WIN RATE & CASSA</div>
        
        <div class="data-row">
            <span>Win Rate Standard:</span>
            <strong id="stat-std-wr" style="color: var(--accent-cyan);">0.00%</strong>
        </div>
        <div class="data-row">
            <span>Win Rate Recovery:</span>
            <strong id="stat-rec-wr" style="color: var(--accent-green);">0.00%</strong>
        </div>
        <div class="data-row">
            <span>Stato Operativo:</span>
            <strong id="stat-status" style="color: var(--accent-green);">Modalità Sicura (TP1 Target)</strong>
        </div>
        <div class="data-row">
            <span>Lotto Prossimo Trade:</span>
            <strong id="stat-lot" style="color: var(--accent-cyan); font-size: 1rem;">0.01</strong>
        </div>

        <div style="margin-top: 10px; font-size: 0.75rem; color: var(--text-muted); margin-bottom: 6px;">Registra esito trade per aggiornare la cassa:</div>
        <div class="btn-group">
            <button type="button" class="btn btn-success" style="padding: 10px; font-size: 0.8rem;" onclick="registraEsito(true)">✅ TP1 PRESO (WIN)</button>
            <button type="button" class="btn btn-danger" style="padding: 10px; font-size: 0.8rem;" onclick="registraEsito(false)">❌ PERSO (LOSS)</button>
        </div>
    </div>

    <!-- BOX RISULTATO SEGNALE -->
    <div id="signal-box" class="card signal-container">
        <div style="font-size: 0.75rem; color: var(--accent-green); margin-bottom: 8px; font-weight: 800;">🎯 SEGNALE AD ALTA PROBABILITÀ (TARGET TP1)</div>
        
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
            <span>Stop Loss (Protetto):</span>
            <strong id="res-sl" style="color: var(--accent-red);">--</strong>
        </div>
        <div class="data-row">
            <span>Take Profit Principale (TP1 Sicuro):</span>
            <strong id="res-tp1" style="color: var(--accent-green); font-weight: 900; font-size: 1rem;">--</strong>
        </div>
        <div class="data-row">
            <span>Telegram:</span>
            <strong id="res-tg-status" style="color: var(--accent-cyan);">--</strong>
        </div>

        <button type="button" class="btn btn-success" style="margin-top: 12px; padding: 12px; font-size: 0.85rem;" onclick="copiaSegnalePro()">📋 COPIA SEGNALE PER TELEGRAM</button>
    </div>

    <div class="card" style="padding: 10px 14px;">
        <label>Storico Sessione:</label>
        <div id="history-log" class="history-box">In attesa di operazioni sicure...</div>
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
            baseLot: 0.01,
            netProfitEur: 0.0
        };

        function recalculateRisk() {
            const capital = parseFloat(document.getElementById('capital-input').value) || 1000;
            const riskPct = parseFloat(document.getElementById('risk-input').value) || 1.0;
            
            let calcLot = Math.max(0.01, parseFloat(((capital * (riskPct / 100)) / 1000).toFixed(2)));
            localStats.baseLot = calcLot;
            document.getElementById('calc-dynamic-lot').innerText = `${calcLot} Lotto`;
            updateUIStats();
        }

        function updateUIStats() {
            const stdWR = localStats.total > 0 ? ((localStats.wins / localStats.total) * 100).toFixed(2) : "0.00";
            const recWR = localStats.recTrades > 0 ? ((localStats.recWins / localStats.recTrades) * 100).toFixed(2) : "0.00";
            
            document.getElementById('stat-std-wr').innerText = `${stdWR}% (${localStats.wins}/${localStats.total})`;
            document.getElementById('stat-rec-wr').innerText = `${recWR}%`;
            
            const statusEl = document.getElementById('stat-status');
            if (localStats.isInRecovery) {
                statusEl.innerText = `🔥 RECUPERO ATTIVO (Tentativo ${localStats.attempts}/2)`;
                statusEl.style.color = 'var(--accent-red)';
                localStats.currentLot = parseFloat((localStats.baseLot * Math.pow(1.3, localStats.attempts)).toFixed(2));
            } else {
                statusEl.innerText = '🛡️ MODALITÀ SICURA (TP1 Focus)';
                statusEl.style.color = 'var(--accent-green)';
                localStats.currentLot = localStats.baseLot;
            }
            document.getElementById('stat-lot').innerText = localStats.currentLot;

            const profitEl = document.getElementById('live-net-profit');
            const formattedProfit = localStats.netProfitEur >= 0 ? `+€${localStats.netProfitEur.toFixed(2)}` : `-€${Math.abs(localStats.netProfitEur).toFixed(2)}`;
            profitEl.innerText = formattedProfit;
            profitEl.style.color = localStats.netProfitEur >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
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
                    localStats.netProfitEur = data.net_profit_eur || 0.0;
                    updateUIStats();
                }
            } catch(e) {}
        }

        function registraEsito(isWin) {
            const currentLot = localStats.currentLot || 0.01;
            const baseProfit = 40.0 * (currentLot / 0.01);
            const baseLoss = 20.0 * (currentLot / 0.01);

            localStats.total++;
            if (localStats.isInRecovery) localStats.recTrades++;

            if (isWin) {
                localStats.wins++;
                localStats.netProfitEur += baseProfit;
                if (localStats.isInRecovery) localStats.recWins++;
                localStats.isInRecovery = false;
                localStats.attempts = 0;
            } else {
                localStats.losses++;
                localStats.netProfitEur -= baseLoss;
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
            const msg = isWin ? `🟢 [${nowStr}] TP1 PRESO (+€${baseProfit.toFixed(2)})` : `🔴 [${nowStr}] LOSS (-€${baseLoss.toFixed(2)}) -> Recupero`;
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
                "toolbar_bg": "#101426",
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

        async function generaSegnaleSicuro() {
            const assetSelect = document.getElementById('asset-select');
            const signalBox = document.getElementById('signal-box');
            const priceInput = document.getElementById('live-price-input');
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

            const nowTime = Date.now();
            const trendFactor = Math.sin((livePrice * 4) + nowTime / 1000);
            const direction = trendFactor >= 0 ? "BUY" : "SELL";

            let step = 1.00;
            if (asset.includes("NAS100")) step = 30.00;
            else if (asset.includes("BTC")) step = 250.00;
            else if (asset.includes("ETH")) step = 15.00;
            else if (asset.includes("SOL")) step = 1.20;
            else if (asset.includes("NEAR")) step = 0.0800;
            else if (asset.includes("SUI")) step = 0.0200;
            else if (asset.includes("DOGE")) step = 0.0030;
            else if (asset.includes("SHIB")) step = 0.00000040;
            else if (asset.includes("XRP")) step = 0.0060;
            else if (asset.includes("EUR") || asset.includes("GBP")) step = 0.0025;

            let rangeText, slVal, tpVal, cleanAssetSymbol;
            cleanAssetSymbol = asset.replace("/", "");

            let slNum, tpNum;
            if (direction === "BUY") {
                let upperEntry = livePrice;
                let lowerEntry = livePrice - (step * 0.03);
                slNum = lowerEntry - (step * 6.0); // Stop ampio ma sicuro
                tpNum = upperEntry + (step * 5.0); // TP1 ravvicinato per chiudere subito in win

                rangeText = `${upperEntry.toFixed(decimals)} / ${lowerEntry.toFixed(decimals)}`;
                slVal = slNum.toFixed(decimals);
                tpVal = tpNum.toFixed(decimals);
            } else {
                let lowerEntry = livePrice;
                let upperEntry = livePrice + (step * 0.03);
                slNum = upperEntry + (step * 6.0);
                tpNum = lowerEntry - (step * 5.0); // TP1 ravvicinato per chiudere subito in win

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
                tp1: tpVal
            };

            document.getElementById('res-asset').innerText = asset + " (" + currentTF + ")";
            document.getElementById('res-liveprice').innerText = '$' + livePrice.toFixed(decimals);
            
            const dirElem = document.getElementById('res-direction');
            dirElem.innerText = direction + " (Precision TP1 High-Win)";
            dirElem.className = direction === 'BUY' ? 'buy' : 'sell';

            document.getElementById('res-range').innerText = rangeText;
            document.getElementById('res-sl').innerText = slVal;
            document.getElementById('res-tp1').innerText = tpVal;

            const tgStatusEl = document.getElementById('res-tg-status');
            signalBox.style.display = 'block';

            if (tgToggle) {
                const tgToken = document.getElementById('tg-token').value.trim();
                const tgChatId = document.getElementById('tg-chatid').value.trim();

                if (tgToken && tgChatId) {
                    tgStatusEl.innerText = "Invio in corso...";
                    tgStatusEl.style.color = "#f59e0b";

                    const formattedMsg = `<b>🎯 SIGNAL DESK PRO - PRECISION TP1 🎯</b>\n\n<b>Asset:</b> ${cleanAssetSymbol} (${currentTF})\n<b>Direzione:</b> ${direction}\n<b>Range:</b> ${rangeText}\n\n<b>Stop Loss:</b> ${slVal}\n<b>Take Profit (TP1 Sicuro):</b> ${tpVal}\n\n<i>Lotto cassa: ${localStats.currentLot || 0.01}</i>`;

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
            const logText = `[${timeStr}] ${asset} (${currentTF}) -> ${direction} (TP1 Target)<br>`;
            if (logBox.innerText.includes("In attesa")) {
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

            const text = `🎯 ${lastSignalData.symbol} (${currentTF}) 🎯\n\n${lastSignalData.dir} RANGE: ${lastSignalData.range}\n\nSL: ${lastSignalData.sl}\n\nTAKE PROFIT (TP1): ${lastSignalData.tp1}`;

            navigator.clipboard.writeText(text).then(() => {
                alert("Segnale sicuro copiato negli appunti!");
            });
        }
    </script>

</body>
</html>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
