import uuid
from decimal import Decimal
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import joinedload

from src.core.uow import IUnitOfWork
from src.chains.repository import ChainRepository
from src.operations.repository import OperationRepository
from src.categories.user_categories.repository import UserCategoryRepository
from src.accounts.repository import AccountRepository
from src.chains.schemas import ChainMetadata, ChainCreate, ChainUpdate
from src.chains.models import Chain
from src.common.enums import OperationType
from src.operations.models import Operation
from src.chains.exceptions import (
    NotEnoughOperationsForChainError, OperationsConflictError,
    TransferNotAllowedInChainError, ChainNotFoundError
)
from src.categories.user_categories.models import UserCategory
from src.categories.user_categories.exceptions import (
    UserCategoryNotFoundError, UserCategoryTypeMismatchError
)

class ChainService:
    def __init__(self, uow: IUnitOfWork):
        self.uow = uow

    @property
    def chain_repo(self) -> ChainRepository:
        return self.uow.get_repo(ChainRepository)

    @property
    def op_repo(self) -> OperationRepository:
        return self.uow.get_repo(OperationRepository)

    @property
    def cat_repo(self) -> UserCategoryRepository:
        return self.uow.get_repo(UserCategoryRepository)

    @property
    def acc_repo(self) -> AccountRepository:
        return self.uow.get_repo(AccountRepository)

    def _suggest_type(self, amount: Decimal) -> OperationType | None:
        if amount > 0:
            return OperationType.INCOME
        if amount < 0:
            return OperationType.EXPENSE
        return None

    async def _validate_and_get_metadata(
            self,
            operation_ids: list[uuid.UUID],
            user_id: uuid.UUID,
            chain_id: uuid.UUID | None = None,
            allow_free: bool = False
    ) -> ChainMetadata:
        operations = await self.op_repo.get_operations_for_chain(
            operation_ids=operation_ids,
            user_id=user_id,
            chain_id=chain_id,
            allow_free=allow_free
        )

        operations_count = len(operations)

        if operations_count < 2:
            raise NotEnoughOperationsForChainError()

        if operations_count != len(operation_ids):
            raise OperationsConflictError()

        total_amount = sum(operation.amount for operation in operations)
        unique_types = {operation.category.type for operation in operations}

        if OperationType.TRANSFER in unique_types:
            raise TransferNotAllowedInChainError()

        return ChainMetadata(
            total_amount=total_amount,
            operations=operations,
            operations_count=operations_count,
            suggested_type=self._suggest_type(total_amount)
        )

    async def _validate_and_get_category(
        self,
        prev_category: UserCategory | None,
        new_category_id: uuid.UUID | None,
        amount: Decimal,
        user_id: uuid.UUID
    ) -> UserCategory | None:
        new_type = self._suggest_type(amount)

        if new_type is None:
            return None

        if new_category_id:
            if prev_category and prev_category.id == new_category_id:
                category = prev_category
            else:
                category = await self.cat_repo.get_one_by(
                    id=new_category_id,
                    user_id=user_id
                )
            if not category:
                raise UserCategoryNotFoundError()
            if category.type != new_type:
                raise UserCategoryTypeMismatchError(
                    message=f"Invalid category type. Expected: {new_type}"
                )
            return category

        if prev_category and prev_category.type != new_type:
            raise UserCategoryTypeMismatchError(
                message=f"Amount sign changed. Need category with type: {new_type}"
            )

        if prev_category is None:
            raise UserCategoryTypeMismatchError(
                message=f"Amount sign changed. Need category with type: {new_type}"
            )

        return prev_category

    async def create(
            self,
            create_data: ChainCreate,
            user_id: uuid.UUID
    ) -> Chain:
        if len(create_data.operation_ids) < 2:
            raise NotEnoughOperationsForChainError()

        meta = await self._validate_and_get_metadata(
            operation_ids=create_data.operation_ids,
            user_id=user_id,
            chain_id=None,
            allow_free=True
        )

        data_dict = create_data.model_dump(exclude=["operation_ids",])

        if meta.suggested_type:
            if not create_data.category_id:
                raise ValueError("Category is required for this chain sum")

            category = await self.cat_repo.get_one_by(
                id=create_data.category_id,
                user_id=user_id
            )

            if not category:
                raise UserCategoryNotFoundError()

            if category.type != meta.suggested_type:
                raise UserCategoryTypeMismatchError(
                    message=f"Required category type: {meta.suggested_type}"
                )
        else:
            data_dict["category_id"] = None

        data_dict["amount"] = meta.total_amount
        data_dict["operations_count"] = meta.operations_count

        chain = await self.chain_repo.create(data_dict, user_id)

        await self.op_repo.update_with_chain(
            create_data.operation_ids,
            chain.id,
            user_id
        )

        return await self.get_by_id(chain_id=chain.id, user_id=user_id)

    async def get_all(self, user_id: uuid.UUID) -> list[Chain]:
        return list(await self.chain_repo.get_all_by(user_id))

    async def get_by_id(
            self,
            chain_id: uuid.UUID,
            user_id: uuid.UUID
    ) -> Chain:
        chain = await self.chain_repo.get_one_by(
            id=chain_id,
            user_id=user_id
        )

        if not chain:
            raise ChainNotFoundError()

        return chain

    async def update(
            self,
            chain_id: uuid.UUID,
            update_schema: ChainUpdate,
            user_id: uuid.UUID
    ) -> Chain:
        chain = await self.get_by_id(chain_id, user_id)

        amount = chain.amount

        update_data = update_schema.model_dump(
            exclude_unset=True,
            exclude=["operation_ids", ]
        )

        operations = chain.operations
        category = chain.category
        needs_category = category is not None
        to_add_ids, to_remove_ids = [], []

        if update_schema.operation_ids is not None:
            operations_update_data = await self.get_operations_data_for_update(
                chain,
                set(update_schema.operation_ids),
                user_id
            )
            operations = operations_update_data["operations"]
            amount = operations_update_data["amount"]
            to_add_ids = operations_update_data["to_add_ids"]
            to_remove_ids = operations_update_data["to_remove_ids"]

            needs_category = amount != 0

        if needs_category:
            category_type = category.type if category else None
            if category_type != self._suggest_type(amount) and "category_id" not in update_data:
                raise UserCategoryTypeMismatchError(
                    message=f"Required category type: {self._suggest_type(amount)}"
                )
            elif "category_id" in update_data:
                new_category = await self._validate_and_get_category(
                    prev_category=chain.category,
                    new_category_id=update_data["category_id"],
                    amount=amount,
                    user_id=user_id
                )

                if category != new_category:
                    category = new_category
                    update_data["category_id"] = category.id if category else None
        else:
            category = None
            update_data["category_id"] = None

        if to_add_ids or to_remove_ids:
            update_dict = {op_id: {"chain_id": chain.id} for op_id in to_add_ids}
            to_remove_dict = {op_id: {"chain_id": None} for op_id in to_remove_ids}
            update_dict.update(to_remove_dict)
            await self.op_repo.batch_update(update_dict, user_id)

            update_data["amount"] = amount
            update_data["operations_count"] = len(operations)

        if update_data:
            updated = await self.chain_repo.update(
                model_id=chain_id,
                update_data=update_data,
                user_id=user_id
            )

            updated.category = category
            updated.operations = operations
            updated.amount = amount
            updated.operations_count = len(operations)

            return updated

        return chain

    async def delete(
            self,
            chain_id: uuid.UUID,
            cascade: bool,
            user_id: uuid.UUID
    ) -> bool:
        if cascade:
            deleted_ops = await self.op_repo.delete_chain_operations(
                chain_id=chain_id,
                user_id=user_id
            )

            if deleted_ops:
                account_deltas = defaultdict(Decimal)

                for op in deleted_ops:
                    account_deltas[op.account_id] += op.amount

                for account_id, amount in account_deltas.items():
                    await self.acc_repo.update_balance(
                        account_id=account_id,
                        delta=-amount,
                        user_id=user_id
                    )

        await self.chain_repo.delete(model_id=chain_id, user_id=user_id)
        return True

    async def get_operations_data_for_update(
        self,
        chain: Chain,
        update_operation_ids: set[uuid.UUID],
        user_id: uuid.UUID
    ) -> dict[str, Any]:
        if len(update_operation_ids) < 2:
            raise NotEnoughOperationsForChainError()

        chain_operation_ids = {op.id for op in chain.operations}

        if update_operation_ids == chain_operation_ids:
            return {
                "operations": chain.operations,
                "amount": chain.amount,
                "to_add_ids": [],
                "to_remove_ids": []
            }

        amount = chain.amount
        operations = chain.operations[:]

        operation_ids_to_add = update_operation_ids - chain_operation_ids
        operation_ids_to_remove = chain_operation_ids - update_operation_ids

        if operation_ids_to_add:
            operations_to_add: list[Operation] = await self.op_repo.get_all_by(
                user_id,
                True,
                joinedload(Operation.category),
                joinedload(Operation.account),
                id__in=operation_ids_to_add,
                chain_id=None
            )

            unique_types = {operation.category.type for operation in operations_to_add}

            if OperationType.TRANSFER in unique_types:
                raise TransferNotAllowedInChainError()

            amount += sum(op.amount for op in operations_to_add)
            operations.extend(operations_to_add)

        if operation_ids_to_remove:
            removed_operations = [
                op for op in chain.operations
                if op.id in operation_ids_to_remove
            ]
            amount -= sum(op.amount for op in removed_operations)

            operations = [
                op for op in operations
                if op.id not in operation_ids_to_remove
            ]

        return {
            "operations": operations,
            "amount": amount,
            "to_add_ids": list(operation_ids_to_add),
            "to_remove_ids": list(operation_ids_to_remove)
        }
