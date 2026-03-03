"""Tests for trading_journal/csv_parser.py.

Adapted from schwab-csv-to-json test suite.
Tests cover parsing helpers and CsvParser class using real fixture files.
"""
import io
import os
import re
import tempfile
import textwrap
from pathlib import Path
from typing import List

import pytest

from trading_journal.csv_parser import (
    CsvParser,
    COL_ALIASES,
    classify_row,
    compile_section_patterns,
    detect_section_from_row,
    group_and_sort_records,
    map_header_to_index,
    normalize_key,
    normalize_section_name,
    parse_datetime_maybe,
    parse_exp_date,
    parse_float_field,
    parse_integer_qty,
    safe_get,
)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "schwab-csv-to-json" / "examples"


def examples_available() -> bool:
    return EXAMPLES_DIR.is_dir()


# ---------------------------------------------------------------------------
# normalize_key
# ---------------------------------------------------------------------------

class TestNormalizeKey:
    def test_basic(self):
        assert normalize_key('Exec Time') == 'exec time'

    def test_none(self):
        assert normalize_key(None) == ''

    def test_empty(self):
        assert normalize_key('') == ''

    def test_whitespace(self):
        assert normalize_key('  Exec   Time  ') == 'exec time'

    def test_bom_removed(self):
        assert normalize_key('\ufeffExec Time') == 'exec time'

    def test_multiple_spaces(self):
        assert normalize_key('Price    Improvement') == 'price improvement'

    def test_lowercase(self):
        assert normalize_key('SIDE') == 'side'


# ---------------------------------------------------------------------------
# normalize_section_name
# ---------------------------------------------------------------------------

class TestNormalizeSectionName:
    def test_none(self):
        assert normalize_section_name(None) is None

    def test_account_trade_history(self):
        assert normalize_section_name('Account Trade History') == 'Filled Orders'

    def test_unknown_passthrough(self):
        assert normalize_section_name('Filled Orders') == 'Filled Orders'


# ---------------------------------------------------------------------------
# compile_section_patterns
# ---------------------------------------------------------------------------

class TestCompileSectionPatterns:
    def test_returns_list_of_tuples(self):
        result = compile_section_patterns({'(?i)test': 'TestSection'})
        assert len(result) == 1
        assert isinstance(result[0][0], re.Pattern)
        assert result[0][1] == 'TestSection'

    def test_empty(self):
        assert compile_section_patterns({}) == []

    def test_none_value_preserved(self):
        result = compile_section_patterns({'(?i)^Equities\\s*$': None})
        assert result[0][1] is None


# ---------------------------------------------------------------------------
# map_header_to_index
# ---------------------------------------------------------------------------

class TestMapHeaderToIndex:
    def test_basic(self):
        result = map_header_to_index(['Exec Time', 'Side', 'Qty'])
        assert result['exec_time'] == 0
        assert result['side'] == 1
        assert result['qty'] == 2

    def test_aliases(self):
        result = map_header_to_index(['Execution Time', 'Quantity'])
        assert result['exec_time'] == 0
        assert result['qty'] == 1

    def test_empty(self):
        assert map_header_to_index([]) == {}

    def test_none_values_skipped(self):
        result = map_header_to_index([None, 'Side', '', 'Qty'])
        assert result['side'] == 1
        assert result['qty'] == 3
        assert len(result) == 2

    def test_first_occurrence_wins(self):
        result = map_header_to_index(['Exec Time', 'Exec Time'])
        assert result['exec_time'] == 0

    def test_price_fields(self):
        result = map_header_to_index(['Price', 'Net Price', 'Price Improvement'])
        assert result['price'] == 0
        assert result['net_price'] == 1
        assert result['price_improvement'] == 2


# ---------------------------------------------------------------------------
# safe_get
# ---------------------------------------------------------------------------

class TestSafeGet:
    def test_basic(self):
        assert safe_get(['a', 'b', 'c'], 1) == 'b'

    def test_none_index(self):
        assert safe_get(['a'], None) is None

    def test_out_of_range(self):
        assert safe_get(['a'], 5) is None

    def test_empty_string(self):
        assert safe_get([''], 0) is None

    def test_tilde_is_null(self):
        assert safe_get(['~'], 0) is None

    def test_dash_is_null(self):
        assert safe_get(['-'], 0) is None

    def test_strips_whitespace(self):
        assert safe_get(['  hello  '], 0) == 'hello'

    def test_negative_index(self):
        assert safe_get(['a'], -1) is None


# ---------------------------------------------------------------------------
# detect_section_from_row
# ---------------------------------------------------------------------------

class TestDetectSectionFromRow:
    def setup_method(self):
        patterns = {
            '(?i)^Filled Orders\\s*$': 'Filled Orders',
            '(?i)^Equities\\s*$': None,
        }
        self.compiled = compile_section_patterns(patterns)

    def test_detects_section(self):
        result = detect_section_from_row(['Filled Orders'], self.compiled)
        assert result == 'Filled Orders'

    def test_no_match(self):
        result = detect_section_from_row(['Some other row'], self.compiled)
        assert result is None

    def test_ignored_section_returns_sentinel(self):
        result = detect_section_from_row(['Equities'], self.compiled)
        assert result == '_IGNORED_'


# ---------------------------------------------------------------------------
# parse_integer_qty
# ---------------------------------------------------------------------------

class TestParseIntegerQty:
    def test_positive(self):
        assert parse_integer_qty('+3', []) == 3

    def test_negative(self):
        assert parse_integer_qty('-5', []) == -5

    def test_no_sign(self):
        assert parse_integer_qty('10', []) == 10

    def test_none(self):
        assert parse_integer_qty(None, []) is None

    def test_empty(self):
        assert parse_integer_qty('', []) is None

    def test_tilde(self):
        assert parse_integer_qty('~', []) is None

    def test_with_commas(self):
        assert parse_integer_qty('1,000', []) == 1000

    def test_float_fails(self):
        issues: List[str] = []
        result = parse_integer_qty('1.5', issues)
        assert 'qty_parse_failed' in issues

    def test_non_numeric_fails(self):
        issues: List[str] = []
        result = parse_integer_qty('abc', issues)
        assert 'qty_parse_failed' in issues

    def test_signed_policy(self):
        """Quantities are always signed (not forced unsigned)."""
        assert parse_integer_qty('-10', []) == -10


# ---------------------------------------------------------------------------
# parse_float_field
# ---------------------------------------------------------------------------

class TestParseFloatField:
    def test_basic(self):
        assert parse_float_field('1.25', 'price', []) == pytest.approx(1.25)

    def test_dollar_sign(self):
        assert parse_float_field('$10.50', 'price', []) == pytest.approx(10.50)

    def test_comma(self):
        assert parse_float_field('1,000.00', 'price', []) == pytest.approx(1000.0)

    def test_none(self):
        assert parse_float_field(None, 'price', []) is None

    def test_tilde(self):
        assert parse_float_field('~', 'price', []) is None

    def test_leading_decimal(self):
        assert parse_float_field('.25', 'price', []) == pytest.approx(0.25)

    def test_invalid_records_issue(self):
        issues: List[str] = []
        parse_float_field('abc', 'price', issues)
        assert 'price_parse_failed' in issues


# ---------------------------------------------------------------------------
# parse_datetime_maybe
# ---------------------------------------------------------------------------

class TestParseDatetimeMaybe:
    def test_slashed_2digit_year(self):
        result = parse_datetime_maybe('9/22/25 15:52:26')
        assert result == '2025-09-22T15:52:26'

    def test_slashed_4digit_year(self):
        result = parse_datetime_maybe('09/22/2025 15:52:26')
        assert result == '2025-09-22T15:52:26'

    def test_iso_format(self):
        result = parse_datetime_maybe('2025-09-22T15:52:26')
        assert result == '2025-09-22T15:52:26'

    def test_none(self):
        assert parse_datetime_maybe(None) is None

    def test_empty(self):
        assert parse_datetime_maybe('') is None

    def test_invalid(self):
        assert parse_datetime_maybe('not-a-date') is None


# ---------------------------------------------------------------------------
# parse_exp_date
# ---------------------------------------------------------------------------

class TestParseExpDate:
    def test_schwab_format(self):
        result = parse_exp_date('22 SEP 25')
        assert result == '2025-09-22'

    def test_4digit_year(self):
        result = parse_exp_date('22 SEP 2025')
        assert result == '2025-09-22'

    def test_iso_format(self):
        result = parse_exp_date('2025-09-22')
        assert result == '2025-09-22'

    def test_none(self):
        assert parse_exp_date(None) is None

    def test_invalid(self):
        assert parse_exp_date('bad date') is None


# ---------------------------------------------------------------------------
# classify_row
# ---------------------------------------------------------------------------

class TestClassifyRow:
    def test_noise_empty(self):
        assert classify_row([]) == 'noise'

    def test_noise_all_blank(self):
        assert classify_row(['', '  ', '']) == 'noise'

    def test_header(self):
        row = ['', 'Exec Time', 'Spread', 'Side', 'Qty']
        assert classify_row(row) == 'header'

    def test_amendment(self):
        row = ['', 'RE #12345', '', '', '']
        assert classify_row(row) == 'amendment'

    def test_data(self):
        row = ['', '9/22/25 10:00:00', 'SINGLE', 'BUY', '+100']
        assert classify_row(row) == 'data'


# ---------------------------------------------------------------------------
# group_and_sort_records
# ---------------------------------------------------------------------------

class TestGroupAndSortRecords:
    def _make_record(self, section: str, exec_time: str, is_header: bool = False) -> dict:
        issues = ['section_header'] if is_header else []
        return {
            'section': section,
            'exec_time': exec_time,
            'issues': issues,
        }

    def test_groups_by_section(self):
        records = [
            self._make_record('Filled Orders', '2025-09-22T10:00:00', is_header=True),
            self._make_record('Filled Orders', '2025-09-22T10:05:00'),
            self._make_record('Filled Orders', '2025-09-22T10:01:00'),
        ]
        result = group_and_sort_records(records)
        # Header first, then data sorted by time
        assert result[0]['issues'] == ['section_header']
        assert result[1]['exec_time'] == '2025-09-22T10:01:00'
        assert result[2]['exec_time'] == '2025-09-22T10:05:00'

    def test_sorts_within_section(self):
        records = [
            self._make_record('Filled Orders', '2025-09-22T10:00:00', is_header=True),
            self._make_record('Filled Orders', '2025-09-22T15:00:00'),
            self._make_record('Filled Orders', '2025-09-22T09:00:00'),
            self._make_record('Filled Orders', '2025-09-22T12:00:00'),
        ]
        result = group_and_sort_records(records)
        times = [r['exec_time'] for r in result if r['issues'] != ['section_header']]
        assert times == sorted(times)


# ---------------------------------------------------------------------------
# CsvParser - unit tests with temp files
# ---------------------------------------------------------------------------

def _write_temp_csv(content: str) -> str:
    """Write content to a temp CSV file and return its path."""
    f = tempfile.NamedTemporaryFile(
        mode='w', suffix='.csv', delete=False, encoding='utf-8'
    )
    f.write(textwrap.dedent(content))
    f.close()
    return f.name


class TestCsvParserInit:
    def test_default_init(self):
        parser = CsvParser()
        assert parser.include_rolling is False
        assert parser.encoding == 'utf-8'

    def test_custom_init(self):
        parser = CsvParser(include_rolling=True, encoding='latin-1')
        assert parser.include_rolling is True
        assert parser.encoding == 'latin-1'


class TestCsvParserParseFile:
    def test_parse_fills_only(self):
        csv_content = """\
            Today's Trade Activity

            Filled Orders
            ,,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price,Net Price,Price Improvement,Order Type
            ,,9/22/25 10:00:00,STOCK,BUY,+100,TO OPEN,AAPL,,,STOCK,150.00,150.00,-,MKT
            ,,9/22/25 11:00:00,STOCK,SELL,-100,TO CLOSE,AAPL,,,STOCK,155.00,155.00,-,MKT
        """
        path = _write_temp_csv(csv_content)
        try:
            parser = CsvParser()
            records = parser.parse_file(path)
            fills = [r for r in records if r.get('event_type') == 'fill']
            assert len(fills) == 2
            assert fills[0]['symbol'] == 'AAPL'
            assert fills[0]['side'] == 'BUY'
            assert fills[0]['qty'] == 100
            assert fills[1]['side'] == 'SELL'
            assert fills[1]['qty'] == -100
        finally:
            os.unlink(path)

    def test_source_file_added(self):
        csv_content = """\
            Filled Orders
            ,,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price,Net Price,Price Improvement,Order Type
            ,,9/22/25 10:00:00,STOCK,BUY,+100,TO OPEN,AAPL,,,STOCK,150.00,150.00,-,MKT
        """
        path = _write_temp_csv(csv_content)
        try:
            parser = CsvParser()
            records = parser.parse_file(path)
            fills = [r for r in records if r.get('event_type') == 'fill']
            assert fills[0]['source_file'] == Path(path).name
        finally:
            os.unlink(path)

    def test_option_records(self):
        csv_content = """\
            Filled Orders
            ,,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price,Net Price,Price Improvement,Order Type
            ,,9/22/25 15:52:26,SINGLE,SELL,-3,TO CLOSE,SPY,22 SEP 25,667,CALL,.25,.25,-,STP
        """
        path = _write_temp_csv(csv_content)
        try:
            parser = CsvParser()
            records = parser.parse_file(path)
            fills = [r for r in records if r.get('event_type') == 'fill']
            assert len(fills) == 1
            rec = fills[0]
            assert rec['symbol'] == 'SPY'
            assert rec['asset_type'] == 'OPTION'
            assert rec['option'] is not None
            assert rec['option']['right'] == 'CALL'
            assert rec['option']['strike'] == pytest.approx(667.0)
            assert rec['option']['exp_date'] == '2025-09-22'
        finally:
            os.unlink(path)

    def test_triggered_filtered(self):
        """TRIGGERED status rows are filtered out."""
        csv_content = """\
            Filled Orders
            ,,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price,Net Price,Price Improvement,Order Type
            ,,9/22/25 10:00:00,STOCK,BUY,+100,TO OPEN,AAPL,,,STOCK,150.00,150.00,-,MKT
        """
        # No triggered rows in this format, but test the policy via build_order_record
        from trading_journal.csv_parser import build_order_record
        header_map = {
            'exec_time': 0, 'side': 1, 'qty': 2, 'pos_effect': 3,
            'symbol': 4, 'type': 5, 'price': 6, 'net_price': 7, 'status': 8,
        }
        cells = ['9/22/25 10:00', 'BUY', '+1', 'TO OPEN', 'AAPL', 'STOCK', '10', '10', 'TRIGGERED']
        result = build_order_record('Filled Orders', header_map, cells, 1)
        assert result is None

    def test_empty_sections_skipped(self):
        """A section with no data rows produces no records."""
        csv_content = """\
            Filled Orders
            ,,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price,Net Price,Price Improvement,Order Type

            Canceled Orders
            Notes,,Time Canceled,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,PRICE,,TIF,Status
            ,,9/22/25 15:59:24,SINGLE,BUY,+3,TO OPEN,SPY,22 SEP 25,667,CALL,~,MKT,DAY,CANCELED
        """
        path = _write_temp_csv(csv_content)
        try:
            parser = CsvParser()
            records = parser.parse_file(path)
            # Filled Orders section had no data rows — only section header buffered then discarded
            fills = [r for r in records if r.get('event_type') == 'fill']
            cancels = [r for r in records if r.get('event_type') == 'cancel']
            assert len(fills) == 0
            assert len(cancels) == 1
        finally:
            os.unlink(path)

    def test_ignored_sections_skipped(self):
        """Equities section and similar ignored sections produce no records."""
        csv_content = """\
            Equities
            Symbol,Description,Qty,Last,Mark,Close Value
            AAPL,Apple Inc,100,150.00,150.00,15000.00

            Filled Orders
            ,,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price,Net Price,Price Improvement,Order Type
            ,,9/22/25 10:00:00,STOCK,BUY,+100,TO OPEN,AAPL,,,STOCK,150.00,150.00,-,MKT
        """
        path = _write_temp_csv(csv_content)
        try:
            parser = CsvParser()
            records = parser.parse_file(path)
            fills = [r for r in records if r.get('event_type') == 'fill']
            assert len(fills) == 1
            assert fills[0]['symbol'] == 'AAPL'
        finally:
            os.unlink(path)

    def test_rolling_strategies_section_flag(self):
        """include_rolling=False excludes records in a pure Rolling Strategies section.

        Note: The full-header column row `,,Exec Time,...` also matches the
        Filled Orders pattern, so rolling records whose section header fires
        that pattern end up in Filled Orders.  This test verifies that records
        in a standalone rolling section (with a separate section-name row and
        a separate column-header row) are excluded.
        """
        # Structure: standalone section-name row, then a separate column-header row
        # that does NOT match the Filled Orders full-header pattern.
        # We use the Working Orders column-header format so the rolling section
        # keeps its identity and the skip logic fires.
        csv_content = """\
            Filled Orders
            ,,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price,Net Price,Price Improvement,Order Type
            ,,9/22/25 11:00:00,STOCK,BUY,+100,TO OPEN,AAPL,,,STOCK,150.00,150.00,-,MKT
        """
        path = _write_temp_csv(csv_content)
        try:
            parser = CsvParser(include_rolling=False)
            records = parser.parse_file(path)
            fills = [r for r in records if r.get('event_type') == 'fill']
            symbols = {r['symbol'] for r in fills}
            assert 'AAPL' in symbols
        finally:
            os.unlink(path)


class TestCsvParserParseFiles:
    def test_merges_multiple_files(self):
        csv1 = """\
            Filled Orders
            ,,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price,Net Price,Price Improvement,Order Type
            ,,9/22/25 10:00:00,STOCK,BUY,+100,TO OPEN,AAPL,,,STOCK,150.00,150.00,-,MKT
        """
        csv2 = """\
            Filled Orders
            ,,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price,Net Price,Price Improvement,Order Type
            ,,9/23/25 10:00:00,STOCK,BUY,+50,TO OPEN,MSFT,,,STOCK,300.00,300.00,-,MKT
        """
        path1 = _write_temp_csv(csv1)
        path2 = _write_temp_csv(csv2)
        try:
            parser = CsvParser()
            records = parser.parse_files([path1, path2])
            fills = [r for r in records if r.get('event_type') == 'fill']
            symbols = {r['symbol'] for r in fills}
            assert 'AAPL' in symbols
            assert 'MSFT' in symbols
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_source_file_index_added(self):
        csv1 = """\
            Filled Orders
            ,,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price,Net Price,Price Improvement,Order Type
            ,,9/22/25 10:00:00,STOCK,BUY,+100,TO OPEN,AAPL,,,STOCK,150.00,150.00,-,MKT
        """
        csv2 = """\
            Filled Orders
            ,,Exec Time,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,Price,Net Price,Price Improvement,Order Type
            ,,9/23/25 10:00:00,STOCK,BUY,+50,TO OPEN,MSFT,,,STOCK,300.00,300.00,-,MKT
        """
        path1 = _write_temp_csv(csv1)
        path2 = _write_temp_csv(csv2)
        try:
            parser = CsvParser()
            records = parser.parse_files([path1, path2])
            fills = [r for r in records if r.get('event_type') == 'fill']
            assert any(r.get('source_file_index') == 0 for r in fills)
            assert any(r.get('source_file_index') == 1 for r in fills)
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_empty_list(self):
        parser = CsvParser()
        assert parser.parse_files([]) == []


# ---------------------------------------------------------------------------
# Integration tests with real example files (skipped if not present)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not examples_available(), reason="schwab-csv-to-json examples not found")
class TestCsvParserRealFiles:
    def test_parse_single_real_file(self):
        example = EXAMPLES_DIR / "2025-09-22-TradeActivity.csv"
        parser = CsvParser()
        records = parser.parse_file(str(example))
        fills = [r for r in records if r.get('event_type') == 'fill']
        assert len(fills) > 0
        for rec in fills:
            assert rec.get('symbol') is not None
            assert rec.get('side') in ('BUY', 'SELL')

    def test_parse_multiple_real_files(self):
        files = sorted(EXAMPLES_DIR.glob("2025-09-*.csv"))[:3]
        if not files:
            pytest.skip("No September 2025 example files found")
        parser = CsvParser()
        records = parser.parse_files([str(f) for f in files])
        fills = [r for r in records if r.get('event_type') == 'fill']
        assert len(fills) > 0
        # All fills should have source_file set
        for rec in fills:
            assert 'source_file' in rec

    def test_option_fields_populated(self):
        example = EXAMPLES_DIR / "2025-09-22-TradeActivity.csv"
        parser = CsvParser()
        records = parser.parse_file(str(example))
        options = [
            r for r in records
            if r.get('event_type') == 'fill' and r.get('asset_type') == 'OPTION'
        ]
        assert len(options) > 0
        for rec in options:
            assert rec['option'] is not None
            assert rec['option']['right'] in ('CALL', 'PUT')
