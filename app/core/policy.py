
def requires_approval(services: list, postgres: bool, redis: bool, ttl_hours: int) -> tuple[bool, str]:
    """
    Decides whether an environment request needs admin approval,
    or can be auto-approved instantly.

    Returns (needs_approval: bool, reason: str)
    """
    if postgres or redis:
        return True, "Requests provisioning a database (Postgres/Redis) require admin approval"

    if ttl_hours > 8:
        return True, "Environments longer than 8 hours require admin approval"

    if len(services) > 2:
        return True, "Requests with more than 2 services require admin approval"

    return False, "Auto-approved: low-risk request"
