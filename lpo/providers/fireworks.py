"""Fireworks AI adapter (Section 8) — the only wired-up provider in v0.2.

OpenAI-compatible chat-completions API. Owns endpoint, auth, model IDs, how
structured output is requested, how thinking mode is toggled, transport retries,
and truncation detection.
"""

from __future__ import annotations

import json
import time
from typing import Any

import requests

from ..config import Config
from .base import (
    FormulationResult,
    ProviderCapabilities,
    ProviderError,
)


class FireworksProvider:
    name = "fireworks"
    capabilities = ProviderCapabilities(
        strict_schema=True,
        reasoning_toggle=True,
        tool_calling=True,
        prompt_cache_discount=True,
        max_context=256_000,
    )

    def __init__(self, config: Config):
        if not config.fireworks_api_key:
            raise ProviderError(
                "FIREWORKS_API_KEY is not set. Put it in .env or the environment "
                "(never in source — Section 12)."
            )
        self.config = config
        self._url = config.fireworks_base_url.rstrip("/") + "/chat/completions"

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #
    def formulate(
        self, messages: list[dict], schema: dict[str, Any]
    ) -> FormulationResult:
        body = {
            "model": self.config.formulation_model,
            "messages": messages,
            "temperature": self.config.formulation_temperature,
            "max_tokens": self.config.max_tokens,
            # Schema-constrained generation: the schema is enforced during decode.
            "response_format": {"type": "json_object", "schema": schema},
        }
        if self.config.enable_thinking:
            # Fireworks reasoning control. Field shape is an open question
            # (Section 15.2); confirm against current docs.
            body["reasoning_effort"] = "high"

        data = self._post(body)
        choice = data["choices"][0]
        message = choice["message"]
        finish = choice.get("finish_reason")
        truncated = finish == "length"

        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or message.get("reasoning")

        try:
            ir = json.loads(content)
        except json.JSONDecodeError as exc:
            # Under schema mode this almost always means truncation.
            raise ProviderError(
                f"Fireworks returned unparseable JSON (finish_reason={finish!r}). "
                f"Likely truncation; retry with higher max_tokens. {exc}"
            ) from exc

        return FormulationResult(
            ir=ir,
            reasoning=reasoning,
            truncated=truncated,
            usage=data.get("usage", {}),
        )

    def explain(self, messages: list[dict]) -> str:
        body = {
            "model": self.config.explanation_model,
            "messages": messages,
            "temperature": self.config.explanation_temperature,
            "max_tokens": self.config.max_tokens,
        }
        data = self._post(body)
        return (data["choices"][0]["message"].get("content") or "").strip()

    # ------------------------------------------------------------------ #
    # Transport with exponential backoff on 429 / 5xx (Section 8)          #
    # ------------------------------------------------------------------ #
    def _post(self, body: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.config.fireworks_api_key}",
            "Content-Type": "application/json",
        }
        last_exc: Exception | None = None
        for attempt in range(self.config.api_max_attempts):
            try:
                resp = requests.post(
                    self._url,
                    headers=headers,
                    json=body,
                    timeout=self.config.request_timeout,
                )
            except requests.RequestException as exc:
                last_exc = exc
                self._sleep(attempt)
                continue

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = ProviderError(
                    f"Fireworks {resp.status_code}: {resp.text[:300]}"
                )
                self._sleep(attempt)
                continue
            # 4xx other than 429 — not retryable.
            raise ProviderError(f"Fireworks {resp.status_code}: {resp.text[:500]}")

        raise ProviderError(
            f"Fireworks request failed after {self.config.api_max_attempts} "
            f"attempts: {last_exc}"
        )

    @staticmethod
    def _sleep(attempt: int) -> None:
        # 0.5, 1, 2, 4 ... seconds. Capped attempts keep cost bounded.
        time.sleep(min(0.5 * (2**attempt), 8.0))
