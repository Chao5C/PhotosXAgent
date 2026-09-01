from __future__ import annotations

import asyncio
import logging

from app.core.database import get_db
from app.services.session_service import SessionService
from app.utils.serialize import utcnow

logger = logging.getLogger(__name__)
#推送

async def flush_once() -> None:
    try:
        db = get_db()
    except Exception:
        return
    sessions = SessionService(db)
    now = utcnow()
    cursor = db.user_sessions.find({})
    async for session in cursor:
        user_id = session.get("user_id")
        if not user_id:
            continue
        state = sessions.classify_state(session.get("last_message_at"), now)
        if state == "ACTIVE":
            continue
        try:
            await sessions.deliver_pending(user_id, merge=state == "DORMANT")
        except Exception:
            logger.exception("deliver pending failed for %s", user_id)

    try:
        due = await sessions.due_reminders()
    except Exception:
        logger.exception("due reminders failed")
        due = []
    for item in due:
        user_id = item.get("user_id")
        if not user_id:
            continue
        try:
            await sessions.deliver_reminder(user_id, item)
        except Exception:
            logger.exception("deliver reminder failed for %s", user_id)


async def run_push_worker() -> None:
    while True:
        try:
            await flush_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("push worker loop failed")
        await asyncio.sleep(5)
