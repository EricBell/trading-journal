#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "psycopg2-binary",
#   "python-dotenv",
#   "tabulate",
# ]
# ///
"""Standalone PostgreSQL query CLI for trading-journal.

Reads connection settings from the project .env (two directories up from this
file) so it works when invoked from any directory.

Usage:
    uv run tools/psql/psql.py "SELECT * FROM trades LIMIT 5"
    uv run tools/psql/psql.py --format json "SELECT symbol, count(*) FROM trades GROUP BY symbol"
    echo "SELECT 1" | uv run tools/psql/psql.py
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up: tools/psql/ → tools/ → project/)
load_dotenv(Path(__file__).parent.parent.parent / '.env')

import psycopg2
from psycopg2.extras import RealDictCursor
from tabulate import tabulate


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='psql',
        description='Run a SQL query against the trading-journal PostgreSQL database.',
    )
    p.add_argument(
        'sql',
        nargs='?',
        help='SQL to execute. Reads from stdin if omitted.',
    )
    p.add_argument(
        '--format', '-f',
        choices=['table', 'csv', 'json'],
        default='table',
        help='Output format (default: table)',
    )
    p.add_argument(
        '--limit', '-l',
        type=int,
        default=500,
        help='Maximum rows to return for SELECT queries (default: 500)',
    )
    p.add_argument(
        '--host',
        default=None,
        help='PostgreSQL host (overrides DB_HOST in .env)',
    )
    p.add_argument(
        '--port',
        type=int,
        default=None,
        help='PostgreSQL port (overrides DB_PORT in .env)',
    )
    p.add_argument(
        '--dbname',
        default=None,
        help='Database name (overrides DB_NAME in .env)',
    )
    p.add_argument(
        '--user',
        default=None,
        help='Database user (overrides DB_USER in .env)',
    )
    p.add_argument(
        '--password',
        default=None,
        help='Database password (overrides DB_PASSWORD in .env)',
    )
    return p


def get_connection(args: argparse.Namespace):
    return psycopg2.connect(
        host=args.host or os.environ.get('DB_HOST', 'localhost'),
        port=args.port or int(os.environ.get('DB_PORT', 5432)),
        dbname=args.dbname or os.environ.get('DB_NAME', 'trading_journal'),
        user=args.user or os.environ.get('DB_USER', 'postgres'),
        password=args.password or os.environ.get('DB_PASSWORD', ''),
    )


def run_query(sql: str, args: argparse.Namespace) -> None:
    with get_connection(args) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Inject LIMIT if it's a SELECT without one and limit is set
            stripped = sql.strip().rstrip(';')
            is_select = stripped.upper().lstrip('(').startswith('SELECT')
            if is_select and args.limit and 'limit' not in sql.lower():
                sql = f"{stripped} LIMIT {args.limit}"

            cur.execute(sql)

            if cur.description:
                rows = [dict(r) for r in cur.fetchall()]
                if not rows:
                    print('(0 rows)')
                    return

                if args.format == 'json':
                    print(json.dumps(rows, indent=2, default=str))
                elif args.format == 'csv':
                    import csv, io
                    out = io.StringIO()
                    writer = csv.DictWriter(out, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                    print(out.getvalue(), end='')
                else:
                    print(tabulate(rows, headers='keys', tablefmt='psql'))
                    print(f'\n({len(rows)} rows)')
            else:
                print(f'Query OK, {cur.rowcount} rows affected')


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    sql = args.sql or sys.stdin.read().strip()
    if not sql:
        parser.print_help(sys.stderr)
        sys.exit(1)

    try:
        run_query(sql, args)
    except psycopg2.Error as e:
        print(f'Database error: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
