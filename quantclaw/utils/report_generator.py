# ==============================================================================
# quantclaw/utils/report_generator.py — Performance Archive & Dashboard Generator
# ==============================================================================
"""
Generates beautiful, interactive standalone HTML dashboards with Tailwind CSS and Chart.js
for archived versions of the trading bot.
"""

import json
import time
from pathlib import Path
from quantclaw.config import get_trade_history_path, get_app_data_dir

def archive_and_generate_report(old_version: str, current_version: str) -> str:
    """
    Archive the active trades history to a versioned file, calculate performance metrics,
    and generate a premium interactive HTML report with Chart.js equity curves.
    
    Returns the path to the generated HTML report, or empty string if no history to archive.
    """
    history_path = get_trade_history_path()
    if not history_path.exists():
        return ""
        
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            trades = json.load(f)
    except Exception:
        return ""
        
    if not trades:
        return ""

    # ── Create archive directories ─────────────────────────────────────────
    archive_dir = get_app_data_dir() / "performance_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean version string for filenames (replace spaces and parens)
    clean_ver = old_version.replace(" ", "_").replace("(", "").replace(")", "")
    
    # Save the raw trade history archive
    archive_history_path = archive_dir / f"history_{clean_ver}.json"
    with open(archive_history_path, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2, ensure_ascii=False)

    # ── Calculate metrics ──────────────────────────────────────────────────
    total_trades = len(trades)
    wins = [t for t in trades if t.get("realized_pnl", 0.0) > 0.0]
    losses = [t for t in trades if t.get("realized_pnl", 0.0) < 0.0]
    breakevens = [t for t in trades if t.get("realized_pnl", 0.0) == 0.0]
    
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0
    total_pnl = sum(t.get("realized_pnl", 0.0) for t in trades)
    
    gross_profits = sum(t.get("realized_pnl", 0.0) for t in wins)
    gross_losses = abs(sum(t.get("realized_pnl", 0.0) for t in losses))
    profit_factor = (gross_profits / gross_losses) if gross_losses > 0 else (gross_profits if gross_profits > 0 else 1.0)
    
    avg_win = (gross_profits / len(wins)) if len(wins) > 0 else 0.0
    avg_loss = (gross_losses / len(losses)) if len(losses) > 0 else 0.0
    
    # Sizing-based ROI calculation (assume nominal base capital is 10x the trade size)
    avg_size = sum(t.get("quantity", 0.0) * t.get("entry_price", 0.0) for t in trades) / total_trades if total_trades > 0 else 100.0
    base_capital = max(100.0, avg_size * 10.0)
    roi_pct = (total_pnl / base_capital * 100)
    
    # ── Prepare Chart Data ─────────────────────────────────────────────────
    # Running equity curve
    cumulative_pnl = 0.0
    equity_points = [0.0]
    equity_labels = ["Start"]
    
    for i, t in enumerate(trades):
        cumulative_pnl += t.get("realized_pnl", 0.0)
        equity_points.append(round(cumulative_pnl, 2))
        equity_labels.append(f"Trade {i+1}")
        
    # Symbol-specific breakdowns
    symbol_data = {}
    for t in trades:
        sym = t.get("signal", {}).get("symbol", "UNKNOWN").upper()
        pnl = t.get("realized_pnl", 0.0)
        if sym not in symbol_data:
            symbol_data[sym] = {"wins": 0, "losses": 0, "net": 0.0}
        symbol_data[sym]["net"] += pnl
        if pnl > 0.0:
            symbol_data[sym]["wins"] += 1
        elif pnl < 0.0:
            symbol_data[sym]["losses"] += 1
            
    symbols_list = list(symbol_data.keys())
    symbols_wins = [symbol_data[s]["wins"] for s in symbols_list]
    symbols_losses = [symbol_data[s]["losses"] for s in symbols_list]
    symbols_net = [round(symbol_data[s]["net"], 2) for s in symbols_list]

    # Detailed trade log rows for HTML
    log_rows_html = ""
    for i, t in enumerate(trades):
        signal_data = t.get("signal") or {}
        dec_data = t.get("decision") or {}
        pnl = t.get("realized_pnl", 0.0)
        pnl_class = "text-emerald-400 font-semibold" if pnl > 0.0 else "text-rose-400 font-semibold" if pnl < 0.0 else "text-gray-400"
        action = signal_data.get("action", "BUY").upper()
        action_class = "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" if action in ("BUY", "LONG") else "bg-rose-500/10 text-rose-400 border border-rose-500/20"
        
        log_rows_html += f"""
        <tr class="border-b border-slate-800 hover:bg-slate-900/50 transition">
            <td class="px-6 py-4 text-slate-300 font-mono text-sm">#{i+1}</td>
            <td class="px-6 py-4 text-slate-300 font-mono text-sm">{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t.get('executed_at', time.time())))}</td>
            <td class="px-6 py-4 text-slate-100 font-bold">{signal_data.get('symbol', 'UNKNOWN')}</td>
            <td class="px-6 py-4">
                <span class="px-2 py-1 rounded text-xs font-bold uppercase tracking-wider {action_class}">{action}</span>
            </td>
            <td class="px-6 py-4 text-slate-300 font-mono text-sm">${t.get('entry_price', 0.0):,.2f}</td>
            <td class="px-6 py-4 text-slate-300 font-mono text-sm">${t.get('quantity', 0.0):,.4f}</td>
            <td class="px-6 py-4 text-slate-300 font-mono text-sm">{dec_data.get('regime', 'BETA')}</td>
            <td class="px-6 py-4 {pnl_class} font-mono">${pnl:+.2f}</td>
        </tr>
        """

    # ── Build the HTML Template ────────────────────────────────────────────
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuantClaw Performance Report - {old_version}</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Chart.js CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        slate: {{
                            950: '#0b0f19',
                            900: '#111827',
                            800: '#1f2937',
                        }},
                        cyan: {{
                            400: '#22d3ee',
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap');
        body {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: #0b0f19;
        }}
        .font-mono {{
            font-family: 'JetBrains Mono', monospace;
        }}
        .glass-card {{
            background: rgba(17, 24, 39, 0.7);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }}
    </style>
</head>
<body class="text-slate-100 min-h-screen pb-12">
    <!-- Header -->
    <header class="border-b border-slate-800 bg-slate-900/50 py-6 mb-8 backdrop-blur-md sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-6 flex justify-between items-center">
            <div class="flex items-center space-x-3">
                <div class="w-4 h-4 bg-cyan-400 rounded-full animate-pulse"></div>
                <div>
                    <h1 class="text-xl font-extrabold tracking-tight text-white flex items-center">
                        QUANTCLAW <span class="text-cyan-400 ml-2 text-sm font-semibold tracking-wider bg-cyan-400/10 px-2 py-0.5 rounded border border-cyan-400/20">PERFORMANCE REPORT</span>
                    </h1>
                </div>
            </div>
            <div class="text-right">
                <div class="text-xs text-slate-400 font-mono">ARCHIVED VERSION</div>
                <div class="text-sm font-bold text-slate-200">{old_version}</div>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 space-y-8">
        <!-- Summary Stats Grid -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
            <!-- Net profit -->
            <div class="glass-card p-6 rounded-2xl flex flex-col justify-between">
                <span class="text-xs font-bold tracking-wider text-slate-400 uppercase">Net Realized PnL</span>
                <span class="text-3xl font-extrabold font-mono mt-2 flex items-baseline {'text-emerald-400' if total_pnl >= 0 else 'text-rose-400'}">
                    ${total_pnl:+.2f}
                </span>
                <span class="text-xs text-slate-500 mt-2 font-mono">Base capital: ${base_capital:,.2f}</span>
            </div>
            
            <!-- ROI -->
            <div class="glass-card p-6 rounded-2xl flex flex-col justify-between">
                <span class="text-xs font-bold tracking-wider text-slate-400 uppercase">Estimated ROI</span>
                <span class="text-3xl font-extrabold font-mono mt-2 {'text-emerald-400' if roi_pct >= 0 else 'text-rose-400'}">
                    {roi_pct:+.2f}%
                </span>
                <span class="text-xs text-slate-500 mt-2">10x Avg sizing leverage</span>
            </div>
            
            <!-- Win Rate -->
            <div class="glass-card p-6 rounded-2xl flex flex-col justify-between">
                <span class="text-xs font-bold tracking-wider text-slate-400 uppercase">Win Rate</span>
                <span class="text-3xl font-extrabold font-mono mt-2 text-cyan-400">
                    {win_rate:.1f}%
                </span>
                <span class="text-xs text-slate-500 mt-2">{len(wins)} wins / {len(losses)} losses</span>
            </div>

            <!-- Profit Factor -->
            <div class="glass-card p-6 rounded-2xl flex flex-col justify-between">
                <span class="text-xs font-bold tracking-wider text-slate-400 uppercase">Profit Factor</span>
                <span class="text-3xl font-extrabold font-mono mt-2 text-indigo-400">
                    {profit_factor:.2f}
                </span>
                <span class="text-xs text-slate-500 mt-2">Gross wins / Gross losses</span>
            </div>

            <!-- Total Trades -->
            <div class="glass-card p-6 rounded-2xl flex flex-col justify-between">
                <span class="text-xs font-bold tracking-wider text-slate-400 uppercase">Total Trades</span>
                <span class="text-3xl font-extrabold font-mono mt-2 text-white">
                    {total_trades}
                </span>
                <span class="text-xs text-slate-500 mt-2 font-mono">Capped size wins</span>
            </div>
        </div>

        <!-- Charts Grid -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- Equity curve chart -->
            <div class="glass-card p-6 rounded-2xl lg:col-span-2">
                <h3 class="text-md font-bold text-white mb-4 flex items-center">
                    <span class="w-2.5 h-2.5 bg-cyan-400 rounded-full mr-2"></span> Cumulative Equity Curve (USD)
                </h3>
                <div class="h-[300px]">
                    <canvas id="equityChart"></canvas>
                </div>
            </div>

            <!-- Asset Breakdown Chart -->
            <div class="glass-card p-6 rounded-2xl">
                <h3 class="text-md font-bold text-white mb-4 flex items-center">
                    <span class="w-2.5 h-2.5 bg-indigo-400 rounded-full mr-2"></span> Asset Performance Breakdown
                </h3>
                <div class="h-[300px]">
                    <canvas id="breakdownChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Detailed Trades Table -->
        <div class="glass-card rounded-2xl overflow-hidden">
            <div class="px-6 py-5 border-b border-slate-800 flex justify-between items-center bg-slate-900/40">
                <h3 class="text-md font-bold text-white flex items-center">
                    <span class="w-2.5 h-2.5 bg-purple-400 rounded-full mr-2"></span> Executed Trade Registry
                </h3>
                <span class="text-xs text-slate-400 font-mono">{total_trades} transactions audited</span>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-slate-800 bg-slate-950 text-slate-400 text-xs font-bold uppercase tracking-wider">
                            <th class="px-6 py-4">Index</th>
                            <th class="px-6 py-4">Execution Time</th>
                            <th class="px-6 py-4">Symbol</th>
                            <th class="px-6 py-4">Action</th>
                            <th class="px-6 py-4">Execution Price</th>
                            <th class="px-6 py-4">Quantity (Contracts)</th>
                            <th class="px-6 py-4">Regime</th>
                            <th class="px-6 py-4">Realized PnL</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-850">
                        {log_rows_html}
                    </tbody>
                </table>
            </div>
        </div>
    </main>

    <!-- Chart Scripts -->
    <script>
        // ── Cumulative PnL Chart ───────────────────────────────────────────
        const ctxEquity = document.getElementById('equityChart').getContext('2d');
        const equityLabels = {json.dumps(equity_labels)};
        const equityData = {json.dumps(equity_points)};
        
        new Chart(ctxEquity, {{
            type: 'line',
            data: {{
                labels: equityLabels,
                datasets: [{{
                    label: 'Cumulative PnL ($)',
                    data: equityData,
                    borderColor: '#22d3ee',
                    backgroundColor: 'rgba(34, 211, 238, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.1,
                    pointBackgroundColor: '#22d3ee',
                    pointRadius: equityData.length > 50 ? 0 : 3
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    x: {{
                        grid: {{ color: 'rgba(255, 255, 255, 0.05)' }},
                        ticks: {{ color: 'rgba(148, 163, 184, 0.7)', font: {{ family: 'Plus Jakarta Sans' }} }}
                    }},
                    y: {{
                        grid: {{ color: 'rgba(255, 255, 255, 0.05)' }},
                        ticks: {{ color: 'rgba(148, 163, 184, 0.7)', font: {{ family: 'Plus Jakarta Sans' }} }}
                    }}
                }}
            }}
        }});

        // ── Symbol breakdown chart ─────────────────────────────────────────
        const ctxBreakdown = document.getElementById('breakdownChart').getContext('2d');
        const symbolsList = {json.dumps(symbols_list)};
        const symbolsWins = {json.dumps(symbols_wins)};
        const symbolsLosses = {json.dumps(symbols_losses)};
        
        new Chart(ctxBreakdown, {{
            type: 'bar',
            data: {{
                labels: symbolsList,
                datasets: [
                    {{
                        label: 'Wins',
                        data: symbolsWins,
                        backgroundColor: 'rgba(52, 211, 153, 0.8)',
                        borderRadius: 6
                    }},
                    {{
                        label: 'Losses',
                        data: symbolsLosses,
                        backgroundColor: 'rgba(248, 113, 113, 0.8)',
                        borderRadius: 6
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        labels: {{ color: 'rgba(255, 255, 255, 0.7)', font: {{ family: 'Plus Jakarta Sans' }} }}
                    }}
                }},
                scales: {{
                    x: {{
                        stacked: true,
                        grid: {{ display: false }},
                        ticks: {{ color: 'rgba(148, 163, 184, 0.7)', font: {{ family: 'Plus Jakarta Sans' }} }}
                    }},
                    y: {{
                        stacked: true,
                        grid: {{ color: 'rgba(255, 255, 255, 0.05)' }},
                        ticks: {{ color: 'rgba(148, 163, 184, 0.7)', font: {{ family: 'Plus Jakarta Sans' }} }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""

    report_path = archive_dir / f"report_{clean_ver}.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Empty the active trades history file for the new version start
    try:
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump([], f)
    except Exception:
        pass
        
    return str(report_path)
