"""Pydantic schemas for NDJSON validation."""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field, validator


class OptionDetails(BaseModel):
    """Option details nested object."""
    exp_date: date
    strike: float
    right: str  # CALL or PUT


class NdjsonRecord(BaseModel):
    """Schema for NDJSON records from Schwab converter."""

    # Required fields
    section: str
    row_index: int
    raw: str
    issues: List[str] = Field(default_factory=list)

    # Event details
    exec_time: Optional[datetime] = None
    time_canceled: Optional[datetime] = None
    time_placed: Optional[datetime] = None

    # Trade details
    side: Optional[str] = None
    qty: Optional[int] = None
    pos_effect: Optional[str] = None
    symbol: Optional[str] = None

    # Option details
    exp: Optional[date] = None
    strike: Optional[float] = None
    type: Optional[str] = None  # STOCK, CALL, PUT
    spread: Optional[str] = None

    # Pricing
    price: Optional[float] = None
    net_price: Optional[float] = None
    price_improvement: Optional[float] = None
    order_type: Optional[str] = None

    # Order details
    tif: Optional[str] = None  # Time in force
    status: Optional[str] = None
    notes: Optional[str] = None
    mark: Optional[str] = None

    # Converter-added fields
    event_type: Optional[str] = None  # fill, cancel, amend
    asset_type: Optional[str] = None  # STOCK, OPTION
    option: Optional[OptionDetails] = None

    # Source tracking
    source_file: Optional[str] = None
    source_file_index: Optional[int] = None

    # Amendment details (for amendment records)
    amendment: Optional[Dict[str, Any]] = None

    @validator('side')
    def validate_side(cls, v):
        if v is not None and v not in ['BUY', 'SELL']:
            raise ValueError('side must be BUY or SELL')
        return v

    @validator('pos_effect')
    def validate_pos_effect(cls, v):
        if v is not None and v not in ['TO OPEN', 'TO CLOSE']:
            raise ValueError('pos_effect must be TO OPEN or TO CLOSE')
        return v

    @validator('event_type')
    def validate_event_type(cls, v):
        if v is not None and v not in ['fill', 'cancel', 'amend']:
            raise ValueError('event_type must be fill, cancel, or amend')
        return v

    @validator('asset_type')
    def validate_asset_type(cls, v):
        if v is not None and v not in ['STOCK', 'OPTION']:
            raise ValueError('asset_type must be STOCK or OPTION')
        return v

    @property
    def is_fill(self) -> bool:
        """Check if this is a fill record."""
        return self.event_type == 'fill' and self.exec_time is not None

    @property
    def is_equity(self) -> bool:
        """Check if this is an equity trade."""
        return self.asset_type == 'STOCK' or self.type == 'STOCK'

    @property
    def is_option(self) -> bool:
        """Check if this is an option trade."""
        return self.asset_type == 'OPTION' or self.type in ['CALL', 'PUT']

    @property
    def is_section_header(self) -> bool:
        """Check if this is a section header row."""
        return 'section_header' in self.issues

    @property
    def unique_key(self) -> str:
        """Generate unique key for upsert logic."""
        # Use source file, row index, and key trade details
        base_key = f"{self.source_file}:{self.row_index}"

        if self.exec_time:
            base_key += f":{self.exec_time.isoformat()}"
        elif self.time_canceled:
            base_key += f":{self.time_canceled.isoformat()}"

        if self.symbol:
            base_key += f":{self.symbol}"

        if self.side and self.qty:
            base_key += f":{self.side}:{self.qty}"

        return base_key