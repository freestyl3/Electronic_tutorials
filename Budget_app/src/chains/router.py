import uuid

from fastapi import APIRouter, Response, Query

from src.auth.dependencies import CurrentUserID
from src.chains.schemas import (
    ChainCreate, ChainDetailRead, ChainShortRead, ChainUpdate
)
from src.chains.dependencies import ChainServiceDep

router = APIRouter()

@router.post("/", response_model=ChainDetailRead)
async def create_chain(
    chain_create: ChainCreate,
    service: ChainServiceDep,
    user_id: CurrentUserID
):
    return await service.create(chain_create, user_id)

@router.get("/", response_model=list[ChainShortRead])
async def get_all_chains(
    service: ChainServiceDep,
    user_id: CurrentUserID
):
    return await service.get_all(user_id)

@router.get("/{chain_id}", response_model=ChainDetailRead)
async def get_chain(
    chain_id: uuid.UUID,
    service: ChainServiceDep,
    user_id: CurrentUserID
):
    return await service.get_by_id(chain_id, user_id)

@router.patch("/{chain_id}", response_model=ChainDetailRead)
async def update_chain(
    chain_id: uuid.UUID,
    update_schema: ChainUpdate,
    service: ChainServiceDep,
    user_id: CurrentUserID
):
    return await service.update(
        chain_id=chain_id,
        update_schema=update_schema,
        user_id=user_id
    )

@router.delete("/{chain_id}")
async def delete_chain(
    chain_id: uuid.UUID,
    service: ChainServiceDep,
    user_id: CurrentUserID,
    cascade: bool = Query(False, description="Если True, будут удалены и все операции внутри цепочки")
):
    await service.delete(chain_id, cascade, user_id)
    return Response(status_code=204)
