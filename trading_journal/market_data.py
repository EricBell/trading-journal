"""Massive.com (formerly Polygon.io) market data client for automatic trade enrichment."""

import json
import logging
import os
import time
import urllib.error
import urllib.request
import zoneinfo
from datetime import datetime, timedelta, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .database import db_manager
from .models import CompletedTrade, OhlcvPriceSeries, TradeAnnotation

logger = logging.getLogger(__name__)

_MASSIVE_BASE = "https://api.polygon.io"
_APP_TZ = zoneinfo.ZoneInfo("US/Eastern")


def _db_ts_to_utc(ts: datetime) -> datetime:
    """Convert a DB-stored timestamp to real UTC.

    Source data has no timezone info so timestamps are ingested as naive ET and
    stored in a TIMESTAMP WITH TIME ZONE column.  PostgreSQL labels them UTC, but
    the values are actually Eastern time.  Strip the wrong UTC label, attach the
    app timezone, then convert to real UTC.
    """
    naive = ts.replace(tzinfo=None)
    return naive.replace(tzinfo=_APP_TZ).astimezone(timezone.utc)

# Free tier: 5 req/min. Sleep this many seconds between API calls to stay safe.
_RATE_LIMIT_SLEEP = 13

# Max API calls per enrichment run to keep upload response times reasonable.
# Remaining unenriched trades are filled in on the next upload.
_MAX_CALLS_PER_RUN = 4


class MassiveClient:
    """Thin wrapper around the Massive/Polygon 1-minute aggregate bars endpoint."""

    def __init__(self) -> None:
        self.api_key = os.environ.get("MASSIVE_API_KEY", "")
        self.enabled = bool(self.api_key)
        if not self.enabled:
            logger.debug("MASSIVE_API_KEY not set — market data enrichment disabled")

    def get_underlying_close_at(self, symbol: str, ts: datetime) -> Optional[float]:
        """
        Return the 1-minute bar close price for *symbol* at time *ts*.

        Checks ohlcv_price_series cache first; fetches from Massive on a miss.
        Returns None if disabled, no data exists, or any error occurs.
        Raises _RateLimitError on HTTP 429 or _UnavailableError on HTTP 403.
        """
        if not self.enabled or ts is None:
            return None

        # Normalize to UTC-aware datetime
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_utc = ts.astimezone(timezone.utc)

        cached = self._cache_lookup(symbol, ts_utc)
        if cached is not None:
            return cached

        return self._fetch_and_cache(symbol, ts_utc)

    def _cache_lookup(self, symbol: str, ts_utc: datetime) -> Optional[float]:
        """Return cached close price if a 1m bar within ±90s of ts_utc exists."""
        window = timedelta(seconds=90)
        try:
            with db_manager.get_session() as session:
                row = (
                    session.query(OhlcvPriceSeries)
                    .filter(
                        OhlcvPriceSeries.symbol == symbol,
                        OhlcvPriceSeries.timeframe == "1m",
                        OhlcvPriceSeries.timestamp >= ts_utc - window,
                        OhlcvPriceSeries.timestamp <= ts_utc + window,
                        OhlcvPriceSeries.close_price > 1,
                    )
                    .order_by(
                        sa.func.abs(
                            sa.extract("epoch", OhlcvPriceSeries.timestamp)
                            - ts_utc.timestamp()
                        )
                    )
                    .first()
                )
                if row is not None:
                    logger.debug("Cache hit for %s at %s", symbol, ts_utc)
                    return float(row.close_price)
        except Exception as exc:
            logger.warning("ohlcv cache lookup failed: %s", exc)
        return None

    def _fetch_and_cache(self, symbol: str, ts_utc: datetime) -> Optional[float]:
        """Fetch 1-min bars from Massive around ts_utc, cache them, return closest close."""
        window = timedelta(minutes=3)
        from_ms = int((ts_utc - window).timestamp() * 1000)
        to_ms = int((ts_utc + window).timestamp() * 1000)

        url = (
            f"{_MASSIVE_BASE}/v2/aggs/ticker/{symbol}/range/1/minute"
            f"/{from_ms}/{to_ms}"
            f"?adjusted=false&sort=asc&limit=10&apiKey={self.api_key}"
        )

        try:
            data = self._http_get(url, symbol, ts_utc, timeframe="1m")
        except _UnavailableError:
            # 1-minute bars blocked (403) — fall back to daily bar
            logger.debug("1m bars unavailable for %s at %s — trying daily fallback", symbol, ts_utc)
            return self._fetch_daily_fallback(symbol, ts_utc)

        if data is None:
            return None

        if data.get("status") not in ("OK", "DELAYED") or not data.get("results"):
            # 1-minute bars returned empty — fall back to daily bar (open price)
            logger.debug(
                "No 1m results for %s at %s (status=%s) — trying daily fallback",
                symbol, ts_utc, data.get("status"),
            )
            return self._fetch_daily_fallback(symbol, ts_utc)

        bars = data["results"]
        self._cache_bars(symbol, bars)

        ts_epoch_ms = ts_utc.timestamp() * 1000
        closest = min(bars, key=lambda b: abs(b["t"] - ts_epoch_ms))
        price = float(closest["c"])
        if price <= 1:
            logger.warning(
                "Massive returned implausible close=%.4f for %s at %s — ignoring",
                price, symbol, ts_utc,
            )
            return None
        logger.debug("Fetched underlying %s at %s → close=%.4f", symbol, ts_utc, price)
        return price

    def _http_get(self, url: str, symbol: str, ts_utc: datetime, timeframe: str = ""):
        """Execute a GET request, raising _UnavailableError / _RateLimitError as appropriate."""
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                try:
                    body = exc.read().decode()
                except Exception:
                    body = "(unreadable)"
                print(f"[enrich] 403 body for {symbol} ({timeframe}): {body}", flush=True)
                raise _UnavailableError()
            if exc.code == 429:
                logger.warning("Massive: rate limited (429) for %s at %s", symbol, ts_utc)
                raise _RateLimitError()
            logger.warning("Massive API call failed for %s at %s: %s", symbol, ts_utc, exc)
            return None
        except Exception as exc:
            logger.warning("Massive API call failed for %s at %s: %s", symbol, ts_utc, exc)
            return None

    def _fetch_daily_fallback(self, symbol: str, ts_utc: datetime) -> Optional[float]:
        """
        Fall back to the daily bar for the trade date and return its open price.
        Used when 1-minute bars are unavailable (e.g. older data on free tier).
        """
        date_str = ts_utc.strftime("%Y-%m-%d")
        url = (
            f"{_MASSIVE_BASE}/v2/aggs/ticker/{symbol}/range/1/day"
            f"/{date_str}/{date_str}"
            f"?adjusted=false&sort=asc&limit=1&apiKey={self.api_key}"
        )
        try:
            data = self._http_get(url, symbol, ts_utc, timeframe="1d")
        except (_UnavailableError, _RateLimitError):
            raise

        if data is None or data.get("status") not in ("OK", "DELAYED") or not data.get("results"):
            logger.debug("No daily fallback results for %s on %s", symbol, date_str)
            return None

        bar = data["results"][0]
        price = float(bar.get("o") or bar.get("c") or 0)
        if price <= 1:
            logger.warning(
                "Daily fallback returned implausible price=%.4f for %s on %s — ignoring",
                price, symbol, date_str,
            )
            return None
        logger.debug("Daily fallback %s on %s → open=%.4f", symbol, date_str, price)
        return price

    def _cache_bars(self, symbol: str, bars: list) -> None:
        """Insert bars into ohlcv_price_series, ignoring conflicts."""
        if not bars:
            return
        try:
            with db_manager.get_session() as session:
                for bar in bars:
                    bar_ts = datetime.fromtimestamp(bar["t"] / 1000, tz=timezone.utc)
                    stmt = pg_insert(OhlcvPriceSeries).values(
                        symbol=symbol,
                        timestamp=bar_ts,
                        timeframe="1m",
                        open_price=bar.get("o"),
                        high_price=bar.get("h"),
                        low_price=bar.get("l"),
                        close_price=bar.get("c"),
                        volume=int(bar["v"]) if bar.get("v") is not None else None,
                    ).on_conflict_do_nothing(
                        index_elements=["symbol", "timestamp", "timeframe"]
                    )
                    session.execute(stmt)
                session.commit()
        except Exception as exc:
            logger.warning("Failed to cache ohlcv bars for %s: %s", symbol, exc)


class _RateLimitError(Exception):
    pass


class _UnavailableError(Exception):
    pass


def get_unenriched_option_trades(user_id: int) -> list:
    """
    Return a list of dicts for option CompletedTrades missing underlying_at_entry.

    Each dict has: completed_trade_id, symbol, underlying, opened_at, option_details.
    """
    try:
        with db_manager.get_session() as session:
            trades = (
                session.query(CompletedTrade)
                .outerjoin(
                    TradeAnnotation,
                    TradeAnnotation.completed_trade_id == CompletedTrade.completed_trade_id,
                )
                .filter(
                    CompletedTrade.user_id == user_id,
                    CompletedTrade.instrument_type == "OPTION",
                    sa.or_(
                        TradeAnnotation.annotation_id.is_(None),
                        TradeAnnotation.underlying_at_entry.is_(None),
                        TradeAnnotation.underlying_at_entry == 0,
                    ),
                )
                .order_by(CompletedTrade.opened_at.desc())
                .all()
            )
            result = []
            for t in trades:
                underlying = t.symbol.split()[0] if t.symbol else None
                details = t.option_details_dict or {}
                result.append({
                    "completed_trade_id": t.completed_trade_id,
                    "symbol": t.symbol,
                    "underlying": underlying,
                    "opened_at": t.opened_at,
                    "right": details.get("right", ""),
                    "strike": details.get("strike"),
                    "exp_date": details.get("exp_date"),
                })
            return result
    except Exception as exc:
        logger.warning("get_unenriched_option_trades failed: %s", exc)
        return []


def enrich_trades_by_ids(user_id: int, trade_ids: list) -> dict:
    """
    Fetch and store underlying_at_entry for specific completed_trade_ids.

    Processes at most _MAX_CALLS_PER_RUN API calls, sleeping between each.
    Returns dict with keys: enriched, failed, unavailable, skipped, disabled.
    """
    client = MassiveClient()
    if not client.enabled:
        return {"enriched": 0, "skipped": 0, "failed": 0, "unavailable": 0, "disabled": True}

    enriched = 0
    skipped = 0
    failed = 0
    unavailable = 0
    api_calls = 0

    try:
        with db_manager.get_session() as session:
            for trade_id in trade_ids:
                trade = session.get(CompletedTrade, trade_id)
                if trade is None or trade.user_id != user_id:
                    skipped += 1
                    continue
                if trade.opened_at is None:
                    skipped += 1
                    continue

                underlying = trade.symbol.split()[0] if trade.symbol else None
                if not underlying:
                    skipped += 1
                    continue

                ts_utc = _db_ts_to_utc(trade.opened_at)
                print(f"[enrich] trade={trade_id} underlying={underlying} opened_at={trade.opened_at} ts_utc={ts_utc}", flush=True)

                cached_price = client._cache_lookup(underlying, ts_utc)
                if cached_price is not None:
                    print(f"[enrich] trade={trade_id} cache hit: {cached_price}", flush=True)
                    price = cached_price
                else:
                    if api_calls >= _MAX_CALLS_PER_RUN:
                        skipped += 1
                        continue
                    try:
                        price = client._fetch_and_cache(underlying, ts_utc)
                        api_calls += 1
                        print(f"[enrich] trade={trade_id} fetched price={price}", flush=True)
                    except _UnavailableError:
                        print(f"[enrich] trade={trade_id} UNAVAILABLE (403)", flush=True)
                        unavailable += 1
                        api_calls += 1
                        continue
                    except _RateLimitError:
                        print(f"[enrich] trade={trade_id} RATE LIMITED", flush=True)
                        failed += 1
                        api_calls += 1
                        break

                if price is None:
                    failed += 1
                    continue

                ann = session.query(TradeAnnotation).filter_by(
                    completed_trade_id=trade.completed_trade_id
                ).one_or_none()
                if ann is None:
                    ann = session.query(TradeAnnotation).filter_by(
                        user_id=trade.user_id,
                        symbol=trade.symbol,
                        opened_at=trade.opened_at,
                    ).one_or_none()
                    if ann is not None:
                        ann.completed_trade_id = trade.completed_trade_id
                if ann is None:
                    ann = TradeAnnotation(
                        completed_trade_id=trade.completed_trade_id,
                        user_id=trade.user_id,
                        symbol=trade.symbol,
                        opened_at=trade.opened_at,
                    )
                    session.add(ann)

                ann.underlying_at_entry = price
                enriched += 1

            session.commit()

    except Exception as exc:
        logger.warning("enrich_trades_by_ids failed: %s", exc)

    logger.info(
        "Manual enrichment complete: enriched=%d skipped=%d failed=%d unavailable=%d",
        enriched, skipped, failed, unavailable,
    )
    return {
        "enriched": enriched,
        "skipped": skipped,
        "failed": failed,
        "unavailable": unavailable,
        "disabled": False,
    }


def enrich_missing_underlying_prices(user_id: int) -> dict:
    """
    For every option CompletedTrade without underlying_at_entry, fetch the underlying
    close price at opened_at from Massive and store it in trade_annotations.

    Idempotent: skips trades that already have underlying_at_entry set.
    Fire-and-forget: individual fetch failures are logged but do not raise.

    Processes at most _MAX_CALLS_PER_RUN API calls per invocation to avoid
    rate-limiting on the free tier. Remaining trades are filled on the next upload.

    Returns dict with keys: enriched, skipped, failed, unavailable, disabled.
    """
    client = MassiveClient()
    if not client.enabled:
        return {"enriched": 0, "skipped": 0, "failed": 0, "unavailable": 0, "disabled": True}

    enriched = 0
    skipped = 0
    failed = 0
    unavailable = 0
    api_calls = 0

    try:
        with db_manager.get_session() as session:
            trades = (
                session.query(CompletedTrade)
                .outerjoin(
                    TradeAnnotation,
                    TradeAnnotation.completed_trade_id == CompletedTrade.completed_trade_id,
                )
                .filter(
                    CompletedTrade.user_id == user_id,
                    CompletedTrade.instrument_type == "OPTION",
                    sa.or_(
                        TradeAnnotation.annotation_id.is_(None),
                        TradeAnnotation.underlying_at_entry.is_(None),
                        TradeAnnotation.underlying_at_entry == 0,
                    ),
                )
                .all()
            )

            for trade in trades:
                if trade.opened_at is None:
                    skipped += 1
                    continue

                # Derive underlying ticker from option contract symbol
                # e.g. "SPY 03/21/26 580.00 C" → "SPY"
                underlying = trade.symbol.split()[0] if trade.symbol else None
                if not underlying:
                    skipped += 1
                    continue

                # Check cache first — no API call needed if already cached
                ts_utc = _db_ts_to_utc(trade.opened_at)
                cached_price = client._cache_lookup(underlying, ts_utc)
                if cached_price is not None:
                    price = cached_price
                else:
                    # Need an API call — enforce per-run cap
                    if api_calls >= _MAX_CALLS_PER_RUN:
                        skipped += 1
                        continue

                    if api_calls > 0:
                        time.sleep(_RATE_LIMIT_SLEEP)

                    try:
                        price = client._fetch_and_cache(underlying, ts_utc)
                        api_calls += 1
                    except _UnavailableError:
                        unavailable += 1
                        api_calls += 1
                        continue
                    except _RateLimitError:
                        failed += 1
                        api_calls += 1
                        break  # Stop immediately on rate limit

                if price is None:
                    failed += 1
                    continue

                ann = session.query(TradeAnnotation).filter_by(
                    completed_trade_id=trade.completed_trade_id
                ).one_or_none()
                if ann is None:
                    ann = session.query(TradeAnnotation).filter_by(
                        user_id=trade.user_id,
                        symbol=trade.symbol,
                        opened_at=trade.opened_at,
                    ).one_or_none()
                    if ann is not None:
                        ann.completed_trade_id = trade.completed_trade_id
                if ann is None:
                    ann = TradeAnnotation(
                        completed_trade_id=trade.completed_trade_id,
                        user_id=trade.user_id,
                        symbol=trade.symbol,
                        opened_at=trade.opened_at,
                    )
                    session.add(ann)

                ann.underlying_at_entry = price
                enriched += 1

            session.commit()

    except Exception as exc:
        logger.warning("enrich_missing_underlying_prices failed: %s", exc)

    logger.info(
        "Market data enrichment complete: enriched=%d skipped=%d failed=%d unavailable=%d",
        enriched, skipped, failed, unavailable,
    )
    return {
        "enriched": enriched,
        "skipped": skipped,
        "failed": failed,
        "unavailable": unavailable,
        "disabled": False,
    }
