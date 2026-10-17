"""Issue #54: NinjaTrader exec CSV with an 'Account' header must populate account_number."""
from trading_journal.ninjatrader_parser import NinjaTraderParser

HEADER = "Instrument,Action,Quantity,Price,Time,ID,E/X,Position,Order ID,Name,Commission,Rate,{acct},Connection,\n"
ROW = "MNQ DEC26,Sell,3,30735.75,10/13/2026 13:39:30,8844587881,Entry,-,,,$1.05,1,1102517,Live,\n"


def _parse(tmp_path, acct):
    p = tmp_path / "x-exec.csv"
    p.write_text(HEADER.format(acct=acct) + ROW)
    return NinjaTraderParser().parse_file(str(p))


def test_account_header(tmp_path):
    assert _parse(tmp_path, "Account")[0]['account_number'] == '1102517'


def test_account_display_name_header(tmp_path):
    assert _parse(tmp_path, "Account display name")[0]['account_number'] == '1102517'
