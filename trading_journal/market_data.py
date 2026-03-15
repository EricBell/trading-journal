"""Massive.com (formerly Polygon.io) market data client for automatic trade enrichment."""

import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .database import db_manager
from .models import CompletedTrade, OhlcvPriceSeries, TradeAnnotation

logger = logging.getLogger(__name__)

_MASSIVE_BASE = "https://api.polygon.io"


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
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except Exception as exc:
            logger.warning("Massive API call failed for %s at %s: %s", symbol, ts_utc, exc)
            return None

        if data.get("status") not in ("OK", "DELAYED") or not data.get("results"):
            logger.debug(
                "No Massive results for %s at %s: status=%s",
                symbol, ts_utc, data.get("status"),
            )
            return None

        bars = data["results"]
        self._cache_bars(symbol, bars)

        ts_epoch_ms = ts_utc.timestamp() * 1000
        closest = min(bars, key=lambda b: abs(b["t"] - ts_epoch_ms))
        logger.debug("Fetched underlying %s at %s → close=%.4f", symbol, ts_utc, closest["c"])
        return float(closest["c"])

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


def enrich_missing_underlying_prices(user_id: int) -> dict:
    """
    For every option CompletedTrade without underlying_at_entry, fetch the underlying
    close price at opened_at from Massive and store it in trade_annotations.

    Idempotent: skips trades that already have underlying_at_entry set.
    Fire-and-forget: individual fetch failures are logged but do not raise.

    Returns dict with keys: enriched, skipped, failed, disabled.
    """
    client = MassiveClient()
    if not client.enabled:
        return {"enriched": 0, "skipped": 0, "failed": 0, "disabled": True}

    enriched = 0
    skipped = 0
    failed = 0

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

                option_details = trade.option_details_dict
                underlying = (option_details or {}).get("underlying")
                if not underlying:
                    skipped += 1
                    continue

                price = client.get_underlying_close_at(underlying, trade.opened_at)
                if price is None:
                    failed += 1
                    continue

                ann = session.query(TradeAnnotation).filter_by(
                    completed_trade_id=trade.completed_trade_id
                ).one_or_none()
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
        "Market data enrichment complete: enriched=%d skipped=%d failed=%d",
        enriched, skipped, failed,
    )
    return {"enriched": enriched, "skipped": skipped, "failed": failed, "disabled": False}
