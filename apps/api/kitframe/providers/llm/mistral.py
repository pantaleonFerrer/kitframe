from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

import httpx

from kitframe.errors import AppError, ErrorCode
from kitframe.settings import Settings

logger = logging.getLogger("kitframe.mistral")


class MistralLLMClient:
    key = "mistral"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.mistral.ai/v1",
        model: str = "mistral-large-2512",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.last_usage: dict[str, int] = {}

    def complete_json(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any],
        schema_name: str = "response",
        images: list[bytes] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        return asyncio.run(
            self.complete_json_async(
                system, user, json_schema, schema_name=schema_name, images=images, temperature=temperature
            )
        )

    async def complete_json_async(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any],
        schema_name: str = "response",
        images: list[bytes] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": user}]
        for img in (images or [])[:8]:
            b64 = base64.b64encode(img).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": f"data:image/png;base64,{b64}"}
            )
        body = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": 8192,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                },
            },
        }
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                raw = await self._chat(body)
                usage = raw.get("usage") or {}
                self.last_usage = {
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage.get("completion_tokens") or 0),
                }
                text = raw["choices"][0]["message"]["content"]
                parsed = json.loads(text)
                return parsed
            except (json.JSONDecodeError, KeyError, TypeError, AppError) as exc:
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue
                break
        raise AppError(
            ErrorCode.LLM_INVALID_OUTPUT,
            f"Invalid LLM output: {last_exc}",
            status_code=502,
        )

    async def _chat(self, body: dict[str, Any]) -> dict[str, Any]:
        delays_5xx = [2.0, 4.0]
        delays_429 = [1.0, 2.0, 4.0]
        a5 = 0
        a429 = 0
        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                try:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=body,
                    )
                except httpx.HTTPError as exc:
                    if a5 >= len(delays_5xx):
                        raise AppError(ErrorCode.PROVIDER_ERROR, str(exc), status_code=502) from exc
                    await asyncio.sleep(delays_5xx[a5])
                    a5 += 1
                    continue
                if resp.status_code in (401, 403):
                    raise AppError(
                        ErrorCode.PROVIDER_ERROR,
                        "Mistral auth failed",
                        status_code=502,
                        details={"code": "mistral_auth_failed"},
                    )
                if resp.status_code == 429:
                    if a429 >= len(delays_429):
                        raise AppError(ErrorCode.PROVIDER_ERROR, "Mistral rate limited", status_code=502)
                    await asyncio.sleep(delays_429[a429])
                    a429 += 1
                    continue
                if resp.status_code >= 500:
                    if a5 >= len(delays_5xx):
                        raise AppError(
                            ErrorCode.PROVIDER_ERROR,
                            f"Mistral HTTP {resp.status_code}",
                            status_code=502,
                        )
                    await asyncio.sleep(delays_5xx[a5])
                    a5 += 1
                    continue
                if resp.status_code >= 400:
                    raise AppError(
                        ErrorCode.PROVIDER_ERROR,
                        f"Mistral HTTP {resp.status_code}: {resp.text[:300]}",
                        status_code=502,
                    )
                return resp.json()


def mistral_from_settings(settings: Settings, llm_config: dict[str, Any] | None = None) -> MistralLLMClient:
    cfg = llm_config or {}
    return MistralLLMClient(
        api_key=settings.mistral_api_key,
        base_url=settings.mistral_api_base_url,
        model=str(cfg.get("model") or settings.llm_provider_model or "mistral-large-2512"),
    )
