# QuantClaw ML Tuning Report
Generated: 2026-07-26 10:04 UTC
Lessons analyzed: 50 (of 68 total)

## Current Config
- SL%: 1.15
- TP%: 2.3
- Trail ATR Mult: 1.8
- ML Primary Threshold: 55
- ML Borderline Low: 45

## ML Weights
```json
{}
```

## Performance by Trade Profile
| Name | W | L | Total | Win% |
|---|---|---|---|---|
| UNKNOWN | 15 | 35 | 50 | 30% |

## Performance by Session
| Name | W | L | Total | Win% |
|---|---|---|---|---|
| ASIA | 2 | 2 | 4 | 50% |
| LONDON | 0 | 5 | 5 | 0% |
| NY | 0 | 1 | 1 | 0% |
| OFF_HOURS | 2 | 0 | 2 | 100% |
| OVERLAP | 1 | 0 | 1 | 100% |
| UNKNOWN | 10 | 27 | 37 | 27% |

## Performance by Symbol
| Name | W | L | Total | Win% |
|---|---|---|---|---|
| BTCUSD.P | 7 | 13 | 20 | 35% |
| ETHUSD.P | 3 | 12 | 15 | 20% |
| XAUTUSD.P | 5 | 10 | 15 | 33% |

## Performance by Market Regime
| Name | W | L | Total | Win% |
|---|---|---|---|---|
| CHOP_RANGE | 2 | 1 | 3 | 66% |
| UNKNOWN | 13 | 34 | 47 | 27% |

## Shadow Trade Monitor
- Avoided Losses (Correct Rejects): 2
- Missed Wins (Too Strict Rejects): 0
- Pending (Still Monitoring): 0

## Flagged Areas (Auto-Detected)
- PROFILE UNKNOWN: low win rate 30% (15/50) — NEEDS REVIEW
- REGIME UNKNOWN: very low win rate 28% — consider AVOIDING entries in this regime

## Recent Trade Lessons (Last 30)
| # | Symbol | Dir | Type | P&L% | Profile | Regime | Session | Lesson |
|---|---|---|---|---|---|---|---|---|
| 1 | XAUTUSD.P | SHORT | LOST_TRADE | +0.00% | None | None | None | Avoid shorting with neutral RSI (52.91) and extremely low volume ratio (0.24) despite bear regime signals. |
| 2 | XAUTUSD.P | SHORT | LOST_TRADE | +0.00% | None | None | None | High confidence in TREND_BEAR with RSI 40.79 failed; verify stronger momentum confirmation before approving short entries. |
| 3 | XAUTUSD.P | SHORT | WIN_TRADE | +0.00% | None | None | None | The AI correctly identified a bearish trend, but minimal profit suggests tighter entry timing or larger position sizing is needed. |
| 4 | XAUTUSD.P | SHORT | LOST_TRADE | +0.00% | None | None | None | Avoid shorting with low volume ratio (0.8) and neutral RSI (45), as weak bearish confirmation increases false signal risk. |
| 5 | XAUTUSD.P | SHORT | WIN_TRADE | +0.00% | None | None | None | The AI correctly identified a bearish trend, but the minimal +0.01% gain suggests over-confidence given low volume ratio (0.52). |
| 6 | ETHUSD.P | LONG | LOST_TRADE | +0.00% | None | None | None | Extremely low volume ratio (0.01) signaled insufficient momentum; AI should reject LONG signals without strong volume confirmation. |
| 7 | ETHUSD.P | LONG | LOST_TRADE | +0.00% | None | None | None | The AI should require stronger volume confirmation (Volume Ratio > 0) before approving LONG entries despite high ML confidence. |
| 8 | XAUTUSD.P | LONG | LOST_TRADE | +0.00% | None | None | None | High volume breakout signals with neutral RSI (51) lack directional conviction; require stronger momentum confirmation before approving. |
| 9 | BTCUSD.P | SHORT | WIN_TRADE | +0.00% | None | None | None | The AI correctly identified a short opportunity, but minimal price movement suggests tighter profit targets are needed in CHOP_RANGE regimes. |
| 10 | BTCUSD.P | SHORT | LOST_TRADE | +0.00% | None | None | None | High ML confidence in BREAKOUT regime with neutral RSI (53) was misleading; future shorts require stronger bearish confirmation before entry. |
| 11 | BTCUSD.P | SHORT | WIN_TRADE | +0.00% | None | None | None | The AI correctly identified a short opportunity, but the minimal +0.01% gain suggests tighter profit targets or earlier exits should be prioritized in BREAKOUT regimes. |
| 12 | ETHUSD.P | SHORT | LOST_TRADE | +0.00% | None | None | None | In CHOP_RANGE regime with RSI at 40.9, shorting lacks edge; avoid directional trades in choppy, indecisive markets. |
| 13 | XAUTUSD.P | SHORT | LOST_TRADE | +0.00% | None | None | None | Low volume ratio (0.56) signaled weak momentum; avoid SHORT entries without strong volume confirmation despite ML confidence. |
| 14 | XAUTUSD.P | SHORT | WIN_TRADE | +0.00% | None | None | None | The AI correctly identified a bearish trend, but minimal profit (+0.00%) suggests tighter entry timing or larger targets are needed. |
| 15 | XAUTUSD.P | LONG | LOST_TRADE | +0.00% | None | None | None | In CHOP_RANGE regimes, avoid LONG entries near resistance; wait for clearer directional confirmation before approving. |
| 16 | ETHUSD.P | LONG | LOST_TRADE | +0.00% | None | None | None | In CHOP_RANGE regimes, avoid LONG entries even with high ML confidence, as choppy markets lack directional follow-through. |
| 17 | ETHUSD.P | LONG | LOST_TRADE | +0.00% | None | None | None | High volume spikes alone don't confirm breakouts; require price confirmation before approving LONG entries near resistance. |
| 18 | XAUTUSD.P | LONG | WIN_TRADE | +0.00% | None | CHOP_RANGE | OVERLAP | The AI correctly approved a low-risk LONG in CHOP_RANGE, but should target higher-confidence setups for more meaningful gains. |
| 19 | XAUTUSD.P | SHORT | WIN_TRADE | +0.00% | None | UNKNOWN | OFF_HOURS | The AI correctly identified a short opportunity in CHOP_RANGE, but the minimal +0.01% gain suggests tighter profit targets should be set in choppy, low-momentum conditions. |
| 20 | ETHUSD.P | LONG | WIN_TRADE | +0.00% | None | CHOP_RANGE | ASIA | The AI correctly identified direction but ignored extremely low volume ratio (0.04), signaling weak conviction; future entries require stronger volume confirmation. |
| 21 | ETHUSD.P | SHORT | WIN_TRADE | +0.00% | None | UNKNOWN | ASIA | The AI correctly identified a short opportunity in CHOP_RANGE, but the minimal +0.01% gain suggests tighter profit targets should be set in choppy conditions. |
| 22 | ETHUSD.P | SHORT | LOST_TRADE | +0.00% | None | UNKNOWN | ASIA | In CHOP_RANGE regimes, avoid shorting with RSI near oversold levels (40) as price may reverse upward. |
| 23 | BTCUSD.P | SHORT | LOST_TRADE | +0.00% | None | CHOP_RANGE | ASIA | In CHOP_RANGE regimes with RSI above 50, avoid shorting as price lacks directional conviction. |
| 24 | BTCUSD.P | LONG | LOST_TRADE | +0.00% | None | UNKNOWN | NY | Avoid LONG entries in CHOP_RANGE with RSI below 50 and volume ratio below 0.5. |
| 25 | BTCUSD.P | SHORT | LOST_TRADE | -0.00% | None | UNKNOWN | LONDON | SHORT on BTCUSD.P failed (-0.00%) in UNKNOWN — reassess entry conditions. |
| 26 | ETHUSD.P | SHORT | LOST_TRADE | -0.01% | None | UNKNOWN | LONDON | Low volume (0.7x) in UNKNOWN — weak conviction trade failed. |
| 27 | XAUTUSD.P | LONG | LOST_TRADE | -0.00% | None | UNKNOWN | LONDON | Low volume (0.3x) in UNKNOWN — weak conviction trade failed. |
| 28 | ETHUSD.P | SHORT | LOST_TRADE | -0.01% | None | UNKNOWN | LONDON | Low volume (0.5x) in UNKNOWN — weak conviction trade failed. |
| 29 | XAUTUSD.P | SHORT | LOST_TRADE | -0.01% | None | UNKNOWN | LONDON | SHORT on XAUTUSD.P failed (-0.01%) in UNKNOWN — reassess entry conditions. |
| 30 | BTCUSD.P | LONG | WIN_TRADE | +0.05% | None | UNKNOWN | OFF_HOURS | LONG in UNKNOWN during OFF_HOURS succeeded — preserve this setup pattern. |

---
*Paste this report into Antigravity to get ML parameter tuning recommendations.*