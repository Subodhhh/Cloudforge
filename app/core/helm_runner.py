import subprocess


def run_helm_command(args: list) -> dict:
    """
    Runs a helm CLI command and captures output.
    Using subprocess instead of a Python helm library because
    the official helm SDK support is limited — the CLI is the
    most reliable interface.
    """
    try:
        result = subprocess.run(
            ["helm"] + args,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()}
        return {"success": True, "output": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Helm command timed out"}


def install_postgres(namespace: str, release_name: str = "postgres"):
    args = [
        "install", release_name, "bitnami/postgresql",
        "--namespace", namespace,
        "--set", "auth.postgresPassword=cloudforge123",
        "--set", "primary.persistence.size=1Gi",
        "--wait",
        "--timeout", "180s",
    ]
    return run_helm_command(args)


def install_redis(namespace: str, release_name: str = "redis"):
    args = [
        "install", release_name, "bitnami/redis",
        "--namespace", namespace,
        "--set", "auth.enabled=false",
        "--set", "master.persistence.size=1Gi",
        "--wait",
        "--timeout", "180s",
    ]
    return run_helm_command(args)


def uninstall_release(namespace: str, release_name: str):
    args = ["uninstall", release_name, "--namespace", namespace]
    return run_helm_command(args)


def list_releases(namespace: str):
    args = ["list", "--namespace", namespace, "-o", "json"]
    return run_helm_command(args)

def get_postgres_connection_env(namespace: str) -> dict:
    """
    Returns env vars for connecting to the Postgres instance installed
    in this namespace via install_postgres() (bitnami chart, release name 'postgres').
    """
    host = f"postgres-postgresql.{namespace}.svc.cluster.local"
    return {
        "DATABASE_URL": f"postgresql://postgres:cloudforge123@{host}:5432/postgres",
        "DB_HOST": host,
        "DB_PORT": "5432",
        "DB_USER": "postgres",
        "DB_PASSWORD": "cloudforge123",
        "DB_NAME": "postgres",
    }


def get_redis_connection_env(namespace: str) -> dict:
    """
    Returns env vars for connecting to the Redis instance installed
    in this namespace via install_redis() (bitnami chart, release name 'redis').
    """
    host = f"redis-master.{namespace}.svc.cluster.local"
    return {
        "REDIS_URL": f"redis://{host}:6379/0",
        "REDIS_HOST": host,
        "REDIS_PORT": "6379",
    }