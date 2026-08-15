import uuid
from sqlalchemy import Column, String, Integer, ForeignKey
from app.database import Base


class ServiceComponent(Base):
    __tablename__ = "service_components"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    environment_id = Column(String, ForeignKey("environments.id"), nullable=False)

    name = Column(String, nullable=False)          # e.g. "frontend", "backend", "worker"
    image = Column(String, nullable=False)          # e.g. "myorg/payments-frontend:v2"
    container_port = Column(Integer, nullable=True)  # null = not exposed (e.g. background worker)
    replicas = Column(Integer, default=1)