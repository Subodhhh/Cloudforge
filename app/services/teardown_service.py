from datetime import datetime
from app.database import SessionLocal
from app.models.environment import Environment, EnvStatus
from app.services.environment_service import delete_environment


class _SystemActor:
    """
    Synthetic actor used for audit logging when the teardown scheduler
    deletes an environment automatically (no human triggered it).
    """
    username = "system-scheduler"


def teardown_expired_environments():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        expired = db.query(Environment).filter(
            Environment.status == EnvStatus.running,
            Environment.expires_at != None,
            Environment.expires_at <= now,
        ).all()

        results = []
        system_actor = _SystemActor()
        for env in expired:
            print(f"[teardown] Expiring environment: {env.name} (expired at {env.expires_at})")
            try:
                delete_environment(db, env, system_actor)
                results.append({"name": env.name, "status": "deleted"})
            except Exception as e:
                print(f"[teardown] Failed to delete {env.name}: {e}")
                results.append({"name": env.name, "status": "failed", "error": str(e)})

        return results
    finally:
        db.close()