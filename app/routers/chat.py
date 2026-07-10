import os

import requests
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ChatRequest
from app.routers import check_permission

router = APIRouter()

# Dify Chatflow API 配置
DIFY_API_URL = os.getenv("DIFY_API_URL", "")
DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")


@router.post("/chat")
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """与 Dify Chatflow 对话（转发请求）"""
    try:
        if not check_permission(req.current_user_type):
            return {"code": 403, "msg": "无权限操作", "data": None}

        if not DIFY_API_URL or not DIFY_API_KEY:
            return {"code": 500, "msg": "Dify 未配置（请设置 DIFY_API_URL 和 DIFY_API_KEY 环境变量）", "data": None}

        resp = requests.post(
            f"{DIFY_API_URL.rstrip('/')}/v1/chat-messages",
            headers={
                "Authorization": f"Bearer {DIFY_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "query": req.query,
                "inputs": {},
                "response_mode": "blocking",
                "user": str(req.current_user_id),
            },
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        return {"code": 0, "msg": "success", "data": result}
    except requests.Timeout:
        return {"code": 500, "msg": "Dify 请求超时", "data": None}
    except requests.RequestException as e:
        return {"code": 500, "msg": f"Dify 请求失败: {e}", "data": None}
    except Exception as e:
        return {"code": 500, "msg": str(e), "data": None}
