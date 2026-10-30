# ==============================================================================
# quantclaw/dashboard.py â€” MetaTrader 5 Telemetry, Diagnostics & Control HUD
# ==============================================================================
"""
QuantClaw MT5 Pro Telemetry & Control Dashboard.
Modern, responsive Dark UI embedding live MT5 account telemetry, positions,
pending orders, multi-engine strategy radar, real-time log terminal,
AI market discussions, and complete settings editor.
"""

from __future__ import annotations

DASHBOARD_VERSION = "v4.5 MT5 Pro"

_HTML_PART1 = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>QuantClaw MT5 â€” Autonomous AI+ML Trading System</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#070a0f;--panel:#0d131f;--card:#141c2c;--border:#1f2d42;--border-light:#2c3e5b;
  --green:#00e676;--green-glow:rgba(0,230,118,0.25);
  --red:#ff3d57;--red-glow:rgba(255,61,87,0.25);
  --yellow:#ffb300;--blue:#2979ff;--blue-glow:rgba(41,121,255,0.25);
  --purple:#7c4dff;--muted:#7e92b0;--text:#e8effa;--text2:#b0c2de;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Oxygen,Ubuntu,Cantarell,sans-serif;font-size:13px;line-height:1.4;overflow-x:hidden;}
#header{display:flex;align-items:center;justify-content:space-between;padding:10px 20px;background:var(--panel);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100;flex-wrap:wrap;gap:12px;}
#header .logo{font-size:18px;font-weight:800;letter-spacing:.6px;display:flex;align-items:center;}
#header .logo span{color:var(--blue);}
#arm-btn{padding:9px 24px;border:none;border-radius:6px;font-size:13px;font-weight:800;cursor:pointer;transition:all .2s;box-shadow:0 0 10px transparent;}
#arm-btn.armed{background:var(--red);color:#fff;box-shadow:0 0 14px var(--red-glow);}
#arm-btn.disarmed{background:var(--green);color:#000;box-shadow:0 0 14px var(--green-glow);}
.hstats{display:flex;gap:18px;align-items:center;flex-wrap:wrap;}
.stat-chip{display:flex;flex-direction:column;align-items:flex-end;padding:2px 8px;}
.stat-chip .label{font-size:9.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;font-weight:600;}
.stat-chip .val{font-size:15px;font-weight:800;font-variant-numeric:tabular-nums;}
.pos{color:var(--green);}.neg{color:var(--red);}.neu{color:var(--text);}
#main{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(360px,440px);gap:0;height:calc(100vh - 58px);overflow:hidden;}
#left{display:flex;flex-direction:column;overflow-y:auto;padding:16px;gap:16px;}
#right{background:var(--panel);border-left:1px solid var(--border);display:flex;flex-direction:column;overflow-y:auto;}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:8px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.25);}
.panel-header{padding:10px 14px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;}
.panel-body{padding:14px;}
.equity-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px;}
.eq-card{background:var(--card);border-radius:6px;padding:10px;text-align:center;border:1px solid var(--border);transition:border-color .2s;}
.eq-card:hover{border-color:var(--border-light);}
.eq-card .el{font-size:10px;color:var(--muted);text-transform:uppercase;margin-bottom:4px;font-weight:600;}
.eq-card .ev{font-size:16px;font-weight:800;font-variant-numeric:tabular-nums;}
table.custom-table{width:100%;border-collapse:collapse;font-size:12px;}
table.custom-table th{background:var(--card);color:var(--muted);font-weight:700;text-align:left;padding:9px 12px;font-size:10px;text-transform:uppercase;letter-spacing:.5px;}
table.custom-table td{padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:middle;}
table.custom-table tr:hover{background:rgba(255,255,255,.015);}
.badge{padding:3px 7px;border-radius:4px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.4px;}
.badge-buy{background:rgba(0,230,118,.15);color:var(--green);border:1px solid rgba(0,230,118,.3);}
.badge-sell{background:rgba(255,61,87,.15);color:var(--red);border:1px solid rgba(255,61,87,.3);}
.badge-neu { background: #f59e0b; color: #fff; }
#terminal{background:#03060a;color:#a9c0dc;font-family:'JetBrains Mono','Consolas','Courier New',monospace;font-size:11.5px;padding:12px;height:260px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;line-height:1.6;}
.log-line{margin-bottom:3px;white-space:pre-wrap;word-break:break-all;}
.log-info{color:#00e676;}.log-warn{color:#ffb300;}.log-err{color:#ff3d57;}.log-ml{color:#2979ff;}
.setting-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;gap:8px;}
.setting-row label{font-size:11px;color:var(--text2);flex:1;}
.setting-row input[type=number],.setting-row input[type=text],.setting-row input[type=password],.setting-row select{background:#04070c;border:1px solid var(--border);color:var(--text);border-radius:5px;padding:5px 8px;font-size:11px;outline:none;transition:border-color .2s;}
.setting-row input:focus,.setting-row select:focus{border-color:var(--blue);}
.setting-row input[type=number]{width:85px;}
.setting-row input[type=text],.setting-row input[type=password]{width:170px;}
.setting-row select{width:170px;}
.toggle{position:relative;display:inline-block;width:36px;height:18px;flex-shrink:0;}
.toggle input{opacity:0;width:0;height:0;}
.slider{position:absolute;cursor:pointer;inset:0;background:#1f2d42;border-radius:18px;transition:.2s;}
.slider:before{content:'';position:absolute;height:12px;width:12px;left:3px;bottom:3px;background:white;border-radius:50%;transition:.2s;}
input:checked+.slider{background:var(--green);}input:checked+.slider:before{transform:translateX(18px);}
.tabs{display:flex;gap:4px;padding:8px 14px 0;background:var(--panel);border-bottom:1px solid var(--border);overflow-x:auto;}
.tab-btn{padding:7px 14px;border:none;background:none;color:var(--muted);cursor:pointer;font-size:11px;font-weight:700;border-bottom:2px solid transparent;transition:all .15s;white-space:nowrap;}
.tab-btn.active{color:var(--text);border-bottom-color:var(--blue);}
.tab-content{display:none;padding:14px;}.tab-content.active{display:block;}
.btn-sm{padding:5px 12px;border:none;border-radius:5px;cursor:pointer;font-size:11px;font-weight:700;transition:opacity .15s,transform .1s;}
.btn-sm:hover{opacity:.9;}.btn-sm:active{transform:scale(.98);}
.btn-danger{background:var(--red);color:#fff;}.btn-primary{background:var(--blue);color:#fff;}.btn-success{background:var(--green);color:#000;}
.empty{color:var(--muted);text-align:center;padding:18px;font-size:12px;}
#status-bar{background:#03060a;border-top:1px solid var(--border);padding:5px 16px;font-size:10px;color:var(--muted);display:flex;gap:20px;align-items:center;}
.dot{width:6px;height:6px;border-radius:50%;display:inline-block;margin-right:4px;}
.dot.green{background:var(--green);}.dot.red{background:var(--red);}.dot.yellow{background:var(--yellow);}
#toast{position:fixed;bottom:24px;right:24px;padding:12px 18px;background:var(--card);border:1px solid var(--blue);box-shadow:0 8px 30px rgba(0,0,0,.6);border-radius:8px;font-size:12px;font-weight:600;z-index:9999;transition:opacity .3s,transform .3s;opacity:0;transform:translateY(10px);pointer-events:none;}
::-webkit-scrollbar{width:6px;height:6px;}::-webkit-scrollbar-track{background:transparent;}::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}::-webkit-scrollbar-thumb:hover{background:var(--border-light);}
@media(max-width:1080px){#main{grid-template-columns:1fr;height:auto;overflow-y:auto;}#right{border-left:none;border-top:1px solid var(--border);}}
</style>
</head>
<body>
<div id="header">
  <div class="logo">Quant<span>Claw</span> <small style="font-size:10px;color:var(--blue);font-weight:800;background:rgba(41,121,255,.15);padding:2px 7px;border-radius:4px;margin-left:6px;border:1px solid rgba(41,121,255,.3);">MT5 PRO</small></div>
  <div class="hstats">
    <div class="stat-chip"><span class="label">Balance</span><span class="val neu" id="h-balance">$--</span></div>
    <div class="stat-chip"><span class="label">Equity</span><span class="val neu" id="h-equity">$--</span></div>
    <div class="stat-chip"><span class="label">Floating P&amp;L</span><span class="val" id="h-floating">--</span></div>
    <div class="stat-chip"><span class="label">Today P&amp;L</span><span class="val" id="h-today">--</span></div>
    <div class="stat-chip"><span class="label">ML Score</span><span class="val pos" id="h-decscore">--</span></div>
    <div class="stat-chip"><span class="label">Daily DD</span><span class="val" id="hDrawdown">0.0%</span></div>
    <div class="stat-chip"><span class="label">Margin Lvl</span><span class="val" id="hMarginLvl">--%</span></div>
  </div>
  <div style="display:flex;gap:8px;">
    <button id="arm-btn" class="disarmed" onclick="toggleArm()">ARM BOT</button>
    <button class="btn-sm btn-danger" onclick="flattenAll()" style="padding:9px 16px;">âš¡ FLATTEN ALL</button>
  </div>
</div>
"""

_HTML_PART2 = f"""
<div id="main">
<!-- Left Column -->
<div id="left">

  <!-- Live MT5 Open Positions Table -->
  <div class="panel" style="min-height:190px;display:flex;flex-direction:column;flex-shrink:0;">
    <div class="panel-header">
      <span style="display:flex;align-items:center;gap:6px;">ðŸ“Š MetaTrader 5 Open Positions</span>
      <span id="pos-count-badge" class="badge" style="background:var(--card);color:var(--text2)">0 Active</span>
    </div>
    <div class="panel-body" style="padding:0;overflow-x:auto;overflow-y:auto;min-height:140px;max-height:300px;flex:1;">
      <table class="custom-table" id="positions-table" style="min-width:720px;width:100%;">
        <thead>
          <tr>
            <th style="width:85px;">Ticket</th>
            <th style="width:110px;">Symbol</th>
            <th style="width:75px;">Type</th>
            <th style="width:70px;">Lots</th>
            <th style="width:105px;">Open Price</th>
            <th style="width:105px;">Current</th>
            <th style="width:95px;">SL</th>
            <th style="width:95px;">TP</th>
            <th style="width:100px;">Profit ($)</th>
            <th style="width:125px;text-align:center;">Action</th>
          </tr>
        </thead>
        <tbody id="positions-tbody">
          <tr><td colspan="10" class="empty" style="padding:42px 20px;font-size:13px;">No open positions on MetaTrader 5</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Equity & Capital Growth Chart -->
  <div class="panel" style="flex-shrink:0;">
    <div class="panel-header">
      <span>ðŸ“ˆ Account Growth &amp; Equity Curve</span>
      <div style="display:flex;gap:6px">
        <button class="btn-sm btn-primary" onclick="setChartPeriod(7)" id="p7">7D</button>
        <button class="btn-sm btn-primary" onclick="setChartPeriod(30)" id="p30" style="opacity:.5">30D</button>
        <button class="btn-sm btn-primary" onclick="setChartPeriod(90)" id="p90" style="opacity:.5">90D</button>
      </div>
    </div>
    <div class="panel-body" style="padding:12px 14px;">
      <div class="equity-grid">
        <div class="eq-card"><div class="el">Margin Free</div><div class="ev neu" id="eq-marginfree">$--</div></div>
        <div class="eq-card"><div class="el">Margin Level</div><div class="ev pos" id="eq-marginlvl">--%</div></div>
        <div class="eq-card"><div class="el">Today Realized</div><div class="ev" id="eq-today">--</div></div>
        <div class="eq-card"><div class="el">Drawdown vs Limit (<span id="cfg-daily-max">3.0</span>%)</div><div class="ev neu" id="eq-drawdown">0.0%</div></div>
      </div>
      <div style="height:125px;width:100%;position:relative;">
        <canvas id="equityChart" style="height:125px;width:100%;"></canvas>
      </div>
    </div>
  </div>

  <!-- Telemetry & Diagnostic Tabs (Bottom Left) -->
  <div class="panel">
    <div class="tabs">
      <button class="tab-btn active" onclick="switchLeftTab('logs')">ðŸ“œ Live Bot Terminal</button>
      <button class="tab-btn" onclick="switchLeftTab('diagnostics')">ðŸ”¬ Auto-Diagnostics &amp; ML Brain</button>
      <button class="tab-btn" onclick="switchLeftTab('signals')">ðŸŽ¯ 24/7 Strategy Radar</button>
      <button class="tab-btn" onclick="switchLeftTab('journal')">ðŸ“‹ MT5 Trade History</button>
      <button class="tab-btn" onclick="switchLeftTab('discussions')">ðŸ¤– 24/7 AI Discussion</button>
      <button class="tab-btn" onclick="switchLeftTab('news')">ðŸ“° News &amp; Macro</button>
      <button class="tab-btn" onclick="switchLeftTab('performance')">ðŸ“Š Performance Analytics</button>
    </div>

    <!-- Live Terminal Tab -->
    <div id="ltab-logs" class="tab-content active" style="padding:10px;">
      <div style="display:flex;justify-content:space-between;margin-bottom:6px;align-items:center;">
        <span style="font-size:10px;color:var(--muted);text-transform:uppercase;">Real-time execution &amp; MT5 telemetry stream</span>
        <button class="btn-sm" style="background:var(--card);color:var(--text2);" onclick="clearLogs()">Clear</button>
      </div>
      <div id="terminal"><div class="log-line log-info">QuantClaw MT5 System initialized. Listening for telemetry events...</div></div>
    </div>

    <!-- Auto-Diagnostics Tab -->
    <div id="ltab-diagnostics" class="tab-content" style="padding:14px;">
      <div class="equity-grid" style="margin-bottom:12px;">
        <div class="eq-card"><div class="el">Decision Score</div><div class="ev pos" id="diag-score">100%</div></div>
        <div class="eq-card"><div class="el">Market Health</div><div class="ev neu" id="diag-status">Going smooth</div></div>
        <div class="eq-card"><div class="el">Correct Decisions</div><div class="ev pos" id="diag-correct">0</div></div>
        <div class="eq-card"><div class="el">Incorrect Decisions</div><div class="ev neg" id="diag-incorrect">0</div></div>
      </div>
      <div style="font-size:11px;font-weight:600;margin-bottom:6px;color:var(--text);">Adaptive ML Feature Weights Matrix</div>
      <div id="weights-box" style="background:#04070c;border:1px solid var(--border);border-radius:6px;padding:10px;font-family:monospace;font-size:11px;color:var(--text2);max-height:140px;overflow-y:auto;">Loading ML weights...</div>
    </div>

    <!-- Strategy Radar Tab -->
    <div id="ltab-signals" class="tab-content" style="padding:0;">
      <div id="signals-list" style="padding:10px 14px;"><div class="empty">Scanning Forex, Gold, Crypto &amp; Indices for setups...</div></div>
    </div>

    <!-- Trade Journal Tab -->
    <div id="ltab-journal" class="tab-content" style="padding:0;">
      <div style="padding:10px 14px 0;">
        <button onclick='exportTrades()' style='padding:6px 14px; background:#6366f1; color:#fff; border:none; border-radius:6px; cursor:pointer;'>&#x2B07; Export CSV</button>
      </div>
      <div id="trades-list" style="padding:6px 14px;"><div class="empty">No completed MT5 trades recorded yet</div></div>
    </div>

    <!-- AI Discussion Tab -->
    <div id="ltab-discussions" class="tab-content" style="padding:14px;">
      <div style="font-size:11px;font-weight:600;margin-bottom:6px;color:var(--text);">Continuous AI Market Commentary &amp; Briefings</div>
      <div id="discussions-list" style="background:#04070c;border:1px solid var(--border);border-radius:6px;padding:10px;font-size:11px;color:var(--text2);min-height:120px;line-height:1.6;">AI Market Discussion initializing...</div>
    </div>

    <!-- News & Macro Tab -->
    <div id="ltab-news" class="tab-content" style="padding:14px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <div style="font-size:11px;font-weight:600;color:var(--text);">Global Economic News &amp; Macro Calendar</div>
        <div id="news-global-pill" class="badge badge-buy">Sentiment: Neutral</div>
      </div>
      <div id="news-list" style="background:#04070c;border:1px solid var(--border);border-radius:6px;padding:10px;font-size:11px;color:var(--text2);min-height:120px;max-height:260px;overflow-y:auto;">Loading economic headlines...</div>
    </div>

    <!-- Performance Analytics Tab -->
    <div id="ltab-performance" class="tab-content" style="padding:14px;">
      <div class="equity-grid" style="margin-bottom:12px;">
        <div class="eq-card"><div class="el">Win Rate</div><div class="ev pos" id="perf-winrate">0.0%</div></div>
        <div class="eq-card"><div class="el">Profit Factor</div><div class="ev neu" id="perf-pf">0.00</div></div>
        <div class="eq-card"><div class="el">Total Net P&amp;L</div><div class="ev pos" id="perf-pnl">$0.00</div></div>
        <div class="eq-card"><div class="el">Avg Risk:Reward</div><div class="ev neu" id="perf-rr">0.00</div></div>
      </div>
      <div class="equity-grid" style="margin-bottom:12px;">
        <div class="eq-card"><div class="el">Total Trades</div><div class="ev neu" id="perf-total">0</div></div>
        <div class="eq-card"><div class="el">Max Win Streak</div><div class="ev pos" id="perf-winstreak">0</div></div>
        <div class="eq-card"><div class="el">Max Loss Streak</div><div class="ev neg" id="perf-lossstreak">0</div></div>
        <div class="eq-card"><div class="el">Top Symbol</div><div class="ev pos" id="perf-topsym">--</div></div>
      </div>
      <div style="font-size:11px;font-weight:600;margin-bottom:6px;color:var(--text);">Asset P&amp;L Breakdown</div>
      <div id="perf-symbol-breakdown" style="background:#04070c;border:1px solid var(--border);border-radius:6px;padding:10px;font-family:monospace;font-size:11px;color:var(--text2);">Loading symbol breakdown...</div>
    </div>
  </div>

</div>

<!-- Right Column: MT5 Settings & Controls -->
<div id="right">
  <!-- Connection Health Card -->
  <div style="padding:14px;border-bottom:1px solid var(--border);">
    <div style="font-size:10px;color:var(--muted);text-transform:uppercase;margin-bottom:8px;font-weight:600;">MetaTrader 5 Status</div>
    <div class="setting-row"><label>Broker Server</label><span id="rep-server" style="font-weight:700;color:var(--blue)">--</span></div>
    <div class="setting-row"><label>Account Login</label><span id="rep-login" style="font-weight:700">--</span></div>
    <div class="setting-row"><label>Connection</label><span id="rep-conn" style="font-weight:700;color:var(--yellow)">Checking...</span></div>
    <div class="setting-row"><label>Trade Permission</label><span id="rep-trade" style="font-weight:700;color:var(--green)">ALLOWED</span></div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchRightTab('mt5')">MT5 Login</button>
    <button class="tab-btn" onclick="switchRightTab('sizing')">Lot Sizing</button>
    <button class="tab-btn" onclick="switchRightTab('strategies')">Strategies</button>
    <button class="tab-btn" onclick="switchRightTab('risk')">Risk &amp; ML</button>
    <button class="tab-btn" onclick="switchRightTab('order')">Manual Order</button>
  </div>


  <!-- Tab 1: MT5 Connection -->
  <div id="rtab-mt5" class="tab-content active">
    <div style="font-size:10px;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px;">MetaTrader 5 Terminal Credentials</div>
    <div class="setting-row"><label>Account Login ID</label><input type="number" id="cfg-mt5login" placeholder="e.g. 10982341" onchange="saveSetting('mt5_login',+this.value)"/></div>
    <div class="setting-row"><label>Account Password</label><input type="password" id="cfg-mt5pass" placeholder="Password" onchange="saveSetting('mt5_password',this.value)"/></div>
    <div class="setting-row"><label>Broker Server</label><input type="text" id="cfg-mt5server" placeholder="e.g. Exness-Real2" onchange="saveSetting('mt5_server',this.value)"/></div>
    <div class="setting-row"><label>Custom MT5 Path</label><input type="text" id="cfg-mt5path" placeholder="Leave blank for auto" onchange="saveSetting('mt5_path',this.value)"/></div>
    <div class="setting-row"><label>Magic Number</label><input type="number" id="cfg-magic" value="999111" onchange="saveSetting('mt5_magic_number',+this.value)"/></div>

    <div style="border-top:1px solid var(--border);padding-top:8px;margin-top:8px;">
      <div style="font-size:10px;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px;">Claude AI Co-Pilot</div>
      <div class="setting-row"><label>Anthropic API Key</label><input type="password" id="cfg-anthropic" placeholder="sk-ant-..." onchange="saveSetting('anthropic_api_key',this.value)"/></div>
      <div class="setting-row"><label>Claude Model</label><select id="cfg-claudemodel" onchange="saveSetting('anthropic_model',this.value)"><option value="claude-sonnet-4-6">Claude Sonnet 4.6</option><option value="claude-3-7-sonnet-20250219">Claude 3.7 Sonnet</option><option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet</option></select></div>
    </div>
    <button class="btn-sm btn-success" onclick="saveAndConnectMT5()" style="margin-top:12px;width:100%">â†º Save &amp; Connect MT5</button>
  </div>

  <!-- Tab 2: Multi-Asset Lot Sizing -->
  <div id="rtab-sizing" class="tab-content">
    <div style="font-size:10px;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px;">Asset Classes &amp; Lot Sizes</div>
    <div class="setting-row"><label>Sizing Mode</label><select id="cfg-sizingmode" onchange="saveSetting('trade_sizing_mode',this.value)"><option value="AutoRisk">AutoRisk (% Risk / SL Points)</option><option value="ManualLots">Manual Lot Quantities</option></select></div>
    <div class="setting-row"><label>Risk Per Trade %</label><input type="number" id="cfg-risktradepct" step=".1" min=".1" max="10" onchange="saveSetting('risk_per_trade_pct',+this.value)"/></div>
    <div class="setting-row"><label>Max Dollar Risk ($ Cap)</label><input type="number" id="cfg-maxriskusd" step="1" min="1" max="50" onchange="saveSetting('max_risk_usd_per_trade',+this.value)"/></div>
    <div class="setting-row"><label>Min Dollar Risk ($ Floor)</label><input type="number" id="cfg-minriskusd" step="1" min="1" max="20" onchange="saveSetting('min_risk_usd_per_trade',+this.value)"/></div>
    <div class="setting-row"><label>Max Spread (Points)</label><input type="number" id="cfg-maxspread" min="5" max="200" onchange="saveSetting('max_spread_points',+this.value)"/></div>
    <div style="border-top:1px solid var(--border);padding-top:10px;margin-top:10px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
        <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;">📋 Symbol Permissions</div>
        <div id="sym-active-count" style="font-size:10px;color:var(--accent);font-weight:700;"></div>
      </div>
      <div style="font-size:9px;color:var(--muted);margin-bottom:8px;">Tick ON symbols you want the bot to trade. Untick to block completely.</div>
      <input type="text" id="sym-search" placeholder="🔍 Search pairs (e.g. NDX, BTC, EUR, XAU)..." onkeyup="filterSymbolList()" style="width:100%;box-sizing:border-box;padding:5px 8px;font-size:11px;margin-bottom:6px;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);"/>
      <div id="symbol-toggle-list" style="display:flex;flex-direction:column;gap:5px;max-height:240px;min-height:140px;overflow-y:auto;padding-right:4px;border:1px solid var(--border);border-radius:6px;padding:6px;background:rgba(0,0,0,0.15);"><div style="color:var(--muted);font-size:11px;text-align:center;padding:12px;">Loading preset symbols...</div></div>
      <div style="display:flex;gap:4px;margin-top:6px;">
        <input type="text" id="add-sym-input" placeholder="Add custom pair (e.g. NDXUSD, DJIUSD, XAUUSD.p)" style="flex:1;padding:5px 8px;font-size:11px;background:var(--input-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);"/>
        <button onclick="addCustomSymbol()" style="background:#3b82f6;color:#fff;border:none;padding:5px 12px;border-radius:4px;font-size:11px;cursor:pointer;font-weight:600;">+ Add</button>
      </div>
      <div style="margin-top:8px;display:flex;gap:6px;">
        <button onclick="setAllSymbols(true)" style="flex:1;background:#22c55e;color:#fff;border:none;padding:5px 0;border-radius:5px;cursor:pointer;font-size:11px;font-weight:600;">✅ Enable All</button>
        <button onclick="setAllSymbols(false)" style="flex:1;background:#ef4444;color:#fff;border:none;padding:5px 0;border-radius:5px;cursor:pointer;font-size:11px;font-weight:600;">🔴 Disable All</button>
      </div>
    </div>

    <div style="border-top:1px solid var(--border);padding-top:8px;margin-top:8px;">
      <div style="font-size:10px;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px;">Default Lot Sizes (Manual Mode)</div>
      <div class="setting-row"><label>EURUSD Lots</label><input type="number" id="cfg-qty-eurusd" step="0.01" min="0.01" onchange="saveSymbolQty('EURUSD',+this.value)"/></div>
      <div class="setting-row"><label>GBPUSD Lots</label><input type="number" id="cfg-qty-gbpusd" step="0.01" min="0.01" onchange="saveSymbolQty('GBPUSD',+this.value)"/></div>
      <div class="setting-row"><label>USDJPY Lots</label><input type="number" id="cfg-qty-usdjpy" step="0.01" min="0.01" onchange="saveSymbolQty('USDJPY',+this.value)"/></div>
      <div class="setting-row"><label>GOLD (XAUUSD) Lots</label><input type="number" id="cfg-qty-xauusd" step="0.01" min="0.01" onchange="saveSymbolQty('XAUUSD',+this.value)"/></div>
      <div class="setting-row"><label>BTCUSD Lots</label><input type="number" id="cfg-qty-btcusd" step="0.01" min="0.01" onchange="saveSymbolQty('BTCUSD',+this.value)"/></div>
      <div class="setting-row"><label>US30 / DJI Lots</label><input type="number" id="cfg-qty-us30" step="0.01" min="0.01" onchange="saveSymbolQty('US30',+this.value)"/></div>
      <div class="setting-row"><label>NAS100 / NDX Lots</label><input type="number" id="cfg-qty-nas100" step="0.01" min="0.01" onchange="saveSymbolQty('NAS100',+this.value)"/></div>
      <div class="setting-row"><label>NDXUSD Lots</label><input type="number" id="cfg-qty-ndxusd" step="0.01" min="0.01" onchange="saveSymbolQty('NDXUSD',+this.value)"/></div>
      <div class="setting-row"><label>DJIUSD Lots</label><input type="number" id="cfg-qty-djiusd" step="0.01" min="0.01" onchange="saveSymbolQty('DJIUSD',+this.value)"/></div>
    </div>
    <button class="btn-sm btn-success" onclick="loadSettings()" style="margin-top:10px;width:100%">â†º Refresh Sizing</button>
  </div>

  <!-- Tab 3: Strategies -->
  <div id="rtab-strategies" class="tab-content">
    <div style="font-size:10px;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px;">Autonomous Engine</div>
    <div class="setting-row"><label>24/7 Autonomous Scanning</label><label class="toggle"><input type="checkbox" id="cfg-auto" onchange="saveSetting('enable_autonomous_trading',this.checked)"><span class="slider"></span></label></div>

    <div style="border-top:1px solid var(--border);margin-top:8px;padding-top:8px;">
      <div style="font-size:10px;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px;">5 Institutional Strategies</div>
      <div class="setting-row"><label>⚡ TITAN PRO (Institutional Flow &amp; Reversal)</label><label class="toggle"><input type="checkbox" id="cfg-titan" onchange="saveSetting('strategy_titan_pro_enabled',this.checked)"><span class="slider"></span></label></div>
      <div class="setting-row"><label>SMC Liquidity &amp; Order Blocks</label><label class="toggle"><input type="checkbox" id="cfg-smc" onchange="saveSetting('strategy_smc_enabled',this.checked)"><span class="slider"></span></label></div>
      <div class="setting-row"><label>OCC R5 Trend &amp; Momentum</label><label class="toggle"><input type="checkbox" id="cfg-occ" onchange="saveSetting('strategy_occ_r5_enabled',this.checked)"><span class="slider"></span></label></div>
      <div class="setting-row"><label>Eyes Smart Structure Pro</label><label class="toggle"><input type="checkbox" id="cfg-eyes" onchange="saveSetting('strategy_eyes_sme_enabled',this.checked)"><span class="slider"></span></label></div>
      <div class="setting-row"><label>Mean-Reversion Snapper</label><label class="toggle"><input type="checkbox" id="cfg-meanrev" onchange="saveSetting('strategy_mean_rev_enabled',this.checked)"><span class="slider"></span></label></div>
      <div class="setting-row"><label>Quant Way Institutional Flow</label><label class="toggle"><input type="checkbox" id="cfg-qw" onchange="saveSetting('strategy_quant_way_enabled',this.checked)"><span class="slider"></span></label></div>
    </div>
  </div>

  <!-- Tab 4: Risk & ML -->
  <div id="rtab-risk" class="tab-content">
    <div style="font-size:10px;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px;">Capital Preservation &amp; Protection</div>
    <div class="setting-row"><label>Daily Max Loss % (Circuit Breaker)</label><input type="number" id="cfg-dloss" step=".5" min="1" max="20" onchange="saveSetting('daily_max_loss_pct',+this.value)"/></div>
    <div class="setting-row"><label>Weekly Profit Target %</label><input type="number" id="cfg-wtp" step="5" min="10" max="100" onchange="saveSetting('weekly_profit_target_pct',+this.value)"/></div>
    <div class="setting-row"><label>Max Concurrent Positions</label><input type="number" id="cfg-maxpos" step="1" min="1" max="10" onchange="saveSetting('max_concurrent_positions',+this.value)"/></div>
    <div class="setting-row"><label>🛡️ Soft Risk Reduction (+0.75R to -0.25R SL)</label><label class="toggle"><input type="checkbox" id="cfg-softrisk" onchange="saveSetting('enable_soft_risk_reduction',this.checked)"><span class="slider"></span></label></div>
    <div class="setting-row"><label>🛡️ Early Breakeven (+0.45R to 0 SL)</label><label class="toggle"><input type="checkbox" id="cfg-earlybe" onchange="saveSetting('enable_early_breakeven',this.checked)"><span class="slider"></span></label></div>
    <div class="setting-row"><label>Dynamic Breakeven (1.2R)</label><label class="toggle"><input type="checkbox" id="cfg-breakeven" onchange="saveSetting('enable_breakeven_trigger',this.checked)"><span class="slider"></span></label></div>
    <div class="setting-row"><label>Partial Take Profit (40% @ 1.8R)</label><label class="toggle"><input type="checkbox" id="cfg-partialtp" onchange="saveSetting('enable_partial_take_profit',this.checked)"><span class="slider"></span></label></div>
    <div class="setting-row"><label>ATR Trailing Stop</label><label class="toggle"><input type="checkbox" id="cfg-trailing" onchange="saveSetting('enable_trailing_stop',this.checked)"><span class="slider"></span></label></div>

    <div style="border-top:1px solid var(--border);padding-top:8px;margin-top:8px;">
      <div style="font-size:10px;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px;">ML Brain &amp; Confluence</div>
      <div class="setting-row"><label>ML Execution Threshold</label><input type="number" id="cfg-mlthresh" step="1" min="50" max="100" onchange="saveSetting('ml_brain_min_execute_score',+this.value)"/></div>
      <div class="setting-row"><label>Confluence Bonus (+Pts)</label><input type="number" id="cfg-confluence" step="5" min="0" max="50" onchange="saveSetting('ml_brain_confluence_bonus',+this.value)"/></div>
    </div>
  </div>

  <!-- Tab 5: Manual Market Order -->
  <div id="rtab-order" class="tab-content">
    <div style="font-size:10px;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px;">Manual Market Order Dispatch</div>
    <div class="setting-row"><label>Symbol</label><input type="text" id="ord-symbol" placeholder="EURUSD, XAUUSD, BTCUSD" value="EURUSD"/></div>
    <div class="setting-row"><label>Action</label><select id="ord-action"><option value="BUY">BUY (Long)</option><option value="SELL">SELL (Short)</option></select></div>
    <div class="setting-row"><label>Lots</label><input type="number" id="ord-lots" step="0.01" min="0.01" value="0.01"/></div>
    <div class="setting-row"><label>Stop Loss (Price)</label><input type="number" id="ord-sl" step="0.0001" placeholder="0.00000 (Optional)"/></div>
    <div class="setting-row"><label>Take Profit (Price)</label><input type="number" id="ord-tp" step="0.0001" placeholder="0.00000 (Optional)"/></div>
    <button class="btn-sm btn-success" onclick="placeManualOrder()" style="margin-top:14px;width:100%">ðŸš€ Send Market Order to MT5</button>
  </div>
</div>
</div>

<div id="status-bar">
  <span><span class="dot" id="dot-engine"></span>Engine: <span id="sb-engine">--</span></span>
  <span><span class="dot" id="dot-mt5"></span>MT5 Terminal: <span id="sb-mt5">--</span></span>
  <span>Last Signal: <span id="sb-signal">--</span></span>
  <span id="session-pill" style="padding:2px 6px;border-radius:4px;font-weight:bold;margin-left:10px;color:#000;"></span>
  <span style="margin-left:auto">QuantClaw {DASHBOARD_VERSION}</span>
</div>
<div id="toast"></div>
"""

_HTML_JS = """
<script>
let PORT=PORT_PLACEHOLDER,AUTH='AUTH_PLACEHOLDER',armed=false,chart,chartPeriod=7,seenLogs=new Set();
const BASE_PREFIX = window.location.pathname.startsWith('/lasthopepanel') ? '/lasthopepanel' : '';
function api(p,o){
  const cleanP = p.startsWith('/') ? p : '/' + p;
  let url = BASE_PREFIX + cleanP;
  if (AUTH) {
    const sep = url.includes('?') ? '&' : '?';
    const authClean = AUTH.replace(/^[?&]+/, '');
    if (authClean) url += sep + authClean;
  }
  return fetch(url,o||{}).then(r=>r.json()).catch(e=>({error:e.message}));
}

// â”€â”€ Chart â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function initChart(){
  const ctx=document.getElementById('equityChart').getContext('2d');
  chart=new Chart(ctx,{type:'line',data:{labels:[],datasets:[{label:'Equity',data:[],borderColor:'#00e676',backgroundColor:'rgba(0,230,118,.1)',fill:true,tension:.3,pointRadius:2}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#8395b0',maxTicksLimit:8},grid:{color:'#24324a'}},y:{ticks:{color:'#8395b0',callback:v=>'$'+v.toFixed(0)},grid:{color:'#24324a'}}}}});
}
function setChartPeriod(d){chartPeriod=d;['7','30','90'].forEach(x=>{const b=document.getElementById('p'+x);if(b)b.style.opacity=(x==String(d))?'1':'.5';});loadEquity();}
async function loadEquity(){
  const d=await api('/api/v4/equity-history?days='+chartPeriod);
  const h=d.history||[];
  if(chart&&h.length){
    chart.data.labels = h.map(x => {
    if (!x.date) return '';
    try { return new Date(typeof x.date === 'number' ? x.date*1000 : x.date).toLocaleDateString('en-GB',{month:'short',day:'numeric'}); }
    catch(e) { return String(x.date).slice(5,10); }
});
    chart.data.datasets[0].data=h.map(x=>x.equity||0);
    chart.update('none');
  }
}

// â”€â”€ Account Telemetry â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadAccount(){
  const d=await api('/api/v4/account');
  const fmt=v=>v!==undefined?('$'+Math.abs(v||0).toFixed(2)):'$--';
  const cls=v=>v===undefined?'neu':(v>=0?'pos':'neg');
  const se=(id,v,p)=>{const e=document.getElementById(id);if(!e)return;e.textContent=(p||'')+fmt(v);e.className='val '+cls(v);};

  const hb=document.getElementById('h-balance');if(hb){hb.textContent=fmt(d.balance);hb.className = 'val ' + (d.today_pnl < 0 ? 'neg' : (d.today_pnl > 0 ? 'pos' : 'neu'));}
  se('h-equity',d.equity);
  se('h-floating',d.floating_pnl,d.floating_pnl>=0?'+':'-');
  se('h-today',d.today_pnl,d.today_pnl>=0?'+':'-');

  const mf=document.getElementById('eq-marginfree');if(mf)mf.textContent=fmt(d.margin_free);
  const ml=document.getElementById('eq-marginlvl');if(ml)ml.textContent=(d.margin_level||0).toFixed(1)+'%';
  const et=document.getElementById('eq-today');if(et){et.textContent=(d.today_pnl>=0?'+':'-')+fmt(d.today_pnl);et.className='ev '+cls(d.today_pnl);}

  const repServer=document.getElementById('rep-server');if(repServer)repServer.textContent=d.server||'--';
  const repLogin=document.getElementById('rep-login');if(repLogin)repLogin.textContent=d.login||'--';
  const repConn=document.getElementById('rep-conn');
  if(repConn){
    repConn.textContent=d.connected?'CONNECTED':'DISCONNECTED';
    repConn.style.color=d.connected?'var(--green)':'var(--red)';
  }
  const repTrade=document.getElementById('rep-trade');
  if(repTrade){
    if(d.connected){
      if(d.trade_allowed !== false){
        repTrade.textContent='ALLOWED ðŸŸ¢';
        repTrade.style.color='var(--green)';
      }else{
        repTrade.textContent='TRADING BLOCKED BY BROKER ðŸ”´';
        repTrade.style.color='var(--red)';
      }
    }else{
      repTrade.textContent='--';
      repTrade.style.color='var(--muted)';
    }
  }
}

// â”€â”€ Live Positions Table â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadPositions(){
  const d=await api('/api/positions');
  const positions=d.positions||[];
  const tbody=document.getElementById('positions-tbody');
  const badge=document.getElementById('pos-count-badge');

  if(badge)badge.textContent=positions.length+' Active';
  if(!positions.length){
    tbody.innerHTML='<tr><td colspan="10" class="empty">No open positions on MetaTrader 5</td></tr>';
    return;
  }
  tbody.innerHTML=positions.map(p=>{
    const isBuy=String(p.type||'').toUpperCase()==='BUY'||String(p.side||'').toLowerCase()==='buy';
    const sideBadge=isBuy?'<span class="badge badge-buy">BUY</span>':'<span class="badge badge-sell">SELL</span>';
    const profit=parseFloat(p.profit||p.unrealized_pnl||0);
    const pCls=profit>=0?'pos':'neg';
    const pStr=(profit>=0?'+':'')+'$'+profit.toFixed(2);
    const t=p.ticket;
    return '<tr><td><b>#'+t+'</b></td><td><b>'+(p.symbol||'')+'</b></td><td>'+sideBadge+'</td><td>'+parseFloat(p.volume||p.size||0).toFixed(2)+'</td><td>'+parseFloat(p.open_price||p.entry_price||0).toFixed(5)+'</td><td>'+parseFloat(p.current_price||p.mark_price||0).toFixed(5)+'</td><td>'+(parseFloat(p.sl||0)?parseFloat(p.sl).toFixed(5):'--')+'</td><td>'+(parseFloat(p.tp||0)?parseFloat(p.tp).toFixed(5):'--')+'</td><td class="'+pCls+'" style="font-weight:700">'+pStr+'</td><td><button class="btn-sm btn-danger" onclick="closePos('+t+')">Close</button> <button class="btn-sm btn-primary" onclick="breakevenPos('+t+')">BE</button></td></tr>';
  }).join('');
}

async function closePos(ticket){
  showToast('Closing Position #' + ticket + '...', false);
  const r = await api('/api/close-position', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ticket: ticket})
  });
  if (r && r.success) {
    showToast('Position #' + ticket + ' Closed Successfully ðŸŸ¢', false);
  } else {
    showToast('Close Failed: ' + (r && (r.message || r.error) || 'Error'), true);
  }
  await loadPositions();
  await loadAccount();
}

async function breakevenPos(ticket){
  showToast('Moving SL to Breakeven for #' + ticket + '...', false);
  const r = await api('/api/mt5/breakeven', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ticket: ticket})
  });
  if (r && r.success) {
    showToast('Position #' + ticket + ' Stop Loss moved to Entry ðŸŸ¢', false);
  } else {
    showToast('Breakeven Failed: ' + (r && (r.message || r.error) || 'Check price distance'), true);
  }
  await loadPositions();
}

async function flattenAll(){
  showToast('Flattening all open positions...', false);
  const r = await api('/api/mobile/flatten', {method: 'POST'});
  if (r && r.success) {
    showToast('Flatten complete: ' + r.closed_count + ' closed ðŸŸ¢', false);
  } else {
    showToast('Flatten: ' + (r && r.error || 'Failed'), true);
  }
  await loadPositions();
  await loadAccount();
}

// â”€â”€ Live Logs Terminal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadLogs(){
  const d=await api('/api/v4/logs?limit=80');
  const logs=d.logs||[];
  const term=document.getElementById('terminal');
  if(!logs.length||!term)return;
  let added=false;
  logs.forEach(l=>{
    if(!seenLogs.has(l)){
      seenLogs.add(l);
      // Bound memory usage: prevent unbounded Set growth
      if(seenLogs.size > 500){
        const first = seenLogs.values().next().value;
        seenLogs.delete(first);
      }
      added=true;
      const div=document.createElement('div');
      div.className='log-line';
      if(l.includes('ERROR')||l.includes('FAILED')||l.includes('âŒ'))div.className+=' log-err';
      else if(l.includes('WARN')||l.includes('âš ï¸'))div.className+=' log-warn';
      else if(l.includes('ML')||l.includes('Score')||l.includes('Confluence'))div.className+=' log-ml';
      else div.className+=' log-info';
      div.textContent=l;
      term.appendChild(div);
    }
  });
  if(added){
    term.scrollTop=term.scrollHeight;
    while(term.children.length>200){term.removeChild(term.firstChild);}
  }
}
function clearLogs(){const term=document.getElementById('terminal');if(term)term.innerHTML='';seenLogs.clear();}

// â”€â”€ Auto-Diagnostics & ML Brain â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadDiagnostics(){
  const d=await api('/api/v4/diagnostics');
  if(!d||d.error)return;
  const sc=parseFloat(d.decision_score||100);
  const scEl=document.getElementById('diag-score');
  if(scEl){scEl.textContent=sc.toFixed(1)+'%';scEl.className='ev '+(sc>=70?'pos':(sc>=40?'neu':'neg'));}
  const hDec=document.getElementById('h-decscore');
  if(hDec){hDec.textContent=sc.toFixed(0)+'%';hDec.className='val '+(sc>=70?'pos':(sc>=40?'neu':'neg'));}
  const stEl=document.getElementById('diag-status');
  if(stEl)stEl.textContent=d.decision_status||'Going smooth';
  const dm=d.decision_metrics||{};
  const corEl=document.getElementById('diag-correct');if(corEl)corEl.textContent=dm.correct||0;
  const incEl=document.getElementById('diag-incorrect');if(incEl)incEl.textContent=dm.incorrect||0;

  const wBox=document.getElementById('weights-box');
  if(wBox&&d.weights){wBox.textContent=JSON.stringify(d.weights,null,2);}
}

// â”€â”€ Strategy Radar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadSignals(){
  const d=await api('/api/v4/signals');
  const sigs=d.signals||[];
  const list=document.getElementById('signals-list');
  if(!sigs.length){list.innerHTML='<div class="empty">Scanning Forex, Gold, Crypto &amp; Indices for setups...</div>';return;}
  list.innerHTML=sigs.slice(0,15).map(s=>{
    const isBuy=s.action.toLowerCase()==='buy';
    const dc=isBuy?'badge-buy':'badge-sell';
    const lb=isBuy?'BUY':'SELL';
    const age=Math.round((Date.now()/1000-s.timestamp)/60);
    const at=age<1?'just now':age+'m ago';
    return '<div class="setting-row" style="border-bottom:1px solid var(--border);padding-bottom:6px;"><span class="badge '+dc+'">'+lb+'</span><div style="flex:1;margin-left:8px;"><div style="font-weight:700;font-size:12px;">'+(s.symbol||'')+' Â· '+(s.timeframe||'')+'</div><div style="font-size:10px;color:var(--muted)">'+(s.strategy||'').replace('_',' ')+' Â· '+at+'</div></div><span style="color:var(--blue);font-weight:700">STR '+(parseFloat(s.strength||0)).toFixed(0)+'</span></div>';
  }).join('');
  if(sigs.length){const sb=document.getElementById('sb-signal');if(sb)sb.textContent=sigs[0].symbol+' '+sigs[0].action.toUpperCase();}
}

// â”€â”€ Trade Journal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadJournal(){
  const d=await api('/api/v4/journal?limit=25');
  const trades=d.trades||[];
  const list=document.getElementById('trades-list');
  if(!trades.length){list.innerHTML='<div class="empty">No completed MT5 trades recorded yet</div>';return;}
  list.innerHTML='<table class="custom-table"><thead><tr><th>Ticket</th><th>Symbol</th><th>Action</th><th>Lots</th><th>P&amp;L</th><th>Outcome</th></tr></thead><tbody>'+
    trades.slice(0,15).map(t=>{
      const pnl=parseFloat(t.pnl_usd||0);
      const ps=pnl>=0?'pos':'neg';
      const oc=t.outcome==='win'?'badge-buy':'badge-sell';
      return '<tr><td>#'+(t.ticket||'--')+'</td><td><b>'+(t.symbol||'--')+'</b></td><td>'+(t.action||'').toUpperCase()+'</td><td>'+parseFloat(t.volume||0).toFixed(2)+'</td><td class="'+ps+'" style="font-weight:700">'+(pnl>=0?'+':'')+'$'+pnl.toFixed(2)+'</td><td><span class="badge '+oc+'">'+(t.outcome||'--').toUpperCase()+'</span></td></tr>';
    }).join('')+'</tbody></table>';
}


function exportTrades() {
    api('/api/v4/journal?limit=10000')
        .then(data=>{
            const rows = data.trades || data;
            if (!rows.length) return showToast('No trades to export','warn');
            const headers = Object.keys(rows[0]);
            const csv = [headers.join(','), ...rows.map(r=>headers.map(h=>JSON.stringify(r[h]||'')).join(','))].join('\\n');
            const a = document.createElement('a');
            a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
            a.download = 'quantclaw_trades.csv';
            a.click();
        });
}

// â”€â”€ AI Discussions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadDiscussions(){
  const d=await api('/api/v4/discussions');
  const items=d.discussions||[];
  const box=document.getElementById('discussions-list');
  if(!box)return;
  if(!items.length){box.innerHTML='<div class="empty">24/7 AI Discussion initializing...</div>';return;}
  box.innerHTML=items.slice(0,5).map(i=>'<div style="margin-bottom:8px;border-bottom:1px solid #161f31;padding-bottom:6px;"><b style="color:var(--blue)">['+(i.symbol||'')+']</b> '+(i.text||'')+'</div>').join('');
}

// â”€â”€ News & Macro Calendar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadNews(){
  const d=await api('/api/v4/news');
  if(!d||d.error)return;
  const pill=document.getElementById('news-global-pill');
  if(pill){
    const score=parseFloat(d.global_sentiment||0);
    pill.textContent='Sentiment: '+(score>0.15?'Bullish (+'+score.toFixed(2)+')':(score<-0.15?'Bearish ('+score.toFixed(2)+')':'Neutral ('+score.toFixed(2)+')'));
    pill.className='badge '+(score>0.15?'badge-buy':(score<-0.15?'badge-sell':'badge-neu'));
  }
  const headlines=d.headlines||[];
  const box=document.getElementById('news-list');
  if(!box)return;
  if(!headlines.length){box.innerHTML='<div class="empty">No economic news headlines available</div>';return;}
  box.innerHTML=headlines.slice(0,10).map(h=>{
    const score=parseFloat(h.score||0);
    const badge=score>0?'<span class="badge badge-buy" style="font-size:9px;">+POS</span>':(score<0?'<span class="badge badge-sell" style="font-size:9px;">-NEG</span>':'<span style="font-size:9px;color:var(--muted)">NEU</span>');
    return '<div style="margin-bottom:8px;border-bottom:1px solid #161f31;padding-bottom:6px;display:flex;align-items:flex-start;justify-content:space-between;"><div><div style="font-weight:600;color:var(--text)">'+(h.title||'')+'</div><div style="font-size:10px;color:var(--muted);margin-top:2px;">'+(h.summary||'').substring(0,120)+'...</div></div><div style="margin-left:8px;">'+badge+'</div></div>';
  }).join('');
}

// â”€â”€ Performance Analytics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadPerformance(){
  const d=await api('/api/v4/performance');
  if(!d||d.error)return;
  const setVal=(id,val,isPos)=>{const el=document.getElementById(id);if(el){el.textContent=val;if(isPos!==undefined)el.className='ev '+(isPos?'pos':'neg');}};
  setVal('perf-winrate',parseFloat(d.win_rate||0).toFixed(1)+'%',parseFloat(d.win_rate||0)>=50);
  setVal('perf-pf',parseFloat(d.profit_factor||0).toFixed(2),parseFloat(d.profit_factor||0)>=1.2);
  const pnl=parseFloat(d.total_pnl||0);
  setVal('perf-pnl',(pnl>=0?'+$':'$')+pnl.toFixed(2),pnl>=0);
  setVal('perf-rr',parseFloat(d.avg_rr||0).toFixed(2),parseFloat(d.avg_rr||0)>=1.0);
  setVal('perf-total',d.total_trades||0);
  setVal('perf-winstreak',d.max_win_streak||0);
  setVal('perf-lossstreak',d.max_loss_streak||0);
  setVal('perf-topsym',d.best_symbol||'--');

  const bdBox=document.getElementById('perf-symbol-breakdown');
  if(bdBox&&d.symbol_pnl){
    bdBox.innerHTML=Object.entries(d.symbol_pnl).map(([sym,val])=>'<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #161f31;"><span>'+sym+'</span><b class="'+(val>=0?'pos':'neg')+'">'+(val>=0?'+$':'$')+parseFloat(val).toFixed(2)+'</b></div>').join('');
  }
}

// â”€â”€ Manual Market Order Dispatch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function placeManualOrder(){
  const sym=document.getElementById('ord-symbol').value.trim().toUpperCase();
  const action=document.getElementById('ord-action').value;
  const lots=+document.getElementById('ord-lots').value||0.01;
  const sl=+document.getElementById('ord-sl').value||0.0;
  const tp=+document.getElementById('ord-tp').value||0.0;

  if(!sym){showToast('Enter a valid symbol',true);return;}
  showToast('Dispatching '+action+' '+lots+' lots '+sym+'...',false);

  const r=await api('/api/mt5/order',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({symbol:sym,action:action,lots:lots,sl:sl,tp:tp})
  });

  if(r&&r.success){
    showToast('Market Order Executed: #'+(r.result&&r.result.ticket||'Done')+' ðŸŸ¢',false);
    await loadPositions();
    await loadAccount();
  }else{
    showToast('Order Failed: '+(r&&(r.result&&r.result.error||r.error)||'Error'),true);
  }
}

// â”€â”€ Settings â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function loadSettings(){
  const d=await api('/api/v4/settings');
  if(!d||d.error)return;
  const sc=(id,v)=>{const e=document.getElementById(id);if(e)e.checked=!!v;};
  const sn=(id,v)=>{const e=document.getElementById(id);if(e&&v!==undefined)e.value=v;};

  sn('cfg-mt5login',d.mt5_login);sn('cfg-mt5pass',d.mt5_password);sn('cfg-mt5server',d.mt5_server);sn('cfg-mt5path',d.mt5_path);sn('cfg-magic',d.mt5_magic_number);
  sn('cfg-anthropic',d.anthropic_api_key);sn('cfg-claudemodel',d.anthropic_model);
  sn('cfg-sizingmode',d.trade_sizing_mode);sn('cfg-risktradepct',d.risk_per_trade_pct);
  sn('cfg-maxriskusd',d.max_risk_usd_per_trade);sn('cfg-minriskusd',d.min_risk_usd_per_trade);
  sn('cfg-maxspread',d.max_spread_points);

  const maxLossEl=document.getElementById('cfg-daily-max');
  if(maxLossEl&&d.daily_max_loss_pct!==undefined)maxLossEl.textContent=parseFloat(d.daily_max_loss_pct).toFixed(1);

  const sq=d.symbol_quantities||{};
  sn('cfg-qty-eurusd',sq['EURUSD']||0.1);sn('cfg-qty-gbpusd',sq['GBPUSD']||0.1);sn('cfg-qty-usdjpy',sq['USDJPY']||0.1);
  sn('cfg-qty-xauusd',sq['XAUUSD']||0.01);sn('cfg-qty-btcusd',sq['BTCUSD']||0.01);
  sn('cfg-qty-us30',sq['US30']||0.01);sn('cfg-qty-nas100',sq['NAS100']||0.01);
  sn('cfg-qty-ndxusd',sq['NDXUSD']||sq['NAS100']||0.01);sn('cfg-qty-djiusd',sq['DJIUSD']||sq['US30']||0.01);

  sc('cfg-auto',d.enable_autonomous_trading);sc('cfg-titan',d.strategy_titan_pro_enabled);sc('cfg-smc',d.strategy_smc_enabled);sc('cfg-occ',d.strategy_occ_r5_enabled);sc('cfg-eyes',d.strategy_eyes_sme_enabled);sc('cfg-meanrev',d.strategy_mean_rev_enabled);sc('cfg-qw',d.strategy_quant_way_enabled);

  sn('cfg-dloss',d.daily_max_loss_pct);sn('cfg-wtp',d.weekly_profit_target_pct);sn('cfg-maxpos',d.max_concurrent_positions);
  sc('cfg-softrisk',d.enable_soft_risk_reduction);sc('cfg-earlybe',d.enable_early_breakeven);sc('cfg-breakeven',d.enable_breakeven_trigger);sc('cfg-partialtp',d.enable_partial_take_profit);sc('cfg-trailing',d.enable_trailing_stop);
  sn('cfg-mlthresh',d.ml_brain_min_execute_score);sn('cfg-confluence',d.ml_brain_confluence_bonus);

  updateArmButton(d.armed);
  // Load symbol toggles after settings
  loadSymbolToggles();
}
// ── Symbol Permission Toggles ──────────────────────────────────────────────────
const FALLBACK_PRESET_SYMBOLS = [
  'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD',
  'EURGBP', 'EURJPY', 'GBPJPY',
  'XAUUSD', 'XAGUSD',
  'NAS100', 'NDXUSD', 'US30', 'DJIUSD', 'SPX500', 'GER40', 'USOIL'
];

async function loadSymbolToggles(){
  let items = [];
  let activeCount = 0;
  let totalCount = 0;
  try {
    const d = await api('/api/v4/symbols');
    if (d && Array.isArray(d.symbols) && d.symbols.length > 0) {
      items = d.symbols;
      activeCount = d.active_count || 0;
      totalCount = d.total_count || items.length;
    }
  } catch(e) {
    console.warn('Symbols API lookup error:', e);
  }

  // Robust preset fallback if API unreachable
  if (items.length === 0) {
    items = FALLBACK_PRESET_SYMBOLS.map(s => ({symbol: s, enabled: true}));
    activeCount = items.length;
    totalCount = items.length;
  }

  const list = document.getElementById('symbol-toggle-list');
  if(!list)return;
  list.innerHTML = '';
  items.forEach(item => {
    const row = document.createElement('div');
    row.setAttribute('data-symbol', item.symbol);
    row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:6px 10px;background:var(--card);border-radius:6px;border:1px solid var(--border);margin-bottom:2px;';
    const nameDiv = document.createElement('div');
    nameDiv.style.cssText = 'font-size:12px;font-weight:700;color:var(--text);display:flex;align-items:center;gap:6px;';
    nameDiv.innerHTML = '<span>' + item.symbol + '</span>';
    const label = document.createElement('label');
    label.className = 'toggle';
    label.style.margin = '0';
    const chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.checked = !!item.enabled;
    const span = document.createElement('span');
    span.className = 'slider';
    label.appendChild(chk);
    label.appendChild(span);
    
    // Status badge
    const badge = document.createElement('span');
    badge.id = 'sym-badge-' + item.symbol.replace(/[^a-zA-Z0-9]/g,'_');
    badge.style.cssText = 'font-size:9px;padding:2px 7px;border-radius:10px;margin-right:6px;font-weight:700;transition:all .2s;';
    badge.textContent = item.enabled ? 'ACTIVE' : 'BLOCKED';
    badge.style.background = item.enabled ? '#22c55e' : '#ef4444';
    badge.style.color = '#fff';
    
    chk.onchange = async () => {
      badge.textContent = chk.checked ? 'ACTIVE' : 'BLOCKED';
      badge.style.background = chk.checked ? '#22c55e' : '#ef4444';
      await toggleSymbol(item.symbol, chk.checked);
    };
    
    const right = document.createElement('div');
    right.style.cssText = 'display:flex;align-items:center;gap:4px;';
    right.appendChild(badge);
    right.appendChild(label);
    row.appendChild(nameDiv);
    row.appendChild(right);
    list.appendChild(row);
  });
  const activeEl = document.getElementById('sym-active-count');
  if(activeEl) activeEl.textContent = activeCount + '/' + totalCount + ' active';
}

function filterSymbolList() {
  const q = (document.getElementById('sym-search').value || '').toLowerCase().trim();
  const list = document.getElementById('symbol-toggle-list');
  if(!list) return;
  const rows = list.children;
  for(let i=0; i<rows.length; i++) {
    const sym = rows[i].getAttribute('data-symbol') || rows[i].textContent || '';
    rows[i].style.display = (!q || sym.toLowerCase().includes(q)) ? 'flex' : 'none';
  }
}

async function addCustomSymbol() {
  const inp = document.getElementById('add-sym-input');
  if(!inp || !inp.value) return;
  const sym = inp.value.trim().toUpperCase();
  if(!sym) return;
  await toggleSymbol(sym, true);
  inp.value = '';
  await loadSymbolToggles();
}

async function toggleSymbol(symbol, enabled){
  const r = await api('/api/v4/symbols/toggle', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({symbol, enabled})
  });
  showToast(r&&r.success ? (enabled ? symbol+' ENABLED ✅' : symbol+' DISABLED 🔴') : 'Failed: '+(r&&r.error||'Error'), !r||!r.success);
}

async function setAllSymbols(enabled){
  const d = await api('/api/v4/symbols');
  if(!d||!d.symbols)return;
  const updates = {};
  d.symbols.forEach(s => updates[s.symbol] = enabled);
  const r = await api('/api/v4/symbols/batch', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({symbols: updates})
  });
  showToast(r&&r.success ? (enabled?'All symbols ENABLED':'All symbols DISABLED') : 'Failed', !r||!r.success);
  loadSymbolToggles();
}

async function saveAndConnectMT5(){
  const login = +document.getElementById('cfg-mt5login').value || 0;
  const pass = document.getElementById('cfg-mt5pass').value || '';
  const server = document.getElementById('cfg-mt5server').value || '';
  const path = document.getElementById('cfg-mt5path').value || '';
  const magic = +document.getElementById('cfg-magic').value || 999111;
  const anthropic = document.getElementById('cfg-anthropic').value || '';
  const claudemodel = document.getElementById('cfg-claudemodel').value || 'claude-3-5-sonnet-20241022';

  const payload = {
    mt5_login: login,
    mt5_server: server,
    mt5_path: path,
    mt5_magic_number: magic,
    anthropic_model: claudemodel
  };
  if (pass && !pass.includes('********')) payload.mt5_password = pass;
  if (anthropic && !anthropic.includes('********')) payload.anthropic_api_key = anthropic;

  showToast('Saving & Connecting to MetaTrader 5...', false);

  // 1. Save settings
  await api('/api/v4/settings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });

  // 2. Trigger explicit connect
  const connRes = await api('/api/mt5/connect', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      login: login,
      password: pass,
      server: server,
      path: path
    })
  });

  if (connRes && connRes.success) {
    showToast('MT5 Connected Successfully ðŸŸ¢', false);
  } else {
    const err = connRes && (connRes.message || connRes.error) || 'Check credentials';
    showToast('MT5: ' + err, true);
  }

  await refreshFast();
  await refreshSlow();
}

async function saveSetting(k,v){
  const b={};b[k]=v;
  const r=await api('/api/v4/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
  showToast(r&&r.success?'Saved '+k:'Failed '+k,!r||!r.success);
  loadSettings();
}

async function saveSymbolQty(sym,qty){
  const b={symbol_quantities:{}};b.symbol_quantities[sym]=qty;
  const r=await api('/api/v4/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
  showToast(r&&r.success?'Saved '+sym+' Lots: '+qty:'Failed',!r||!r.success);
  loadSettings();
}

async function toggleArm(){
  const ns=!armed;
  showToast(ns?'Arming Autonomous Engine...':'Disarming Bot...',false);
  const r=await api('/api/arm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({armed:ns})});
  if(r&&(r.success||r.armed!==undefined)){
    armed=!!r.armed;
    updateArmButton(armed);
    showToast(armed?'BOT ARMED ðŸŸ¢ (Auto Execution Active)':'BOT DISARMED ðŸ”´ (Trading Halted)',false);
  }else{
    showToast('Failed: '+(r&&(r.message||r.error)||'Error'),true);
  }
  await loadStatus();
  await loadSettings();
}

function updateArmButton(a){
  armed=!!a;const b=document.getElementById('arm-btn');if(!b)return;
  b.textContent=armed?'ARMED - Click to Disarm':'ARM BOT';b.className=armed?'armed':'disarmed';
}

async function loadStatus(){
  const d=await api('/api/status');
  if(d&&!d.error){
    if(d.armed!==undefined)updateArmButton(d.armed);
    const dot=document.getElementById('dot-engine');const sb=document.getElementById('sb-engine');
    if(dot)dot.className='dot '+(d.armed?'green':(d.status==='ERROR'?'red':'yellow'));
    if(sb)sb.textContent=d.armed?'ARMED ðŸŸ¢':(d.status||'IDLE');

    const dot2=document.getElementById('dot-mt5');const sb2=document.getElementById('sb-mt5');
    if(d.connected){if(dot2)dot2.className='dot green';if(sb2)sb2.textContent='Connected ('+(d.server||'MT5')+')';}
    else{if(dot2)dot2.className='dot red';if(sb2)sb2.textContent='Disconnected';}

    const dd = document.getElementById('hDrawdown');
    if (dd && d.daily_drawdown_pct !== undefined) {
        dd.textContent = d.daily_drawdown_pct.toFixed(2) + '%';
        dd.className = 'val ' + (d.daily_drawdown_pct > 2.0 ? 'neg' : (d.daily_drawdown_pct > 1.0 ? 'warn' : 'pos'));
    }
    const ml = document.getElementById('hMarginLvl');
    if (ml && d.margin_level !== undefined) {
        const mlv = parseFloat(d.margin_level);
        ml.textContent = mlv > 0 ? mlv.toFixed(0) + '%' : '--';
        ml.className = 'val ' + (mlv > 0 && mlv < 200 ? 'neg' : mlv < 500 ? 'warn' : 'pos');
    }
  }
}

function switchLeftTab(n){
  const tabs=['logs','diagnostics','signals','journal','discussions','news','performance'];
  tabs.forEach(t=>{const el=document.getElementById('ltab-'+t);if(el)el.classList.toggle('active',t===n);});
  document.querySelectorAll('#left .tabs .tab-btn').forEach((b,i)=>{if(tabs[i])b.classList.toggle('active',tabs[i]===n);});
}
function switchRightTab(n){
  const tabs=['mt5','sizing','strategies','risk','order'];
  tabs.forEach(t=>{const el=document.getElementById('rtab-'+t);if(el)el.classList.toggle('active',t===n);});
  document.querySelectorAll('#right .tabs .tab-btn').forEach((b,i)=>{if(tabs[i])b.classList.toggle('active',tabs[i]===n);});
}

let tt;function showToast(m,e){const el=document.getElementById('toast');if(!el)return;el.textContent=m;el.style.borderColor=e?'var(--red)':'var(--green)';el.style.opacity='1';clearTimeout(tt);tt=setTimeout(()=>{el.style.opacity='0';},3000);}

async function refreshFast(){await Promise.all([loadPositions(),loadLogs(),loadStatus()]);}
async function refreshSlow(){await Promise.all([loadAccount(),loadSignals(),loadJournal(),loadEquity(),loadDiagnostics(),loadDiscussions(),loadNews(),loadPerformance()]);}

window.addEventListener('DOMContentLoaded',async()=>{
  
function getSession() {
    const h = new Date().getUTCHours();
    if (h >= 22 || h < 7) return {name: 'Asian', color: '#a78bfa'};
    if (h >= 7 && h < 12) return {name: 'London', color: '#34d399'};
    if (h >= 12 && h < 16) return {name: 'NY Overlap', color: '#f59e0b'};
    if (h >= 16 && h < 22) return {name: 'New York', color: '#60a5fa'};
    return {name: 'Closed', color: '#6b7280'};
}
function updateSession() {
    const s = getSession();
    const el = document.getElementById('session-pill');
    if (el) {
        el.textContent = s.name;
        el.style.backgroundColor = s.color;
    }
}
setInterval(updateSession, 60000);
updateSession();

  initChart();
  await loadSettings();
  await loadSymbolToggles();
  await refreshFast();
  await refreshSlow();
  setInterval(refreshFast,2000);
  setInterval(refreshSlow,10000);
});

</script>
</body>
</html>
"""

def get_dashboard_html(token: str = "", port: int = 80) -> str:
    """Return complete MT5 monitoring dashboard as HTML."""
    auth_param = f"?token={token}" if token else ""
    js = _HTML_JS.replace("PORT_PLACEHOLDER", str(port)).replace("AUTH_PLACEHOLDER", auth_param)
    return _HTML_PART1 + _HTML_PART2 + js
