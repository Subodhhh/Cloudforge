import uuid
from sqlalchemy import Column, String, Integer, ForeignKey, JSON
from app.database import Base


class ServiceComponent(Base):
    __tablename__ = "service_components"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    name = Column(String, nullable=False)
    image = Column(String, nullable=False)
    container_port = Column(Integer, nullable=True)
    replicas = Column(Integer, default=1)
    env_vars = Column(JSON, nullable=True)
    private_registry = Column(JSON, nullable=True)  # {"server": "...", "username": "...", "password": "..."}