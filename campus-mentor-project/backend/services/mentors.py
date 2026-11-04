"""Syntitan으로 정리된 선배 CSV를 로드한다."""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CLEANED_PATH = DATA_DIR / "mentors.cleaned.csv"
EXAMPLE_PATH = DATA_DIR / "mentors.example.csv"


@dataclass
class Mentor:
    mentor_id: str
    display_name: str
    major: str
    experiences: list[str]
    help_topics: list[str]
    bio: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _split_pipe(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split("|") if part.strip()]


def _row_to_mentor(row: dict) -> Mentor:
    mentor_id = (row.get("mentor_id") or "").strip()
    major = (row.get("major") or "").strip()
    display = (row.get("display_name") or row.get("name") or mentor_id).strip()
    return Mentor(
        mentor_id=mentor_id,
        display_name=display,
        major=major,
        experiences=_split_pipe(row.get("experiences", "")),
        help_topics=_split_pipe(row.get("help_topics", "")),
        bio=(row.get("bio") or "").strip(),
    )


class MentorStore:
    def __init__(self) -> None:
        self._mentors: list[Mentor] = []
        self.source_path: Path | None = None
        self.reload()

    def reload(self, path: Path | None = None) -> int:
        target = path
        if target is None:
            target = CLEANED_PATH if CLEANED_PATH.exists() else EXAMPLE_PATH
        mentors: list[Mentor] = []
        with target.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mentor = _row_to_mentor(row)
                if mentor.mentor_id:
                    mentors.append(mentor)
        self._mentors = mentors
        self.source_path = target
        return len(mentors)

    def replace_from_csv_text(self, text: str, save: bool = True) -> int:
        reader = csv.DictReader(io.StringIO(text))
        mentors = [_row_to_mentor(row) for row in reader if (row.get("mentor_id") or "").strip()]
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
                "bio": m.bio,
            }
            for m in self._mentors
        ]


store = MentorStore()
