"""Tests for annotation_service.merge_notepad_entry (issue #33)."""

from datetime import datetime, timezone

from trading_journal.annotation_service import merge_notepad_entry
from trading_journal.models import CompletedTrade, NotepadEntry, TradeAnnotation, User


def _make_user_and_trade(db_session, username):
    user = User(
        username=username,
        email=f"{username}@example.com",
        auth_method="api_key",
        is_active=True,
        timezone="US/Eastern",
    )
    db_session.add(user)
    db_session.commit()

    trade = CompletedTrade(
        user_id=user.user_id,
        symbol="AAPL",
        instrument_type="EQUITY",
        total_qty=100,
        net_pnl=500.00,
        opened_at=datetime(2026, 7, 1, 13, 30, tzinfo=timezone.utc),
    )
    db_session.add(trade)
    db_session.flush()
    return user, trade


def test_merge_into_empty_trade_notes(db_session):
    user, trade = _make_user_and_trade(db_session, "merge_user_1")

    entry = NotepadEntry(user_id=user.user_id, symbol="AAPL", body="Watching for a breakout.")
    db_session.add(entry)
    db_session.flush()

    ann = merge_notepad_entry(db_session, entry, trade, user)
    db_session.commit()

    assert ann.trade_notes is not None
    assert "Watching for a breakout." in ann.trade_notes
    assert "Notepad entry" in ann.trade_notes
    assert entry.matched_trade_id == trade.completed_trade_id
    assert entry.matched_symbol == "AAPL"
    assert entry.matched_opened_at == trade.opened_at
    assert entry.matched_at is not None


def test_second_merge_appends_after_first(db_session):
    user, trade = _make_user_and_trade(db_session, "merge_user_2")

    entry1 = NotepadEntry(user_id=user.user_id, symbol="AAPL", body="First thought.")
    entry2 = NotepadEntry(user_id=user.user_id, symbol="AAPL", body="Second thought.")
    db_session.add_all([entry1, entry2])
    db_session.flush()

    merge_notepad_entry(db_session, entry1, trade, user)
    db_session.commit()
    ann = merge_notepad_entry(db_session, entry2, trade, user)
    db_session.commit()

    assert ann.trade_notes.index("First thought.") < ann.trade_notes.index("Second thought.")
    assert entry1.matched_trade_id == trade.completed_trade_id
    assert entry2.matched_trade_id == trade.completed_trade_id


def test_merge_preserves_existing_manual_notes(db_session):
    user, trade = _make_user_and_trade(db_session, "merge_user_3")

    ann = TradeAnnotation(
        completed_trade_id=trade.completed_trade_id,
        user_id=user.user_id,
        symbol=trade.symbol,
        opened_at=trade.opened_at,
        trade_notes="Manually typed note on the annotate page.",
    )
    db_session.add(ann)
    db_session.flush()

    entry = NotepadEntry(user_id=user.user_id, symbol="AAPL", body="Pre-trade thought.")
    db_session.add(entry)
    db_session.flush()

    merged_ann = merge_notepad_entry(db_session, entry, trade, user)
    db_session.commit()

    assert "Manually typed note on the annotate page." in merged_ann.trade_notes
    assert "Pre-trade thought." in merged_ann.trade_notes
    assert merged_ann.annotation_id == ann.annotation_id
