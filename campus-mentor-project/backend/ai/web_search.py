"""Optional public web search used when local school chats have no match."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request


def search_web(query: str, *, max_results: int = 5) -> str:
	params = urllib.parse.urlencode({"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"})
	request = urllib.request.Request(
		f"https://api.duckduckgo.com/?{params}",
		headers={"User-Agent": "campus-mentor-school-bot/1.0"},
	)
	with urllib.request.urlopen(request, timeout=5) as response:
		payload = json.loads(response.read().decode("utf-8"))
	rows: list[str] = []
	abstract = str(payload.get("AbstractText") or "").strip()
	if abstract:
		rows.append(abstract)
	for topic in payload.get("RelatedTopics") or []:
		if isinstance(topic, dict):
			text = str(topic.get("Text") or "").strip()
			if text:
				rows.append(text)
		if len(rows) >= max_results:
			break
	return "\n".join(f"- {row}" for row in rows[:max_results])
