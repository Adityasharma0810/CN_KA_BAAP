"""Multi-link WAN status routes."""

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.api.v1.deps import get_current_user, get_session
from backend.app.models.gateway import Gateway
from backend.app.models.multiwan import MultiWANLink
from sqlalchemy import select

router = APIRouter()


@router.get("/gateways/{gateway_id}/multiwan")
async def multiwan_status(gateway_id: str, user = Depends(get_current_user), session = Depends(get_session)):
    gateway = await session.scalar(select(Gateway).where(Gateway.gateway_id == gateway_id))
    if not gateway:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_gateway")
    result = await session.execute(select(MultiWANLink).where(MultiWANLink.gateway_id == gateway_id))
    links = [
        {
            "id": str(l.id),
            "name": l.name,
            "link_type": l.link_type,
            "state": l.state,
            "capacity_download_mbps": l.capacity_download_mbps,
            "capacity_upload_mbps": l.capacity_upload_mbps,
            "latency_ms": l.latency_ms,
            "loss_percent": l.loss_percent,
            "preferred": l.preferred,
            "backup": l.backup,
            "last_measured_at": l.last_measured_at,
        }
        for l in result.scalars().all()
    ]
    available = len(links) > 0
    return {
        "gateway_id": gateway_id,
        "multi_wan_available": available,
        "links": links,
        "note": "Multi-link shown only when more than one usable WAN interface exists.",
    }
