"""Configuration for report column layouts."""

from typing import Dict, List


# Column definitions for completed trades reports
# Each column has a key used in code and a human-readable label.
TRADE_COLUMN_DEFS: Dict[str, Dict[str, object]] = {
    "id": {"label": "ID", "width": 6, "align": "<"},
    "symbol": {"label": "Symbol", "width": 8, "align": "<"},
    "instrument_type": {"label": "Asset", "width": 6, "align": "<"},
    "type": {"label": "Type", "width": 6, "align": "<"},
    "qty": {"label": "Qty", "width": 6, "align": ">"},
    "date": {"label": "Date", "width": 6, "align": ">"},
    "entm": {"label": "EnTm", "width": 4, "align": ">"},
    "entry": {"label": "Entry", "width": 10, "align": ">"},
    "extm": {"label": "ExTm", "width": 4, "align": ">"},
    "exit": {"label": "Exit", "width": 10, "align": ">"},
    "pnl": {"label": "P&L", "width": 12, "align": ">"},
    "result": {"label": "Result", "width": 8, "align": "<"},
    "pattern": {"label": "Pattern", "width": 20, "align": "<"},
}


# Named layouts for the trades report.
# Each layout defines the ordered columns to display and an optional default sort.
TRADE_REPORT_LAYOUTS: Dict[str, Dict[str, object]] = {
    "default": {
        "columns": [
            "id",
            "symbol",
            "type",
            "qty",
            "date",
            "entm",
            "entry",
            "extm",
            "exit",
            "pnl",
            "result",
            "pattern",
        ],
        "default_sort": ["date", "entm"],
    },
    "with-assets": {
        "columns": [
            "id",
            "symbol",
            "instrument_type",
            "type",
            "qty",
            "date",
            "entm",
            "entry",
            "extm",
            "exit",
            "pnl",
            "result",
            "pattern",
        ],
        "default_sort": ["instrument_type", "date", "entm"],
    },
}


TRADE_SORTABLE_COLUMNS = set(TRADE_COLUMN_DEFS.keys())

