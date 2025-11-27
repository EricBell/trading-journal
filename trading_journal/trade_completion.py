"""Trade completion engine - groups executions into completed round-trip trades."""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from .database import db_manager
from .models import Trade, CompletedTrade
from .authorization import AuthContext

logger = logging.getLogger(__name__)


class TradeCompletionEngine:
    """Groups individual executions into completed round-trip trades."""

    def __init__(self):
        self.db_manager = db_manager

    def process_completed_trades(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Identify and process completed trades from unlinked executions."""
        user_id = AuthContext.require_user().user_id

        with self.db_manager.get_session() as session:
            # Get fill trades that aren't linked to completed trades yet
            query = session.query(Trade).filter(
                and_(
                    Trade.user_id == user_id,
                    Trade.event_type == 'fill',
                    Trade.completed_trade_id.is_(None),
                    Trade.symbol.isnot(None),
                    Trade.qty.isnot(None),
                    Trade.net_price.isnot(None)
                )
            )

            if symbol:
                query = query.filter(Trade.symbol == symbol)

            unlinked_trades = query.order_by(Trade.exec_timestamp).all()

            if not unlinked_trades:
                return {"completed_trades": 0, "message": "No unlinked trades to process"}

            # Group by symbol and instrument type
            trade_groups = {}
            for trade in unlinked_trades:
                key = (trade.symbol, trade.instrument_type)
                if trade.option_data:
                    # For options, include expiration and strike in key
                    option_key = (trade.exp_date, trade.strike_price, trade.option_type)
                    key = key + option_key

                if key not in trade_groups:
                    trade_groups[key] = []
                trade_groups[key].append(trade)

            completed_count = 0
            for group_key, trades in trade_groups.items():
                completed_count += self._process_trade_group(session, trades)

            session.commit()

            return {
                "completed_trades": completed_count,
                "message": f"Processed {completed_count} completed trades"
            }

    def _process_trade_group(self, session: Session, trades: List[Trade]) -> int:
        """Process a group of trades for the same instrument to find completed cycles."""
        if not trades:
            return 0

        trades.sort(key=lambda t: t.exec_timestamp or datetime.min)

        completed_cycles = 0
        current_position = 0
        cycle_executions: List[Trade] = []

        for trade in trades:
            # Skip trades that are already part of a completed trade
            if trade.completed_trade_id is not None:
                continue

            if not cycle_executions:
                # Start of a new potential cycle
                if trade.pos_effect == 'TO CLOSE':
                    logger.warning(f"Skipping a 'TO CLOSE' trade that appears before any 'TO OPEN': {trade.trade_id}")
                    continue
            
            cycle_executions.append(trade)
            
            # The qty is already signed, so just add it to the current position
            current_position += trade.qty

            if current_position == 0:
                # Position is closed, a cycle is complete.
                self._create_completed_trade_from_cycle(session, cycle_executions)
                completed_cycles += 1
                cycle_executions = [] # Reset for the next cycle

        return completed_cycles

    def _create_completed_trade_from_cycle(self, session: Session, cycle_trades: List[Trade]):
        """Create a single CompletedTrade from a list of executions that form a full cycle."""
        if not cycle_trades:
            return

        opens = [t for t in cycle_trades if t.pos_effect == 'TO OPEN']
        closes = [t for t in cycle_trades if t.pos_effect == 'TO CLOSE']

        if not opens or not closes:
            logger.warning(f"Trade cycle for {cycle_trades[0].symbol} is incomplete, skipping.")
            return

        # Calculate weighted average entry price from all "TO OPEN" trades
        total_open_cost = sum(Decimal(str(t.net_price)) * abs(t.qty) for t in opens)
        total_open_qty = sum(abs(t.qty) for t in opens)
        entry_avg_price = total_open_cost / total_open_qty if total_open_qty else Decimal(0)

        # Calculate weighted average exit price from all "TO CLOSE" trades
        total_close_proceeds = sum(Decimal(str(t.net_price)) * abs(t.qty) for t in closes)
        total_close_qty = sum(abs(t.qty) for t in closes)
        exit_avg_price = total_close_proceeds / total_close_qty if total_close_qty else Decimal(0)
        
        # Gross cost and proceeds
        gross_cost = total_open_cost
        gross_proceeds = total_close_proceeds

        # Determine trade type (LONG/SHORT) from the first opening trade
        first_open = opens[0]
        if first_open.side == "BUY":
            net_pnl = gross_proceeds - gross_cost
            trade_type = "LONG"
        else:
            net_pnl = gross_cost - gross_proceeds # For shorts, P&L is cost - proceeds
            trade_type = "SHORT"
            
        # Timestamps and duration
        opened_at = min(t.exec_timestamp for t in opens if t.exec_timestamp)
        closed_at = max(t.exec_timestamp for t in closes if t.exec_timestamp)
        hold_duration = closed_at - opened_at if opened_at and closed_at else None

        # Create the single CompletedTrade object
        completed_trade = CompletedTrade(
            user_id=first_open.user_id,
            symbol=first_open.symbol,
            instrument_type=first_open.instrument_type,
            option_details=first_open.option_data,
            total_qty=total_open_qty,
            entry_avg_price=float(entry_avg_price),
            exit_avg_price=float(exit_avg_price),
            gross_proceeds=float(gross_proceeds),
            gross_cost=float(gross_cost),
            net_pnl=float(net_pnl),
            opened_at=opened_at,
            closed_at=closed_at,
            hold_duration=hold_duration,
            is_winning_trade=net_pnl > 0,
            trade_type=trade_type,
        )
        
        session.add(completed_trade)
        session.flush() # To get the new completed_trade_id

        # Link all executions in the cycle to this new CompletedTrade
        for trade in cycle_trades:
            trade.completed_trade_id = completed_trade.completed_trade_id

        logger.info(
            f"Created completed trade: {completed_trade.symbol} "
            f"{trade_type} {completed_trade.total_qty} @ {entry_avg_price:.4f} -> {exit_avg_price:.4f} "
            f"P&L: ${net_pnl:.2f}"
        )
        return completed_trade

    def get_completed_trades_summary(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get summary of completed trades."""

        with self.db_manager.get_session() as session:
            query = session.query(CompletedTrade)

            if symbol:
                query = query.filter(CompletedTrade.symbol == symbol)

            completed_trades = query.all()

            if not completed_trades:
                return {"message": "No completed trades found"}

            winning_trades = [t for t in completed_trades if t.is_winning_trade]
            losing_trades = [t for t in completed_trades if not t.is_winning_trade]

            total_pnl = sum(t.net_pnl for t in completed_trades)
            win_rate = len(winning_trades) / len(completed_trades) * 100 if completed_trades else 0

            avg_win = sum(t.net_pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(t.net_pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0

            return {
                "total_trades": len(completed_trades),
                "winning_trades": len(winning_trades),
                "losing_trades": len(losing_trades),
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "average_win": avg_win,
                "average_loss": avg_loss,
                "profit_factor": abs(avg_win / avg_loss) if avg_loss != 0 else float('inf'),
                "trades": [
                    {
                        "id": t.completed_trade_id,
                        "symbol": t.symbol,
                        "type": t.trade_type,
                        "qty": t.total_qty,
                        "entry_price": t.entry_avg_price,
                        "exit_price": t.exit_avg_price,
                        "pnl": t.net_pnl,
                        "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
                        "setup_pattern": t.setup_pattern,
                        "notes": t.trade_notes
                    }
                    for t in completed_trades
                ]
            }