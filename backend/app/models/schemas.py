from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class DataIn(BaseModel):
    """데이터 추가 시 받는 형식"""

    date: str = Field(..., description="날짜 (YYYY-MM-DD)")
    value: float = Field(..., description="값 (예: 종가)")
    memo: str = Field("", description="메모")

    @field_validator("date")
    @classmethod
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("date는 YYYY-MM-DD 형식이어야 합니다")
        return v


class DataUpdate(BaseModel):
    """데이터 수정 시 받는 형식 (일부만 보낼 수 있음)"""

    date: Optional[str] = None
    value: Optional[float] = None
    memo: Optional[str] = None


class Message(BaseModel):
    role: str = Field(..., description="user 또는 assistant")
    content: str = Field(..., description="메시지 내용")


class ConversationIn(BaseModel):
    title: Optional[str] = Field(None, description="대화 제목")
    messages: List[Message] = Field(..., description="메시지 목록")


class ChatIn(BaseModel):
    """챗봇 요청 형식"""

    message: str = Field(..., description="사용자 질문")
    history: List[Message] = Field(default=[], description="이전 대화 메시지 (선택)")
    user_id: Optional[str] = Field(
        None,
        max_length=64,
        description="브라우저별 익명 사용자 ID. 개인정보 동의 후 프론트에서 생성하며, 재방문 시 대화 복원에 쓴다.",
    )
