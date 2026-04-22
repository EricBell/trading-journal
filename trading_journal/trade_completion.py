"""Trade completion engine - groups executions into completed round-trip trades."""

import logging
from collections import defaultdict
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, text

from .database import db_manager
from .models import Trade, CompletedTrade, TradeAnnotation
from .authorization import AuthContext
from .positions import get_contract_multiplier

logger = logging.getLogger(__name__)


class TradeCompletionEngine:
    """Groups individual executions into completed round-trip trades."""

    def __init__(self):
        self.db_manager = db_manager

    def reprocess_all_completed_trades(self, user_id: int) -> Dict[str, Any]:
        """Clear and rebuild all completed trades for a user from scratch."""
        with self.db_manager.get_session() as session:
            # Unlink all executions from their completed trades
            session.query(Trade).filter(Trade.user_id == user_id).update(
                {Trade.completed_trade_id: None}, synchronize_session=False
            )
            # Delete all completed trades for this user
            session.query(CompletedTrade).filter(
                CompletedTrade.user_id == user_id
            ).delete(synchronize_session=False)
            session.commit()

        # Now process from scratch (all trades are unlinked)
        with self.db_manager.get_session() as session:
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
            unlinked_trades = query.order_by(Trade.exec_timestamp).all()

            # Spreads (multi-leg orders) are processed as single CompletedTrades;
            # non-spread fills use the existing per-instrument-key grouping.
            spread_trades = [t for t in unlinked_trades if t.spread_order_tag]
            non_spread_trades = [t for t in unlinked_trades if not t.spread_order_tag]

            trade_groups: Dict[Any, List[Trade]] = {}
            for trade in non_spread_trades:
                key = (trade.symbol, trade.instrument_type, trade.account_id)
                if trade.instrument_type == 'OPTION' and trade.option_data:
                    key = key + (trade.exp_date, trade.strike_price, trade.option_type)
                elif trade.instrument_type == 'FUTURES':
                    key = key + (trade.exp_date,)
                trade_groups.setdefault(key, []).append(trade)

            completed_count = 0
            for trades in trade_groups.values():
                completed_count += self._process_trade_group(session, trades)

            completed_count += self._process_spread_trades(session, spread_trades)

            session.commit()

        # Re-link any annotations that were orphaned by the completed_trades rebuild.
        # The natural key (user_id, symbol, opened_at) ties each annotation back to
        # its newly-created completed_trade row so they are never left with a NULL FK.
        with self.db_manager.get_session() as session:
            session.execute(
                text("""
                    UPDATE trade_annotations ta
                    SET completed_trade_id = ct.completed_trade_id
                    FROM completed_trades ct
                    WHERE ta.user_id   = :user_id
                      AND ta.completed_trade_id IS NULL
                      AND ct.user_id   = :user_id
                      AND ta.symbol    = ct.symbol
                      AND ta.opened_at = ct.opened_at
                """),
                {"user_id": user_id},
            )
            session.commit()

        return {
            "completed_trades": completed_count,
            "message": f"Reprocessed {completed_count} completed trades"
        }

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

            spread_trades = [t for t in unlinked_trades if t.spread_order_tag]
            non_spread_trades = [t for t in unlinked_trades if not t.spread_order_tag]

            trade_groups: Dict[Any, List[Trade]] = {}
            for trade in non_spread_trades:
                key = (trade.symbol, trade.instrument_type, trade.account_id)
                if trade.instrument_type == 'OPTION' and trade.option_data:
                    key = key + (trade.exp_date, trade.strike_price, trade.option_type)
                elif trade.instrument_type == 'FUTURES':
                    key = key + (trade.exp_date,)
                trade_groups.setdefault(key, []).append(trade)

            completed_count = 0
            for trades in trade_groups.values():
                completed_count += self._process_trade_group(session, trades)

            completed_count += self._process_spread_trades(session, spread_trades)

            session.commit()

            return {
                "completed_trades": completed_count,
                "message": f"Processed {completed_count} completed trades"
            }

    def _process_spread_trades(self, session: Session, spread_trades: List[Trade]) -> int:
        """Process multi-leg spread executions into single CompletedTrades (one per spread)."""
        if not spread_trades:
            return 0

        # Group executions by their order tag (all legs of one multi-leg order share a tag)
        by_tag: Dict[str, List[Trade]] = defaultdict(list)
        for t in spread_trades:
            by_tag[t.spread_order_tag].append(t)

        # Classify each tag group: all TO OPEN → open order; all TO CLOSE → close order
        open_groups: List[List[Trade]] = []
        close_groups: List[List[Trade]] = []
        for tag, legs in by_tag.items():
            effects = {l.pos_effect for l in legs}
            if effects == {'TO OPEN'}:
                open_groups.append(legs)
            elif effects == {'TO CLOSE'}:
                close_groups.append(legs)
            else:
                logger.warning(f"Skipping spread order {tag}: mixed pos_effect {effects}")

        def _identity(legs: List[Trade]) -> Tuple:
            """Key that identifies which open order matches which close order."""
            l = legs[0]
            return (l.symbol, l.instrument_type, l.account_id, l.exp_date,
                    frozenset(l.strike_price for l in legs))

        def _min_ts(legs: List[Trade]) -> datetime:
            return min((l.exec_timestamp for l in legs if l.exec_timestamp), default=datetime.min)

        # Group and sort by identity key so FIFO matching works correctly
        opens_by_key: Dict[Tuple, List[List[Trade]]] = defaultdict(list)
        closes_by_key: Dict[Tuple, List[List[Trade]]] = defaultdict(list)
        for legs in open_groups:
            opens_by_key[_identity(legs)].append(legs)
        for legs in close_groups:
            closes_by_key[_identity(legs)].append(legs)
        for v in opens_by_key.values():
            v.sort(key=_min_ts)
        for v in closes_by_key.values():
            v.sort(key=_min_ts)

        completed_count = 0
        for key in set(opens_by_key) & set(closes_by_key):
            for open_legs, close_legs in zip(opens_by_key[key], closes_by_key[key]):
                self._create_spread_completed_trade(session, open_legs, close_legs)
                completed_count += 1

        return completed_count

    def _create_spread_completed_trade(
        self, session: Session, open_legs: List[Trade], close_legs: List[Trade]
    ) -> Optional[CompletedTrade]:
        """Create one CompletedTrade representing a complete multi-leg spread round-trip."""
        if not open_legs or not close_legs:
            return None

        first_leg = open_legs[0]
        multiplier = get_contract_multiplier(first_leg.instrument_type, first_leg.symbol or '')
        total_qty = abs(open_legs[0].qty) if open_legs[0].qty else 1

        # Net debit paid to open: BUY costs (+), SELL credits (-)
        net_debit = sum(
            Decimal(str(l.net_price)) * (1 if l.side == 'BUY' else -1) * abs(l.qty)
            for l in open_legs
        )
        # Net credit received to close: SELL credits (+), BUY costs (-)
        net_credit = sum(
            Decimal(str(l.net_price)) * (1 if l.side == 'SELL' else -1) * abs(l.qty)
            for l in close_legs
        )

        gross_cost = net_debit * multiplier
        gross_proceeds = net_credit * multiplier
        net_pnl = gross_proceeds - gross_cost

        entry_avg_price = gross_cost / total_qty if total_qty else Decimal('0')
        exit_avg_price = gross_proceeds / total_qty if total_qty else Decimal('0')

        opened_at = min(l.exec_timestamp for l in open_legs if l.exec_timestamp)
        closed_at = max(l.exec_timestamp for l in close_legs if l.exec_timestamp)
        hold_duration = closed_at - opened_at if opened_at and closed_at else None

        # Direction: the long (BUY) leg drives trade_type
        long_legs = [l for l in open_legs if l.side == 'BUY']
        if long_legs:
            trade_type = 'SHORT' if long_legs[0].option_type == 'PUT' else 'LONG'
        else:
            short_leg = next((l for l in open_legs if l.side == 'SELL'), first_leg)
            trade_type = 'LONG' if short_leg.option_type == 'PUT' else 'SHORT'

        # Multi-leg option_details: legs sorted highest-strike first
        sorted_legs = sorted(open_legs, key=lambda l: float(l.strike_price or 0), reverse=True)
        option_details = {
            'spread_type': first_leg.spread_type or 'VERTICAL',
            'exp_date': first_leg.exp_date.isoformat() if first_leg.exp_date else None,
            'legs': [
                {'strike': float(l.strike_price), 'right': l.option_type, 'side': l.side}
                for l in sorted_legs
            ],
        }

        completed_trade = CompletedTrade(
            user_id=first_leg.user_id,
            account_id=first_leg.account_id,
            symbol=first_leg.symbol,
            instrument_type=first_leg.instrument_type,
            option_details=option_details,
            total_qty=total_qty,
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
        session.flush()

        for leg in open_legs + close_legs:
            leg.completed_trade_id = completed_trade.completed_trade_id

        logger.info(
            f"Created spread: {completed_trade.symbol} {trade_type} {total_qty}x "
            f"@ {float(entry_avg_price):.2f} -> {float(exit_avg_price):.2f} "
            f"P&L: ${float(net_pnl):.2f}"
        )
        return completed_trade

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

            # Sign the qty based on side and pos_effect
            # TO OPEN: BUY = positive, SELL = negative (short)
            # TO CLOSE: BUY = negative (closing long), SELL = positive (closing short)
            # AUTO: infer from context — if position is flat, treat as TO OPEN; otherwise TO CLOSE
            if trade.pos_effect == 'TO OPEN':
                signed_qty = trade.qty if trade.side == 'BUY' else -trade.qty
            elif trade.pos_effect == 'TO CLOSE':
                signed_qty = -trade.qty if trade.side == 'SELL' else trade.qty
            else:  # AUTO
                if current_position == 0:
                    signed_qty = trade.qty if trade.side == 'BUY' else -trade.qty
                else:
                    signed_qty = -trade.qty if trade.side == 'SELL' else trade.qty

            current_position += signed_qty

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

        # Classify AUTO trades by their position in the cycle:
        # first AUTO trade(s) when position is flat = open, remaining = close
        position = 0
        auto_opens = set()
        auto_closes = set()
        for t in cycle_trades:
            if t.pos_effect == 'AUTO':
                if position == 0:
                    auto_opens.add(t.trade_id)
                    signed = t.qty if t.side == 'BUY' else -t.qty
                else:
                    auto_closes.add(t.trade_id)
                    signed = -t.qty if t.side == 'SELL' else t.qty
            elif t.pos_effect == 'TO OPEN':
                signed = t.qty if t.side == 'BUY' else -t.qty
            else:
                signed = -t.qty if t.side == 'SELL' else t.qty
            position += signed

        opens = [t for t in cycle_trades if t.pos_effect == 'TO OPEN' or t.trade_id in auto_opens]
        closes = [t for t in cycle_trades if t.pos_effect == 'TO CLOSE' or t.trade_id in auto_closes]

        if not opens or not closes:
            logger.warning(f"Trade cycle for {cycle_trades[0].symbol} is incomplete, skipping.")
            return

        # Get contract multiplier (100 for options, $N/point for futures, 1 for equity)
        first_trade = cycle_trades[0]
        multiplier = get_contract_multiplier(first_trade.instrument_type, first_trade.symbol or '')

        total_open_qty = sum(abs(t.qty) for t in opens)
        total_close_qty = sum(abs(t.qty) for t in closes)

        if first_trade.instrument_type == 'FUTURES':
            # For futures: store raw point prices (not dollar notional) so the UI shows
            # recognisable index levels (e.g. 6590.50) rather than contract notional.
            # The multiplier is applied only when calculating gross_cost/proceeds and P&L.
            entry_avg_price = (
                sum(Decimal(str(t.net_price)) * abs(t.qty) for t in opens) / total_open_qty
                if total_open_qty else Decimal(0)
            )
            exit_avg_price = (
                sum(Decimal(str(t.net_price)) * abs(t.qty) for t in closes) / total_close_qty
                if total_close_qty else Decimal(0)
            )
            gross_cost = entry_avg_price * total_open_qty * multiplier
            gross_proceeds = exit_avg_price * total_close_qty * multiplier
        else:
            # EQUITY / OPTION: existing behaviour — entry_avg_price absorbs the multiplier
            # (options show per-contract dollar cost, equities show per-share price)
            total_open_cost = sum(Decimal(str(t.net_price)) * abs(t.qty) * multiplier for t in opens)
            entry_avg_price = total_open_cost / total_open_qty if total_open_qty else Decimal(0)
            total_close_proceeds = sum(Decimal(str(t.net_price)) * abs(t.qty) * multiplier for t in closes)
            exit_avg_price = total_close_proceeds / total_close_qty if total_close_qty else Decimal(0)
            gross_cost = total_open_cost
            gross_proceeds = total_close_proceeds

        # Determine trade type (LONG/SHORT) from the first opening trade.
        # For options, the right (CALL/PUT) determines direction:
        #   BUY CALL = LONG, BUY PUT = SHORT, SELL CALL = SHORT, SELL PUT = LONG
        # For equities and futures, side alone determines: BUY = LONG, SELL = SHORT.
        first_open = opens[0]
        if first_open.side == "BUY":
            net_pnl = gross_proceeds - gross_cost
        else:
            net_pnl = gross_cost - gross_proceeds  # For shorts, P&L is cost - proceeds

        if first_open.instrument_type == "OPTION" and first_open.option_type == "PUT":
            trade_type = "SHORT" if first_open.side == "BUY" else "LONG"
        else:
            trade_type = "LONG" if first_open.side == "BUY" else "SHORT"
            
        # Timestamps and duration
        opened_at = min(t.exec_timestamp for t in opens if t.exec_timestamp)
        closed_at = max(t.exec_timestamp for t in closes if t.exec_timestamp)
        hold_duration = closed_at - opened_at if opened_at and closed_at else None

        # Build option_details for completed_trade:
        # - OPTION: copy from the execution's option_data JSONB
        # - FUTURES: store contract expiry so the UI can display the contract month
        # - EQUITY: None
        if first_open.instrument_type == 'FUTURES':
            ct_option_details = (
                {"exp_date": first_open.exp_date.isoformat()}
                if first_open.exp_date else None
            )
        else:
            ct_option_details = first_open.option_data

        # Compute spread_group_id: sorted unique spread_order_tags from all cycle executions.
        # Both legs of the same multi-leg order will share identical tags → identical group_id.
        tags = sorted({t.spread_order_tag for t in cycle_trades if t.spread_order_tag})
        spread_group_id = ",".join(tags) if tags else None

        # Create the single CompletedTrade object
        completed_trade = CompletedTrade(
            user_id=first_open.user_id,
            account_id=first_open.account_id,
            symbol=first_open.symbol,
            instrument_type=first_open.instrument_type,
            option_details=ct_option_details,
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
            spread_group_id=spread_group_id,
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

    def get_completed_trades_summary(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Get summary of completed trades with optional filtering."""
        user_id = AuthContext.require_user().user_id

        with self.db_manager.get_session() as session:
            query = session.query(CompletedTrade).filter(
                CompletedTrade.user_id == user_id
            )

            if symbol:
                query = query.filter(CompletedTrade.symbol == symbol)

            # Apply date filters
            if start_date:
                query = query.filter(CompletedTrade.closed_at >= start_date)
            if end_date:
                # Include the entire end date (through end of day)
                query = query.filter(CompletedTrade.closed_at < datetime.combine(
                    end_date, datetime.max.time()
                ))

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
                        "instrument_type": t.instrument_type,
                        "symbol": t.symbol,
                        "type": t.trade_type,
                        "qty": t.total_qty,
                        "entry_price": t.entry_avg_price,
                        "exit_price": t.exit_avg_price,
                        "pnl": t.net_pnl,
                        "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
                        "setup_pattern": (t.trade_annotation.setup_pattern_rel.pattern_name if t.trade_annotation and t.trade_annotation.setup_pattern_rel else None),
                        "notes": (t.trade_annotation.trade_notes if t.trade_annotation else None)
                    }
                    for t in completed_trades
                ]
            }
