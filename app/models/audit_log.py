import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_username = Column(String, nullable=False)
    action = Column(String, nullable=False)       # e.g. "create_environment_request", "approve", "reject", "deactivate_user"
    target = Column(String, nullable=True)          # e.g. environment name or username affected
    details = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())