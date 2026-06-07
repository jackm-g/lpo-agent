"""Configuration (Section 3, 8, 13). One active provider per deployment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # Load .env if present; harmless if python-dotenv is missing.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


# Fireworks model IDs (Section 3.1). Confirm against the live catalog before deploy.
FIREWORKS_FORMULATION_MODEL = "accounts/fireworks/models/gemma-4-31b-it"
FIREWORKS_EXPLANATION_MODEL = "accounts/fireworks/models/gemma-4-26b-a4b-it"


@dataclass
class Config:
    provider: str = "fireworks"
    fireworks_api_key: str | None = None
    fireworks_base_url: str = "https://api.fireworks.ai/inference/v1"
    formulation_model: str = FIREWORKS_FORMULATION_MODEL
    explanation_model: str = FIREWORKS_EXPLANATION_MODEL
    # Inference controls (Sections 6.1, 6.4).
    formulation_temperature: float = 0.0
    explanation_temperature: float = 0.3
    max_tokens: int = 4096
    enable_thinking: bool = True
    request_timeout: int = 120
    api_max_attempts: int = 4  # transport-level retries (429/5xx backoff)
    enable_critic: bool = True
    extra: dict = field(default_factory=dict)


def load_config() -> Config:
    """Build a Config from environment variables (Section 12: keys from env)."""

    return Config(
        provider=os.environ.get("LPO_PROVIDER", "fireworks").lower(),
        fireworks_api_key=os.environ.get("FIREWORKS_API_KEY"),
        fireworks_base_url=os.environ.get(
            "FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1"
        ),
        formulation_model=os.environ.get(
            "LPO_FORMULATION_MODEL", FIREWORKS_FORMULATION_MODEL
        ),
        explanation_model=os.environ.get(
            "LPO_EXPLANATION_MODEL", FIREWORKS_EXPLANATION_MODEL
        ),
        max_tokens=int(os.environ.get("LPO_MAX_TOKENS", "4096")),
        enable_thinking=os.environ.get("LPO_ENABLE_THINKING", "true").lower()
        == "true",
        request_timeout=int(os.environ.get("LPO_REQUEST_TIMEOUT", "120")),
        enable_critic=os.environ.get("LPO_ENABLE_CRITIC", "true").lower() == "true",
    )
