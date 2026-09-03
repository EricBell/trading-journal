"""Shared date-range string parsing, used by dashboard/API and trades-list filtering."""

import re
from datetime import date, datetime, timedelta
from typing import Optional, Tuple


def parse_date_range(date_range_str: Optional[str]) -> Tuple[Optional[date], Optional[date]]:
    """
    Parse date range string into (start_date, end_date) tuple.

    Supported formats:
      today                   -> (today, today)
      Nd                      -> last N days including today (e.g. "7d")
      YYYY-MM-DD              -> single day (start == end)
      YYYY-MM-DD/YYYY-MM-DD   -> explicit range
      YYYY-MM-DD/             -> from date to today (inclusive)
      /YYYY-MM-DD             -> no lower bound, up to date (inclusive)
      /                       -> (None, today) — no lower bound filter
    """
    if not date_range_str:
        return None, None

    today = date.today()
    s = date_range_str.strip()

    # "today" keyword
    if s.lower() == 'today':
        return today, today

    # Nd notation — e.g. "7d" = last 7 days including today
    nd_match = re.fullmatch(r'(\d+)d', s, re.IGNORECASE)
    if nd_match:
        n = int(nd_match.group(1))
        if n < 1:
            raise ValueError("Day count must be 1 or greater (e.g. '7d' for last 7 days)")
        return today - timedelta(days=n - 1), today

    # Slash-separated range (all "/" variants)
    if '/' in s:
        start_str, end_str = s.split('/', 1)
        start_str, end_str = start_str.strip(), end_str.strip()

        start_date: Optional[date] = None
        end_date: Optional[date] = None

        if start_str:
            try:
                start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError(f"Invalid start date '{start_str}'. Expected format: YYYY-MM-DD")

        if end_str:
            try:
                end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError(f"Invalid end date '{end_str}'. Expected format: YYYY-MM-DD")
        else:
            end_date = today  # trailing slash → "up to today"

        return start_date, end_date

    # Bare date (no slash) — treat as single day (start == end)
    try:
        single = datetime.strptime(s, '%Y-%m-%d').date()
        return single, single
    except ValueError:
        pass

    raise ValueError(
        "Date range must be one of: 'today', 'Nd' (e.g. '7d'), "
        "'YYYY-MM-DD' (single day), 'YYYY-MM-DD/YYYY-MM-DD', "
        "'YYYY-MM-DD/' (open end), '/YYYY-MM-DD' (open start), or '/' (no filter)"
    )
