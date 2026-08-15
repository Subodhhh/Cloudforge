import enum
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from app.database import Base

class EnvStatus(str, enum.Enum):
    pending = "pending"       # awaiting admin approval
    creating = "creating"     # approved, provisioning in progress
    running = "running"
    failed = "failed"
    rejected = "rejected"     # admin declined the request
    deleting = "deleting"
    deleted = "deleted"

class Environment(Base):
    __tablename__ = "environments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, index=True, nullable=False)
    namespace = Column(String, unique=True, nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)

    postgres_enabled = Column(Boolean, default=False)
    redis_enabled = Column(Boolean, default=False)

    status = Column(Enum(EnvStatus), default=EnvStatus.creating)

    ttl_hours = Column(String, default="24")   # for teardown automation
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
