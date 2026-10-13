from __future__ import annotations

from typing import Any, Protocol


class LLMClient(Protocol):
    def complete_json(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any],
        schema_name: str = "response",
        images: list[bytes] | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]: ...
