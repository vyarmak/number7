from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field


class PreRegistration(BaseModel):
    """Machine-readable hypothesis (blueprint §5): committed BEFORE any backtest runs;
    the harness enforces the declared parameter space."""

    family: str
    origin: Literal["human", "llm"]
    mechanism: str = Field(min_length=40)
    citations: list[str] = Field(min_length=1)
    expected_effect: str
    falsification: str
    param_space: dict[str, list]

    @property
    def search_space_size(self) -> int:
        return math.prod(len(v) for v in self.param_space.values()) or 1
