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
# GESTORE STATO & DUAL-MODE ENGINE
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

    def get_next_lot(self, is_scalp=False):
        multiplier = 1.4 if is_scalp else self.lot_multiplier
        if self.is_in_recovery and self.recovery_attempts <= self.max_recovery_attempts:
            return round(self.base_lot * (multiplier ** self.recovery_attempts), 2)
        return self.base_lot

    def process_result(self, is_win: bool, is_scalp: bool = False):
        current_lot = self.get_next_lot(is_scalp)
        self.total_trades += 1
        
        # Profitto scalping leggermente più rapido ma frequente, standard più solido
        profit_multiplier = 30.0 if is_scalp else 45.0
        trade_win_value = profit_multiplier * (current_lot / 0.01)
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
            "net_profit_eur": round(self.net_profit_eur, 2)
        }

tracker = SignalTrackerState()

class TradeResultRequest(BaseModel):
    is_win: bool
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
    tracker.process_result(payload.is_win, payload.is_scalp)
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
    <title>Signal Desk Pro - Dual Mode v73</title>
    <style>
        :root {
            --bg-color: #05070f;
            --card-bg: #0d1124;
            --border-color: #1a2342;
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
            background: linear-gradient(135deg, #0d1124, #19254a);
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
            background: linear-gradient(135deg, var(--accent-purple), #6d28d9);
            color: #fff;
            padding: 4px 10px;
            border-radius: 9999px;
            font-weight: 800;
            box-shadow: 0 0 12px rgba(168, 85, 247, 0.4);
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
            background-color: #05070f;
            color: var(--accent-cyan);
            border: 1px solid #243059;
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
            background-color: #05070f;
            border: 1px solid #243059;
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
            background-color: #05070f;
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
            color: #05070f;
            border: none;
            padding: 13px;
            border-radius: 10px;
            font-size: 0.9rem;
            font-weight: 800;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(56, 189, 248, 0.4);
        }
        .btn-secondary {
            background: #19254a;
            border: 1px solid #36487a;
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
            background-color: #05070f;
            padding: 14px;
            border-radius: 12px;
            border-left: 5px solid var(--accent-purple);
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
            border-bottom: 1px solid #11182d;
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
            background: #05070f;
            padding: 8px;
            border-radius: 6px;
        }
        .toggle-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background-color: #05070f;
            padding: 10px 12px;
            border-radius: 10px;
            border: 1px solid #243059;
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
            background-color: #243059; transition: .3s; border-radius: 24px;
        }
        .slider:before {
            position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px;
            background-color: white; transition: .3s; border-radius: 50%;
        }
        input:checked + .slider { background-color: var(--accent-purple); }
        input:checked + .slider:before { transform: translateX(22px); }
    </style>
</head>
<body>

    <div class="header">
        <h1>SIGNAL DESK PRO</h1>
        <div class="badge">DUAL-MODE v73</div>
    </div>

    <!-- GESTIONE CAPITALE & CASSA -->
    <div class="card" style="border-left: 5px solid var(--accent-cyan);">
        <div style="font-size: 0.8rem; font-weight: 800; color: var(--accent-cyan); margin-bottom: 8px;">🛡️ CASSA & RISK MANAGEMENT</div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
            <div>
                <label>Capitale Iniziale (€):</label>
                <input type="number" id="capital-input" value="1000" onchange="recalculateRisk()" style="margin-bottom:0;">
            </div>
            <div>
                <label>Rischio Base (%):</label>
                <input type="number" id="risk-input" value="1.0" step="0.1" onchange="recalculateRisk()" style="margin-bottom:0;">
            </div>
        </div>

        <div class="data-row">
            <span>Profitto Netto Totale:</span>
            <strong id="live-net-profit" style="color: var(--accent-green); font-size: 1.1rem;">+€0.00</strong>
        </div>
        <div class="data-row">
            <span>Lotto Standard:</span>
            <strong id="calc-dynamic-lot" style="color: var(--accent-cyan);">0.01 Lotto</strong>
        </div>
        <div class="data-row">
            <span>Lotto Scalping (High Yield):</span>
            <strong id="calc-scalp-lot" style="color: var(--accent-purple);">0.015 Lotto</strong>
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
            <option value="standard">🛡️ Standard Sicura (Focus su TP1 Sicuro)</option>
            <option value="scalp">⚡ Scalping Ultra-Rapido (Micro-TP & Lotto Alto)</option>
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

        <button type="button" id="gen-btn" class="btn" style="width: 100%; padding: 15px; font-size: 1rem;" onclick="generaSegnaleDual()">🎯 GENERA SEGNALE</button>
    </div>

    <!-- STATISTICHE E WIN RATE -->
    <div class="card" style="border-left: 5px solid var(--accent-purple);">
        <div style="font-size: 0.78rem; color: var(--accent-purple); margin-bottom: 8px; font-weight: 800;">📊 MONITOR WIN RATE & CASSA</div>
        
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
            <strong id="stat-status" style="color: var(--accent-green);">Modalità Standard</strong>
        </div>
        <div class="data-row">
            <span>Lotto Attivo Corrente:</span>
            <strong id="stat-lot" style="color: var(--accent-cyan); font-size: 1rem;">0.01</strong>
        </div>

        <div style="margin-top: 10px; font-size: 0.75rem; color: var(--text-muted); margin-bottom: 6px;">Registra esito trade per aggiornare la cassa:</div>
        <div class="btn-group">
            <button type="button" class="btn btn-success" style="padding: 10px; font-size: 0.8rem;" onclick="registraEsito(true)">✅ TARGET PRESO (WIN)</button>
            <button type="button" class="btn btn-danger" style="padding: 10px; font-size: 0.8rem;" onclick="registraEsito(false)">❌ PERSO (LOSS)</button>
        </div>
    </div>

    <!-- BOX RISULTATO SEGNALE -->
    <div id="signal-box" class="card signal-container">
        <div id="signal-title-box" style="font-size: 0.75rem; color: var(--accent-purple); margin-bottom: 8px; font-weight: 800;">🎯 SEGNALE PRONTO</div>
        
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
            <span>Stop Loss:</span>
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

        <button type="button" id="copy-action-btn" class="btn" style="margin-top: 12px; padding: 12px; font-size: 0.85rem;" onclick="copiaSegnalePro()">📋 COPIA SEGNALE PER TELEGRAM</button>
    </div>

    <div class="card" style="padding: 10px 14px;">
        <label>Storico Sessione:</label>
        <div id="history-log" class="history-box">In attesa di operazioni...</div>
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
            scalpLot: 0.015,
            netProfitEur: 0.0
        };

        function recalculateRisk() {
            const capital = parseFloat(document.getElementById('capital-input').value) || 1000;
            const riskPct = parseFloat(document.getElementById('risk-input').value) || 1.0;
            
            let calcLot = Math.max(0.01, parseFloat(((capital * (riskPct / 100)) / 1000).toFixed(2)));
            let scalpLotVal = parseFloat((calcLot * 1.5).toFixed(2));
            
            localStats.baseLot = calcLot;
            localStats.scalpLot = scalpLotVal;

            document.getElementById('calc-dynamic-lot').innerText = `${calcLot} Lotto`;
            document.getElementById('calc-scalp-lot').innerText = `${scalpLotVal} Lotto`;
            updateUIStats();
        }

        function onModeChange() {
            const mode = document.getElementById('strategy-mode').value;
            const genBtn = document.getElementById('gen-btn');
            const copyBtn = document.getElementById('copy-action-btn');
            
            if (mode === 'scalp') {
                genBtn.style.background = 'linear-gradient(135deg, #a855f7, #6d28d9)';
                genBtn.innerText = '⚡ GENERA SEGNALE SCALPING (HIGH YIELD)';
                copyBtn.className = 'btn btn-scalp';
            } else {
                genBtn.style.background = 'linear-gradient(135deg, #38bdf8, #0284c7)';
                genBtn.innerText = '🎯 GENERA SEGNALE STANDARD (TP1)';
                copyBtn.className = 'btn btn-success';
            }
            updateUIStats();
        }

        function updateUIStats() {
            const mode = document.getElementById('strategy-mode').value;
            const isScalp = mode === 'scalp';
            const stdWR = localStats.total > 0 ? ((localStats.wins / localStats.total) * 100).toFixed(2) : "0.00";
            const recWR = localStats.recTrades > 0 ? ((localStats.recWins / localStats.recTrades) * 100).toFixed(2) : "0.00";
            
            document.getElementById('stat-std-wr').innerText = `${stdWR}% (${localStats.wins}/${localStats.total})`;
            document.getElementById('stat-rec-wr').innerText = `${recWR}%`;
            
            const statusEl = document.getElementById('stat-status');
            let activeLot = isScalp ? localStats.scalpLot : localStats.baseLot;

            if (localStats.isInRecovery) {
                statusEl.innerText = `🔥 RECUPERO ATTIVO (Tentativo ${localStats.attempts}/2)`;
                statusEl.style.color = 'var(--accent-red)';
                let multiplier = isScalp ? 1.4 : 1.3;
                activeLot = parseFloat((activeLot * Math.pow(multiplier, localStats.attempts)).toFixed(2));
            } else {
                statusEl.innerText = isScalp ? '⚡ SCALPING MODE (Micro-TP)' : '🛡️ MODALITÀ SICURA (TP1 Focus)';
                statusEl.style.color = isScalp ? 'var(--accent-purple)' : 'var(--accent-green)';
            }
            localStats.currentLot = activeLot;
            document.getElementById('stat-lot').innerText = `${activeLot} Lotto (${isScalp ? 'Scalp' : 'Standard'})`;

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
            const mode = document.getElementById('strategy-mode').value;
            const isScalp = mode === 'scalp';
            const currentLot = localStats.currentLot || 0.01;
            
            const profitMultiplier = isScalp ? 30.0 : 40.0;
            const baseProfit = profitMultiplier * (currentLot / 0.01);
            const baseLoss = 20.0 * (currentLot / 0.01);

            localStats.total++;
            if (localStats.isInRecovery) localStats.recTrades++;

            if (isWin) {
                localStats.wins++;
                localStats.netProfitEur += baseProfit;
                if (localStats.isInRecovery) localStats.recWins++;
                localStats.is_in_recovery = false;
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
            const modeName = isScalp ? '⚡ [SCALP]' : '🎯 [STANDARD]';
            const msg = isWin ? `${modeName} [${nowStr}] TARGET PRESO (+€${baseProfit.toFixed(2)})` : `${modeName} [${nowStr}] LOSS (-€${baseLoss.toFixed(2)}) -> Recupero`;
            logBox.innerHTML = msg + '<br>' + logBox.innerHTML;

            fetch('/api/trade/result', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_win: isWin, is_scalp: isScalp })
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
                "toolbar_bg": "#0d1124",
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

        async function generaSegnaleDual() {
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
            if (isScalp) {
                // SCALPING: TP molto vicino e SL stretto
                let tpMultiplier = 1.2; 
                let slMultiplier = 1.8;
                if (direction === "BUY") {
                    tpNum = livePrice + (step * tpMultiplier);
                    slNum = livePrice - (step * slMultiplier);
                    rangeText = `${livePrice.toFixed(decimals)} / ${(livePrice - step*0.02).toFixed(decimals)}`;
                } else {
                    tpNum = livePrice - (step * tpMultiplier);
                    slNum = livePrice + (step * slMultiplier);
                    rangeText = `${livePrice.toFixed(decimals)} / ${(livePrice + step*0.02).toFixed(decimals)}`;
                }
            } else {
                // STANDARD: TP sicuro bilanciato
                if (direction === "BUY") {
                    let upperEntry = livePrice;
                    let lowerEntry = livePrice - (step * 0.03);
                    slNum = lowerEntry - (step * 5.0);
                    tpNum = upperEntry + (step * 4.5);
                    rangeText = `${upperEntry.toFixed(decimals)} / ${lowerEntry.toFixed(decimals)}`;
                } else {
                    let lowerEntry = livePrice;
                    let upperEntry = livePrice + (step * 0.03);
                    slNum = upperEntry + (step * 5.0);
                    tpNum = lowerEntry - (step * 4.5);
                    rangeText = `${lowerEntry.toFixed(decimals)} / ${upperEntry.toFixed(decimals)}`;
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
                lot: localStats.currentLot
            };

            document.getElementById('res-asset').innerText = asset + " (" + currentTF + ")";
            document.getElementById('res-liveprice').innerText = '$' + livePrice.toFixed(decimals);
            
            const titleBox = document.getElementById('signal-title-box');
            titleBox.innerText = isScalp ? "⚡ SEGNALE SCALPING ULTRA-RAPIDO (HIGH YIELD)" : "🎯 SEGNALE STANDARD (TP1 SICURO)";
            
            const dirElem = document.getElementById('res-direction');
            dirElem.innerText = direction + (isScalp ? " [SCALP LAMPO]" : " [STANDARD]");
            dirElem.className = direction === 'BUY' ? 'buy' : 'sell';

            document.getElementById('res-range').innerText = rangeText;
            document.getElementById('res-sl').innerText = slVal;
            document.getElementById('res-tp').innerText = tpVal;
            document.getElementById('res-tp-label').innerText = isScalp ? "Micro-TP (Scalping):" : "Take Profit (TP1):";

            const tgStatusEl = document.getElementById('res-tg-status');
            signalBox.style.display = 'block';

            if (tgToggle) {
                const tgToken = document.getElementById('tg-token').value.trim();
                const tgChatId = document.getElementById('tg-chatid').value.trim();

                if (tgToken && tgChatId) {
                    tgStatusEl.innerText = "Invio in corso...";
                    tgStatusEl.style.color = "#f59e0b";

                    const modeTitle = isScalp ? "⚡ SCALPING ULTRA-RAPIDO (LOTTO ALTO)" : "🎯 STANDARD PRECISION (TP1)";
                    const formattedMsg = `<b>${modeTitle}</b>\n\n<b>Asset:</b> ${cleanAssetSymbol} (${currentTF})\n<b>Direzione:</b> ${direction}\n<b>Range:</b> ${rangeText}\n\n<b>Stop Loss:</b> ${slVal}\n<b>Target (TP):</b> ${tpVal}\n\n<i>Lotto consigliato: ${localStats.currentLot}</i>`;

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
            const logText = `[${timeStr}] ${asset} (${currentTF}) -> ${direction} (${isScalp ? 'Scalp' : 'Standard'})<br>`;
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

            const modeTitle = lastSignalData.isScalp ? "⚡ SCALPING ULTRA-RAPIDO" : "🎯 STANDARD TP1";
            const text = `${modeTitle} - ${lastSignalData.symbol} (${currentTF})\n\n${lastSignalData.dir} RANGE: ${lastSignalData.range}\n\nSL: ${lastSignalData.sl}\nTP: ${lastSignalData.tp1}\nLotto: ${lastSignalData.lot}`;

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
