from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.models.user import User, UserRole
from app.auth import get_current_user, require_role
from app.services.environment_service import (
    request_environment,
    approve_environment,
    reject_environment,
    delete_environment,
    list_environments_for_user,
    list_pending_environments,
    get_environment_or_404,
    get_environment_live_status,
    check_ownership,
)

router = APIRouter(prefix="/environments", tags=["environments"])


class ServiceSpec(BaseModel):
    name: str
    image: str
    container_port: Optional[int] = None
    replicas: int = 1


class CreateEnvironmentRequest(BaseModel):
    name: str
    services: List[ServiceSpec] = [ServiceSpec(name="app", image="nginxdemos/hello", container_port=80)]
    postgres: bool = False
    redis: bool = False
    ttl_hours: int = 24


def _serialize(env, services=None):
    return {
        "name": env.name,
        "namespace": env.namespace,
        "status": env.status,
        "postgres": env.postgres_enabled,
        "redis": env.redis_enabled,
        "expires_at": env.expires_at,
        "services": [
            {"name": s.name, "url": f"http://localhost:8080/{env.name}-{s.name}" if s.container_port else None}
            for s in (services or [])
        ],
    }


@router.post("/")
def create_env(
    payload: CreateEnvironmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.developer)),
):
    try:
        env = request_environment(
            db, name=payload.name, owner=current_user, services=payload.services,
            postgres=payload.postgres, redis=payload.redis, ttl_hours=payload.ttl_hours,
        )
        return _serialize(env, payload.services)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Environment creation failed: {str(e)}")


@router.get("/")
def list_envs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    envs = list_environments_for_user(db, current_user)
    return [_serialize(e) for e in envs]


@router.get("/pending")
def list_pending(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    envs = list_pending_environments(db)
    return [_serialize(e) for e in envs]


@router.post("/{name}/approve")
def approve_env(
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    try:
        env = get_environment_or_404(db, name)
        env = approve_environment(db, env, current_user)
        return _serialize(env)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approval failed: {str(e)}")


class RejectRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/{name}/reject")
def reject_env(
    name: str,
    payload: RejectRequest = RejectRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    try:
        env = get_environment_or_404(db, name)
        env = reject_environment(db, env, current_user, reason=payload.reason)
        return _serialize(env)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{name}")
def get_env(name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        env = get_environment_or_404(db, name)
        check_ownership(env, current_user)
        live_status = get_environment_live_status(env) if env.status == "running" else env.status
        return {**_serialize(env), "live_k8s_status": live_status}
    except ValueError:
        raise HTTPException(status_code=404, detail="Environment not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Access denied to this environment")


@router.delete("/{name}")
def delete_env(
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.developer)),
):
    try:
        env = get_environment_or_404(db, name)
        check_ownership(env, current_user)
        deleted_env = delete_environment(db, env, current_user)
        return {"name": deleted_env.name, "status": deleted_env.status}
    except ValueError:
        raise HTTPException(status_code=404, detail="Environment not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="You do not own this environment")