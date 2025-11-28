"""NDJSON data ingestion and processing."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import click
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .database import db_manager
from .models import Trade, ProcessingLog
from .schemas import NdjsonRecord
from .positions import PositionTracker
from .authorization import AuthContext
from .duplicate_detector import DuplicateDetector

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
        verbose: bool = False,
        skip_duplicate_check: bool = False,
        force: bool = False
    ) -> Dict[str, Any]:
        """Process a single NDJSON file with duplicate detection."""

        logger.info(f"Processing file: {file_path}")
        user_id = AuthContext.require_user().user_id

        # Start processing log
        processing_log = ProcessingLog(
            user_id=user_id,
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

            # Duplicate detection (before processing)
            if not skip_duplicate_check and successful_records:
                detector = DuplicateDetector()

                # Check for cross-user duplicates
                cross_user_dupes = detector.check_duplicates_cross_user(
                    successful_records,
                    user_id
                )

                if cross_user_dupes.has_duplicates:
                    report = detector.format_duplicate_report(cross_user_dupes, user_id)

                    if not dry_run:
                        click.echo(report)
                        click.echo("These records already exist in the database.")
                        click.echo("UPSERT will UPDATE existing records for your data.")
                        click.echo("Other users' data will NOT be affected.\n")

                        if not force:
                            if not click.confirm("Do you want to continue?"):
                                return {
                                    "file_path": str(file_path),
                                    "records_processed": 0,
                                    "records_failed": 0,
                                    "validation_errors": ["User cancelled due to duplicates"],
                                    "success": False,
                                    "dry_run": False,
                                    "duplicates_found": cross_user_dupes.duplicate_count,
                                    "inserts": 0,
                                    "updates": 0
                                }
                    else:
                        logger.info(f"DRY RUN: {report}")

            # Process records to database with insert/update tracking
            insert_count = 0
            update_count = 0

            if not dry_run and successful_records:
                insert_count, update_count = self._insert_records_with_tracking(
                    user_id,
                    successful_records,
                    str(file_path)
                )
                # Position tracking handled within _insert_records_with_tracking

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
                "inserts": insert_count,
                "updates": update_count,
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

    def _insert_records(self, user_id: int, records: List[NdjsonRecord], source_file_path: str) -> List[int]:
        """Insert validated records into database using UPSERT."""
        inserted_trade_ids = []

        with self.db_manager.get_session() as session:
            for record in records:
                trade_data = self._convert_to_trade_data(record, source_file_path)
                trade_data['user_id'] = user_id

                # Use PostgreSQL UPSERT (INSERT ... ON CONFLICT)
                stmt = insert(Trade).values(**trade_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['user_id', 'unique_key'],
                    set_=dict(
                        # Update key fields if record already exists
                        exec_timestamp=stmt.excluded.exec_timestamp,
                        net_price=stmt.excluded.net_price,
                        realized_pnl=stmt.excluded.realized_pnl,
                        processing_timestamp=stmt.excluded.processing_timestamp
                    )
                ).returning(Trade.trade_id)

                result = session.execute(stmt)
                trade_id = result.scalar()
                if trade_id:
                    inserted_trade_ids.append(trade_id)

            # Commit the transaction
            session.commit()

        return inserted_trade_ids

    def _insert_records_with_tracking(
        self,
        user_id: int,
        records: List[NdjsonRecord],
        source_file_path: str
    ) -> Tuple[int, int]:
        """
        Insert validated records into database using UPSERT, tracking inserts vs updates.

        Returns:
            Tuple of (insert_count, update_count)
        """
        insert_count = 0
        update_count = 0
        inserted_trade_ids = []

        with self.db_manager.get_session() as session:
            for record in records:
                trade_data = self._convert_to_trade_data(record, source_file_path)
                trade_data['user_id'] = user_id

                # Check if exists first (for tracking)
                existing = session.query(Trade).filter_by(
                    user_id=user_id,
                    unique_key=trade_data['unique_key']
                ).first()

                is_update = existing is not None

                # Use PostgreSQL UPSERT
                stmt = insert(Trade).values(**trade_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['user_id', 'unique_key'],
                    set_=dict(
                        exec_timestamp=stmt.excluded.exec_timestamp,
                        net_price=stmt.excluded.net_price,
                        realized_pnl=stmt.excluded.realized_pnl,
                        processing_timestamp=stmt.excluded.processing_timestamp
                    )
                ).returning(Trade.trade_id)

                result = session.execute(stmt)
                trade_id = result.scalar()

                if trade_id:
                    inserted_trade_ids.append(trade_id)
                    if is_update:
                        update_count += 1
                    else:
                        insert_count += 1

            # Commit the transaction
            session.commit()

            # Update positions for fill trades
            for trade_id in inserted_trade_ids:
                trade = session.get(Trade, trade_id)
                if trade and trade.is_fill:
                    self.position_tracker.update_positions_from_trade(trade)

        return insert_count, update_count

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
                "option_data": json.dumps(record.option.dict(), default=str) if record.option else None
            })

        return trade_data

    def _save_processing_log(self, processing_log: ProcessingLog) -> None:
        """Save processing log to database."""
        with self.db_manager.get_session() as session:
            session.add(processing_log)

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