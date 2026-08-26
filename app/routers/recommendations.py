from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.utils.serialize import serialize, utcnow

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("")
async def list_recommendations(user=Depends(get_current_user)):
    db = get_db()
    cursor = db.recommendations.find({"user_id": str(user["_id"])}).sort("created_at", -1).limit(50)
    items = [serialize(doc) for doc in await cursor.to_list(50)]
    unread = await db.recommendations.count_documents({"user_id": str(user["_id"]), "read": False})
    return ok({"items": items, "unread": unread})


@router.post("/{rec_id}/read")
async def mark_read(rec_id: str, user=Depends(get_current_user)):
    db = get_db()
    result = await db.recommendations.update_one(
        {"_id": ObjectId(rec_id), "user_id": str(user["_id"])},
        {"$set": {"read": True, "read_at": utcnow()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="推荐不存在")
    return ok({"read": True})


@router.post("/read-all")
async def mark_all_read(user=Depends(get_current_user)):
    db = get_db()
    await db.recommendations.update_many(
        {"user_id": str(user["_id"]), "read": False},
        {"$set": {"read": True, "read_at": utcnow()}},
    )
    return ok({"read": True})
