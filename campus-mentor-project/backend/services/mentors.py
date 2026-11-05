"""Syntitan으로 정리된 선배 CSV를 로드한다."""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CLEANED_PATH = DATA_DIR / "mentors.cleaned.csv"
MENTORS_PATH = DATA_DIR / "Mentors.csv"
MENTORS_ADD_PATH = DATA_DIR / "Mentors.add.csv"


@dataclass
class Mentor:
    mentor_id: str
    display_name: str
    major: str
    experiences: list[str]
    help_topics: list[str]
    status: str = ""
    bio: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _split_pipe(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split("|") if part.strip()]


def _row_to_mentor(row: dict, generated_id: str = "") -> Mentor:
    mentor_id = (row.get("mentor_id") or generated_id).strip()
    major = (row.get("major") or row.get("본인의 학과") or "").strip()
    display = (row.get("display_name") or row.get("name") or row.get("닉네임") or mentor_id).strip()
    experiences = row.get("experiences") or ""
    help_topics = row.get("help_topics") or ""
    if not experiences and not help_topics:
        experiences = "|".join(
            value.strip()
            for value in (row.get("진로 경험", ""), row.get("학교 활동 경험", ""))
            if value and value.strip()
        )
        help_topics = experiences
    return Mentor(
        mentor_id=mentor_id,
        display_name=display,
        major=major,
        experiences=_split_pipe(experiences.replace(",", "|")),
        help_topics=_split_pipe(help_topics.replace(",", "|")),
        status=(row.get("status") or row.get("학년") or "").strip(),
        bio=(row.get("bio") or row.get("경험 소개") or "").strip(),
    )


def _row_key(row: dict) -> str:
    timestamp = (row.get("타임스탬프") or row.get("timestamp") or "").strip()
    nickname = (row.get("닉네임") or row.get("display_name") or row.get("name") or "").strip()
    return f"{timestamp}|{nickname}" if timestamp or nickname else ""


class MentorStore:
    def __init__(self) -> None:
        self._mentors: list[Mentor] = []
        self.source_path: Path | None = None
        self.reload()

    def reload(self, path: Path | None = None) -> int:
        targets = [path] if path is not None else [MENTORS_PATH, MENTORS_ADD_PATH]
        merged: dict[str, Mentor] = {}
        next_id = 1
        source = None
        for target in targets:
            if target is None or not target.exists():
                continue
            source = source or target
            with target.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    key = _row_key(row) or f"row-{next_id}"
                    if key not in merged:
                        next_id += 1
                    merged[key] = _row_to_mentor(row, f"M{next_id - 1:03d}")
        if not merged:
            raise FileNotFoundError("멘토 CSV를 찾을 수 없습니다.")
        mentors = list(merged.values())
        self._mentors = mentors
        self.source_path = source
        return len(mentors)

    def replace_from_csv_text(self, text: str, save: bool = True) -> int:
        reader = csv.DictReader(io.StringIO(text))
        mentors = [
            _row_to_mentor(row, f"M{index:03d}")
            for index, row in enumerate(reader, 1)
            if (row.get("mentor_id") or row.get("닉네임") or "").strip()
        ]
        if not mentors:
            raise ValueError("유효한 mentor_id 행이 없습니다.")
        self._mentors = mentors
        if save:
            CLEANED_PATH.parent.mkdir(parents=True, exist_ok=True)
            fieldnames = [
                "mentor_id",
                "display_name",
                "major",
                "experiences",
                "help_topics",
                "bio",
            ]
            with CLEANED_PATH.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for m in mentors:
                    writer.writerow(
                        {
                            "mentor_id": m.mentor_id,
                            "display_name": m.display_name,
                            "major": m.major,
                            "experiences": "|".join(m.experiences),
                            "help_topics": "|".join(m.help_topics),
                            "bio": m.bio,
                        }
                    )
            self.source_path = CLEANED_PATH
        return len(mentors)

    def list(self) -> list[Mentor]:
        return list(self._mentors)

    def as_matching_rows(self) -> list[dict]:
        """matcher가 쓰는 최소 필드 dict."""
        return [
            {
                "mentor_id": m.mentor_id,
                "display_name": m.display_name,
                "major": m.major,
                "experiences": m.experiences,
                "help_topics": m.help_topics,
                "status": m.status,
                "bio": m.bio,
            }
            for m in self._mentors
        ]


store = MentorStore()
