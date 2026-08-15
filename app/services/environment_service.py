from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models.environment import Environment, EnvStatus
from app.models.user import User
from app.models.service_component import ServiceComponent
from app.core.k8s_client import (
    create_namespace,
    delete_namespace,
    get_namespace_status,
    create_app_deployment,
    create_app_service,
    create_app_ingress,
)
from app.core.helm_runner import install_postgres, install_redis
from app.core.policy import requires_approval
from app.services.audit_service import log_action


def request_environment(
    db: Session,
    name: str,
    owner: User,
    services: list,
    postgres: bool = False,
    redis: bool = False,
    ttl_hours: int = 24,
) -> Environment:
    """
    Step 1 of environment lifecycle: create the DB record.
    - If low-risk (per policy), immediately provisions it.
    - If high-risk, leaves it in 'pending' status for admin approval.
    """
    existing = db.query(Environment).filter(Environment.name == name).first()
    if existing:
        if existing.status not in (EnvStatus.deleted, EnvStatus.rejected):
            raise ValueError(f"Environment '{name}' already exists")
        # Name was previously used but is now deleted/rejected — clean up the old row
        # (and its service components) so the namespace/name can be reused.
        db.query(ServiceComponent).filter(ServiceComponent.environment_id == existing.id).delete()
        db.delete(existing)
        db.commit()

    namespace = f"env-{name}"
    expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

    needs_approval, reason = requires_approval(services, postgres, redis, ttl_hours)

    env = Environment(
        name=name,
        namespace=namespace,
        owner_id=owner.id,
        postgres_enabled=postgres,
        redis_enabled=redis,
        status=EnvStatus.pending if needs_approval else EnvStatus.creating,
        ttl_hours=str(ttl_hours),
        expires_at=expires_at,
    )
    db.add(env)
    db.commit()
    db.refresh(env)

    for svc in services:
        db.add(ServiceComponent(
            environment_id=env.id,
            name=svc.name,
            image=svc.image,
            container_port=svc.container_port,
            replicas=svc.replicas,
        ))
    db.commit()

    log_action(
        db, owner.username, "request_environment", target=name,
        details=reason,
    )

    if needs_approval:
        return env

    return provision_environment(db, env)


def provision_environment(db: Session, env: Environment) -> Environment:
    """
    Step 2: does the actual Kubernetes/Helm work.
    Called either immediately (auto-approved) or after admin approval.
    """
    try:
        create_namespace(
            env.namespace,
            labels={
                "managed-by": "cloudforge",
                "owner": env.owner_id,
                "env-name": env.name,
            },
        )

        components = db.query(ServiceComponent).filter(ServiceComponent.environment_id == env.id).all()

        for svc in components:
            create_app_deployment(
                env.namespace,
                name=svc.name,
                image=svc.image,
                container_port=svc.container_port or 80,
                replicas=svc.replicas,
            )
            if svc.container_port:
                create_app_service(env.namespace, name=svc.name, container_port=svc.container_port)
                create_app_ingress(env.namespace, env_name=f"{env.name}-{svc.name}", service_name=svc.name)

        if env.postgres_enabled:
            result = install_postgres(env.namespace)
            if not result["success"]:
                raise RuntimeError(f"Postgres install failed: {result['error']}")

        if env.redis_enabled:
            result = install_redis(env.namespace)
            if not result["success"]:
                raise RuntimeError(f"Redis install failed: {result['error']}")

        env.status = EnvStatus.running
        db.commit()
        db.refresh(env)
        return env

    except Exception as e:
        env.status = EnvStatus.failed
        db.commit()
        db.refresh(env)
        raise e


def approve_environment(db: Session, env: Environment, admin: User) -> Environment:
    if env.status != EnvStatus.pending:
        raise ValueError("Only pending environments can be approved")
    log_action(db, admin.username, "approve_environment", target=env.name)
    env.status = EnvStatus.creating
    db.commit()
    return provision_environment(db, env)


def reject_environment(db: Session, env: Environment, admin: User, reason: str = None) -> Environment:
    if env.status != EnvStatus.pending:
        raise ValueError("Only pending environments can be rejected")
    env.status = EnvStatus.rejected
    db.commit()
    db.refresh(env)
    log_action(db, admin.username, "reject_environment", target=env.name, details=reason)
    return env


def delete_environment(db: Session, env: Environment, actor: User) -> Environment:
    env.status = EnvStatus.deleting
    db.commit()

    delete_namespace(env.namespace)

    env.status = EnvStatus.deleted
    env.deleted_at = datetime.utcnow()
    db.commit()
    db.refresh(env)

    log_action(db, actor.username, "delete_environment", target=env.name)
    return env


def get_environment_live_status(env: Environment) -> str:
    k8s_status = get_namespace_status(env.namespace)
    return k8s_status["status"]


def list_environments_for_user(db: Session, user: User):
    query = db.query(Environment).filter(Environment.status != EnvStatus.deleted)
    if user.role.value != "admin":
        query = query.filter(Environment.owner_id == user.id)
    return query.all()


def list_pending_environments(db: Session):
    return db.query(Environment).filter(Environment.status == EnvStatus.pending).all()


def get_environment_or_404(db: Session, name: str) -> Environment:
    env = db.query(Environment).filter(
        Environment.name == name,
        Environment.status != EnvStatus.deleted,
    ).first()
    if not env:
        raise ValueError("Environment not found")
    return env


def check_ownership(env: Environment, user: User):
    if user.role.value == "admin":
        return
    if env.owner_id != user.id:
        raise PermissionError("You do not have access to this environment")