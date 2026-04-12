import chess

from app.core.adaptation import SessionBayesianAdapter
from app.core.levels import get_level
from app.core.move_engine import MoveEngine
from app.core.services import AnalysisService


def test_session_adapter_updates_from_moves_and_feedback():
    adapter = SessionBayesianAdapter.for_level("1000")
    features = {
        "eval_gap": 35.0,
        "difficulty": 1.4,
        "safety_change": 40.0,
        "center_change": 15.0,
        "king_safety_change": 8.0,
        "development_change": 1.0,
        "mobility_change": 3.0,
        "material_change": 0.0,
        "opponent_pressure_change": 2.0,
        "is_capture": 0.0,
        "is_check": 0.0,
        "is_castling": 1.0,
        "num_preferred_tags": 2.0,
        "num_priorities": 2.0,
    }

    assert adapter.move_choice_adjustment(features) == 0.0
    assert adapter.tutor_score_adjustment(features) == 0.0

    adapter.observe_move_choice(
        features,
        tutor_features={**features, "development_change": 0.0},
        eval_gap_cp=110,
        difficulty=2.1,
        tactical_risk_score=26.0,
        mistake_class="mistake",
        level=get_level("1000"),
    )
    adapter.observe_feedback(
        features,
        {
            "clarity": 5,
            "usefulness": 5,
            "actionability": 4,
            "overwhelm_reduction": 4,
        },
    )

    assert adapter.move_observations == 1
    assert adapter.feedback_observations == 1
    assert adapter.move_choice_adjustment(features) != 0.0
    assert adapter.tutor_score_adjustment(features) != 0.0


def test_session_adapter_can_shift_effective_level_supportiveness():
    adapter = SessionBayesianAdapter.for_level("600")
    level = get_level("600")
    features = {
        "eval_gap": 180.0,
        "difficulty": 2.7,
        "safety_change": -120.0,
        "center_change": 0.0,
        "king_safety_change": -8.0,
        "development_change": 0.0,
        "mobility_change": -2.0,
        "material_change": -100.0,
        "opponent_pressure_change": 0.0,
        "is_capture": 0.0,
        "is_check": 0.0,
        "is_castling": 0.0,
        "num_preferred_tags": 0.0,
        "num_priorities": 0.0,
    }

    adapter.observe_move_choice(
        features,
        eval_gap_cp=220,
        difficulty=2.8,
        tactical_risk_score=44.0,
        mistake_class="blunder",
        level=level,
    )
    adapted = adapter.adapt_level(level)

    assert adapted.max_eval_loss >= level.max_eval_loss
    assert adapted.complexity_weight >= level.complexity_weight


def test_analysis_service_preserves_model_features_in_candidate_reports():
    board = chess.Board()
    service = AnalysisService(MoveEngine(adapter=SessionBayesianAdapter.for_level("1000")))
    report = service.analyze_position(board, get_level("1000"))

    assert report.tutor_move.model_features
    assert "eval_gap" in report.tutor_move.model_features
