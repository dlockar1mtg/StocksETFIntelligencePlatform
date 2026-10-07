"""Paced Yahoo chart v8 client for hosted daily collection (full history or from a start date)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) StocksETFIntelligencePlatform/1.0 (personal research)"
SYMBOL_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")


class ChartClient:
    def __init__(self, provider: dict, *, sleep=time.sleep, clock=time.monotonic, opener=urllib.request.urlopen):
        self.provider = provider
        self._sleep, self._clock, self._open = sleep, clock, opener
        self._last = 0.0

    def _pace(self) -> None:
        gap = float(self.provider["minimum_seconds_between_requests"]) - (self._clock() - self._last)
        if gap > 0:
            self._sleep(gap)
        self._last = self._clock()

    def url(self, symbol: str, period1: int, period2: int, host: str | None = None) -> str:
        safe = symbol.strip().upper()
        if not safe or set(safe) - SYMBOL_CHARS:
            raise ValueError(f"Invalid symbol {symbol!r}")
        base = self.provider["endpoint_template"].format(symbol=urllib.parse.quote(safe))
        if host:
            base = base.replace("query1.finance.yahoo.com", host)
        query = urllib.parse.urlencode({"interval": "1d", "period1": int(period1), "period2": int(period2),
                                        "events": "div,splits", "includeAdjustedClose": "true"})
        return f"{base}?{query}"

    def fetch(self, symbol: str, *, start: datetime | None = None, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        period1 = 0 if start is None else int(start.timestamp())
        errors: list[str] = []
        for host in (None, self.provider.get("fallback_host")):
            for attempt in range(int(self.provider["retry_attempts"])):
                self._pace()
                try:
                    request = urllib.request.Request(self.url(symbol, period1, int(now.timestamp()), host),
                                                     headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
                    with self._open(request, timeout=int(self.provider["timeout_seconds"])) as response:
                        return json.loads(response.read())
                except urllib.error.HTTPError as exc:
                    errors.append(f"HTTP {exc.code}")
                    if exc.code == 404:
                        raise LookupError(f"{symbol}: not found") from exc
                    self._sleep(2 * (attempt + 1) * (3 if exc.code == 429 else 1))
                except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
                    errors.append(type(exc).__name__)
                    self._sleep(2 * (attempt + 1))
        raise RuntimeError(f"{symbol}: chart fetch failed ({', '.join(errors[-4:])})")
