"""Minimal client for any OpenAI-compatible chat completions API.

Works with OpenAI, Groq, OpenRouter, Together, or a local Ollama / LM Studio
server. Configure with environment variables (see .env.example). When no model
is configured, PaperPilot runs in extractive mode and never calls an LLM.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


class LLMError(RuntimeError):
    pass


@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str | None = None
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> LLMConfig | None:
        model = os.getenv("LLM_MODEL", "").strip()
        if not model:
            return None
        return cls(
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            model=model,
            api_key=os.getenv("LLM_API_KEY") or None,
            timeout=float(os.getenv("LLM_TIMEOUT", "60")),
        )


class ChatClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    def complete(self, system: str, user: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload = {
            "model": self.config.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = httpx.post(
                f"{self.config.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.config.timeout,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
