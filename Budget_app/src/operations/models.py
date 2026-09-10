from decimal import Decimal
import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy import String, ForeignKey, Numeric, func, Index

from src.database.base import Base

if TYPE_CHECKING:
    from src.categories.user_categories.models import UserCategory
    from src.accounts.models import Account

class Operation(Base):
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2))
    date: Mapped[dt.date] = mapped_column(server_default=func.current_date())
    description: Mapped[str|None] = mapped_column(String(255), nullable=True)
    ignore: Mapped[bool] = mapped_column(server_default="false")

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE")
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_categories.id", ondelete="CASCADE")
    )
    related_operation_id: Mapped[uuid.UUID|None] = mapped_column(
        ForeignKey("operations.id", ondelete="SET NULL"),
        nullable=True
    )
    chain_id: Mapped[uuid.UUID|None] = mapped_column(
        ForeignKey("chains.id", ondelete="SET NULL"),
        nullable=True
    )
    
    category: Mapped["UserCategory"] = relationship(
        back_populates="operations"
    )
    account: Mapped["Account"] = relationship(
        back_populates="operations"
    )

    __table_args__ = (
        Index("idx_user_date", "user_id", "date"),
        Index("idx_account_date", "account_id", "date"),
        Index("idx_category_date", "category_id", "date")
    )
