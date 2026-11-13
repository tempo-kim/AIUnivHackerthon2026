from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from ai.extractor import _client, _model_name

BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ENV_PATH = BASE_DIR / ".env"

VECTOR_DIR = BASE_DIR / "vector_db"
COLLECTION_NAME = os.getenv("RAG_COLLECTION_NAME", "campus_rag")
SEED_CHAT_PATH = DATA_DIR / "school_bot_seed_chats.json"


def _embedding_model_name() -> str:
	return (
		os.getenv("EMBEDDING_MODEL", "").strip()
		or os.getenv("NIM_EMBEDDING_MODEL", "").strip()
		or os.getenv("NVIDIA_EMBEDDING_MODEL", "").strip()
		or "nvidia/nv-embedqa-e5-v5"
	)


@lru_cache(maxsize=1)
def _collection():
	if not VECTOR_DIR.exists():
		raise RuntimeError("vector DB가 없습니다. 먼저 build_vector_db.py를 실행하세요.")
	client = chromadb.PersistentClient(path=str(VECTOR_DIR))
	return client.get_collection(COLLECTION_NAME)


def _embed_query(query: str) -> list[float]:
	resp = _client().embeddings.create(model=_embedding_model_name(), input=[query])
	return resp.data[0].embedding


def retrieve_contexts(question: str, k: int = 5) -> list[dict[str, Any]]:
	if not question.strip():
		return []
	query_vector = _embed_query(question)
	collection = _collection()
	result = collection.query(query_embeddings=[query_vector], n_results=min(k, collection.count()))

	documents = result.get("documents") or [[]]
	metadatas = result.get("metadatas") or [[]]
	distances = result.get("distances") or [[]]

	rows: list[dict[str, Any]] = []
	for idx, doc in enumerate(documents[0]):
		rows.append(
			{
				"rank": idx + 1,
				"text": doc,
				"metadata": metadatas[0][idx] if idx < len(metadatas[0]) else {},
				"distance": distances[0][idx] if idx < len(distances[0]) else None,
			}
		)
	return rows


@lru_cache(maxsize=1)
def _few_shot_examples(max_examples: int = 3) -> list[tuple[str, str]]:
	if not SEED_CHAT_PATH.exists():
		return []

	raw = json.loads(SEED_CHAT_PATH.read_text(encoding="utf-8"))
	by_school = raw.get("conversations_by_school") if isinstance(raw, dict) else None
	if not isinstance(by_school, dict):
		return []

	examples: list[tuple[str, str]] = []
	for convs in by_school.values():
		if not isinstance(convs, list):
			continue
		for conv in convs:
			messages = conv.get("messages") if isinstance(conv, dict) else None
			if not isinstance(messages, list):
				continue
			for i in range(len(messages) - 1):
				cur = messages[i]
				nxt = messages[i + 1]
				if not isinstance(cur, dict) or not isinstance(nxt, dict):
					continue
				if str(cur.get("senderRole", "")).lower() != "junior":
					continue
				if str(nxt.get("senderRole", "")).lower() != "senior":
					continue
				q = str(cur.get("text") or "").strip()
				a = str(nxt.get("text") or "").strip()
				if not q or not a:
					continue
				examples.append((q, a))
				if len(examples) >= max_examples:
					return examples
	return examples


def _build_context_block(contexts: list[dict[str, Any]]) -> str:
	lines: list[str] = []
	for item in contexts:
		md = item.get("metadata") or {}
		source = md.get("source", "unknown")
		lines.append(f"[근거 {item['rank']}] source={source}")
		lines.append(str(item.get("text") or ""))
		lines.append("")
	return "\n".join(lines).strip()


def _build_messages(question: str, contexts: list[dict[str, Any]]) -> list[dict[str, str]]:
	system_prompt = (
		"너는 캠퍼스 멘토 데이터 기반 답변 봇이다. "
		"반드시 제공된 근거 텍스트 안에서만 답하고, 근거에 없는 사실은 추측하거나 생성하지 마라. "
		"근거에 충분한 정보가 없으면 '제공된 데이터에서 확인되지 않습니다.'라고 명확히 답해라. "
		"답변은 한국어로 간결하게 작성하고, 가능하면 근거 source를 함께 언급해라."
	)

	messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

	for q, a in _few_shot_examples(3):
		messages.append({"role": "user", "content": q})
		messages.append({"role": "assistant", "content": a})

	context_text = _build_context_block(contexts)
	user_prompt = (
		f"[질문]\n{question}\n\n"
		f"[검색된 근거]\n{context_text}\n\n"
		"위 근거만 사용해서 답변해줘. 근거에 없으면 모른다고 답해줘."
	)
	messages.append({"role": "user", "content": user_prompt})
	return messages


def answer_with_rag(question: str, k: int = 5) -> dict[str, Any]:
	contexts = retrieve_contexts(question, k=k)
	messages = _build_messages(question, contexts)

	res = _client().chat.completions.create(
		model=_model_name(),
		messages=messages,
		temperature=0.1,
		max_tokens=600,
		timeout=25.0,
	)

	answer = (res.choices[0].message.content or "").strip()
	citations = [
		{
			"rank": c["rank"],
			"source": (c.get("metadata") or {}).get("source", "unknown"),
			"distance": c.get("distance"),
		}
		for c in contexts
	]

	return {
		"question": question,
		"answer": answer,
		"contexts": contexts,
		"citations": citations,
	}


def _cli() -> None:
	load_dotenv(ENV_PATH)
	print("RAG CLI 시작. 종료하려면 exit 입력")
	while True:
		question = input("\n질문> ").strip()
		if not question:
			continue
		if question.lower() in {"exit", "quit", "q"}:
			print("종료")
			break
		try:
			result = answer_with_rag(question, k=5)
			print("\n[답변]")
			print(result["answer"])
			print("\n[근거]")
			for c in result["citations"]:
				print(f"- #{c['rank']} {c['source']} (distance={c['distance']})")
		except Exception as exc:
			print(f"오류: {exc}")


if __name__ == "__main__":
	_cli()

