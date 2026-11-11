"""Feedback API — submit, retrieve, and inspect learned state."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.schemas.feedback import FeedbackSubmission, FeedbackRecord, LearningState
from app.services import feedback_store, user_store

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def _require_uid(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> str:
    uid = user_store.decode_token(creds.credentials) if creds else None
    if not uid:
        raise HTTPException(401, "Authentication required.")
    return uid


@router.post("/feedback", response_model=FeedbackRecord, status_code=201)
def submit_feedback(sub: FeedbackSubmission, uid: str = Depends(_require_uid)):
    return feedback_store.submit_feedback(uid, sub)


@router.get("/feedback", response_model=list[FeedbackRecord])
def get_feedback(limit: int = 50, uid: str = Depends(_require_uid)):
    return feedback_store.get_user_feedback(uid, limit=min(limit, 200))


@router.get("/feedback/learning", response_model=LearningState)
def get_learning_state(uid: str = Depends(_require_uid)):
    return feedback_store.get_learning_state(uid)
