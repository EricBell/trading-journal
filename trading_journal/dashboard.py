"""Dashboard metrics and analytics engine."""

import logging
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal

from sqlalchemy import and_, func, case
from sqlalchemy.orm import Session

from .database import db_manager
from .models import CompletedTrade, Position
from .authorization import AuthContext

logger = logging.getLogger(__name__)


class DashboardEngine:
    """Generates comprehensive dashboard metrics and analytics."""

    def __init__(self):
        self.db_manager = db_manager

    def generate_dashboard(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate complete dashboard metrics.

        Args:
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            symbol: Optional symbol filter

        Returns:
            Dictionary with all dashboard metrics
        """
        user_id = AuthContext.require_user().user_id

        with self.db_manager.get_session() as session:
            # Build base query for completed trades
            query = session.query(CompletedTrade).filter(
                CompletedTrade.user_id == user_id
            )

            # Apply date filters
            if start_date:
                query = query.filter(CompletedTrade.closed_at >= start_date)
            if end_date:
                # Include the entire end date (through end of day)
                query = query.filter(CompletedTrade.closed_at < datetime.combine(
                    end_date, datetime.max.time()
                ))
            if symbol:
                query = query.filter(CompletedTrade.symbol == symbol)

            trades = query.order_by(CompletedTrade.closed_at).all()

            if not trades:
                return {
                    "period": {
                        "start_date": start_date.isoformat() if start_date else None,
                        "end_date": end_date.isoformat() if end_date else None,
                        "symbol": symbol
                    },
                    "message": "No completed trades found for the specified period"
                }

            # Calculate all metrics
            core_metrics = self._calculate_core_metrics(trades)
            pattern_metrics = self._calculate_pattern_metrics(trades)
            equity_curve = self._calculate_equity_curve(trades)
            max_drawdown = self._calculate_max_drawdown(equity_curve)
            position_summary = self._get_position_summary(session, user_id)

            return {
                "period": {
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None,
                    "symbol": symbol,
                    "first_trade": trades[0].closed_at.isoformat() if trades else None,
                    "last_trade": trades[-1].closed_at.isoformat() if trades else None
                },
                "core_metrics": core_metrics,
                "pattern_analysis": pattern_metrics,
                "equity_curve": equity_curve,
                "max_drawdown": max_drawdown,
                "positions": position_summary
            }

    def _calculate_core_metrics(self, trades: List[CompletedTrade]) -> Dict[str, Any]:
        """Calculate core performance metrics."""
        if not trades:
            return {}

        total_trades = len(trades)
        winning_trades = [t for t in trades if t.is_winning_trade]
        losing_trades = [t for t in trades if not t.is_winning_trade]

        winning_count = len(winning_trades)
        losing_count = len(losing_trades)

        # Calculate P&L
        total_pnl = sum(t.net_pnl for t in trades if t.net_pnl)
        winning_pnl = sum(t.net_pnl for t in winning_trades if t.net_pnl)
        losing_pnl = sum(t.net_pnl for t in losing_trades if t.net_pnl)

        # Calculate averages
        avg_win = winning_pnl / winning_count if winning_count > 0 else Decimal('0')
        avg_loss = losing_pnl / losing_count if losing_count > 0 else Decimal('0')

        # Win rate
        win_rate = (winning_count / total_trades * 100) if total_trades > 0 else 0

        # Profit factor
        profit_factor = abs(winning_pnl / losing_pnl) if losing_pnl != 0 else float('inf')

        # Average trade
        avg_trade = total_pnl / total_trades if total_trades > 0 else Decimal('0')

        # Largest win/loss
        largest_win = max((t.net_pnl for t in trades if t.net_pnl), default=Decimal('0'))
        largest_loss = min((t.net_pnl for t in trades if t.net_pnl), default=Decimal('0'))

        # Calculate consecutive streaks
        max_win_streak, max_loss_streak = self._calculate_streaks(trades)

        return {
            "total_trades": total_trades,
            "winning_trades": winning_count,
            "losing_trades": losing_count,
            "win_rate_pct": float(win_rate),
            "total_pnl": float(total_pnl),
            "total_winning_pnl": float(winning_pnl),
            "total_losing_pnl": float(losing_pnl),
            "average_win": float(avg_win),
            "average_loss": float(avg_loss),
            "average_trade": float(avg_trade),
            "largest_win": float(largest_win),
            "largest_loss": float(largest_loss),
            "profit_factor": float(profit_factor) if profit_factor != float('inf') else None,
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak
        }

    def _calculate_pattern_metrics(self, trades: List[CompletedTrade]) -> Dict[str, Any]:
        """Calculate metrics by setup pattern."""
        pattern_stats = {}

        # Group trades by pattern
        for trade in trades:
            pattern = trade.setup_pattern or "No Pattern"

            if pattern not in pattern_stats:
                pattern_stats[pattern] = {
                    "trades": [],
                    "total_pnl": Decimal('0'),
                    "winning_count": 0,
                    "losing_count": 0
                }

            stats = pattern_stats[pattern]
            stats["trades"].append(trade)
            stats["total_pnl"] += trade.net_pnl if trade.net_pnl else Decimal('0')

            if trade.is_winning_trade:
                stats["winning_count"] += 1
            else:
                stats["losing_count"] += 1

        # Calculate metrics for each pattern
        pattern_results = []
        for pattern, stats in pattern_stats.items():
            total_trades = len(stats["trades"])
            win_rate = (stats["winning_count"] / total_trades * 100) if total_trades > 0 else 0

            pattern_results.append({
                "pattern": pattern,
                "total_trades": total_trades,
                "winning_trades": stats["winning_count"],
                "losing_trades": stats["losing_count"],
                "win_rate_pct": float(win_rate),
                "total_pnl": float(stats["total_pnl"]),
                "avg_pnl": float(stats["total_pnl"] / total_trades) if total_trades > 0 else 0.0
            })

        # Sort by total P&L (best performing first)
        pattern_results.sort(key=lambda x: x["total_pnl"], reverse=True)

        return {
            "by_pattern": pattern_results,
            "top_pattern": pattern_results[0] if pattern_results else None,
            "worst_pattern": pattern_results[-1] if pattern_results else None
        }

    def _calculate_equity_curve(self, trades: List[CompletedTrade]) -> List[Dict[str, Any]]:
        """Calculate equity curve showing cumulative P&L over time."""
        curve = []
        cumulative_pnl = Decimal('0')

        for trade in trades:
            cumulative_pnl += trade.net_pnl if trade.net_pnl else Decimal('0')
            curve.append({
                "timestamp": trade.closed_at.isoformat() if trade.closed_at else None,
                "trade_id": trade.completed_trade_id,
                "symbol": trade.symbol,
                "trade_pnl": float(trade.net_pnl) if trade.net_pnl else 0.0,
                "cumulative_pnl": float(cumulative_pnl)
            })

        return curve

    def _calculate_max_drawdown(self, equity_curve: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate maximum drawdown from equity curve."""
        if not equity_curve:
            return {
                "max_drawdown": 0.0,
                "max_drawdown_pct": 0.0,
                "peak_value": 0.0,
                "trough_value": 0.0,
                "peak_date": None,
                "trough_date": None
            }

        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        peak_value = 0.0
        trough_value = 0.0
        peak_date = None
        trough_date = None

        current_peak = 0.0
        current_peak_date = None

        for point in equity_curve:
            value = point["cumulative_pnl"]

            # Update peak
            if value > current_peak:
                current_peak = value
                current_peak_date = point["timestamp"]

            # Calculate drawdown from current peak
            if current_peak > 0:
                drawdown = current_peak - value
                drawdown_pct = (drawdown / current_peak) * 100

                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    max_drawdown_pct = drawdown_pct
                    peak_value = current_peak
                    trough_value = value
                    peak_date = current_peak_date
                    trough_date = point["timestamp"]

        return {
            "max_drawdown": float(max_drawdown),
            "max_drawdown_pct": float(max_drawdown_pct),
            "peak_value": float(peak_value),
            "trough_value": float(trough_value),
            "peak_date": peak_date,
            "trough_date": trough_date
        }

    def _calculate_streaks(self, trades: List[CompletedTrade]) -> Tuple[int, int]:
        """Calculate maximum consecutive winning and losing streaks."""
        max_win_streak = 0
        max_loss_streak = 0
        current_win_streak = 0
        current_loss_streak = 0

        for trade in trades:
            if trade.is_winning_trade:
                current_win_streak += 1
                current_loss_streak = 0
                max_win_streak = max(max_win_streak, current_win_streak)
            else:
                current_loss_streak += 1
                current_win_streak = 0
                max_loss_streak = max(max_loss_streak, current_loss_streak)

        return max_win_streak, max_loss_streak

    def _get_position_summary(self, session: Session, user_id: int) -> Dict[str, Any]:
        """Get summary of current positions."""
        open_positions = session.query(Position).filter(
            and_(
                Position.user_id == user_id,
                Position.closed_at.is_(None),
                Position.current_qty != 0
            )
        ).all()

        closed_positions = session.query(Position).filter(
            and_(
                Position.user_id == user_id,
                Position.closed_at.isnot(None)
            )
        ).all()

        total_open_value = sum(
            abs(p.current_qty * p.avg_cost_basis) for p in open_positions
            if p.avg_cost_basis
        )

        total_realized_pnl = sum(
            p.realized_pnl for p in (open_positions + closed_positions)
            if p.realized_pnl
        )

        return {
            "open_positions": len(open_positions),
            "closed_positions": len(closed_positions),
            "total_open_value": float(total_open_value),
            "total_realized_pnl": float(total_realized_pnl)
        }

    def parse_date_range(self, date_range_str: Optional[str]) -> Tuple[Optional[date], Optional[date]]:
        """
        Parse date range string in format 'YYYY-MM-DD,YYYY-MM-DD'.

        Args:
            date_range_str: Date range string or None

        Returns:
            Tuple of (start_date, end_date), either or both can be None
        """
        if not date_range_str:
            return None, None

        parts = date_range_str.split(',')
        if len(parts) != 2:
            raise ValueError(
                "Date range must be in format 'YYYY-MM-DD,YYYY-MM-DD'"
            )

        start_str, end_str = parts
        start_date = datetime.strptime(start_str.strip(), '%Y-%m-%d').date() if start_str.strip() else None
        end_date = datetime.strptime(end_str.strip(), '%Y-%m-%d').date() if end_str.strip() else None

        return start_date, end_date
