"""Model profiles: the only place that knows which LLM is driving.

The agent loop sees a LangChain chat model plus a ``ModelProfile``. Adding a model
means adding a profile here; nothing else changes.

``context_window`` is the budget the loop works within, which can be smaller than
what the model supports: for the local server it's the server's ``-c`` setting
(see ~/otherPeoplesCode/llama.cpp/run-vision-server.sh), and for paid models it
caps cost per call.

Paid (OpenRouter) profiles are defined but never run without an explicit
``--allow-paid``; see gb_agent/play.py.
"""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

LOCAL_SERVER = "http://127.0.0.1:8080/v1"


@dataclass(frozen=True)
class ModelProfile:
    name: str  # label used in logs and run metadata
    provider: str  # "local" (llama-server) or "openrouter"
    model: str  # model id at that provider
    context_window: int  # tokens; when the context nears this, it's compacted
    vision: bool  # can it take screenshots as images?
    base_url: str | None = None  # for local
    temperature: float = 0.7
    max_output_tokens: int = 1024
    # Screenshots shown after each step, latest first: 1 is just "after" (the
    # "before" is normally the previous step's "after", already in context).
    # Each costs ~25 s of image encoding on this CPU with the 8B.
    images_per_step: int = 1
    describer: str | None = None  # without vision: profile that describes screens
    # Compact when the context reaches this share of context_window. Local models
    # compact earlier: on this CPU generation slows as the context grows (the 8B
    # took ~140 s a call at 12k tokens).
    compact_at: float = 0.75

    @property
    def paid(self) -> bool:
        return self.provider != "local"


# The local server runs one model at a time (VISION_MODEL in run-vision-server.sh,
# set in the service's model.conf drop-in), so only the matching local profile
# works at any moment.
PROFILES: dict[str, ModelProfile] = {p.name: p for p in [
    ModelProfile(
        name="gemma-4-26b-local",
        provider="local",
        model="gemma-4-26b-a4b",  # llama-server's --alias
        base_url=LOCAL_SERVER,
        # The server gives Gemma 64k (its sliding-window layers make that cheap), but
        # generation slows as the context grows: 13.6 tok/s short, 4.3 at 19.5k. So
        # compact at ~26k: still ~3x fewer compactions than at 16k/0.5, which
        # compacted 23 times overnight and kept forgetting where it was.
        context_window=65_536,
        vision=True,
        compact_at=0.4,
        # Gemma thinks first (capped at 256 tokens by the server), and thinking
        # counts against this, so leave room for the tool call after it.
        max_output_tokens=1536,
    ),
    ModelProfile(
        name="qwen3-vl-8b-local",
        provider="local",
        model="qwen3-vl-8b",  # llama-server's --alias
        base_url=LOCAL_SERVER,
        context_window=16_384,
        vision=True,
        compact_at=0.5,
    ),
    ModelProfile(
        name="qwen3-vl-2b-local",
        provider="local",
        model="qwen3-vl-2b",  # llama-server's --alias
        base_url=LOCAL_SERVER,
        context_window=16_384,
        vision=True,
        compact_at=0.5,
    ),
    ModelProfile(
        name="qwen3-vl-8b",
        provider="openrouter",
        model="qwen/qwen3-vl-8b-instruct",
        context_window=64_000,
        vision=True,
        max_output_tokens=2048,
    ),
    ModelProfile(
        name="claude-haiku-5.5",
        provider="openrouter",
        model="anthropic/claude-haiku-5.5",
        context_window=24_000,  # every call re-sends the context, so this sets cost
        vision=True,
        max_output_tokens=2048,
    ),
]}


def get_profile(name: str) -> ModelProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(f"no model profile {name!r}; known: {', '.join(PROFILES)}") from None


def build_chat_model(profile: ModelProfile) -> BaseChatModel:
    if profile.provider == "local":
        # ChatDeepSeek, not ChatOpenAI: llama-server returns the model's thinking as
        # reasoning_content, which ChatOpenAI silently drops. ChatDeepSeek keeps it
        # in additional_kwargs, where the agent logs it (and the live page shows it).
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(
            model=profile.model,
            api_base=profile.base_url,
            api_key="not-needed",
            temperature=profile.temperature,
            max_tokens=profile.max_output_tokens,
            timeout=1_800,  # a full 16k context takes minutes on this CPU
            max_retries=0,  # the agent loop retries
        )
    if profile.provider == "openrouter":
        from agents.config import get_llm  # imports GCP secrets; only when needed

        return get_llm(profile.model, temperature=profile.temperature)
    raise ValueError(f"unknown provider {profile.provider!r}")
