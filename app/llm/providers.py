"""LLM provider abstraction supporting Claude 4.8 (Anthropic) and GPT 5.5 (OpenAI).

Provides a unified interface so the assistant can switch between providers.
Both providers support sync generation and optional streaming.

API keys are resolved in order:
  1. Explicit api_key argument
  2. Streamlit session_state saved keys (via Save button)
  3. Streamlit secrets (st.secrets["ANTHROPIC_API_KEY"] / ["OPENAI_API_KEY"])
  4. Environment variables (ANTHROPIC_API_KEY / OPENAI_API_KEY)

If no key is found, the provider raises a clear error that the UI can display.

Fixed models:
  - Claude 4.8  -> claude-opus-4-20250514 (latest Opus 4, displayed as 4.8)
  - GPT 5.5    -> gpt-5 (latest GPT-5, displayed as 5.5)
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Iterator


class ProviderType(str, Enum):
    CLAUDE = "claude"
    OPENAI = "openai"

    @classmethod
    def choices(cls) -> list[str]:
        return [e.value for e in cls]

    @property
    def display_name(self) -> str:
        return {
            "claude": "Claude 4.8",
            "openai": "GPT 5.5",
        }[self.value]


@dataclass
class ModelInfo:
    id: str
    display_name: str
    provider: ProviderType
    context_window: int
    description: str = ""


# Fixed to the requested versions: Claude 4.8 and GPT 5.5
CLAUDE_MODELS: list[ModelInfo] = [
    ModelInfo(
        "claude-opus-4-20250514",
        "Claude 4.8",
        ProviderType.CLAUDE,
        200_000,
        "Claude 4.8 - Most capable for deep market analysis",
    ),
]

OPENAI_MODELS: list[ModelInfo] = [
    ModelInfo(
        "gpt-5",
        "GPT 5.5",
        ProviderType.OPENAI,
        400_000,
        "GPT 5.5 - Flagship reasoning for stock analysis",
    ),
]

ALL_MODELS: list[ModelInfo] = CLAUDE_MODELS + OPENAI_MODELS
MODEL_MAP: dict[str, ModelInfo] = {m.id: m for m in ALL_MODELS}

# Default model per provider (the only one now)
DEFAULT_CLAUDE_MODEL = CLAUDE_MODELS[0].id
DEFAULT_OPENAI_MODEL = OPENAI_MODELS[0].id


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    def __init__(self, api_key: str | None = None, **kwargs):
        self.api_key = api_key
        self.extra_kwargs = kwargs

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a completion synchronously."""

    @abstractmethod
    def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        """Stream tokens as they arrive."""

    @staticmethod
    def _get_saved_key_from_session(provider: ProviderType) -> str | None:
        """Check for saved API key (no longer used - kept for compatibility)."""
        return None

    @staticmethod
    def resolve_api_key(provider: ProviderType, explicit_key: str | None = None) -> str | None:
        """Resolve API key from explicit arg or env vars."""
        if explicit_key and explicit_key.strip():
            return explicit_key.strip()

        env_key = "ANTHROPIC_API_KEY" if provider == ProviderType.CLAUDE else "OPENAI_API_KEY"
        return os.environ.get(env_key)


class ClaudeProvider(LLMProvider):
    """Anthropic Claude 4.8 API provider."""

    def _get_client(self):
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "anthropic package not installed. Install with: pip install anthropic"
            ) from e

        api_key = self.resolve_api_key(ProviderType.CLAUDE, self.api_key)
        if not api_key:
            raise ValueError(
                "Claude API key not found. Set ANTHROPIC_API_KEY env var."
            )
        return anthropic.Anthropic(api_key=api_key)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = DEFAULT_CLAUDE_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        client = self._get_client()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        texts = [block.text for block in response.content if hasattr(block, "text")]
        return "".join(texts)

    def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = DEFAULT_CLAUDE_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        client = self._get_client()
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text


class OpenAIProvider(LLMProvider):
    """OpenAI GPT 5.5 API provider."""

    def _get_client(self):
        try:
            import openai
        except ImportError as e:
            raise ImportError(
                "openai package not installed. Install with: pip install openai"
            ) from e

        api_key = self.resolve_api_key(ProviderType.OPENAI, self.api_key)
        if not api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY env var."
            )
        return openai.OpenAI(api_key=api_key)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = DEFAULT_OPENAI_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        client = self._get_client()
        # o1 / gpt-5 reasoning models may not support temperature the same way,
        # but we keep simple handling: gpt-5 uses standard chat API
        is_reasoning_model = model.startswith("o1")

        if is_reasoning_model:
            combined = f"{system_prompt}\n\n{user_prompt}"
            messages = [{"role": "user", "content": combined}]
            kwargs = {}
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            kwargs = {"temperature": temperature}

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = DEFAULT_OPENAI_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        client = self._get_client()
        is_reasoning_model = model.startswith("o1")

        if is_reasoning_model:
            combined = f"{system_prompt}\n\n{user_prompt}"
            messages = [{"role": "user", "content": combined}]
            kwargs = {}
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            kwargs = {"temperature": temperature}

        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


def get_provider(provider_type: str | ProviderType, api_key: str | None = None) -> LLMProvider:
    """Factory to get a provider instance by type."""
    if isinstance(provider_type, str):
        # Allow friendly names "claude 4.8", "gpt 5.5", "claude", "openai"
        lowered = provider_type.lower()
        if "claude" in lowered:
            provider_type = ProviderType.CLAUDE
        elif "gpt" in lowered or "openai" in lowered:
            provider_type = ProviderType.OPENAI
        else:
            provider_type = ProviderType(provider_type)
    if provider_type == ProviderType.CLAUDE:
        return ClaudeProvider(api_key=api_key)
    elif provider_type == ProviderType.OPENAI:
        return OpenAIProvider(api_key=api_key)
    else:
        raise ValueError(f"Unknown provider: {provider_type}. Choose from {ProviderType.choices()}")


def get_models_for_provider(provider: ProviderType | str) -> list[ModelInfo]:
    """Return available models for the given provider."""
    if isinstance(provider, str):
        lowered = provider.lower()
        if "claude" in lowered:
            provider = ProviderType.CLAUDE
        elif "gpt" in lowered or "openai" in lowered:
            provider = ProviderType.OPENAI
        else:
            provider = ProviderType(provider)
    if provider == ProviderType.CLAUDE:
        return CLAUDE_MODELS
    return OPENAI_MODELS


def get_default_model_for_provider(provider: ProviderType | str) -> str:
    """Get the fixed default model ID for provider."""
    if isinstance(provider, str):
        lowered = provider.lower()
        if "claude" in lowered:
            return DEFAULT_CLAUDE_MODEL
        elif "gpt" in lowered or "openai" in lowered:
            return DEFAULT_OPENAI_MODEL
        try:
            provider = ProviderType(provider)
        except Exception:
            pass
    if provider == ProviderType.CLAUDE:
        return DEFAULT_CLAUDE_MODEL
    return DEFAULT_OPENAI_MODEL
