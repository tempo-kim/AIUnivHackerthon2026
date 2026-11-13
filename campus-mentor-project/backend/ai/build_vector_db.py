from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from dotenv import load_dotenv

from ai.extractor import _client

BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ENV_PATH = BASE_DIR / ".env"

VECTOR_DIR = BASE_DIR / "vector_db"
COLLECTION_NAME = os.getenv("RAG_COLLECTION_NAME", "campus_rag")

CSV_FILES = (
	DATA_DIR / "Mentors.csv",
	DATA_DIR / "Mentors.add.csv",
	DATA_DIR / "220.new.mentors.csv",
)
README_FILES = (
	PROJECT_DIR / "README.md",
	DATA_DIR / "README.md",
)
SEED_CHAT_PATH = DATA_DIR / "school_bot_seed_chats.json"


@dataclass
class DocChunk:
	doc_id: str
	text: str
	metadata: dict[str, Any]


def _embedding_model_name() -> str:
	return (
		os.getenv("EMBEDDING_MODEL", "").strip()
		or os.getenv("NIM_EMBEDDING_MODEL", "").strip()
		or os.getenv("NVIDIA_EMBEDDING_MODEL", "").strip()
		or "nvidia/nv-embedqa-e5-v5"
	)


def _serialize_row(row: dict[str, str]) -> str:
	preferred = [
		"닉네임",
		"학년",
		"본인의 학과",
		"진로 경험",
		"학교 활동 경험",
		"경험 소개",
		"성별",
		"연령",
		"지역",
		"gender",
		"age",
		"region",
		"한 달에 답변 가능한 질문 수",
		"연결 가능한 후배 수",
	]

	lines: list[str] = []
	used = set()

	for key in preferred:
		value = str(row.get(key, "") or "").strip()
		if not value:
			continue
		used.add(key)
		lines.append(f"{key}: {value}")

	for key, value in row.items():
		if key in used:
			continue
		text = str(value or "").strip()
		if text:
			lines.append(f"{key}: {text}")

	return "\n".join(lines)


def _load_csv_chunks(path: Path) -> list[DocChunk]:
	if not path.exists():
		print(f"[build_vector_db] 파일 없음: {path}")
		return []

	chunks: list[DocChunk] = []
	with path.open("r", encoding="utf-8-sig", newline="") as f:
		reader = csv.DictReader(f)
		for idx, row in enumerate(reader, start=1):
			body = _serialize_row({k: str(v or "") for k, v in row.items()})
			if not body.strip():
				continue

			doc_id = f"csv::{path.name}::{idx}"
			chunks.append(
				DocChunk(
					doc_id=doc_id,
					text=f"[source={path.name} row={idx}]\n{body}",
					metadata={
						"source": path.name,
						"doc_type": "mentor_profile",
						"row_index": idx,
						"nickname": str(row.get("닉네임", "") or "").strip(),
						"major": str(row.get("본인의 학과", "") or "").strip(),
						"grade": str(row.get("학년", "") or "").strip(),
					},
				)
			)

	return chunks


def _load_readme_chunks() -> list[DocChunk]:
	chunks: list[DocChunk] = []
	for path in README_FILES:
		if not path.exists():
			continue
		text = path.read_text(encoding="utf-8").strip()
		if not text:
			continue
		doc_id = f"readme::{path.parent.name}::{path.name}"
		chunks.append(
			DocChunk(
				doc_id=doc_id,
				text=f"[source={path.relative_to(PROJECT_DIR)}]\n{text}",
				metadata={
					"source": str(path.relative_to(PROJECT_DIR)).replace("\\", "/"),
					"doc_type": "readme",
				},
			)
		)
	return chunks


def _load_seed_chat_chunks() -> list[DocChunk]:
	"""Index seed conversations in bounded message chunks (v2 and v3 JSON)."""
	if not SEED_CHAT_PATH.exists():
		return []
	raw = json.loads(SEED_CHAT_PATH.read_text(encoding="utf-8"))
	by_school = raw.get("conversations_by_school") if isinstance(raw, dict) else None
	if isinstance(by_school, dict):
		conversations = [conv for rows in by_school.values() if isinstance(rows, list) for conv in rows]
	else:
		conversations = raw.get("conversations", []) if isinstance(raw, dict) else []
	chunks: list[DocChunk] = []
	for conv_index, conv in enumerate(conversations, start=1):
		if not isinstance(conv, dict):
			continue
		head = f"학교: {conv.get('school', '')}\n주제: {conv.get('topic', '')}\n제목: {conv.get('title', '')}"
		lines = [head]
		part = 1
		for msg in conv.get("messages", []):
			if not isinstance(msg, dict):
				continue
			role = "후배" if str(msg.get("senderRole", "")).lower() == "junior" else "선배"
			line = f"[{role}] {str(msg.get('text') or '').strip()}"
			if len("\n".join(lines)) + len(line) > 2200 and len(lines) > 1:
				chunks.append(DocChunk(
					doc_id=f"seed::{conv.get('id', conv_index)}::{part}",
					text="\n".join(lines),
					metadata={"source": "school_bot_seed_chats.json", "doc_type": "seed_chat", "school": str(conv.get("school", "")), "topic": str(conv.get("topic", ""))},
				))
				part += 1
				lines = [head]
			lines.append(line)
		if len(lines) > 1:
			chunks.append(DocChunk(
				doc_id=f"seed::{conv.get('id', conv_index)}::{part}",
				text="\n".join(lines),
				metadata={"source": "school_bot_seed_chats.json", "doc_type": "seed_chat", "school": str(conv.get("school", "")), "topic": str(conv.get("topic", ""))},
			))
	return chunks


def _embed_texts(texts: list[str], model: str, batch_size: int = 32) -> list[list[float]]:
	all_vectors: list[list[float]] = []
	client = _client()
	for i in range(0, len(texts), batch_size):
		batch = texts[i : i + batch_size]
		response = client.embeddings.create(model=model, input=batch)
		vectors = [item.embedding for item in response.data]
		all_vectors.extend(vectors)
	return all_vectors


def build_vector_db() -> None:
	load_dotenv(ENV_PATH)

	model = _embedding_model_name()
	print(f"[build_vector_db] embedding model: {model}")
	print(f"[build_vector_db] vector dir: {VECTOR_DIR}")

	chunks: list[DocChunk] = []
	for csv_path in CSV_FILES:
		chunks.extend(_load_csv_chunks(csv_path))
	chunks.extend(_load_readme_chunks())
	chunks.extend(_load_seed_chat_chunks())

	if not chunks:
		raise RuntimeError("인덱싱할 문서가 없습니다.")

	VECTOR_DIR.mkdir(parents=True, exist_ok=True)
	client = chromadb.PersistentClient(path=str(VECTOR_DIR))

	texts = [c.text for c in chunks]
	metadatas = [c.metadata for c in chunks]
	ids = [c.doc_id for c in chunks]

	embeddings = _embed_texts(texts, model=model)
	try:
		client.delete_collection(COLLECTION_NAME)
	except Exception:
		pass
	collection = client.create_collection(name=COLLECTION_NAME)
	for start in range(0, len(chunks), 500):
		end = start + 500
		collection.add(
			documents=texts[start:end],
			metadatas=metadatas[start:end],
			ids=ids[start:end],
			embeddings=embeddings[start:end],
		)

	print(
		f"[build_vector_db] 완료: chunks={len(chunks)} "
		f"(csv={sum(1 for c in chunks if c.metadata.get('doc_type') == 'mentor_profile')}, "
		f"readme={sum(1 for c in chunks if c.metadata.get('doc_type') == 'readme')}, "
		f"seed_chat={sum(1 for c in chunks if c.metadata.get('doc_type') == 'seed_chat')})"
	)


if __name__ == "__main__":
	build_vector_db()
