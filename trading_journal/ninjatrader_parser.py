"""Parser for NinjaTrader execution CSV files.

NinjaTrader exports two CSV formats:
- Executions (-exec.csv): actual fills with prices, timestamps, entry/exit flags
- Orders (-ord.csv): all orders including pending/cancelled

Only the executions file is used for ingestion. Detect with is_ninjatrader_exec_file().

Execution CSV column format:
  Instrument, Action, Quantity, Price, Time, ID, E/X, Position,
  Order ID, Name, Commission, Rate, Account display name, Connection

Instrument format: '{ROOT} {MMMYY}' e.g. 'MES JUN26'
  ROOT     = base symbol (MES, ES, NQ, ...)
  MMMYY    = contract month abbreviation + 2-digit year (JUN26, SEP26, ...)
"""

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MONTH_MAP: Dict[str, int] = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

# Columns that identify a NinjaTrader executions file
_NT_REQUIRED_COLS = {'Instrument', 'Action', 'Quantity', 'Price', 'Time', 'E/X'}


def is_ninjatrader_exec_file(file_path: str) -> bool:
    """Return True if the CSV looks like a NinjaTrader executions export."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
        cols = {c.strip() for c in first_line.split(',')}
        return _NT_REQUIRED_COLS.issubset(cols)
    except Exception:
        return False


def _parse_futures_instrument(instrument: str) -> Tuple[str, Optional[date]]:
    """Parse 'MES JUN26' → ('MES', date(2026, 6, 1)).

    Returns (root_symbol, contract_month_date).
    exp_date is the first day of the contract month for uniqueness purposes.
    Returns (instrument, None) if the format is not recognised.
    """
    parts = instrument.strip().split()
    if len(parts) != 2:
        return instrument.upper(), None
    root = parts[0].upper()
    contract = parts[1].upper()
    if len(contract) >= 4:
        month_str = contract[:3]
        year_str = contract[3:]
        month = MONTH_MAP.get(month_str)
        if month and year_str.isdigit():
            year = int(year_str)
            if year < 100:
                year = 2000 + year
            try:
                return root, date(year, month, 1)
            except ValueError:
                pass
    return root, None


def _parse_nt_datetime(s: str) -> Optional[str]:
    """Parse NinjaTrader timestamp '3/26/2026 15:28:12' → ISO-8601 string."""
    if not s:
        return None
    s = s.strip()
    for fmt in ('%m/%d/%Y %H:%M:%S', '%m/%d/%y %H:%M:%S'):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    return None


def _normalize_action(action: str) -> str:
    """Map NinjaTrader action strings to BUY or SELL."""
    a = action.strip().upper()
    if a in ('BUY', 'BUY TO COVER'):
        return 'BUY'
    if a in ('SELL', 'SELL SHORT'):
        return 'SELL'
    return a


def _normalize_ex(ex: str) -> str:
    """Map E/X column value to pos_effect string."""
    e = ex.strip().upper()
    if e == 'ENTRY':
        return 'TO OPEN'
    if e == 'EXIT':
        return 'TO CLOSE'
    return 'AUTO'


class NinjaTraderParser:
    """Parse NinjaTrader executions CSV into record dicts for NdjsonIngester."""

    def parse_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Return a list of fill record dicts compatible with NdjsonIngester.ingest_records()."""
        records: List[Dict[str, Any]] = []
        source_filename = Path(file_path).name

        with open(file_path, 'r', encoding='utf-8', errors='ignore', newline='') as f:
            reader = csv.DictReader(f)
            for row_index, row in enumerate(reader, start=2):  # row 1 is the header
                rec = self._build_record(row, row_index, source_filename)
                if rec is not None:
                    records.append(rec)

        return records

    def _build_record(
        self,
        row: Dict[str, str],
        row_index: int,
        source_file: str,
    ) -> Optional[Dict[str, Any]]:
        instrument = row.get('Instrument', '').strip()
        action = row.get('Action', '').strip()
        qty_str = row.get('Quantity', '').strip()
        price_str = row.get('Price', '').strip()
        time_str = row.get('Time', '').strip()
        ex_str = row.get('E/X', '').strip()
        account = (row.get('Account display name') or '').strip()

        if not (instrument and action and qty_str and price_str and time_str):
            return None

        symbol, exp_date = _parse_futures_instrument(instrument)
        side = _normalize_action(action)
        if side not in ('BUY', 'SELL'):
            return None

        try:
            qty = int(qty_str)
        except ValueError:
            return None

        try:
            price = float(price_str)
        except ValueError:
            return None

        exec_time = _parse_nt_datetime(time_str)
        if not exec_time:
            return None

        pos_effect = _normalize_ex(ex_str)

        return {
            # NdjsonRecord required fields
            'section': 'Fills',
            'row_index': row_index,
            'raw': ','.join(str(v) for v in row.values()),
            'issues': [],
            # Event
            'exec_time': exec_time,
            'time_canceled': None,
            'time_placed': None,
            'event_type': 'fill',
            # Trade
            'side': side,
            'qty': qty,
            'pos_effect': pos_effect,
            'symbol': symbol,
            # Futures contract expiry stored in the 'exp' field (contract month)
            'exp': exp_date.isoformat() if exp_date else None,
            'strike': None,
            'type': None,
            'spread': None,
            # Pricing
            'price': price,
            'net_price': price,
            'price_improvement': None,
            'order_type': None,
            'tif': None,
            'status': None,
            'notes': None,
            'mark': None,
            # Classification
            'asset_type': 'FUTURES',
            'option': None,
            # Source
            'source_file': source_file,
            'account_number': account or None,
            'account_name': None,
        }
