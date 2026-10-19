from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudsentinel_control.config import Settings
from cloudsentinel_control.models import Environment, EnvironmentHealth, RoutingState, RuntimeSettings, Service


async def seed_if_empty(session: AsyncSession, settings: Settings) -> None:
    count = await session.scalar(select(func.count()).select_from(Environment))
    if count:
        return

    # These rows are local stand-ins. The provider field says which cloud the
    # process represents. verification stays not_cloud_verified until someone
    # actually deploys the same image to that cloud.
    specs = [
        {
            "id": "azure-dev",
            "name": "Azure stand-in",
            "provider": "azure",
            "region": "westeurope",
            "cluster_name": "not-provisioned",
            "base_url": settings.analysis_azure_url,
            "role": "preferred",
            "runtime": "local_container",
            "notes": "Local process labelled as the Azure AKS environment. Not an AKS cluster.",
        },
        {
            "id": "gcp-dev",
            "name": "GCP stand-in",
            "provider": "gcp",
            "region": "europe-west2",
            "cluster_name": "not-provisioned",
            "base_url": settings.analysis_gcp_url,
            "role": "secondary",
            "runtime": "local_container",
            "notes": "Local process labelled as the GKE environment. Not a GKE cluster.",
        },
    ]
    for spec in specs:
        session.add(
            Environment(
                kubernetes_version=None,
                verification="not_cloud_verified",
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
