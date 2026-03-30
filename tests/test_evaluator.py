from app.core.evaluator import MoveFeedback, build_review


def test_build_review_surfaces_missed_priority():
    review = build_review(
        [
            MoveFeedback(
                chosen_san="h3",
                best_san="Nf3",
                tutor_san="Nf3",
                score_delta_cp=120,
                verdict="Inaccuracy",
                lesson="Missed development.",
                themes=["activity"],
                addressed_priorities=[],
                missed_priority="development",
                coach_note="Primary coaching goal: address development first.",
            ),
            MoveFeedback(
                chosen_san="a3",
                best_san="O-O",
                tutor_san="O-O",
                score_delta_cp=180,
                verdict="Blunder risk",
                lesson="Missed king safety.",
                themes=["activity"],
                addressed_priorities=[],
                missed_priority="king_safety",
                coach_note="Primary coaching goal: address king safety first.",
            ),
        ],
        "[Event \"Test\"]\n*",
    )
    assert any("missed theme" in finding.lower() for finding in review.findings)
    assert "main lesson" in review.summary.lower()
