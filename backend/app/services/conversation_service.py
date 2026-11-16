from datetime import datetime, timezone

from firebase_admin import firestore

from app.database import db

COLLECTION = "conversations"


def create_conversation(data: dict) -> dict:
    """대화 저장 (생성 시각 자동 기록)"""
    data["created_at"] = datetime.now(timezone.utc).isoformat()
    doc_ref = db.collection(COLLECTION).document()
    doc_ref.set(data)
    return {"id": doc_ref.id, **data}


def get_all_conversations() -> list:
    """대화 목록 조회 (최신순)"""
    docs = (
        db.collection(COLLECTION)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .stream()
    )
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


def get_user_conversations(user_id: str) -> list:
    """해당 사용자의 대화 목록 (최신순). 다른 사용자의 대화는 포함하지 않는다."""
    docs = db.collection(COLLECTION).where("user_id", "==", user_id).stream()
    items = [{"id": doc.id, **doc.to_dict()} for doc in docs]
    return sorted(items, key=lambda c: c.get("created_at", ""), reverse=True)


def get_latest_conversation(user_id: str):
    """해당 사용자의 가장 최근 대화 (없으면 None).

    대화는 매 응답마다 '그때까지의 전체 메시지'로 저장되므로, 가장 최근 문서 하나가
    곧 그 사용자의 마지막 대화 전체다. 복합 색인이 필요 없도록 정렬은 서버에서 한다.
    """
    docs = db.collection(COLLECTION).where("user_id", "==", user_id).stream()
    items = [{"id": doc.id, **doc.to_dict()} for doc in docs]
    if not items:
        return None
    return max(items, key=lambda c: c.get("created_at", ""))


def get_conversation(doc_id: str):
    """특정 대화 전체 불러오기 (없으면 None)"""
    doc = db.collection(COLLECTION).document(doc_id).get()
    if not doc.exists:
        return None
    return {"id": doc.id, **doc.to_dict()}


def delete_conversation(doc_id: str) -> bool:
    """대화 삭제 (없으면 False)"""
    doc_ref = db.collection(COLLECTION).document(doc_id)
    if not doc_ref.get().exists:
        return False
    doc_ref.delete()
    return True
