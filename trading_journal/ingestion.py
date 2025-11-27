"""NDJSON data ingestion and processing."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .database import db_manager
from .models import Trade, ProcessingLog
from .schemas import NdjsonRecord
from .positions import PositionTracker

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Custom exception for ingestion errors."""
    pass


class NdjsonIngester:
    """Handles NDJSON file ingestion and processing."""

    def __init__(self):
        self.db_manager = db_manager
        self.position_tracker = PositionTracker()

    def process_file(
        self,
        file_path: Path,
        dry_run: bool = False,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """Process a single NDJSON file."""

        logger.info(f"Processing file: {file_path}")

        # Start processing log
        processing_log = ProcessingLog(
            file_path=str(file_path),
            processing_started_at=datetime.now(),
            status="processing"
        )

        records_processed = 0
        records_failed = 0
        validation_errors = []
        successful_records = []

        try:
            # Read and validate NDJSON records
            records = self._read_ndjson_file(file_path)

            if verbose:
                logger.info(f"Read {len(records)} records from file")

            for record_data in records:
                try:
                    # Validate record schema
                    record = NdjsonRecord(**record_data)

                    # Skip section headers
                    if record.is_section_header:
                        if verbose:
                            logger.debug(f"Skipping section header: {record.section}")
                        continue

                    # Only process fill records for now
                    if not record.is_fill:
                        if verbose:
                            logger.debug(f"Skipping non-fill record: {record.event_type}")
                        continue

                    successful_records.append(record)
                    records_processed += 1

                except ValidationError as e:
                    records_failed += 1
                    error_msg = f"Row {record_data.get('row_index', 'unknown')}: {str(e)}"
                    validation_errors.append(error_msg)
                    logger.warning(f"Validation error: {error_msg}")

            # Process records to database
            if not dry_run and successful_records:
                inserted_trades = self._insert_records(successful_records, str(file_path))

                # Update positions for fill trades
                for trade in inserted_trades:
                    if trade.is_fill:
                        self.position_tracker.update_positions_from_trade(trade)

            # Update processing log
            processing_log.processing_completed_at = datetime.now()
            processing_log.records_processed = records_processed
            processing_log.records_failed = records_failed
            processing_log.status = "completed" if records_failed == 0 else "partial"

            if not dry_run:
                self._save_processing_log(processing_log)

            result = {
                "file_path": str(file_path),
                "records_processed": records_processed,
                "records_failed": records_failed,
                "validation_errors": validation_errors,
                "success": records_failed == 0,
                "dry_run": dry_run
            }

            if verbose or validation_errors:
                logger.info(f"Processing complete: {result}")

            return result

        except Exception as e:
            logger.error(f"Failed to process file {file_path}: {e}")

            processing_log.status = "failed"
            processing_log.error_message = str(e)
            processing_log.processing_completed_at = datetime.now()

            if not dry_run:
                self._save_processing_log(processing_log)

            raise IngestionError(f"File processing failed: {e}") from e

    def _read_ndjson_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Read and parse NDJSON file."""
        records = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)
                        records.append(record)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error on line {line_num}: {e}")
                        raise IngestionError(f"Invalid JSON on line {line_num}: {e}")

        except FileNotFoundError:
            raise IngestionError(f"File not found: {file_path}")
        except PermissionError:
            raise IngestionError(f"Permission denied reading file: {file_path}")

        return records

    def _insert_records(self, records: List[NdjsonRecord], source_file_path: str) -> List[Trade]:
        """Insert validated records into database using UPSERT."""
        inserted_trades = []

        with self.db_manager.get_session() as session:
            for record in records:
                trade_data = self._convert_to_trade_data(record, source_file_path)

                # Use PostgreSQL UPSERT (INSERT ... ON CONFLICT)
                stmt = insert(Trade).values(**trade_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['unique_key'],
                    set_=dict(
                        # Update key fields if record already exists
                        exec_timestamp=stmt.excluded.exec_timestamp,
                        net_price=stmt.excluded.net_price,
                        realized_pnl=stmt.excluded.realized_pnl,
                        processing_timestamp=stmt.excluded.processing_timestamp
                    )
                ).returning(Trade)

                result = session.execute(stmt)
                trade = result.fetchone()
                if trade:
                    # Convert row to Trade object
                    trade_obj = session.get(Trade, trade[0])  # Get by trade_id
                    if trade_obj:
                        inserted_trades.append(trade_obj)

        return inserted_trades

    def _convert_to_trade_data(self, record: NdjsonRecord, source_file_path: str) -> Dict[str, Any]:
        """Convert NdjsonRecord to Trade table data."""

        # Determine instrument type
        instrument_type = "OPTION" if record.is_option else "EQUITY"

        # Handle event type
        event_type = record.event_type or "fill"  # Default to fill for missing event_type

        trade_data = {
            "unique_key": record.unique_key,
            "exec_timestamp": record.exec_time,
            "event_type": event_type,
            "symbol": record.symbol,
            "instrument_type": instrument_type,
            "side": record.side,
            "qty": record.qty,
            "pos_effect": record.pos_effect,
            "price": record.price,
            "net_price": record.net_price,
            "price_improvement": record.price_improvement,
            "order_type": record.order_type,
            "source_file_path": source_file_path,
            "source_file_index": record.source_file_index or 0,
            "raw_data": record.raw,
            "processing_timestamp": datetime.now(),
        }

        # Add option-specific fields
        if record.is_option and record.option:
            trade_data.update({
                "exp_date": record.option.exp_date,
                "strike_price": record.option.strike,
                "option_type": record.option.right,
                "spread_type": record.spread,
                "option_data": record.option.dict() if record.option else None
            })

        return trade_data

    def _save_processing_log(self, processing_log: ProcessingLog) -> None:
        """Save processing log to database."""
        with self.db_manager.get_session() as session:
            session.merge(processing_log)  # Use merge for upsert behavior

    def process_batch(
        self,
        file_pattern: str,
        dry_run: bool = False,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """Process multiple files matching pattern."""

        files = list(Path.cwd().glob(file_pattern))

        if not files:
            raise IngestionError(f"No files found matching pattern: {file_pattern}")

        results = []
        total_processed = 0
        total_failed = 0

        logger.info(f"Processing {len(files)} files in batch")

        for file_path in sorted(files):  # Process in deterministic order
            try:
                result = self.process_file(file_path, dry_run=dry_run, verbose=verbose)
                results.append(result)
                total_processed += result["records_processed"]
                total_failed += result["records_failed"]

            except IngestionError as e:
                logger.error(f"Failed to process {file_path}: {e}")
                results.append({
                    "file_path": str(file_path),
                    "error": str(e),
                    "success": False
                })

        batch_result = {
            "files_processed": len([r for r in results if r.get("success", False)]),
            "files_failed": len([r for r in results if not r.get("success", False)]),
            "total_records_processed": total_processed,
            "total_records_failed": total_failed,
            "results": results,
            "dry_run": dry_run
        }

        logger.info(f"Batch processing complete: {batch_result}")
        return batch_result