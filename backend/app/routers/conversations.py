from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import ConversationIn
from app.services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("")
def create(conv: ConversationIn):
    return conversation_service.create_conversation(conv.model_dump())


@router.get("")
def list_all():
    return conversation_service.get_all_conversations()


@router.get("/latest")
def latest(user_id: str = Query(..., min_length=8, max_length=64)):
    """재방문한 사용자의 마지막 대화를 돌려준다. 없으면 빈 메시지 목록."""
    conv = conversation_service.get_latest_conversation(user_id)
    if conv is None:
        return {"messages": []}
    return {
        "id": conv["id"],
        "created_at": conv.get("created_at"),
        "messages": conv.get("messages", []),
    }


@router.get("/{doc_id}")
def get_one(doc_id: str):
    result = conversation_service.get_conversation(doc_id)
    if result is None:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다")
    return result


@router.delete("/{doc_id}")
def delete(doc_id: str):
    ok = conversation_service.delete_conversation(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다")
    return {"message": "삭제 완료", "id": doc_id}
