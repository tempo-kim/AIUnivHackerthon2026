"""NVIDIA embeddings client, kept separate from the configured chat provider."""

from __future__ import annotations

import os
from functools import lru_cache

from openai import OpenAI

DEFAULT_NVIDIA_EMBEDDING_URL = "https://integrate.api.nvidia.com/v1"
OPENROUTER_NEMOTRON_EMBEDDING = "nvidia/nemotron-3.5-embed-1b:free"


def _openrouter_base_url() -> str:
	return os.getenv("EMBEDDING_BASE_URL", "").strip() or os.getenv("OPENAI_BASE_URL", "").strip()


def uses_openrouter_embeddings() -> bool:
	return "openrouter.ai" in _openrouter_base_url().lower()


def embedding_model_name() -> str:
	configured = (
		os.getenv("EMBEDDING_MODEL", "").strip()
		or os.getenv("NIM_EMBEDDING_MODEL", "").strip()
		or os.getenv("NVIDIA_EMBEDDING_MODEL", "").strip()
	)
	old_model_ids = {"nvidia/nv-embedqa-e5-v5", "nv-embedqa-e5-v5"}
	if uses_openrouter_embeddings():
		if not configured or configured.lower() in old_model_ids | {"nvidia/nemotron-3.5-embed-1b"}:
			return OPENROUTER_NEMOTRON_EMBEDDING
		return configured
	if configured.lower() in old_model_ids:
		return "nvidia/nemotron-3.5-embed-1b"
	return configured or "nvidia/nemotron-3.5-embed-1b"


def embedding_extra_body(input_type: str) -> dict[str, str]:
	# OpenRouter's embedding route chooses the provider's default query/passage mode.
	if uses_openrouter_embeddings():
		return {}
	return {"input_type": input_type}


@lru_cache(maxsize=1)
def embedding_client() -> OpenAI:
	"""Build an NVIDIA client without exposing credential values in logs."""
	chat_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
	if uses_openrouter_embeddings():
		base_url = _openrouter_base_url()
		api_key = (
			os.getenv("EMBEDDING_API_KEY", "").strip()
			or os.getenv("OPENROUTER_API_KEY", "").strip()
			or os.getenv("OPENAI_API_KEY", "").strip()
		)
		if not api_key:
			raise RuntimeError("OpenRouter embedding credentials are missing.")
		return OpenAI(base_url=base_url, api_key=api_key)

	base_url = (
		os.getenv("EMBEDDING_BASE_URL", "").strip()
		or os.getenv("NVIDIA_BASE_URL", "").strip()
		or DEFAULT_NVIDIA_EMBEDDING_URL
	)
	api_key = (
		os.getenv("EMBEDDING_API_KEY", "").strip()
		or os.getenv("NVIDIA_API_KEY", "").strip()
		or os.getenv("NIM_API_KEY", "").strip()
	)

	# Reuse OPENAI_API_KEY only when the existing chat endpoint is NVIDIA itself.
	if not api_key and "integrate.api.nvidia.com" in chat_base_url.lower():
		api_key = os.getenv("OPENAI_API_KEY", "").strip()
		if not os.getenv("EMBEDDING_BASE_URL", "").strip() and not os.getenv("NVIDIA_BASE_URL", "").strip():
			base_url = chat_base_url

	if not api_key:
		raise RuntimeError(
			"NVIDIA embedding credentials are missing. Set NVIDIA_API_KEY or EMBEDDING_API_KEY."
		)
	return OpenAI(base_url=base_url, api_key=api_key)
