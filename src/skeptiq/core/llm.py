from dataclasses import dataclass
from typing import Any, TypeVar

import instructor
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from skeptiq.core.config import Settings
from skeptiq.core.logging import get_logger

log = get_logger(__name__)

# Pricing for claude-sonnet-4-6 (USD per million tokens).
# https://www.anthropic.com/pricing  — kept here so cost_usd is computed locally.
PRICE_INPUT_PER_MTOK = 3.0
PRICE_OUTPUT_PER_MTOK = 15.0
PRICE_CACHE_WRITE_PER_MTOK = 3.75
PRICE_CACHE_READ_PER_MTOK = 0.30

T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True, kw_only=True)
class LlmCallResult[T: BaseModel]:
    parsed: T
    tokens_input: int
    tokens_output: int
    cache_creation_tokens: int
    cache_read_tokens: int
    cost_usd: float


def _compute_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
) -> float:
    return (
        input_tokens * PRICE_INPUT_PER_MTOK
        + output_tokens * PRICE_OUTPUT_PER_MTOK
        + cache_creation_tokens * PRICE_CACHE_WRITE_PER_MTOK
        + cache_read_tokens * PRICE_CACHE_READ_PER_MTOK
    ) / 1_000_000


class LlmClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._raw = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._client = instructor.from_anthropic(self._raw)

    @property
    def model(self) -> str:
        return self._settings.llm_model

    async def analyze[T: BaseModel](
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        max_tokens: int = 2048,
    ) -> LlmCallResult[T]:
        parsed, completion = await self._client.messages.create_with_completion(
            model=self._settings.llm_model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
            response_model=response_model,
            max_retries=2,
        )
        usage: Any = completion.usage
        cache_creation = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        input_tokens = int(usage.input_tokens)
        output_tokens = int(usage.output_tokens)

        cost = _compute_cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_tokens=cache_creation,
            cache_read_tokens=cache_read,
        )

        log.debug(
            "llm_call_complete",
            model=self._settings.llm_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_tokens=cache_creation,
            cache_read_tokens=cache_read,
            cost_usd=round(cost, 6),
        )

        return LlmCallResult(
            parsed=parsed,
            tokens_input=input_tokens,
            tokens_output=output_tokens,
            cache_creation_tokens=cache_creation,
            cache_read_tokens=cache_read,
            cost_usd=cost,
        )

    async def aclose(self) -> None:
        await self._raw.close()
