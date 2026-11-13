"""학교 생활 Q&A 챗봇.
선배 매칭과 같은 OPENAI_API_KEY / OPENAI_BASE_URL / LLM_MODEL 을 사용한다.
과거·진행 중 채팅을 익명으로 모아 맥락으로 넣는다.
"""

from __future__ import annotations

import os
import traceback

from ai.extractor import _client, _model_name


def _role_label(role: str) -> str:
	value = (role or "").strip().lower()
	if value in ("senior", "mentor"):
		return "선배"
	if value in ("junior",):
		return "후배"
	return "사용자"


def build_chat_context(messages: list[dict], *, max_chars: int = 6000) -> str:
	lines: list[str] = []
	for item in messages:
		text = str(item.get("text") or "").strip()
		if not text:
			continue
		lines.append(f"- [{_role_label(str(item.get('senderRole') or ''))}] {text[:400]}")

	blob = "\n".join(lines)
	if len(blob) > max_chars:
		blob = blob[-max_chars:]
	return blob


def answer_school_question(
	question: str,
	*,
	school: str = "",
	messages: list[dict] | None = None,
) -> dict:
	"""같은 LLM 연결로 학교 관련 질문에 답한다."""
	question = (question or "").strip()
	if not question:
		return {
			"answer": "질문을 입력해 주세요.",
			"used_message_count": 0,
			"source": "empty",
		}

	messages = messages or []
	context = build_chat_context(messages)
	used = len(messages)

	if not os.getenv("OPENAI_API_KEY", "").strip():
		hint = (
			"아직 API 키가 없어 임시 안내만 할 수 있어요. "
			"backend/.env 에 매칭과 같은 OPENAI_API_KEY 를 넣으면 실제 답변이 됩니다."
		)
		if context:
			return {
				"answer": (
					f"{hint}\n\n"
					f"지금은 저장된 대화 {used}개를 참고할 준비가 되어 있어요. "
					"예: 수강신청, 학교생활, 밥집, 진로 관련 질문을 해보세요."
				),
				"used_message_count": used,
				"source": "no_key",
			}
		return {
			"answer": hint + " 아직 참고할 채팅 기록도 거의 없어요.",
			"used_message_count": 0,
			"source": "no_key",
		}

	school_line = f"대상 학교: {school}" if school.strip() else "대상 학교: (미지정)"
	corpus = context if context else "(아직 저장된 선배·후배 대화가 없습니다.)"

	system_prompt = f"""
너는 대학 캠퍼스 멘토링 서비스 '뻔뻔하게'의 학교 생활 안내 챗봇이다.
선배와 후배가 나눈(또는 나누고 있는) 대화들을 익명으로 모아 둔 자료를 참고해 답한다.

규칙:
- 한국어로 짧고 친절하게 답한다.
- 참고 대화에 근거가 있으면 그 내용을 우선한다.
- 근거가 부족하면 추측하지 말고, 모른다고 하거나 일반적인 학교생활 팁 수준으로만 말한다.
- 특정 개인(이름·학번·연락처)을 추론하거나 노출하지 않는다.
- 의료·법률·위험 조언은 하지 않는다.
- {school_line}
"""
	user_prompt = f"""
[참고용 익명 대화 모음]
{corpus}

[사용자 질문]
{question}
"""

	try:
		res = _client().chat.completions.create(
			model=_model_name(),
			messages=[
				{"role": "system", "content": system_prompt.strip()},
				{"role": "user", "content": user_prompt.strip()},
			],
			temperature=0.3,
			max_tokens=700,
			timeout=20.0,
		)
		answer = (res.choices[0].message.content or "").strip()
		if not answer:
			answer = "답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요."
		return {
			"answer": answer,
			"used_message_count": used,
			"source": "llm",
		}
	except Exception as exc:
		print(f"[school_bot] {exc}")
		traceback.print_exc()
		return {
			"answer": "지금은 답변 서버에 연결하지 못했어요. API 키·네트워크를 확인해 주세요.",
			"used_message_count": used,
			"source": "error",
		}
