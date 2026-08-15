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
