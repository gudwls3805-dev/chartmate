"""ChartMate 챗 서비스 — OpenAI 대화 + AI Agent(수동 라우터 방식)

[설계 결정] 지정된 코디세이 엔드포인트(gpt-5-mini)가 function calling(tools)을
지원하지 않아(400 unsupported_feature), tools API 대신 '종목 인식 → 도구 호출 →
결과 주입' 2단계로 Agent를 구현한다.
  1) 종목 인식: 사전(한글명→티커) 우선, 실패 시 모델 라우터로 추출
  2) 도구 실행: get_price / get_indicators 호출
  3) 답변 생성: 조회 결과를 주입해 '짧은 브리핑'으로 응답
"""

import json
import re
import time

from openai import OpenAI

from app.config import OPENAI_API_KEY, OPENAI_BASE_URL
from app.services import market_service
from app.services.conversation_service import create_conversation

if OPENAI_BASE_URL:
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
else:
    client = OpenAI(api_key=OPENAI_API_KEY)

MODEL = "gpt-5-mini"

# 자주 쓰는 한글 종목명 → 티커 (빠르고 확실한 1차 인식)
NAME_TO_TICKER = {
    "엔비디아": "NVDA",
    "애플": "AAPL",
    "테슬라": "TSLA",
    "마이크로소프트": "MSFT",
    "구글": "GOOGL",
    "알파벳": "GOOGL",
    "아마존": "AMZN",
    "메타": "META",
    "넷플릭스": "NFLX",
    "브로드컴": "AVGO",
    "마이크론": "MU",
    "팔란티어": "PLTR",
    "AMD": "AMD",
    "인텔": "INTC",
    "비트코인": "BTC-USD",
    "이더리움": "ETH-USD",
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
}
_STOP = {"AI", "RSI", "ATR", "ETF", "USD", "PER", "CEO", "API", "GPT", "ChartMate".upper()}


def _detect_ticker(message: str):
    """사전 + 간단 규칙으로 티커를 먼저 찾는다. (모델 호출 없이)"""
    for name, tk in NAME_TO_TICKER.items():
        if name.lower() in message.lower():
            return tk
    # 메시지에 대문자 티커가 직접 들어온 경우 (예: NVDA)
    for tok in re.findall(r"\b[A-Z]{2,5}\b", message):
        if tok not in _STOP:
            return tok
    return None


# 답변에 넣는 이전 대화는 최근 것만 사용한다. (복원된 긴 대화로 응답이 느려지는 것을 방지)
MAX_HISTORY_MESSAGES = 12

# gpt-5 계열은 기본 추론 단계가 길어 응답이 느리다. 브리핑은 주어진 수치를 정리하는 작업이라
# 추론 강도를 최소로 낮춘다. 엔드포인트가 이 옵션을 지원하지 않으면 한 번 실패한 뒤 옵션 없이 호출한다.
_use_reasoning_effort = True


def _complete(messages: list, max_tokens: int):
    global _use_reasoning_effort
    if _use_reasoning_effort:
        try:
            return client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_completion_tokens=max_tokens,
                reasoning_effort="minimal",
            )
        except Exception as e:
            print(f"[chat] reasoning_effort 미지원으로 보임, 옵션 없이 재시도: {e}")
            _use_reasoning_effort = False
    return client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_completion_tokens=max_tokens,
    )


def _plan_with_model(message: str):
    """[폴백] 사전에서 못 찾으면 모델에게 티커를 물어본다. (JSON만 유도)"""
    prompt = (
        "다음 메시지가 특정 주식/ETF/크립토의 시세·지표를 묻는지 판단해 JSON으로만 답하라.\n"
        '형식: {"need": true/false, "ticker": "야후파이낸스 티커 또는 null"}\n'
        "한글 종목명은 티커로 변환(예: 엔비디아→NVDA). 시세와 무관하면 need=false.\n"
        f"메시지: {message}"
    )
    try:
        resp = _complete([{"role": "user", "content": prompt}], 300)
        text = resp.choices[0].message.content or ""
        s, e = text.find("{"), text.rfind("}")
        plan = json.loads(text[s : e + 1]) if s >= 0 and e > s else {}
        if plan.get("need") and plan.get("ticker"):
            return plan["ticker"]
    except Exception:
        pass
    return None


SYSTEM_PROMPT = (
    "당신은 투자 초보를 돕는 AI 투자 비서 'ChartMate'입니다.\n"
    "종목 데이터가 주어지면 반드시 아래 '브리핑 형식'으로 짧고 명확하게 답하세요. "
    "장황한 일반론·교과서식 나열은 금지합니다.\n\n"
    "[브리핑 형식]\n"
    "{종목} 브리핑\n"
    "· 현재가: $가격 (전일 대비 ±%)\n"
    "· 추세: 60일선/200일선 대비 위/아래 — 한 줄 해석\n"
    "· 변동성: ATR 기준 높음/보통/낮음\n"
    "· 모멘텀(126일): ±% — 한 줄 해석\n"
    "· 요약: 1~2문장\n\n"
    "규칙:\n"
    "- 주어진 수치만 사용하고 추측하지 않습니다.\n"
    "- 데이터에 error가 있으면 '해당 종목 데이터를 가져오지 못했어요'라고만 답합니다.\n"
    "- 종목 데이터가 없는 일반 질문이면 2~3문장으로 짧게 답합니다.\n"
    "- 끝에 항상 '※ 투자 참고용 정보이며 매수·매도 권유가 아닙니다.'를 붙입니다.\n"
    "- 매수/매도를 지시하거나 권유하지 않습니다."
)


def chat(user_message: str, history: list, user_id: str | None = None) -> dict:
    t_start = time.perf_counter()

    # 1) 종목 인식 (사전 → 모델 폴백)
    ticker = _detect_ticker(user_message) or _plan_with_model(user_message)

    # 2) 도구 실행 — 시세 이력은 한 번만 내려받아 두 도구가 함께 쓴다
    market_context = ""
    if ticker:
        df = market_service.load_history(ticker)
        collected = {
            "price": market_service.get_price(ticker, df),
            "indicators": market_service.get_indicators(ticker, df),
        }
        market_context = json.dumps(collected, ensure_ascii=False)
    t_market = time.perf_counter()

    # 3) 답변 생성
    system_prompt = SYSTEM_PROMPT
    if market_context:
        system_prompt += f"\n\n[조회된 실시간 데이터]\n{market_context}"

    messages = [{"role": "system", "content": system_prompt}]
    messages += history[-MAX_HISTORY_MESSAGES:]
    messages.append({"role": "user", "content": user_message})

    response = _complete(messages, 2000)
    t_llm = time.perf_counter()
    choice = response.choices[0]
    answer = choice.message.content
    if not answer:
        print(f"[chat] 빈 응답 (finish_reason={choice.finish_reason})")
        answer = "죄송해요, 답변을 생성하지 못했어요. 질문을 조금 더 구체적으로 다시 해 주세요."

    # 4) 대화 저장
    saved_messages = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": answer},
    ]
    conv_data = {"title": user_message[:20], "messages": saved_messages}
    if user_id:
        # 사용자별 대화 복원(Long-term Memory)을 위해 익명 사용자 ID를 함께 저장
        conv_data["user_id"] = user_id
    conv = create_conversation(conv_data)

    t_end = time.perf_counter()

    # 구간별 소요 시간(ms) — 화면에 표시해 응답 속도를 확인하는 데 쓴다
    timings = {
        "market_ms": round((t_market - t_start) * 1000),
        "llm_ms": round((t_llm - t_market) * 1000),
        "save_ms": round((t_end - t_llm) * 1000),
        "total_ms": round((t_end - t_start) * 1000),
    }
    print(f"[chat] ticker={ticker} timings={timings}")
    return {
        "answer": answer,
        "conversation_id": conv["id"],
        "ticker": ticker,
        "timings": timings,
    }
