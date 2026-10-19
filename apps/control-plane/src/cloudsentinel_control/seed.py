from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudsentinel_control.config import Settings
from cloudsentinel_control.models import Environment, EnvironmentHealth, RoutingState, RuntimeSettings, Service


def environment_specs(settings: Settings) -> list[dict]:
    cluster_name = settings.cluster_name or "local"
    return [
        {
            "id": "azure-dev",
            "name": settings.primary_name,
            "provider": settings.primary_provider,
            "region": settings.primary_region,
            "cluster_name": cluster_name,
            "base_url": settings.analysis_azure_url,
            "role": "preferred",
            "runtime": settings.cluster_runtime,
            "notes": "",
        },
        {
            "id": "gcp-dev",
            "name": settings.secondary_name,
            "provider": settings.secondary_provider,
            "region": settings.secondary_region,
            "cluster_name": cluster_name,
            "base_url": settings.analysis_gcp_url,
            "role": "secondary",
            "runtime": settings.cluster_runtime,
            "notes": "",
        },
    ]


async def apply_environment_config(session: AsyncSession, settings: Settings) -> None:
    """Keep registered services aligned with the process configuration.

    The database is created once. Later changes to names, provider, and cluster
    identity have to be applied on startup or the console keeps the first seed forever.
    Health history is left alone.
    """
    for spec in environment_specs(settings):
        row = await session.get(Environment, spec["id"])
        if row is None:
            continue
        row.name = spec["name"]
        row.provider = spec["provider"]
        row.region = spec["region"]
        row.cluster_name = spec["cluster_name"]
        row.base_url = spec["base_url"]
        row.runtime = spec["runtime"]
        row.notes = spec["notes"]
        if row.verification == "not_cloud_verified":
            row.verification = "pending"


async def seed_if_empty(session: AsyncSession, settings: Settings) -> None:
    count = await session.scalar(select(func.count()).select_from(Environment))
    if count:
        return

    specs = environment_specs(settings)
    for spec in specs:
        session.add(
            Environment(
                kubernetes_version=None,
                verification="pending",
                experiments_allowed=True,
                enabled=True,
                **spec,
            )
        )
        session.add(EnvironmentHealth(environment_id=spec["id"]))
        session.add(
            Service(
                id=f"analysis-{spec['id']}",
                environment_id=spec["id"],
                name="analysis-api",
            )
        )
    session.add(
        RoutingState(
            id=1,
            active_environment_id=None,
            mode="automatic",
            preferred_environment_id="azure-dev",
            reason="Waiting for the first successful health checks.",
            generation=0,
        )
    )
    session.add(
        RuntimeSettings(
            id=1,
            health_check_interval_seconds=5,
            failure_threshold=3,
            success_threshold=2,
            cooldown_seconds=30,
            latency_threshold_ms=800,
            latency_breach_threshold=3,
            preferred_environment_id="azure-dev",
            alert_error_rate=0.05,
            alert_latency_ms=800,
            recovery_policy="automatic",
        )
    )
    await session.flush()
