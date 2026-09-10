import uuid
from decimal import Decimal
import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, ConfigDict

from src.common.enums import OperationType
from src.operations.schemas import OperationDateValidator
from src.categories.user_categories.schemas import UserCategoryRead
from src.operations.schemas import OperationRead

if TYPE_CHECKING:
    from src.operations.models import Operation


@dataclass
class ChainMetadata():
    total_amount: Decimal
    operations: list["Operation"]
    operations_count: int
    suggested_type: OperationType | None


class ChainCreate(BaseModel, OperationDateValidator):
    operation_ids: list[uuid.UUID] = Field(description="Список ID операций")
    category_id: uuid.UUID | None = Field(None, description="ID категории")
    date: dt.date | None = Field(
        default_factory=dt.date.today,
        description="Дата цепочки"
    )
    description: str | None = Field(None, description="Необязательное описание")


class ChainShortRead(BaseModel):
    id: uuid.UUID
    amount: Decimal
    category: UserCategoryRead | None =Field(None)
    ignore: bool
    date: dt.date
    description: str | None = Field(None)
    operations_count: int

    model_config = ConfigDict(from_attributes=True)


class ChainDetailRead(ChainShortRead):
    operations: list[OperationRead]


class ChainUpdate(BaseModel, OperationDateValidator):
    description: str | None = Field(None, description="Необязательное описание")
    operation_ids: list[uuid.UUID] | None = Field(None, description="Операции в цепочке")
    category_id: uuid.UUID | None = Field(None, description="ID категории")
    date: dt.date | None = Field(None, description="Дата цепочки")
    ignore: bool | None = Field(None, description="Скрытие цепочки")
