from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EngineMetadata:
    provider: str
    analysis_depth: int
    multipv: int
    stockfish_path: str | None = None
    fallback_reason: str | None = None


@dataclass
class DiagnosticFinding:
    category: str
    code: str
    severity: str
    direction: str
    theme: str
    summary: str
    detail: str = ""
    training_habit: str = ""


@dataclass
class CandidateMove:
    san: str
    uci: str
    score_cp: int
    eval_gap_cp: int
    tutor_score: float
    difficulty: float
    tactical_risk_score: float
    strategic_fit_score: float
    human_plausibility_score: float
    mistake_class: str
    primary_theme: str
    primary_reason: str
    player_friendly_explanation: str
    training_habit: str
    better_alternative_reason: str
    tags: list[str] = field(default_factory=list)
    priorities_addressed: list[str] = field(default_factory=list)
    model_features: dict[str, float] = field(default_factory=dict)
    plan: str = ""
    tactical_findings: list[DiagnosticFinding] = field(default_factory=list)
    strategic_findings: list[DiagnosticFinding] = field(default_factory=list)


@dataclass
class PositionAnalysisReport:
    board_fen: str
    side_to_move: str
    level_key: str
    level_label: str
    engine_metadata: EngineMetadata
    position_needs: list[str]
    overview: str
    tutor_explanation: str
    evaluation_story: str
    engine_best_move: CandidateMove
    tutor_move: CandidateMove
    candidate_moves: list[CandidateMove]


@dataclass
class MoveCoachingReport:
    board_fen: str
    move_number: int
    player_color: str
    chosen_move: CandidateMove
    engine_best_move: CandidateMove
    tutor_move: CandidateMove
    eval_before_cp: int
    eval_after_cp: int
    score_delta_cp: int
    verdict: str
    coach_note: str
    lesson: str


@dataclass
class AnnotatedGameMove:
    move_number: int
    player_color: str
    san: str
    eval_before_cp: int
    eval_after_cp: int
    tutor_gap_cp: int
    verdict: str
    primary_theme: str
    explanation: str
    suggested_alternative_san: str
    training_habit: str


@dataclass
class GameReviewReport:
    pgn: str
    annotated_moves: list[AnnotatedGameMove]
    critical_moments: list[str]
    recurring_patterns: list[str]
    strengths: list[str]
    next_steps: list[str]
    findings: list[str]
    summary: str


@dataclass
class EvaluationExample:
    label: str
    level_key: str
    theme: str
    engine_move: str
    tutor_move: str
    eval_gap_cp: int
    explanation: str
    differed_from_engine: bool


@dataclass
class TutorEvaluationResult:
    engine_available: bool
    benchmark_count: int
    game_count: int
    metrics: dict[str, float]
    position_examples: list[EvaluationExample]
    game_summaries: list[str]
    user_feedback_rubric: dict[str, str]
