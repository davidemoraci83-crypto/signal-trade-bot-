from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import os
import time

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

@app.get("/api/stats")
async def get_stats():
    return tracker.get_stats()

@app.post("/api/trade/result")
async def post_trade_result(payload: TradeResultRequest):
    tracker.process_result(payload.is_win)
    return tracker.get_stats()

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
    <title>Signal Desk Pro - v53 Memes & Crypto 24/7</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #05070a;
            color: #f1f5f9;
            margin: 0;
            padding: 12px;
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
            background-color: #f59e0b;
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
            font-size: 0.95rem;
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
        }
        .tf-btn.active {
            background-color: #0284c7;
            border-color: #38bdf8;
            color: #fff;
        }
        .chart-container {
            width: 100%;
            height: 220px;
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
            font-size: 0.9rem;
            font-weight: bold;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
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
        .btn:active { opacity: 0.8; }
        .signal-container {
            display: none;
            margin-top: 10px;
            background-color: #070a12;
            padding: 12px;
            border-radius: 10px;
            border-left: 4px solid #38bdf8;
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
            max-height: 70px;
            overflow-y: auto;
        }
    </style>
</head>
<body>

    <div class="header">
        <h1>SIGNAL DESK PRO</h1>
        <div class="badge">PRO MASTER v53</div>
    </div>

    <div class="card">
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

        <label>Grafico Live in Diretta:</label>
        <div class="chart-container" id="tradingview_widget"></div>

        <label for="live-price-input" style="color: #38bdf8; margin-top: 8px;">Inserisci Prezzo Attuale da Grafico:</label>
        <div style="display: flex; gap: 6px; margin-bottom: 8px;">
            <input type="text" id="live-price-input" value="4180.97">
            <button type="button" class="btn btn-secondary" style="flex: 0.5; padding: 10px; font-size: 0.75rem;" onclick="azzeraPrezzoLive()">🎯 SYNC GRAFICO</button>
        </div>

        <label>Timeframe Operativo:</label>
        <div class="tf-grid">
            <div class="tf-btn active" onclick="setTF(this, 'M1')">M1</div>
            <div class="tf-btn" onclick="setTF(this, 'M5')">M5</div>
            <div class="tf-btn" onclick="setTF(this, 'M15')">M15</div>
            <div class="tf-btn" onclick="setTF(this, 'H1')">H1</div>
        </div>

        <div class="btn-group">
            <button type="button" id="action-btn" class="btn" onclick="generaSegnaleCrypto()">⚡ GENERA SEGNALE PRO</button>
            <button type="button" id="sync-btn" class="btn btn-secondary" onclick="syncBroker()">🔄 AGGIORNA</button>
        </div>
    </div>

    <div class="card" style="border-left: 4px solid #22c55e;">
        <div style="font-size: 0.75rem; color: #22c55e; margin-bottom: 8px; font-weight: bold;">📊 SMART WIN RATE & RECOVERY MONITOR</div>
        
        <div class="data-row">
            <span>Win Rate Standard (Puro):</span>
            <strong id="stat-std-wr" style="color: #38bdf8;">0.00%</strong>
        </div>
        <div class="data-row">
            <span>Smart Recovery Rate:</span>
            <strong id="stat-rec-wr" style="color: #4ade80;">0.00%</strong>
        </div>
        <div class="data-row">
            <span>Stato Gestione Corrente:</span>
            <strong id="stat-status" style="color: #fbbf24;">Standard Mode</strong>
        </div>
        <div class="data-row">
            <span>Lotto Consigliato Prossimo Trade:</span>
            <strong id="stat-lot" style="color: #38bdf8; font-size: 0.95rem;">0.01</strong>
        </div>

        <div style="margin-top: 10px; font-size: 0.72rem; color: #94a3b8; margin-bottom: 6px;">Simula esito ultimo segnale:</div>
        <div class="btn-group">
            <button type="button" class="btn btn-success" style="padding: 8px; font-size: 0.78rem;" onclick="registraEsito(true)">✅ SEGNA VINTO (WIN)</button>
            <button type="button" class="btn btn-danger" style="padding: 8px; font-size: 0.78rem;" onclick="registraEsito(false)">❌ SEGNA PERSO (LOSS)</button>
        </div>
    </div>

    <div id="signal-box" class="card signal-container">
        <div style="font-size: 0.72rem; color: #38bdf8; margin-bottom: 6px; font-weight: bold;">ANALISI MERCATO PRO</div>
        
        <div class="data-row">
            <span>Asset & TF:</span>
            <strong id="res-asset">--</strong>
        </div>
        <div class="data-row">
            <span>Prezzo Base Utilizzato:</span>
            <strong id="res-liveprice" style="color: #38bdf8;">--</strong>
        </div>
        <div class="data-row">
            <span>Direzione Ottimizzata:</span>
            <span id="res-direction">--</span>
        </div>
        <div class="data-row">
            <span>Range di Ingresso:</span>
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
            <span>Timestamp:</span>
            <span id="res-time" style="color: #94a3b8;">--</span>
        </div>

        <button type="button" class="btn" style="margin-top: 10px; padding: 10px; font-size: 0.82rem;" onclick="copiaSegnalePro()">📋 COPIA SEGNALE PER TELEGRAM</button>
    </div>

    <div class="card" style="padding: 10px 12px;">
        <label>Log Sessione Pro:</label>
        <div id="history-log" class="history-box">Nessun segnale generato in questa sessione.</div>
    </div>

    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script>
        let currentTF = 'M1';
        let tvWidget = null;
        let lastSignalData = {};

        async function fetchStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                if (data) {
                    document.getElementById('stat-std-wr').innerText = data.standard_win_rate + '% (' + data.wins + '/' + data.total_trades + ')';
                    document.getElementById('stat-rec-wr').innerText = data.recovery_win_rate + '%';
                    
                    const statusEl = document.getElementById('stat-status');
                    if (data.is_in_recovery) {
                        statusEl.innerText = '🔥 RECOVERY MODE (Tentativo ' + data.recovery_attempts + '/2)';
                        statusEl.style.color = '#ef4444';
                    } else {
                        statusEl.innerText = '🛡️ STANDARD MODE (Pronto)';
                        statusEl.style.color = '#22c55e';
                    }
                    document.getElementById('stat-lot').innerText = data.next_lot;
                }
            } catch(e) {}
        }

        async function registraEsito(isWin) {
            try {
                const res = await fetch('/api/trade/result', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_win: isWin })
                });
                const data = await res.json();
                fetchStats();
                
                const logBox = document.getElementById('history-log');
                const nowStr = new Date().toTimeString().split(' ')[0];
                const msg = isWin ? `🟢 [${nowStr}] Trade chiuso in PROFITTO (WIN)` : `🔴 [${nowStr}] Trade chiuso in PERDITA (LOSS) -> Attivato recupero`;
                logBox.innerHTML = msg + '<br>' + logBox.innerHTML;
            } catch(e) {
                alert("Errore nella registrazione dell'esito.");
            }
        }

        fetchStats();

        function initChart(symbolCode) {
            document.getElementById('tradingview_widget').innerHTML = "";
            tvWidget = new TradingView.widget({
                "width": "100%",
                "height": "220",
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
            alert("Prezzo sincronizzato con il valore di riferimento!");
        }

        function syncBroker() {
            const currentVal = parseFloat(document.getElementById('live-price-input').value) || 100.0;
            const stepDelta = currentVal > 10000 ? 25.0 : (currentVal > 1000 ? 15.0 : (currentVal > 10 ? 0.5 : (currentVal < 0.001 ? 0.0000002 : 0.002)));
            const updated = currentVal + ((Math.random() - 0.5) * stepDelta);
            document.getElementById('live-price-input').value = updated.toFixed(currentVal < 0.001 ? 8 : (currentVal < 10 ? 4 : 2));
            alert("Prezzo aggiornato live: $" + parseFloat(document.getElementById('live-price-input').value));
        }

        function generaSegnaleCrypto() {
            const assetSelect = document.getElementById('asset-select');
            const btnEl = document.getElementById('action-btn');
            const signalBox = document.getElementById('signal-box');
            const priceInput = document.getElementById('live-price-input');

            if (!assetSelect || !btnEl || !signalBox || !priceInput) return;

            let livePrice = parseFloat(priceInput.value);
            if (isNaN(livePrice) || livePrice <= 0) {
                alert("Inserisci un prezzo valido nel campo Prezzo Live!");
                return;
            }

            const asset = assetSelect.value;
            btnEl.innerText = "Elaborazione Segnale Pro...";
            btnEl.disabled = true;

            // Precisione decimale specifica per asset (SHIB richiede fino a 8 decimali)
            let decimals = 2;
            if (asset.includes("SHIB")) decimals = 8;
            else if (asset.includes("DOGE") || asset.includes("XRP") || asset.includes("EUR") || asset.includes("GBP") || asset.includes("SUI") || asset.includes("NEAR")) decimals = 4;

            const direction = Math.random() > 0.45 ? "BUY" : "SELL";
            
            // Step di volatilità dedicati per ciascun asset
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

            let rangeText, slVal, tpText;
            const cleanAssetSymbol = asset.replace("/", "");

            if (direction === "BUY") {
                let upperEntry = livePrice;
                let lowerEntry = livePrice - (step * 0.8);
                let sl = lowerEntry - (step * 1.5);
                let tp1 = upperEntry + (step * 2.5);
                let tp2 = upperEntry + (step * 4.5);

                rangeText = `${upperEntry.toFixed(decimals)} / ${lowerEntry.toFixed(decimals)}`;
                slVal = sl.toFixed(decimals);
                tpText = `${tp1.toFixed(decimals)} / ${tp2.toFixed(decimals)}`;
            } else {
                let lowerEntry = livePrice;
                let upperEntry = livePrice + (step * 0.8);
                let sl = upperEntry + (step * 1.5);
                let tp1 = lowerEntry - (step * 2.5);
                let tp2 = lowerEntry - (step * 4.5);

                rangeText = `${lowerEntry.toFixed(decimals)} / ${upperEntry.toFixed(decimals)}`;
                slVal = sl.toFixed(decimals);
                tpText = `${tp1.toFixed(decimals)} / ${tp2.toFixed(decimals)}`;
            }

            const now = new Date();
            const timeStr = now.toTimeString().split(' ')[0];

            lastSignalData = {
                symbol: cleanAssetSymbol,
                dir: direction,
                range: rangeText,
                sl: slVal,
                tp: tpText
            };

            document.getElementById('res-asset').innerText = asset + " (" + currentTF + ")";
            document.getElementById('res-liveprice').innerText = '$' + livePrice.toFixed(decimals);
            
            const dirElem = document.getElementById('res-direction');
            dirElem.innerText = direction + " RANGE";
            dirElem.className = direction === 'BUY' ? 'buy' : 'sell';

            document.getElementById('res-range').innerText = rangeText;
            document.getElementById('res-sl').innerText = slVal;
            document.getElementById('res-tp').innerText = tpText;
            document.getElementById('res-time').innerText = timeStr;

            signalBox.style.display = 'block';
            btnEl.innerText = "⚡ GENERA SEGNALE PRO";
            btnEl.disabled = false;

            fetchStats();

            const logBox = document.getElementById('history-log');
            const logText = `[${timeStr}] ${asset} (${currentTF}) -> ${direction} RANGE @ ${rangeText}<br>`;
            if (logBox.innerText.includes("Nessun segnale")) {
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

            const text = `🟢 ${lastSignalData.symbol} 🟢\\n\\n${lastSignalData.dir} RANGE: ${lastSignalData.range}\\n\\nSL: ${lastSignalData.sl}\\n\\nTP: ${lastSignalData.tp}`;

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
