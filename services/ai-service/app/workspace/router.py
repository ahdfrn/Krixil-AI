from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context
from app.workspace.fs import (
    WorkspacePathError,
    delete_file,
    list_files,
    read_file,
    write_file,
)

router = APIRouter(prefix="/workspace", tags=["workspace"])


class WorkspaceEntryOut(BaseModel):
    name: str
    path: str
    is_dir: bool
    size_bytes: int | None


class WorkspaceFileOut(BaseModel):
    path: str
    content: str


@router.get("/files", response_model=list[WorkspaceEntryOut])
async def get_files(
    path: str = ".",
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> list[WorkspaceEntryOut]:
    try:
        return [WorkspaceEntryOut(**e) for e in list_files(tenant_ctx.tenant_id, path)]
    except WorkspacePathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/files/content", response_model=WorkspaceFileOut)
async def get_file_content(
    path: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> WorkspaceFileOut:
    try:
        return WorkspaceFileOut(path=path, content=read_file(tenant_ctx.tenant_id, path))
    except WorkspacePathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"'{path}' does not exist"
        ) from exc


@router.post("/files", response_model=WorkspaceFileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    path: str,
    file: UploadFile = File(...),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> WorkspaceFileOut:
    content = (await file.read()).decode("utf-8", errors="replace")
    try:
        write_file(tenant_ctx.tenant_id, path, content)
    except WorkspacePathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return WorkspaceFileOut(path=path, content=content)


@router.delete("/files", status_code=status.HTTP_204_NO_CONTENT)
async def remove_file(
    path: str,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> None:
    try:
        delete_file(tenant_ctx.tenant_id, path)
    except WorkspacePathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IsADirectoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{path}' is a directory"
        ) from exc
