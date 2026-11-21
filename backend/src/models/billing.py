from datetime import datetime
from sqlalchemy import JSON, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.config.database import Base
from src.constants.enums import Receipt
from src.utils.time import now

class AdjustmentBill(Base):
    """调账单头：开出后内容锁定，重复下载结果不变。"""

    __tablename__ = 'adjustment_bills'

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_no: Mapped[str] = mapped_column(String(40), unique=True)
    posting_date: Mapped[str] = mapped_column(String(10), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('runs.id'))
    held_groups: Mapped[list] = mapped_column(JSON, default=list)
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)
    lines: Mapped[list['AdjustmentLine']] = relationship(order_by='AdjustmentLine.id',
                                                         cascade='all, delete-orphan')

class AdjustmentLine(Base):
    """调账行：同一结算日、校区和档口组最多一行等回执，回执确认后不可再改。"""

    __tablename__ = 'adjustment_lines'
    __table_args__ = (
        Index('uq_adjustment_pending_group', 'posting_date', 'zone', 'merchant_group',
              unique=True, postgresql_where=text(f"state = '{Receipt.PENDING}'"),
              sqlite_where=text(f"state = '{Receipt.PENDING}'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey('adjustment_bills.id'), index=True)
    posting_date: Mapped[str] = mapped_column(String(10))
    zone: Mapped[str] = mapped_column(String(80))
    merchant_group: Mapped[str] = mapped_column(String(80))
    expected_cents: Mapped[int]
    confirmed_before_cents: Mapped[int]
    delta_cents: Mapped[int]
    state: Mapped[str] = mapped_column(String(20), default=Receipt.PENDING, index=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(64))
    confirmed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=now)
