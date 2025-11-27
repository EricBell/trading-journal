"""Position tracking and P&L calculation engine."""

import logging
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy.dialects.postgresql import insert

from .database import db_manager
from .models import Trade, Position, CompletedTrade

logger = logging.getLogger(__name__)


class PositionTracker:
    """Manages position tracking and P&L calculations using average cost basis."""

    def __init__(self):
        self.db_manager = db_manager

    def update_positions_from_trade(self, trade: Trade) -> None:
        """Update positions based on a new trade execution."""
        if not trade.is_fill or not trade.symbol:
            return

        with self.db_manager.get_session() as session:
            position = self._get_or_create_position(session, trade)

            if trade.pos_effect == "TO OPEN":
                self._handle_position_open(position, trade)
            elif trade.pos_effect == "TO CLOSE":
                self._handle_position_close(position, trade)

            self._save_position(session, position, trade)
            logger.info(f"Updated position for {trade.symbol}: {position.current_qty} @ {position.avg_cost_basis}")

    def _get_or_create_position(self, session: Session, trade: Trade) -> Position:
        """Get existing position or create new one."""
        # Build option details for unique position identification
        option_details = None
        if trade.instrument_type == "OPTION" and trade.option_data:
            option_details = trade.option_data

        position = session.query(Position).filter(
            and_(
                Position.user_id == trade.user_id,
                Position.symbol == trade.symbol,
                Position.instrument_type == trade.instrument_type,
                Position.option_details == option_details
            )
        ).first()

        if not position:
            position = Position(
                user_id=trade.user_id,
                symbol=trade.symbol,
                instrument_type=trade.instrument_type,
                option_details=option_details,
                current_qty=0,
                avg_cost_basis=Decimal('0'),
                total_cost=Decimal('0'),
                opened_at=trade.exec_timestamp or datetime.now(),
                realized_pnl=Decimal('0')
            )

        return position

    def _save_position(self, session: Session, position: Position, trade: Trade) -> None:
        """Save position using UPSERT to handle conflicts."""
        # Prepare position data
        position_data = {
            'user_id': position.user_id,
            'symbol': position.symbol,
            'instrument_type': position.instrument_type,
            'option_details': position.option_details,
            'current_qty': position.current_qty,
            'avg_cost_basis': position.avg_cost_basis,
            'total_cost': position.total_cost,
            'opened_at': position.opened_at,
            'closed_at': position.closed_at,
            'realized_pnl': position.realized_pnl
        }

        # Use PostgreSQL UPSERT
        stmt = insert(Position).values(**position_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=['user_id', 'symbol', 'instrument_type', 'option_details'],
            set_=dict(
                current_qty=stmt.excluded.current_qty,
                avg_cost_basis=stmt.excluded.avg_cost_basis,
                total_cost=stmt.excluded.total_cost,
                updated_at=stmt.excluded.updated_at,
                closed_at=stmt.excluded.closed_at,
                realized_pnl=stmt.excluded.realized_pnl
            )
        )

        session.execute(stmt)
        session.commit()

    def _handle_position_open(self, position: Position, trade: Trade) -> None:
        """Handle position opening with average cost basis calculation."""
        if not trade.net_price or not trade.qty:
            logger.warning(f"Missing price or quantity for trade {trade.trade_id}")
            return

        trade_qty = trade.qty
        trade_cost = Decimal(str(trade.net_price)) * abs(trade_qty)

        # Determine direction based on side
        if trade.side == "SELL":
            trade_qty = -trade_qty  # Short position

        # Calculate new average cost basis
        if position.current_qty == 0:
            # New position
            position.current_qty = trade_qty
            position.total_cost = trade_cost
            position.avg_cost_basis = Decimal(str(trade.net_price))
            if not position.opened_at:
                position.opened_at = trade.exec_timestamp
        else:
            # Add to existing position
            old_total_cost = position.total_cost
            new_qty = position.current_qty + trade_qty
            new_total_cost = old_total_cost + trade_cost

            if new_qty != 0:
                position.avg_cost_basis = new_total_cost / abs(new_qty)
                position.current_qty = new_qty
                position.total_cost = new_total_cost
            else:
                # Position closed to zero
                position.current_qty = 0
                position.avg_cost_basis = Decimal('0')
                position.total_cost = Decimal('0')
                position.closed_at = trade.exec_timestamp

        position.updated_at = trade.exec_timestamp or datetime.now()

    def _handle_position_close(self, position: Position, trade: Trade) -> None:
        """Handle position closing with P&L calculation."""
        if not trade.net_price or not trade.qty or position.current_qty == 0:
            logger.warning(f"Cannot close position - missing data or zero position for {trade.symbol}")
            return

        # Determine shares being closed
        shares_closed = abs(trade.qty)
        if trade.side == "BUY":
            # Closing short position
            if position.current_qty >= 0:
                logger.warning(f"Trying to buy to close a long position for {trade.symbol}")
                return
            close_direction = 1  # Buying back short
        else:
            # Closing long position
            if position.current_qty <= 0:
                logger.warning(f"Trying to sell to close a short position for {trade.symbol}")
                return
            close_direction = -1  # Selling long

        # Don't close more than we have
        shares_closed = min(shares_closed, abs(position.current_qty))

        # Calculate P&L using average cost basis
        cost_basis_per_share = position.avg_cost_basis
        cost_basis = cost_basis_per_share * shares_closed
        proceeds = Decimal(str(trade.net_price)) * shares_closed

        if position.current_qty > 0:  # Long position
            realized_pnl = proceeds - cost_basis
        else:  # Short position
            realized_pnl = cost_basis - proceeds

        # Update trade with realized P&L
        trade.realized_pnl = float(realized_pnl)

        # Update position
        remaining_shares = abs(position.current_qty) - shares_closed
        if remaining_shares > 0:
            # Partial close
            position.current_qty = remaining_shares * (1 if position.current_qty > 0 else -1)
            position.total_cost = cost_basis_per_share * remaining_shares
            # avg_cost_basis stays the same
        else:
            # Full close
            position.current_qty = 0
            position.total_cost = Decimal('0')
            position.avg_cost_basis = Decimal('0')
            position.closed_at = trade.exec_timestamp

        # Add to realized P&L
        position.realized_pnl += realized_pnl
        position.updated_at = trade.exec_timestamp or datetime.now()

        logger.info(f"Realized P&L for {trade.symbol}: ${realized_pnl}")

    def get_open_positions(self, session: Session) -> List[Position]:
        """Get all open positions."""
        return session.query(Position).filter(
            and_(
                Position.current_qty != 0,
                Position.closed_at.is_(None)
            )
        ).all()

    def get_position_summary(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get position summary."""
        with self.db_manager.get_session() as session:
            query = session.query(Position)

            if symbol:
                query = query.filter(Position.symbol == symbol)

            positions = query.all()

            open_positions = [p for p in positions if p.current_qty != 0]
            closed_positions = [p for p in positions if p.current_qty == 0 and p.closed_at]

            total_realized_pnl = sum(p.realized_pnl for p in positions)
            total_open_value = sum(
                p.current_qty * p.avg_cost_basis for p in open_positions
            )

            return {
                "open_positions": len(open_positions),
                "closed_positions": len(closed_positions),
                "total_realized_pnl": float(total_realized_pnl),
                "total_open_value": float(total_open_value),
                "positions": [
                    {
                        "symbol": p.symbol,
                        "instrument_type": p.instrument_type,
                        "current_qty": p.current_qty,
                        "avg_cost_basis": float(p.avg_cost_basis),
                        "realized_pnl": float(p.realized_pnl),
                        "market_value": float(p.current_qty * p.avg_cost_basis),
                        "is_open": p.current_qty != 0
                    }
                    for p in positions
                ]
            }

    def reprocess_all_positions(self) -> Dict[str, Any]:
        """Reprocess all positions from scratch based on trade history."""
        with self.db_manager.get_session() as session:
            # Clear existing positions
            session.query(Position).delete()

            # Get all fill trades in chronological order
            trades = session.query(Trade).filter(
                Trade.event_type == 'fill'
            ).order_by(Trade.exec_timestamp).all()

            processed_count = 0
            for trade in trades:
                if trade.symbol and trade.net_price and trade.qty:
                    self.update_positions_from_trade(trade)
                    processed_count += 1

            session.commit()

            return {
                "trades_processed": processed_count,
                "message": f"Reprocessed {processed_count} trades"
            }