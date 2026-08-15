from app.models.environment import Environment
from app.models.audit_log import AuditLog
from app.services.environment_service import (
    approve_environment,
    reject_environment,
    list_pending_environments,
)
from app.services.teardown_service import teardown_expired_environments
from app.services.audit_service import log_action
from app.services.environment_service import (
    request_environment,
    delete_environment,
    list_environments_for_user,
    get_environment_or_404,
    check_ownership,
)
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.auth import hash_password, verify_password, create_access_token, decode_token

class _SimpleService:
    def __init__(self, name, image, container_port, replicas=1):
        self.name = name
        self.image = image
        self.container_port = container_port
        self.replicas = replicas

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/templates")


def get_current_user_from_cookie(request: Request, db: Session):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_token(token)
        username = payload.get("sub")
        user = db.query(User).filter(User.username == username).first()
        if user and user.is_active:
            return user
    except Exception:
        return None
    return None


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")
    if user.role == UserRole.admin:
        return RedirectResponse(url="/admin")
    return RedirectResponse(url="/dashboard")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"user": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(request, "login.html", {"user": None, "error": "Invalid username or password"})
    if not user.is_active:
        return templates.TemplateResponse(request, "login.html", {"user": None, "error": "This account has been deactivated"})

    token = create_access_token(data={"sub": user.username, "role": user.role.value})
    redirect_url = "/admin" if user.role == UserRole.admin else "/dashboard"
    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=3600)
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"user": None})


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return templates.TemplateResponse(request, "register.html", {"user": None, "error": "Username already exists"})

    user = User(username=username, hashed_password=hash_password(password), role=UserRole.developer)
    db.add(user)
    db.commit()
    return templates.TemplateResponse(request, "register.html", {"user": None, "success": "Account created. You can now log in."})

def _serialize_env(env):
    return {
        "name": env.name,
        "status": env.status,
        "postgres": env.postgres_enabled,
        "redis": env.redis_enabled,
        "expires_at": env.expires_at,
        "services": [
            {"name": s.name, "url": f"http://localhost:8080/{env.name}-{s.name}" if s.container_port else None}
            for s in env.service_components
        ] if hasattr(env, "service_components") else [],
    }


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    envs = list_environments_for_user(db, user)
    from app.models.service_component import ServiceComponent
    env_data = []
    for env in envs:
        services = db.query(ServiceComponent).filter(ServiceComponent.environment_id == env.id).all()
        env_data.append({
            "name": env.name,
            "status": env.status.value,
            "postgres": env.postgres_enabled,
            "redis": env.redis_enabled,
            "expires_at": env.expires_at,
            "services": [
                {"name": s.name, "url": f"http://localhost:8080/{env.name}-{s.name}" if s.container_port else None}
                for s in services
            ],
        })

    return templates.TemplateResponse(request, "dashboard.html", {"user": user, "environments": env_data})


@router.post("/dashboard/create", response_class=HTMLResponse)
def dashboard_create(
    request: Request,
    name: str = Form(...),
    ttl_hours: int = Form(...),
    image: str = Form(...),
    container_port: int = Form(...),
    postgres: bool = Form(False),
    redis: bool = Form(False),
    db: Session = Depends(get_db),
):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    services = [_SimpleService(name="app", image=image, container_port=container_port)]

    try:
        request_environment(db, name=name, owner=user, services=services, postgres=postgres, redis=redis, ttl_hours=ttl_hours)
        return RedirectResponse(url="/dashboard", status_code=302)
    except ValueError as e:
        envs = list_environments_for_user(db, user)
        from app.models.service_component import ServiceComponent
        env_data = []
        for env in envs:
            svc = db.query(ServiceComponent).filter(ServiceComponent.environment_id == env.id).all()
            env_data.append({
                "name": env.name, "status": env.status, "postgres": env.postgres_enabled,
                "redis": env.redis_enabled, "expires_at": env.expires_at,
                "services": [{"name": s.name, "url": None} for s in svc],
            })
        return templates.TemplateResponse(request, "dashboard.html", {"user": user, "environments": env_data, "error": str(e)})


@router.post("/dashboard/delete/{name}")
def dashboard_delete(name: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login")

    try:
        env = get_environment_or_404(db, name)
        check_ownership(env, user)
        delete_environment(db, env, user)
    except (ValueError, PermissionError):
        pass

    return RedirectResponse(url="/dashboard", status_code=302)

def _require_admin(request: Request, db: Session):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None, RedirectResponse(url="/login")
    if user.role != UserRole.admin:
        return None, RedirectResponse(url="/dashboard")
    return user, None


def _build_admin_context(db: Session, user, extra=None):
    from app.models.service_component import ServiceComponent

    pending_envs = list_pending_environments(db)
    pending = []
    for env in pending_envs:
        owner = db.query(User).filter(User.id == env.owner_id).first()
        pending.append({
            "name": env.name, "owner": owner.username if owner else "unknown",
            "postgres": env.postgres_enabled, "redis": env.redis_enabled, "ttl_hours": env.ttl_hours,
        })

    all_envs_raw = db.query(Environment).filter(Environment.status != "deleted").all()
    all_envs = []
    for env in all_envs_raw:
        owner = db.query(User).filter(User.id == env.owner_id).first()
        all_envs.append({
            "name": env.name, "owner": owner.username if owner else "unknown",
            "status": env.status.value, "postgres": env.postgres_enabled,
            "redis": env.redis_enabled, "expires_at": env.expires_at,
        })

    users = db.query(User).all()
    user_list = [{"username": u.username, "role": u.role.value, "is_active": u.is_active} for u in users]

    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(50).all()
    log_list = [{"timestamp": l.timestamp, "actor": l.actor_username, "action": l.action, "target": l.target, "details": l.details} for l in logs]

    context = {"user": user, "pending": pending, "all_envs": all_envs, "users": user_list, "audit_logs": log_list}
    if extra:
        context.update(extra)
    return context


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "admin.html", _build_admin_context(db, user))


@router.post("/admin/approve/{name}")
def admin_approve(name: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    try:
        env = get_environment_or_404(db, name)
        approve_environment(db, env, user)
    except Exception:
        pass
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/admin/reject/{name}")
def admin_reject(name: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    try:
        env = get_environment_or_404(db, name)
        reject_environment(db, env, user, reason="Rejected via admin dashboard")
    except Exception:
        pass
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/admin/delete/{name}")
def admin_delete(name: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    try:
        env = get_environment_or_404(db, name)
        delete_environment(db, env, user)
    except Exception:
        pass
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/admin/users/{username}/deactivate")
def admin_deactivate(username: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    target = db.query(User).filter(User.username == username).first()
    if target and target.username != user.username:
        target.is_active = False
        db.commit()
        log_action(db, user.username, "deactivate_user", target=username)
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/admin/users/{username}/reactivate")
def admin_reactivate(username: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    target = db.query(User).filter(User.username == username).first()
    if target:
        target.is_active = True
        db.commit()
        log_action(db, user.username, "reactivate_user", target=username)
    return RedirectResponse(url="/admin", status_code=302)

@router.post("/admin/users/{username}/promote")
def admin_promote(username: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    target = db.query(User).filter(User.username == username).first()
    if target and target.role != UserRole.admin:
        target.role = UserRole.admin
        db.commit()
        log_action(db, user.username, "promote_to_admin", target=username)
    return RedirectResponse(url="/admin", status_code=302)

@router.post("/admin/teardown")
def admin_teardown(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect
    teardown_expired_environments()
    return RedirectResponse(url="/admin", status_code=302)

@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response