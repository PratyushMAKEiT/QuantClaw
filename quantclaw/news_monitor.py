# ==============================================================================
# quantclaw/news_monitor.py — 24/7 Global Economic News & Calendar Monitor
# ==============================================================================
"""
Fetches global financial & economic news from public RSS feeds every 15 minutes.
Uses keyword scoring (zero Claude API cost).
Covers Forex, Gold, Crypto, and Indices.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("quantclaw.news_monitor")

RSS_FEEDS = [
    "https://feeds.content.dowjones.io/public/rss/mw_topstories",  # MarketWatch general
    "https://www.investing.com/rss/news.rss",     # Investing.com macro news  
    "https://www.forexlive.com/feed/",             # ForexLive - Forex macro
    "https://cointelegraph.com/rss",               # Crypto news
    "https://coindesk.com/arc/outboundfeeds/rss/", # Crypto news
]

NEGATIVE_KEYWORDS = [
    "hack", "exploit", "breach", "lawsuit", "ban", "crash", "seized",
    "fraud", "bankruptcy", "crackdown", "regulatory", "sanction", "warning",
    "freeze", "illegal", "scam", "rug", "dump", "panic", "sell-off",
    "rate hike", "inflation surge", "recession", "war", "escalation",
    "rate cut", "dovish", "banking crisis", "trade war", "geopolitical",
    "default", "collapse", "debt ceiling", "downgrade", "stagflation"
]

POSITIVE_KEYWORDS = [
    "etf", "approval", "adoption", "upgrade", "partnership", "institutional",
    "record", "approved", "launch", "halving", "bull", "rally", "surges",
    "breakthrough", "mainstream", "integration", "support", "stimulus",
    # NOTE: "rate hike" and "rate cut" removed — they appeared in both lists
    # (cancelling out) and are now handled exclusively as HIGH_IMPACT_KEYWORDS.
    "hawkish", "strong gdp", "jobs added", "inflation easing",
    "beat expectations", "better than expected", "economic expansion"
]

HIGH_IMPACT_KEYWORDS = [
    "cpi", "consumer price index", "inflation", "nonfarm", "nfp",
    "fomc", "federal reserve", "interest rate", "fed decision", "powell",
    "ecb decision", "lagarde", "rate hike", "rate cut", "rate decision",
    "employment", "gdp", "tariff", "war", "emergency", "crisis",
    "ppi", "producer price", "retail sales", "ism manufacturing",
    "jobs report", "unemployment", "payrolls", "boe decision", "boj decision",
    "rba decision", "rbnz decision", "central bank"
]

SYMBOL_PATTERNS: Dict[str, List[str]] = {
    "EURUSD": ["euro", "ecb", "lagarde", "fed", "dollar", "eur"],
    "GBPUSD": ["pound", "sterling", "boe", "bailey", "uk economy", "gbp"],
    "USDJPY": ["yen", "boj", "ueda", "japan", "jpy"],
    "XAUUSD": ["gold", "xau", "bullion", "precious metal", "safe haven"],
    "BTCUSD": ["bitcoin", "btc", "satoshi", "crypto"],
    "ETHUSD": ["ethereum", "eth", "vitalik", "ether"],
    "US30":   ["dow jones", "wall street", "us stocks", "djia"],
    "NAS100": ["nasdaq", "tech stocks", "silicon valley", "qqq"],
}


class NewsMonitor:
    """24/7 Global RSS news sentiment analyzer."""

    def __init__(self, refresh_interval_min: int = 15):
        self._interval = refresh_interval_min * 60
        self._running = False
        self._cache: Dict[str, Dict] = {}
        self._global_score: float = 0.0
        self._last_refresh: float = 0.0
        self._cache_ttl = 45 * 60

    def get_sentiment(self, symbol: str) -> float:
        """Return cached sentiment score (-1.0 to +1.0)."""
        entry = self._cache.get(symbol.upper())
        if not entry:
            return 0.0
        age = time.time() - entry.get("cached_at", 0)
        if age > self._cache_ttl:
            return 0.0
        return entry.get("score", 0.0)

    def get_global_sentiment(self) -> float:
        """Overall market sentiment (-1.0 to +1.0)."""
        return self._global_score

    def get_headlines(self, symbol: Optional[str] = None, limit: int = 5) -> List[Dict]:
        """Latest headlines for symbol or market."""
        if symbol:
            entry = self._cache.get(symbol.upper(), {})
            return entry.get("headlines", [])[:limit]
        all_h = []
        for v in self._cache.values():
            all_h.extend(v.get("headlines", []))
        all_h.sort(key=lambda x: x.get("time", 0), reverse=True)
        return all_h[:limit]

    def is_news_blocked(self, symbol: str) -> tuple[bool, str]:
        """
        Check if high-impact news or extreme sentiment volatility is active for this symbol.
        Returns (is_blocked, reason).
        """
        import re
        # FIX: Robust broker suffix stripping — handles EURUSD.f, EURUSDm, EURUSD.pro, EURUSD_i etc.
        # Strips: trailing dot, .anything, trailing m/p/x (common broker appends), _anything
        clean_sym = re.sub(r'[._].*$|[mpxri]$', '', symbol.upper())
        # Fallback to raw upper if stripping removed too much (e.g. "XAUUSD" losing its last char)
        if len(clean_sym) < 5:
            clean_sym = re.sub(r'[._].*$', '', symbol.upper())

        entry = self._cache.get(clean_sym)
        if not entry:
            return False, ""

        headlines = entry.get("headlines", [])
        now = time.time()
        for h in headlines:
            # Check if headline was published recently (within last 15 minutes)
            h_time = h.get("time", 0)
            if (now - h_time) < 15 * 60:
                text = (h.get("title", "") + " " + h.get("summary", "")).lower()
                for kw in HIGH_IMPACT_KEYWORDS:
                    if re.search(r'\b' + re.escape(kw) + r'\b', text):
                        return True, f"High-impact news event active: '{h.get('title')[:60]}...'"

        score = abs(entry.get("score", 0.0))
        if score >= 0.85:
            return True, f"Extreme news volatility ({entry.get('score'):+.2f}) on {clean_sym}"

        return False, ""


    async def run(self) -> None:
        """Background continuous refresh task."""
        self._running = True
        logger.info("NewsMonitor started.")
        while self._running:
            try:
                await self._refresh()
            except Exception as e:
                logger.debug(f"NewsMonitor error: {e}")
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        self._running = False

    async def _fetch_feed(self, client: Any, url: str) -> List[Dict]:
        """Fetch a single RSS feed URL. Returns parsed headlines or [] on error."""
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                return self._parse_rss(resp.text)
            else:
                logger.debug(f"Feed {url} returned HTTP {resp.status_code}")
        except Exception as e:
            logger.debug(f"Feed fetch failed ({url}): {e}")
        return []

    async def _refresh(self) -> None:
        """Fetch RSS feeds concurrently and score sentiment."""
        # FIX: Browser-like User-Agent — financial sites (MarketWatch, ForexLive) block python-httpx
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }
        headlines: List[Dict] = []
        # FIX: Fetch all feeds CONCURRENTLY — sequential with 8s timeout per feed = 64s worst case
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
            tasks = [self._fetch_feed(client, url) for url in RSS_FEEDS]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    headlines.extend(result)

        if not headlines:
            return

        # Score headlines
        symbol_buckets: Dict[str, List[Dict]] = {s: [] for s in SYMBOL_PATTERNS}
        unclassified: List[Dict] = []

        for h in headlines:
            text = (h["title"] + " " + h.get("summary", "")).lower()
            h["score"] = self._score_text(text)
            matched = False
            for sym, patterns in SYMBOL_PATTERNS.items():
                if any(p in text for p in patterns):
                    symbol_buckets[sym].append(h)
                    matched = True
            if not matched:
                unclassified.append(h)

        now = time.time()
        for sym, items in symbol_buckets.items():
            if items:
                avg = sum(i["score"] for i in items) / len(items)
                self._cache[sym] = {
                    "score": round(max(-1.0, min(1.0, avg)), 2),
                    "headlines": items,
                    "cached_at": now,
                }

        all_scored = headlines
        if all_scored:
            self._global_score = round(
                max(-1.0, min(1.0, sum(h["score"] for h in all_scored) / len(all_scored))), 2
            )
        self._last_refresh = now
        logger.debug(f"NewsMonitor refreshed ({len(headlines)} headlines, global={self._global_score})")


    def is_high_impact_window(self) -> bool:
        """
        Check if market is currently in a high-impact news window or extreme sentiment shift.
        Returns True if high-impact keywords (CPI, NFP, FOMC, Rate Decision) appeared recently
        or global sentiment is heavily skewed (|score| >= 0.75).
        """
        if abs(self._global_score) >= 0.75:
            return True

        high_impact_patterns = [
            r"\bfomc\b", r"\bfed\s+rate\b", r"\binterest\s+rate\b", r"\bcpi\b",
            r"\bnfp\b", r"\bnon-farm\b", r"\binflation\b", r"\becb\s+rate\b",
            r"\bwar\b", r"\bemergency\b", r"\bblack\s+swan\b"
        ]

        recent_headlines = self.get_headlines(limit=15)
        for h in recent_headlines:
            text = (h.get("title", "") + " " + h.get("summary", "")).lower()
            h_time = float(h.get("time", 0.0))
            # If news is within last 90 minutes and matches high-impact keyword
            if (time.time() - h_time) < 5400:
                for pat in high_impact_patterns:
                    if re.search(pat, text):
                        return True
        return False

    def _score_text(self, text: str) -> float:
        score = 0.0
        for kw in POSITIVE_KEYWORDS:
            if re.search(r"\b" + re.escape(kw) + r"\b", text):
                score += 0.3
        for kw in NEGATIVE_KEYWORDS:
            if re.search(r"\b" + re.escape(kw) + r"\b", text):
                score -= 0.3
        return max(-1.0, min(1.0, score))

    def _parse_rss(self, xml_text: str) -> List[Dict]:
        import email.utils
        items = []
        try:
            root = ET.fromstring(xml_text)
            for item in root.findall(".//item")[:15]:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                desc = item.findtext("description", "").strip()
                pub_date_str = item.findtext("pubDate", "").strip()

                pub_ts = time.time()
                if pub_date_str:
                    try:
                        dt = email.utils.parsedate_to_datetime(pub_date_str)
                        if dt:
                            pub_ts = dt.timestamp()
                    except Exception:
                        pub_ts = time.time()

                if title:
                    items.append({
                        "title": title,
                        "link": link,
                        "summary": desc[:250],
                        "time": pub_ts,
                    })
        except Exception:
            pass
        return items

