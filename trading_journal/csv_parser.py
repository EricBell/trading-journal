"""CSV parser for Schwab trade activity reports.

Migrated from schwab-csv-to-json/main.py and batch.py.
Provides CsvParser class with fixed policies:
  - Quantities always signed
  - Empty sections skipped
  - Records grouped and sorted by time
  - TRIGGERED/REJECTED rows filtered out
  - Patterns loaded from bundled data/patterns.json
"""

import csv
import importlib.resources
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Column alias mapping - maps normalized header names to canonical field names
COL_ALIASES = {
    # exec_time aliases
    'exec time': 'exec_time',
    'execution time': 'exec_time',
    'time': 'exec_time',
    # time_canceled aliases
    'time canceled': 'time_canceled',
    'time cancelled': 'time_canceled',
    # time_placed aliases
    'time placed': 'time_placed',
    # spread
    'spread': 'spread',
    # side
    'side': 'side',
    # qty aliases
    'qty': 'qty',
    'quantity': 'qty',
    # pos_effect aliases
    'pos effect': 'pos_effect',
    'position effect': 'pos_effect',
    # symbol
    'symbol': 'symbol',
    # exp aliases
    'exp': 'exp',
    'expiration': 'exp',
    # strike
    'strike': 'strike',
    # type aliases
    'type': 'type',
    'right': 'type',
    'option type': 'type',
    # price aliases
    'price': 'price',
    'exec price': 'price',
    'limit price': 'price',
    # net_price aliases
    'net price': 'net_price',
    'net price ': 'net_price',
    # price_improvement aliases
    'price improvement': 'price_improvement',
    'price impr': 'price_improvement',
    # order_type aliases
    'order type': 'order_type',
    'ordertype': 'order_type',
    'order type ': 'order_type',
    # tif aliases
    'tif': 'tif',
    'time in force': 'tif',
    # status
    'status': 'status',
    # notes
    'notes': 'notes',
    # mark
    'mark': 'mark',
}

AMEND_REF_RE = re.compile(r'^RE\s*#\s*(\d+)', re.IGNORECASE)
MONTH_MAP = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05', 'JUN': '06',
    'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
}

SECTION_NAME_NORMALIZATION = {
    'account trade history': 'Filled Orders',
}


def _load_default_patterns() -> Dict[str, Optional[str]]:
    """Load section patterns from bundled patterns.json."""
    try:
        pkg = importlib.resources.files('trading_journal.data')
        text = (pkg / 'patterns.json').read_text(encoding='utf-8')
        return json.loads(text)
    except Exception:
        # Fallback: load relative to this file
        data_path = Path(__file__).parent / 'data' / 'patterns.json'
        with open(data_path, encoding='utf-8') as f:
            return json.load(f)


def normalize_key(s: Optional[str]) -> str:
    """Normalize header key to lowercase with single spaces, BOM removed."""
    if s is None:
        return ''
    s = s.replace('\ufeff', '').strip()
    s = re.sub(r'\s+', ' ', s)
    return s.lower()


def normalize_section_name(section: Optional[str]) -> Optional[str]:
    """Map account statement section names to trade activity equivalents."""
    if section is None:
        return None
    key = section.lower().strip()
    return SECTION_NAME_NORMALIZATION.get(key, section)


def compile_section_patterns(
    patterns: Dict[str, Optional[str]]
) -> List[Tuple[re.Pattern, Optional[str]]]:
    """Compile pattern dict to list of (compiled_regex, section_name) tuples."""
    return [(re.compile(p), name) for p, name in patterns.items()]


def map_header_to_index(header: List[str]) -> Dict[str, int]:
    """Map header row to {canonical_key: column_index}."""
    result: Dict[str, int] = {}
    for idx, val in enumerate(header):
        if not val or not val.strip():
            continue
        normalized = normalize_key(val)
        if normalized in COL_ALIASES:
            canonical = COL_ALIASES[normalized]
            if canonical not in result:
                result[canonical] = idx
    return result


def safe_get(cells: List[str], index: Optional[int]) -> Optional[str]:
    """Safely get cell value, treating empty/'~'/'-' as None."""
    if index is None or index < 0 or index >= len(cells):
        return None
    value = cells[index]
    if not value or not value.strip():
        return None
    value = value.strip()
    if value in ('~', '-'):
        return None
    return value


def detect_section_from_row(
    cells: List[str],
    compiled_patterns: List[Tuple[re.Pattern, Optional[str]]]
) -> Optional[str]:
    """Detect section name from CSV row using compiled patterns. Returns sentinel '_IGNORED_' for ignored sections."""
    row_str = ','.join('' if c is None else str(c) for c in cells)
    for pattern, section_name in compiled_patterns:
        if pattern.search(row_str):
            return section_name if section_name is not None else '_IGNORED_'
    return None


def parse_integer_qty(value: Optional[str], issues: List[str]) -> Any:
    """Parse quantity as signed integer."""
    if not value:
        return None
    value = value.strip()
    if value in ('~', '-', ''):
        return None
    clean = value.replace(',', '').replace('-+', '-').replace('+-', '-')
    try:
        fval = float(clean)
        if fval.is_integer():
            return int(fval)
        else:
            issues.append('qty_parse_failed')
            return value
    except (ValueError, TypeError):
        issues.append('qty_parse_failed')
        return value


def parse_float_field(
    value: Optional[str], field_name: str, issues: List[str]
) -> Optional[float]:
    """Parse float field with $ and comma removal."""
    if not value:
        return None
    value = value.strip()
    if value in ('~', '-', ''):
        return None
    value = value.replace('$', '').replace(',', '')
    if value.startswith('.') and value != '.':
        value = '0' + value
    try:
        return float(value)
    except (ValueError, TypeError):
        issues.append(f'{field_name}_parse_failed')
        return None


def parse_datetime_maybe(s: Optional[str]) -> Optional[str]:
    """Parse datetime string to ISO format."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except Exception:
            continue
    return None


def parse_exp_date(exp: Optional[str]) -> Optional[str]:
    """Parse option expiration date to ISO format."""
    if not exp:
        return None
    exp = exp.strip().upper()
    m = re.match(r'^(\d{1,2})\s+([A-Z]{3})\s+(\d{2,4})$', exp)
    if not m:
        try:
            return datetime.strptime(exp, "%Y-%m-%d").date().isoformat()
        except Exception:
            return None
    day, mon3, yr = m.groups()
    mon = MONTH_MAP.get(mon3)
    if not mon:
        return None
    if len(yr) == 2:
        yr = ("20" + yr) if int(yr) <= 69 else ("19" + yr)
    return f"{yr}-{mon}-{int(day):02d}"


def classify_row(cells: List[str]) -> str:
    """Classify CSV row as 'noise', 'amendment', 'header', or 'data'."""
    if not cells or all(c.strip() == '' for c in cells):
        return 'noise'
    for c in cells:
        if AMEND_REF_RE.match(c.strip()):
            return 'amendment'
    normalized = [normalize_key(c) for c in cells]
    joined = ','.join(normalized)
    has_time = any(t in joined for t in ['exec time', 'time canceled', 'time placed'])
    has_trade_cols = 'side' in joined and 'qty' in joined
    if has_time and has_trade_cols:
        return 'header'
    return 'data'


def build_order_record(
    section: str,
    header_map: Dict[str, int],
    cells: List[str],
    row_index: int,
) -> Optional[Dict[str, Any]]:
    """Build order record from CSV row using fixed policies."""
    issues: List[str] = []

    exec_time = safe_get(cells, header_map.get('exec_time'))
    time_canceled = safe_get(cells, header_map.get('time_canceled'))
    spread = safe_get(cells, header_map.get('spread'))
    side = safe_get(cells, header_map.get('side'))
    qty_str = safe_get(cells, header_map.get('qty'))
    pos_effect = safe_get(cells, header_map.get('pos_effect'))
    symbol = safe_get(cells, header_map.get('symbol'))
    exp = safe_get(cells, header_map.get('exp'))
    strike_str = safe_get(cells, header_map.get('strike'))
    type_str = safe_get(cells, header_map.get('type'))
    price_str = safe_get(cells, header_map.get('price'))
    net_price_str = safe_get(cells, header_map.get('net_price'))
    price_impr_str = safe_get(cells, header_map.get('price_improvement'))
    order_type = safe_get(cells, header_map.get('order_type'))
    tif = safe_get(cells, header_map.get('tif'))
    status = safe_get(cells, header_map.get('status'))
    notes = safe_get(cells, header_map.get('notes'))
    mark_str = safe_get(cells, header_map.get('mark'))

    if side:
        side = side.upper()
    if pos_effect:
        pos_effect = pos_effect.upper()
    if symbol:
        symbol = symbol.upper()
    if type_str:
        type_str = type_str.upper()
    if order_type:
        order_type = order_type.upper()
    if tif:
        tif = tif.upper()
    if status:
        status = status.upper()

    # Filter TRIGGERED/REJECTED (fixed policy)
    if status and (status == 'TRIGGERED' or status.startswith('REJECTED')):
        return None

    # Skip rows with no meaningful data
    if not side and not qty_str and not symbol and not type_str:
        return None

    qty = parse_integer_qty(qty_str, issues)
    price = parse_float_field(price_str, 'price', issues)
    net_price = parse_float_field(net_price_str, 'net_price', issues)
    price_improvement = parse_float_field(price_impr_str, 'price_improvement', issues)
    strike = parse_float_field(strike_str, 'strike', issues)
    mark = parse_float_field(mark_str, 'mark', issues)

    asset_type = None
    if type_str in {'CALL', 'PUT'}:
        asset_type = 'OPTION'
    elif type_str == 'STOCK':
        asset_type = 'STOCK'
    elif type_str == 'ETF':
        asset_type = 'ETF'

    option = None
    if asset_type == 'OPTION':
        option = {
            'exp_date': parse_exp_date(exp),
            'strike': strike,
            'right': type_str,
        }

    normalized_section = normalize_section_name(section)
    if normalized_section == 'Account Order History' and status:
        if status == 'FILLED':
            event_type = 'fill'
        elif status == 'CANCELED' or status.startswith('REJECTED'):
            event_type = 'cancel'
        else:
            event_type = 'other'
    elif normalized_section == 'Filled Orders':
        event_type = 'fill'
    elif normalized_section == 'Canceled Orders':
        event_type = 'cancel'
    elif normalized_section == 'Working Orders':
        event_type = 'working'
    else:
        event_type = 'other'

    return {
        'section': normalized_section,
        'row_index': row_index,
        'raw': ','.join(cells),
        'issues': issues,
        'exec_time': parse_datetime_maybe(exec_time),
        'time_canceled': parse_datetime_maybe(time_canceled),
        'time_placed': None,
        'side': side,
        'qty': qty,
        'pos_effect': pos_effect,
        'symbol': symbol,
        'exp': parse_exp_date(exp) if option else None,
        'strike': strike if option else None,
        'type': type_str,
        'spread': spread,
        'price': price,
        'net_price': net_price,
        'price_improvement': price_improvement,
        'order_type': order_type,
        'tif': tif,
        'status': status,
        'notes': notes,
        'mark': mark,
        'event_type': event_type,
        'asset_type': asset_type,
        'option': option,
    }


def build_amendment_record(
    section: str, cells: List[str], row_index: int
) -> Dict[str, Any]:
    """Build amendment record from RE # row."""
    issues: List[str] = []
    ref = None
    stop_price = None
    order_type = None
    tif = None

    for c in cells:
        c_str = c.strip()
        m = AMEND_REF_RE.match(c_str)
        if m:
            ref = m.group(1)
            continue
        if stop_price is None and re.match(r'^\.?-?\d+(?:\.\d+)?$', c_str):
            stop_price = parse_float_field(c_str, 'stop_price', issues)
        if c_str.upper() in {'STP', 'STP LMT', 'LMT', 'MKT'}:
            order_type = c_str.upper()
        if c_str.upper() in {'DAY', 'GTC', 'STD'}:
            tif = c_str.upper()

    return {
        'section': normalize_section_name(section),
        'row_index': row_index,
        'event_type': 'amend',
        'amendment': {'ref': ref, 'stop_price': stop_price, 'order_type': order_type, 'tif': tif},
        'raw': ','.join(cells),
        'issues': issues,
    }


def _get_sort_time(record: Dict[str, Any]) -> Optional[datetime]:
    """Extract sort time from record (exec_time > time_canceled > time_placed)."""
    for field in ('exec_time', 'time_canceled', 'time_placed'):
        val = record.get(field)
        if val:
            try:
                return datetime.fromisoformat(val)
            except (ValueError, TypeError):
                pass
    return None


def group_and_sort_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group records by section and sort by time within each section."""
    section_headers: Dict[str, Dict[str, Any]] = {}
    data_by_section: Dict[str, List[Dict[str, Any]]] = {}

    for record in records:
        section = record.get('section', 'Unknown')
        is_header = 'section_header' in record.get('issues', [])
        if is_header:
            if section not in section_headers:
                section_headers[section] = record
        else:
            data_by_section.setdefault(section, []).append(record)

    for section_records in data_by_section.values():
        section_records.sort(key=lambda r: (
            _get_sort_time(r) is None,
            _get_sort_time(r) if _get_sort_time(r) is not None else datetime.max
        ))

    result = []
    for section in sorted(section_headers.keys()):
        result.append(section_headers[section])
        result.extend(data_by_section.get(section, []))

    return result


def _parse_single_file(
    path: str,
    include_rolling: bool,
    encoding: str,
    compiled_patterns: List[Tuple[re.Pattern, Optional[str]]],
) -> List[Dict[str, Any]]:
    """Parse a single CSV file and return list of records (section headers skipped)."""
    results: List[Dict[str, Any]] = []
    section = 'Top'
    in_data = False
    current_header_map: Optional[Dict[str, int]] = None
    row_index = 0

    # Buffering for empty section filtering
    buffered_section_header: Optional[Dict[str, Any]] = None
    buffered_column_header: Optional[Dict[str, Any]] = None
    buffered_header_map: Optional[Dict[str, int]] = None

    _EMPTY_FIELDS: Dict[str, None] = {
        'exec_time': None, 'time_canceled': None, 'time_placed': None,
        'side': None, 'qty': None, 'pos_effect': None, 'symbol': None,
        'exp': None, 'strike': None, 'type': None, 'spread': None,
        'price': None, 'net_price': None, 'price_improvement': None,
        'order_type': None, 'tif': None, 'status': None,
        'notes': None, 'mark': None,
    }

    with open(path, 'r', encoding=encoding, errors='ignore', newline='') as f:
        reader = csv.reader(f)
        for row in reader:
            row_index += 1
            cells = list(row)

            detected = detect_section_from_row(cells, compiled_patterns)

            if detected == '_IGNORED_':
                # Enter ignored section: clear state
                section = None  # type: ignore[assignment]
                in_data = False
                current_header_map = None
                buffered_header_map = None
                buffered_section_header = None
                buffered_column_header = None
                continue

            if detected is not None:
                # New named section detected
                if buffered_section_header is not None:
                    # Previous section was empty — discard buffered headers
                    buffered_section_header = None
                    buffered_column_header = None
                    buffered_header_map = None

                section = detected
                in_data = False
                current_header_map = None

                section_header_record: Dict[str, Any] = {
                    'section': normalize_section_name(section),
                    'row_index': row_index,
                    'raw': ','.join(cells),
                    'issues': ['section_header'],
                    **_EMPTY_FIELDS,
                }

                cls = classify_row(cells)
                if cls == 'header':
                    header_map = map_header_to_index(cells)
                    buffered_section_header = section_header_record
                    buffered_column_header = section_header_record
                    buffered_header_map = header_map
                else:
                    buffered_section_header = section_header_record
                    buffered_column_header = None
                    buffered_header_map = None
                continue

            # No section detected on this row
            if section is None:
                continue

            if section == 'Rolling Strategies' and not include_rolling:
                continue

            cls = classify_row(cells)

            if cls == 'header':
                header_map = map_header_to_index(cells)
                header_record: Dict[str, Any] = {
                    'section': normalize_section_name(section),
                    'row_index': row_index,
                    'raw': ','.join(cells),
                    'issues': ['section_header'],
                    **_EMPTY_FIELDS,
                }
                buffered_column_header = header_record
                buffered_header_map = header_map
                continue

            if cls == 'noise':
                continue

            # Data row: flush buffered headers if any
            if buffered_section_header is not None:
                results.append(buffered_section_header)
                buffered_section_header = None

            if buffered_column_header is not None:
                results.append(buffered_column_header)
                current_header_map = buffered_header_map
                in_data = True
                buffered_column_header = None
                buffered_header_map = None

            if not in_data or not current_header_map:
                continue

            if cls == 'amendment':
                results.append(build_amendment_record(section, cells, row_index))
                continue

            rec = build_order_record(section, current_header_map, cells, row_index)
            if rec is not None:
                results.append(rec)

    return results


class CsvParser:
    """Parse Schwab CSV trade activity files into record dicts.

    Fixed policies (not configurable):
    - Quantities always signed
    - Empty sections skipped
    - Records grouped by section and sorted by time
    - TRIGGERED/REJECTED rows filtered out
    - Section patterns loaded from bundled data/patterns.json
    """

    def __init__(self, include_rolling: bool = False, encoding: str = 'utf-8') -> None:
        self.include_rolling = include_rolling
        self.encoding = encoding
        patterns = _load_default_patterns()
        self._compiled_patterns = compile_section_patterns(patterns)

    def parse_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse a single CSV file. Returns list of fill/trade records (no section headers)."""
        records = _parse_single_file(
            path=file_path,
            include_rolling=self.include_rolling,
            encoding=self.encoding,
            compiled_patterns=self._compiled_patterns,
        )
        # Add source file metadata
        source_filename = Path(file_path).name
        for rec in records:
            rec['source_file'] = source_filename
        return records

    def parse_files(self, file_paths: List[str]) -> List[Dict[str, Any]]:
        """Parse multiple CSV files, returning merged and sorted records.

        Records from all files are combined, grouped by section, and sorted
        by time within each section. Each record has a 'source_file' field.
        """
        all_records: List[Dict[str, Any]] = []

        for file_index, file_path in enumerate(file_paths):
            records = _parse_single_file(
                path=file_path,
                include_rolling=self.include_rolling,
                encoding=self.encoding,
                compiled_patterns=self._compiled_patterns,
            )
            source_filename = Path(file_path).name
            for rec in records:
                rec['source_file'] = source_filename
                rec['source_file_index'] = file_index
            all_records.extend(records)

        if all_records:
            all_records = group_and_sort_records(all_records)

        return all_records
