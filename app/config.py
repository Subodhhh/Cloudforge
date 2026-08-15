from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://cloudforge:cloudforge@localhost:5432/cloudforge"
    SECRET_KEY: str = "change-this-in-production-please"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    KUBE_CONFIG_PATH: str = "~/.kube/config"
    KIND_CLUSTER_CONTEXT: str = "kind-cloudforge"

    class Config:
        env_file = ".env"

settings = Settings()