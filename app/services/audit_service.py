from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def log_action(db: Session, actor_username: str, action: str, target: str = None, details: str = None):
    """
    Records an audit trail entry. Called after any sensitive action:
    environment requests, approvals, rejections, deletions, user deactivation, etc.
    """
    entry = AuditLog(
        actor_username=actor_username,
        action=action,
        target=target,
        details=details,
    )
    db.add(entry)
    db.commit()
