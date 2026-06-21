import logging
import os
from datetime import datetime, timezone

import aiohttp
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

from app.middleware.rate_limit import limiter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/interest", tags=["interest"])

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

VALID_CATEGORIES = {"homes", "books", "clothes", "electronics", "caravans", "other"}


class InterestClick(BaseModel):
    type: str  # "click"
    category: str


class InterestEmail(BaseModel):
    type: str  # "email"
    category: str
    email: EmailStr


async def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info(f"Telegram not configured. Message: {text}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Telegram API error ({resp.status}): {body}")
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


@router.post("")
@limiter.limit("30/minute")
async def track_interest(request: Request):
    body = await request.json()
    interest_type = body.get("type")
    category = body.get("category")

    if not interest_type or not category:
        raise HTTPException(status_code=400, detail="Missing type or category")

    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if interest_type == "click":
        await send_telegram(f"👆 Interest click: *{category}*\n🕐 {now}")
        return JSONResponse({"ok": True})

    if interest_type == "email":
        email = body.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Email required")

        message = "\n".join([
            "🔥 *New interested user!*",
            "",
            f"📧 {email}",
            f"📦 Category: *{category}*",
            f"🕐 {now}",
        ])
        await send_telegram(message)

        logger.info(f"Interest captured: {email} -> {category}")
        return JSONResponse({"ok": True})

    raise HTTPException(status_code=400, detail="Invalid type")
