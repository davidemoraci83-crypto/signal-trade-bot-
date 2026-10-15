from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import httpx
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

@app.get("/api/price/{asset}")
async def get_live_price(asset: str):
    asset = asset.upper()
    price = None
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
            if "XAU" in asset or "GOLD" in asset:
                # API 1: Yahoo Finance GC=F (Gold Spot Futures)
                url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d"
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    price = data['chart']['result'][0]['meta'].get('regularMarketPrice')
                
                # API 2 Backup: GoldApi / Stooq se il primo fallisce
                if not price:
                    stooq_url = "https://stooq.com/q/l/?s=xauusd&f=sd2t2ohlcv&h&e=json"
                    res2 = await client.get(stooq_url, headers=headers)
                    if res2.status_code == 200:
                        d2 = res2.json()
                        price = float(d2['symbols'][0]['close'])

            elif "EUR" in asset:
                url = "https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?interval=1m&range=1d"
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    price = res.json()['chart']['result'][0]['meta'].get('regularMarketPrice')

            elif "GBP" in asset:
                url = "https://query1.finance.yahoo.com/v8/finance/chart/GBPUSD=X?interval=1m&range=1d"
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    price = res.json()['chart']['result'][0]['meta'].get('regularMarketPrice')

            elif "BTC" in asset:
                res = await client.get("https://api.coincap.io/v2/assets/bitcoin")
                if res.status_code == 200:
                    price = float(res.json()['data']['priceUsd'])

    except Exception:
        pass

    if not price:
        raise HTTPException(status_code=503, detail="Feed prezzo non disponibile momentaneamente")

    return {"asset": asset, "price": float(price), "timestamp": time.time()}

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
    <title>Signal Desk Pro - v46 Real Sync Fix</title>
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
            background-color: #0284c7;
            color: #f0fdf4;
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
        select {
            width: 100%;
            padding: 10px;
            background-color: #070a12;
            color: #fff;
            border: 1px solid #334155;
            border-radius: 8px;
            font-size: 0.9rem;
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
        <div class="badge">LIVE SYNC v46</div>
    </div>

    <div class="card">
        <label for="asset-select">Seleziona Asset / Mercato:</label>
        <select id="asset-select" onchange="updateChartSymbol()">
            <option value="XAU/USD">Oro (XAU/USD)</option>
            <option value="EUR/USD">Euro / Dollaro (EUR/USD)</option>
            <option value="GBP/USD">Sterlina / Dollaro (GBP/USD)</option>
            <option value="BTC/USD">Bitcoin (BTC/USD)</option>
        </select>

        <label>Grafico Live in Diretta:</label>
        <div class="chart-container" id="tradingview_widget"></div>

        <label>Timeframe Operativo:</label>
        <div class="tf-grid">
            <div class="tf-btn active" onclick="setTF(this, 'M1')">M1</div>
            <div class="tf-btn" onclick="setTF(this, 'M5')">M5</div>
            <div class="tf-btn" onclick="setTF(this, 'M15')">M15</div>
            <div class="tf-btn" onclick="setTF(this, 'H1')">H1</div>
        </div>

        <div class="btn-group">
            <button type="button" id="action-btn" class="btn" onclick="generaSegnalePro()">⚡ GENERA SEGNALE PRO</button>
            <button type="button" id="sync-btn" class="btn btn-secondary" onclick="syncBroker()">🔄 SYNC</button>
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
        <div style="font-size: 0.72rem; color: #38bdf8; margin-bottom: 6px; font-weight: bold;">ANALISI RANGE DI MERCATO PROFESSIONALE</div>
        
        <div class="data-row">
            <span>Asset & TF:</span>
            <strong id="res-asset">--</strong>
        </div>
        <div class="data-row">
            <span>Prezzo Live Reale:</span>
            <strong id="res-liveprice" style="color: #38bdf8;">--</strong>
        </div>
        <div class="data-row">
            <span>Direzione:</span>
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
            if (asset.includes("EUR")) tvSymbol = "FX:EURUSD";
            else if (asset.includes("GBP")) tvSymbol = "FX:GBPUSD";
            else if (asset.includes("BTC")) tvSymbol = "BITSTAMP:BTCUSD";
            initChart(tvSymbol);
        }

        initChart("OANDA:XAUUSD");

        function setTF(element, tf) {
            document.querySelectorAll('.tf-btn').forEach(btn => btn.classList.remove('active'));
            element.classList.add('active');
            currentTF = tf;
        }

        async function syncBroker() {
            const assetSelect = document.getElementById('asset-select').value;
            const syncBtn = document.getElementById('sync-btn');
            syncBtn.innerText = "...";
            syncBtn.disabled = true;

            try {
                const res = await fetch('/api/price/' + encodeURIComponent(assetSelect));
                const data = await res.json();
                if (data && data.price) {
                    alert("Sincronizzazione completata! Prezzo live da broker: $" + data.price);
                }
            } catch(e) {
                alert("Errore sincronizzazione live. Riprova tra un secondo.");
            } finally {
                syncBtn.innerText = "🔄 SYNC";
                syncBtn.disabled = false;
            }
        }

        async function generaSegnalePro() {
            const assetSelect = document.getElementById('asset-select');
            const btnEl = document.getElementById('action-btn');
            const signalBox = document.getElementById('signal-box');

            if (!assetSelect || !btnEl || !signalBox) return;

            const asset = assetSelect.value;
            btnEl.innerText = "Sincronizzazione Live...";
            btnEl.disabled = true;

            let livePrice = 0;
            
            try {
                const response = await fetch('/api/price/' + encodeURIComponent(asset));
                if (!response.ok) throw new Error("Feed error");
                const data = await response.json();
                if (data && data.price && data.price > 1) {
                    livePrice = parseFloat(data.price);
                }
            } catch (e) {
                alert("⚠️ Impossibile sincronizzare il prezzo live del broker. Il segnale non è stato generato per evitare errori di quotazione.");
                btnEl.innerText = "⚡ GENERA SEGNALE PRO";
                btnEl.disabled = false;
                return;
            }

            const decimals = (asset.includes("USD") && !asset.includes("XAU") && !asset.includes("BTC")) ? 4 : 2;
            const direction = Math.random() > 0.48 ? "BUY" : "SELL";
            
            const step = asset.includes("XAU") ? 2.50 : 0.0025;
            let rangeText, slVal, tpText;
            const cleanAssetSymbol = asset.replace("/", "");

            if (direction === "BUY") {
                let upperEntry = livePrice;
                let lowerEntry = livePrice - step;
                let sl = lowerEntry - (step * 1.5);
                let tp1 = upperEntry + (step * 2);
                let tp2 = upperEntry + (step * 4);

                rangeText = `${upperEntry.toFixed(decimals)} / ${lowerEntry.toFixed(decimals)}`;
                slVal = sl.toFixed(decimals);
                tpText = `${tp1.toFixed(decimals)} / ${tp2.toFixed(decimals)}`;
            } else {
                let lowerEntry = livePrice;
                let upperEntry = livePrice + step;
                let sl = upperEntry + (step * 1.5);
                let tp1 = lowerEntry - (step * 2);
                let tp2 = lowerEntry - (step * 4);

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
                alert("Segnale in stile pro copiato negli appunti per Telegram!");
            });
        }
    </script>

</body>
</html>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
