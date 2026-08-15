from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.models.audit_log import AuditLog
from app.auth import require_role
from app.services.teardown_service import teardown_expired_environments
from app.services.audit_service import log_action

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/teardown/run")
def run_teardown_now(current_user: User = Depends(require_role(UserRole.admin))):
    results = teardown_expired_environments()
    return {"triggered_by": current_user.username, "environments_processed": len(results), "results": results}


@router.get("/users")
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.admin))):
    users = db.query(User).all()
    return [{"username": u.username, "role": u.role, "is_active": u.is_active} for u in users]


@router.post("/users/{username}/deactivate")
def deactivate_user(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.username == current_user.username:
        raise HTTPException(status_code=400, detail="You cannot deactivate yourself")
    user.is_active = False
    db.commit()
    log_action(db, current_user.username, "deactivate_user", target=username)
    return {"username": username, "is_active": False}


@router.post("/users/{username}/reactivate")
def reactivate_user(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    db.commit()
    log_action(db, current_user.username, "reactivate_user", target=username)
    return {"username": username, "is_active": True}


@router.get("/audit-logs")
def get_audit_logs(db: Session = Depends(get_db), current_user: User = Depends(require_role(UserRole.admin))):
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100).all()
    return [
        {"actor": l.actor_username, "action": l.action, "target": l.target, "details": l.details, "timestamp": l.timestamp}
        for l in logs
    ]