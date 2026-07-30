"""Shared helpers for TradeAnnotation lookup/creation and notepad-entry merging."""

import zoneinfo
from datetime import datetime, timezone as dt_timezone

from .models import CompletedTrade, NotepadEntry, TradeAnnotation, User


def get_or_create_annotation(session, trade: CompletedTrade) -> TradeAnnotation:
    """Load the TradeAnnotation for a trade, creating one if it doesn't exist yet.

    Looks up by completed_trade_id first, then falls back to the natural key
    (user_id, symbol, opened_at) to handle the case where a completed_trades
    rebuild has NULLed the FK but the annotation row still exists.
    """
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
    return ann


def merge_notepad_entry(session, entry: NotepadEntry, trade: CompletedTrade, user: User) -> TradeAnnotation:
    """Append a notepad entry's body into the trade's annotation notes, and mark it matched.

    This is an append, not a link: multiple entries can be merged into the same trade's
    `trade_notes` over time. The notepad entry itself is never modified beyond its match
    state, so it remains as an archival record of when/what was originally captured.
    """
    ann = get_or_create_annotation(session, trade)

    user_tz = zoneinfo.ZoneInfo(user.timezone or 'US/Eastern')
    captured_at = entry.created_at
    if captured_at is not None:
        local_captured_at = captured_at.replace(tzinfo=dt_timezone.utc).astimezone(user_tz)
        stamp = local_captured_at.strftime('%Y-%m-%d %H:%M')
    else:
        stamp = 'unknown time'

    section = f"--- Notepad entry ({stamp}) ---\n{entry.body}"
    ann.trade_notes = f"{ann.trade_notes}\n\n{section}" if ann.trade_notes else section

    entry.matched_trade_id = trade.completed_trade_id
    entry.matched_symbol = trade.symbol
    entry.matched_opened_at = trade.opened_at
    entry.matched_at = datetime.now(dt_timezone.utc)

    return ann
