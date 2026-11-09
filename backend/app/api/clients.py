"""Product-facing anonymous client observation routes."""

from fastapi import APIRouter, HTTPException, Path

from backend.app.services.lab_accounting_service import lab_accounting_service

router = APIRouter(prefix="/api/v1/clients", tags=["Clients"])


def _safe_clients() -> list[dict]:
    result = lab_accounting_service.collect()
    observations = {item["client_id"]: item for item in result.get("clients", [])}
    clients = []
    for client in lab_accounting_service.registry.list_clients():
        item = {
            "client_id": client.client_id,
            "display_label": client.display_label,
            "status": client.status,
            "environment": "simulated_lab",
            "first_seen_at": client.first_seen_at,
            "last_seen_at": client.last_seen_at,
            "stale": client.stale,
            "latest_observation": observations.get(client.client_id),
        }
        clients.append(item)
    return clients


@router.get("")
def list_clients():
    """List anonymous clients without physical identity or lab infrastructure."""

    return {
        "count": len(lab_accounting_service.registry.list_clients()),
        "clients": _safe_clients(),
        "source": "linux_namespace_lab",
        "environment": "simulated_lab",
    }


@router.get("/{client_id}")
def get_client(
    client_id: str = Path(
        min_length=14,
        max_length=40,
        pattern=r"^client-[a-z0-9]{8,32}$",
    ),
):
    """Return one anonymous client and its latest lab observation."""

    try:
        client = lab_accounting_service.registry.get(client_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid anonymous client ID") from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Anonymous client not found") from error

    result = lab_accounting_service.collect()
    latest = next(
        (item for item in result.get("clients", []) if item["client_id"] == client_id),
        None,
    )
    return {
        "client_id": client.client_id,
        "display_label": client.display_label,
        "status": client.status,
        "environment": "simulated_lab",
        "first_seen_at": client.first_seen_at,
        "last_seen_at": client.last_seen_at,
        "stale": client.stale,
        "latest_observation": latest,
    }
