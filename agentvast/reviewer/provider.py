"""Provider abstraction for short-lived Reviewer model tasks."""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agentvast.reviewer.prompts import SYSTEM_PROMPT


class ReviewerProviderError(RuntimeError):
    """Raised when the configured model provider cannot return valid JSON."""


@dataclass
class ReviewerConfig:
    api_base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 180
    max_retries: int = 3
    use_response_format: bool = True

    @classmethod
    def from_env(cls) -> "ReviewerConfig":
        timeout_seconds = _positive_int_env("AGENTVAST_REVIEW_TIMEOUT", 180)
        max_retries = _positive_int_env("AGENTVAST_REVIEW_MAX_RETRIES", 3)
        return cls(
            api_base_url=(
                os.getenv("AGENTVAST_REVIEW_API_BASE_URL")
                or os.getenv("LLM_API_BASE_URL")
                or ""
            ).rstrip("/"),
            api_key=(
                os.getenv("AGENTVAST_REVIEW_API_KEY")
                or os.getenv("LLM_API_KEY")
                or ""
            ),
            model=(
                os.getenv("AGENTVAST_REVIEW_MODEL")
                or os.getenv("LLM_MODEL")
                or ""
            ),
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            use_response_format=os.getenv(
                "AGENTVAST_REVIEW_RESPONSE_FORMAT", "true"
            ).lower()
            not in {"0", "false", "no"},
        )

    def configured(self) -> bool:
        return bool(self.api_base_url and self.model)


class OpenAICompatibleReviewerProvider:
    """Minimal OpenAI-compatible JSON provider with compatibility fallback."""

    def __init__(self, config: Optional[ReviewerConfig] = None):
        self.config = config or ReviewerConfig.from_env()
        if not self.config.configured():
            raise ReviewerProviderError(
                "Reviewer API is not configured. Set AGENTVAST_REVIEW_API_BASE_URL, "
                "AGENTVAST_REVIEW_MODEL, and optionally AGENTVAST_REVIEW_API_KEY."
            )

    def review(self, prompt: str, task_mode: str) -> Dict[str, Any]:
        endpoint = self._endpoint()
        last_error: Optional[Exception] = None
        response_format = self.config.use_response_format
        for attempt in range(self.config.max_retries):
            payload: Dict[str, Any] = {
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 6000,
            }
            if response_format:
                payload["response_format"] = {"type": "json_object"}
            try:
                response = self._post(endpoint, payload)
                content = _message_content(response)
                parsed = _parse_json_object(content)
                parsed["_reviewer_meta"] = {
                    "task_mode": task_mode,
                    "model": self.config.model,
                }
                return parsed
            except HTTPError as error:
                last_error = error
                if error.code == 400 and response_format:
                    response_format = False
                    continue
                if error.code in {401, 403}:
                    break
            except (URLError, TimeoutError, ValueError, KeyError, ReviewerProviderError) as error:
                last_error = error
            if attempt < self.config.max_retries - 1:
                time.sleep((2 ** attempt) + random.random())
        raise ReviewerProviderError(
            "Reviewer task {0} failed: {1}".format(task_mode, last_error)
        )

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer {0}".format(self.config.api_key)
        request = Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=self.config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _endpoint(self) -> str:
        base = self.config.api_base_url
        if base.endswith("/v1"):
            return base + "/chat/completions"
        if base.endswith("/chat/completions"):
            return base
        return base + "/v1/chat/completions"


def _message_content(response: Dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ReviewerProviderError("provider response has no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        )
    raise ReviewerProviderError("provider response has no text content")


def _parse_json_object(content: str) -> Dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        text = text[first_newline + 1 :] if first_newline >= 0 else text
        if text.endswith("```"):
            text = text[:-3]
    try:
        value = json.loads(text.strip())
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ReviewerProviderError("Reviewer response is not a JSON object")
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ReviewerProviderError("Reviewer response must be a JSON object")
    return value


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default
