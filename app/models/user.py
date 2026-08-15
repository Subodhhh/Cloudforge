import enum
import uuid
from sqlalchemy import Column, String, Enum, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base

class UserRole(str, enum.Enum):
    admin = "admin"
    developer = "developer"
    viewer = "viewer"

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.developer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())