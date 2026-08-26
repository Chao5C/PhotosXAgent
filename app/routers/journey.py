from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.services.journey_service import JourneyService

router = APIRouter(prefix="/api/journey", tags=["journey"])


@router.get("")
async def get_journey(user=Depends(get_current_user)):
    return ok(await JourneyService(get_db()).build_journey(str(user["_id"])))
