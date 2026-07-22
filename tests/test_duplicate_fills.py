"""Regression test for issue #25: same-second, same-price partial fills
being collapsed into one row by the content-based unique_key UPSERT."""

import json
import tempfile
from pathlib import Path

import pytest

from trading_journal.models import User, Trade
from trading_journal.ingestion import NdjsonIngester
from trading_journal.authorization import AuthContext


@pytest.fixture
def test_user(db_session):
    user = User(
        username="dupfilltest",
        email="dupfilltest@example.com",
        auth_method="api_key",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    from trading_journal.auth import AuthUser
    auth_user = AuthUser(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        is_active=user.is_active,
        auth_method=user.auth_method,
    )
    AuthContext.set_current_user(auth_user)

    yield user

    AuthContext.clear()


def create_ndjson_file(records: list) -> Path:
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.ndjson', delete=False)
    for record in records:
        if "section" not in record:
            record["section"] = "Filled Orders"
        if "row_index" not in record:
            record["row_index"] = 1
        temp_file.write(json.dumps(record) + '\n')
    temp_file.flush()
    return Path(temp_file.name)


def mmm_records():
    return [
        {
            "exec_time": "2026-07-22T10:01:09",
            "side": "SELL",
            "qty": -1,
            "pos_effect": "TO CLOSE",
            "symbol": "MMM",
            "type": "CALL",
            "spread": "SINGLE",
            "net_price": 1.52,
            "event_type": "fill",
            "asset_type": "OPTION",
            "option": {"exp_date": "2026-07-24", "strike": 175.0, "right": "CALL"},
            "source_file": "dup.csv",
            "raw": "sell fill 1",
        },
        {
            "exec_time": "2026-07-22T10:01:09",
            "side": "SELL",
            "qty": -1,
            "pos_effect": "TO CLOSE",
            "symbol": "MMM",
            "type": "CALL",
            "spread": "SINGLE",
            "net_price": 1.52,
            "event_type": "fill",
            "asset_type": "OPTION",
            "option": {"exp_date": "2026-07-24", "strike": 175.0, "right": "CALL"},
            "source_file": "dup.csv",
            "raw": "sell fill 2",
        },
        {
            "exec_time": "2026-07-22T09:58:18",
            "side": "BUY",
            "qty": 2,
            "pos_effect": "TO OPEN",
            "symbol": "MMM",
            "type": "CALL",
            "spread": "SINGLE",
            "net_price": 1.54,
            "event_type": "fill",
            "asset_type": "OPTION",
            "option": {"exp_date": "2026-07-24", "strike": 175.0, "right": "CALL"},
            "source_file": "dup.csv",
            "raw": "buy fill",
        },
    ]


def test_identical_partial_fills_both_persisted(db_session, test_user):
    """Two SELL fills with identical (exec_time, side, qty, price) must both
    land as separate Trade rows instead of the second overwriting the first."""
    file_path = create_ndjson_file(mmm_records())
    ingester = NdjsonIngester()
    result = ingester.process_file(file_path, force=True)

    assert result["success"]
    assert result["records_processed"] == 3

    sells = db_session.query(Trade).filter_by(symbol="MMM", side="SELL").all()
    assert len(sells) == 2, "both partial closing fills should be stored, not collapsed into one"
    assert sum(t.qty for t in sells) == 2

    file_path.unlink()


def test_reupload_same_file_stays_idempotent(db_session, test_user):
    """Re-ingesting the identical file must not create further duplicates."""
    file_path = create_ndjson_file(mmm_records())
    ingester = NdjsonIngester()
    ingester.process_file(file_path, force=True)

    file_path_2 = create_ndjson_file(mmm_records())
    result_2 = ingester.process_file(file_path_2, force=True)

    assert result_2["success"]
    db_session.expire_all()
    sells = db_session.query(Trade).filter_by(symbol="MMM", side="SELL").all()
    assert len(sells) == 2, "re-upload of the same file should update the two existing rows, not add more"

    file_path.unlink()
    file_path_2.unlink()
