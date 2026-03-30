from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LevelProfile:
    key: str
    label: str
    elo: int
    description: str
    complexity_weight: float
    max_eval_loss: int
    preferred_tags: tuple[str, ...]
    commentary_style: str


LEVELS: dict[str, LevelProfile] = {
    "600": LevelProfile(
        key="600",
        label="600 - Foundations",
        elo=600,
        description="Prioritize safety, one-move threats, and basic development.",
        complexity_weight=52.0,
        max_eval_loss=90,
        preferred_tags=("safety", "development", "king_safety", "center"),
        commentary_style="Keep it concrete and habit-focused.",
    ),
    "1000": LevelProfile(
        key="1000",
        label="1000 - Improving",
        elo=1000,
        description="Mix simple tactics with opening principles and cleaner piece activity.",
        complexity_weight=34.0,
        max_eval_loss=70,
        preferred_tags=("safety", "development", "center", "initiative"),
        commentary_style="Name the idea, then the practical habit behind it.",
    ),
    "1400": LevelProfile(
        key="1400",
        label="1400 - Club Player",
        elo=1400,
        description="Allow stronger tactical moves while still avoiding unnecessary complexity.",
        complexity_weight=20.0,
        max_eval_loss=45,
        preferred_tags=("initiative", "center", "activity", "king_safety"),
        commentary_style="Connect tactics to piece coordination and plans.",
    ),
    "1800": LevelProfile(
        key="1800",
        label="1800 - Advanced Club",
        elo=1800,
        description="Prefer the strongest line unless a near-equal move is clearly easier to execute.",
        complexity_weight=10.0,
        max_eval_loss=20,
        preferred_tags=("initiative", "activity", "conversion", "king_safety"),
        commentary_style="Explain concrete calculation with one strategic takeaway.",
    ),
}


def get_level(level_key: str) -> LevelProfile:
    return LEVELS.get(level_key, LEVELS["1000"])
