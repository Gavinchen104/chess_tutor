from __future__ import annotations

from dataclasses import dataclass, field, replace

from app.core.learned_params import learned_params
from app.core.levels import LevelProfile


MOVE_CHOICE_FEATURES = (
    "eval_gap",
    "difficulty",
    "safety_change",
    "center_change",
    "king_safety_change",
    "development_change",
    "mobility_change",
    "material_change",
    "opponent_pressure_change",
    "is_capture",
    "is_check",
    "is_castling",
    "num_preferred_tags",
    "num_priorities",
)

TUTOR_SCORE_FEATURES = (
    "eval_gap",
    "difficulty",
    "safety_change",
    "king_safety_change",
    "center_change",
    "opponent_pressure_change",
    "num_preferred_tags",
    "num_priorities",
)

FEATURE_SCALES = {
    "eval_gap": 120.0,
    "difficulty": 2.0,
    "safety_change": 120.0,
    "center_change": 25.0,
    "king_safety_change": 12.0,
    "development_change": 1.0,
    "mobility_change": 8.0,
    "material_change": 250.0,
    "opponent_pressure_change": 10.0,
    "is_capture": 1.0,
    "is_check": 1.0,
    "is_castling": 1.0,
    "num_preferred_tags": 3.0,
    "num_priorities": 3.0,
}

THEME_STYLE_SCORES = {
    "safety": ("safety_change", "king_safety_change"),
    "development": ("development_change", "num_preferred_tags"),
    "initiative": ("is_capture", "is_check", "opponent_pressure_change"),
    "center": ("center_change",),
}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def normalize_feature(name: str, value: float) -> float:
    return value / FEATURE_SCALES.get(name, 1.0)


def normalize_features(features: dict[str, float], feature_names: tuple[str, ...]) -> dict[str, float]:
    return {
        name: normalize_feature(name, float(features.get(name, 0.0)))
        for name in feature_names
    }


@dataclass
class DiagonalGaussianPosterior:
    means: dict[str, float] = field(default_factory=dict)
    variances: dict[str, float] = field(default_factory=dict)
    noise_variance: float = 0.8
    min_variance: float = 0.04

    def predict(self, features: dict[str, float]) -> float:
        return sum(self.means.get(name, 0.0) * value for name, value in features.items())

    def update(self, features: dict[str, float], target: float) -> None:
        active = {name: value for name, value in features.items() if abs(value) > 1e-9}
        if not active:
            return

        prediction = self.predict(active)
        innovation = target - prediction
        denom = self.noise_variance + sum(
            self.variances.get(name, 0.25) * value * value
            for name, value in active.items()
        )
        if denom <= 1e-9:
            return

        for name, value in active.items():
            variance = self.variances.get(name, 0.25)
            gain = variance * value / denom
            self.means[name] = self.means.get(name, 0.0) + gain * innovation
            self.variances[name] = max(self.min_variance, variance * (1.0 - gain * value))


def _default_adjustment_variances(level_key: str, feature_names: tuple[str, ...], *, model_name: str) -> dict[str, float]:
    if model_name == "move_choice":
        params = learned_params.get_move_choice_params(level_key)
        learned_feature_names = set(params.coefficients) if params is not None else set()
    else:
        params = learned_params.get_tutor_score_params(level_key)
        learned_feature_names = set(params.weights) if params is not None else set()
    return {
        name: 0.18 if name in learned_feature_names else 0.32
        for name in feature_names
    }


@dataclass
class SessionBayesianAdapter:
    level_key: str
    move_choice_posterior: DiagonalGaussianPosterior
    tutor_score_posterior: DiagonalGaussianPosterior
    skill_mean: float = 0.0
    skill_variance: float = 0.75
    move_observations: int = 0
    feedback_observations: int = 0

    @classmethod
    def for_level(cls, level_key: str) -> "SessionBayesianAdapter":
        return cls(
            level_key=level_key,
            move_choice_posterior=DiagonalGaussianPosterior(
                means={name: 0.0 for name in MOVE_CHOICE_FEATURES},
                variances=_default_adjustment_variances(level_key, MOVE_CHOICE_FEATURES, model_name="move_choice"),
                noise_variance=0.75,
            ),
            tutor_score_posterior=DiagonalGaussianPosterior(
                means={name: 0.0 for name in TUTOR_SCORE_FEATURES},
                variances=_default_adjustment_variances(level_key, TUTOR_SCORE_FEATURES, model_name="tutor_score"),
                noise_variance=0.7,
            ),
        )

    def move_choice_adjustment(self, model_features: dict[str, float]) -> float:
        return self.move_choice_posterior.predict(normalize_features(model_features, MOVE_CHOICE_FEATURES))

    def tutor_score_adjustment(self, model_features: dict[str, float]) -> float:
        return self.tutor_score_posterior.predict(normalize_features(model_features, TUTOR_SCORE_FEATURES))

    def observe_move_choice(
        self,
        chosen_features: dict[str, float],
        *,
        tutor_features: dict[str, float] | None = None,
        eval_gap_cp: int = 0,
        difficulty: float = 1.0,
        tactical_risk_score: float = 0.0,
        mistake_class: str = "practical",
        level: LevelProfile | None = None,
    ) -> None:
        chosen = normalize_features(chosen_features, MOVE_CHOICE_FEATURES)
        if tutor_features is None:
            signal = chosen
        else:
            tutor = normalize_features(tutor_features, MOVE_CHOICE_FEATURES)
            signal = {
                name: chosen.get(name, 0.0) - tutor.get(name, 0.0)
                for name in MOVE_CHOICE_FEATURES
            }
        self.move_choice_posterior.update(signal, target=0.85)
        self.move_observations += 1
        self._update_skill(eval_gap_cp, difficulty, tactical_risk_score, mistake_class, level)

    def observe_feedback(self, tutor_features: dict[str, float], ratings: dict[str, float]) -> None:
        normalized = normalize_features(tutor_features, TUTOR_SCORE_FEATURES)
        score = _clamp(
            (
                (ratings.get("clarity", 3.0) - 3.0)
                + (ratings.get("usefulness", 3.0) - 3.0)
                + (ratings.get("actionability", 3.0) - 3.0)
                + (ratings.get("overwhelm_reduction", 3.0) - 3.0)
            ) / 8.0,
            -1.0,
            1.0,
        )
        self.tutor_score_posterior.update(normalized, target=score)
        self.feedback_observations += 1

    def adapt_level(self, level: LevelProfile) -> LevelProfile:
        if level.key != self.level_key:
            return level
        skill = _clamp(self.skill_mean, -1.4, 1.4)
        complexity_weight = _clamp(level.complexity_weight * (1.0 - 0.16 * skill), 6.0, 80.0)
        max_eval_loss = int(round(_clamp(level.max_eval_loss * (1.0 - 0.12 * skill), 12.0, 140.0)))
        description = level.description
        if abs(skill) >= 0.25:
            direction = "slightly stronger" if skill > 0 else "slightly more supportive"
            description = f"{level.description} Live Bayesian adaptation currently treats this session as {direction} than baseline."
        return replace(
            level,
            complexity_weight=complexity_weight,
            max_eval_loss=max_eval_loss,
            description=description,
        )

    def summary(self, level: LevelProfile) -> dict[str, object]:
        adjusted_level = self.adapt_level(level)
        skill_shift = _clamp(self.skill_mean, -1.4, 1.4)
        estimated_elo = int(round(level.elo + skill_shift * 140.0))
        style_scores = {
            theme: sum(self.move_choice_posterior.means.get(feature, 0.0) for feature in features)
            for theme, features in THEME_STYLE_SCORES.items()
        }
        preferred_theme = max(style_scores, key=style_scores.get) if style_scores else "activity"
        observation_count = self.move_observations + self.feedback_observations
        if observation_count >= 12:
            confidence = "High"
        elif observation_count >= 5:
            confidence = "Medium"
        else:
            confidence = "Low"
        return {
            "estimated_elo": estimated_elo,
            "preferred_theme": preferred_theme,
            "confidence": confidence,
            "move_observations": self.move_observations,
            "feedback_observations": self.feedback_observations,
            "adjusted_complexity_weight": adjusted_level.complexity_weight,
            "adjusted_max_eval_loss": adjusted_level.max_eval_loss,
        }

    def _update_skill(
        self,
        eval_gap_cp: int,
        difficulty: float,
        tactical_risk_score: float,
        mistake_class: str,
        level: LevelProfile | None,
    ) -> None:
        max_eval = float(level.max_eval_loss if level is not None else 70)
        quality = 1.0 - min(1.8, eval_gap_cp / max(1.0, max_eval * 2.0))
        complexity = min(1.2, max(0.0, difficulty - 1.0) / 2.5)
        tactical_penalty = min(1.2, tactical_risk_score / 50.0)
        verdict_penalty = {
            "best": 0.0,
            "practical": 0.15,
            "inaccuracy": 0.35,
            "mistake": 0.65,
            "blunder": 1.0,
        }.get(mistake_class, 0.35)
        observation = _clamp(quality - 0.35 * complexity - 0.4 * tactical_penalty - verdict_penalty, -1.2, 1.2)
        gain = self.skill_variance / (self.skill_variance + 0.55)
        self.skill_mean = _clamp(self.skill_mean + gain * (observation - self.skill_mean), -1.5, 1.5)
        self.skill_variance = max(0.08, self.skill_variance * (1.0 - gain))
