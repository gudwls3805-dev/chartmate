from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import ConversationIn
from app.services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

# 대화는 개인정보다. 모든 조회·삭제는 본인의 익명 사용자 ID를 요구하고, 그 사용자의 대화만 다룬다.
UserId = Query(..., min_length=8, max_length=64, description="브라우저별 익명 사용자 ID")


@router.post("")
def create(conv: ConversationIn):
    return conversation_service.create_conversation(conv.model_dump())


@router.get("")
def list_mine(user_id: str = UserId):
    """본인(user_id)의 대화 목록만 돌려준다. 전체 사용자의 대화는 조회할 수 없다."""
    return conversation_service.get_user_conversations(user_id)


@router.get("/latest")
def latest(user_id: str = UserId):
    """재방문한 사용자의 마지막 대화를 돌려준다. 없으면 빈 메시지 목록."""
    conv = conversation_service.get_latest_conversation(user_id)
    if conv is None:
        return {"messages": []}
    return {
        "id": conv["id"],
        "created_at": conv.get("created_at"),
        "messages": conv.get("messages", []),
    }


def _own_conversation(doc_id: str, user_id: str):
    """대화가 있고 요청한 사용자의 것일 때만 돌려준다. 아니면 404 (존재 여부도 알려주지 않는다)."""
    conv = conversation_service.get_conversation(doc_id)
    if conv is None or conv.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다")
    return conv


@router.get("/{doc_id}")
def get_one(doc_id: str, user_id: str = UserId):
    return _own_conversation(doc_id, user_id)


@router.delete("/{doc_id}")
def delete(doc_id: str, user_id: str = UserId):
    _own_conversation(doc_id, user_id)
    conversation_service.delete_conversation(doc_id)
    return {"message": "삭제 완료", "id": doc_id}
