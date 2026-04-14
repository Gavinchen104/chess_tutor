from __future__ import annotations

import hashlib

from app.core.levels import LevelProfile
from app.core.reports import CandidateMove, PositionAnalysisReport


def _theme_label(theme: str) -> str:
    return theme.replace("_", " ")


def format_cp(score_cp: int) -> str:
    if abs(score_cp) >= 90000:
        return "winning by force" if score_cp > 0 else "losing by force"
    return f"{score_cp / 100:.1f}"


def _pick_template(templates: list[str], key: str) -> str:
    if not templates:
        return ""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % len(templates)
    return templates[index]


def _join_themes(items: list[str]) -> str:
    return ", ".join(_theme_label(item) for item in items if item)


def _build_complexity_sentence(move: CandidateMove, key: str) -> str:
    if move.difficulty < 1.2:
        templates = [
            "This should be easy to execute at this rating.",
            "Execution should feel straightforward for this level.",
            "This move is practical and should be easy to carry out at this rating.",
            "The idea is simple enough to play confidently in a real game.",
        ]
    elif move.difficulty < 2.0:
        templates = [
            "This asks for some calculation, but the main idea is still practical.",
            "There is some calculation involved, but the plan is still practical.",
            "You need a bit of accuracy here, yet the core idea remains manageable.",
            "This line asks for attention, but it stays within practical complexity.",
        ]
    else:
        templates = [
            "This is sharper and needs more accuracy to execute well.",
            "This is a sharper choice and it requires accurate follow-up.",
            "The move is playable, but it demands precise calculation to hold up.",
            "Complexity is higher here, so execution discipline matters.",
        ]
    return _pick_template(templates, key)


def build_position_summary(analysis: PositionAnalysisReport, level: LevelProfile) -> str:
    tutor = analysis.tutor_move
    best = analysis.engine_best_move
    needs_text = _join_themes(analysis.position_needs[:2]) or "steady piece improvement"
    tag_text = _join_themes(tutor.tags[:2]) or "solid principles"

    if tutor.uci == best.uci:
        templates = [
            "For {level_label}, `{tutor_san}` is both the strongest move I found and the cleanest teaching move. "
            "It keeps the position around {score_text} and leans on {tag_text}. "
            "Right now the main coaching focus is {needs_text}.",
            "For {level_label}, `{tutor_san}` is both the strongest move and the clearest teaching choice. "
            "It keeps the evaluation around {score_text}, emphasizes {tag_text}, and keeps focus on {needs_text}.",
            "At {level_label}, `{tutor_san}` works as both engine best and best teaching move. "
            "You keep the position near {score_text}, with a practical plan around {tag_text} and {needs_text}.",
            "`{tutor_san}` is the rare move that is both strongest and easiest to teach for {level_label}. "
            "It keeps the game near {score_text} while reinforcing {tag_text}; current coaching priority is {needs_text}.",
        ]
        template = _pick_template(templates, f"agree|{analysis.board_fen}|{level.key}|{tutor.uci}")
        return template.format(
            level_label=level.label,
            tutor_san=tutor.san,
            score_text=format_cp(tutor.score_cp),
            tag_text=tag_text,
            needs_text=needs_text,
        )

    templates = [
        "The engine-style top move is `{best_san}` at {best_score}, but for {level_label} "
        "I recommend `{tutor_san}` instead. It stays within a practical margin while emphasizing "
        "{tag_text} over calculation-heavy play. The move also helps with {needs_text}.",
        "Engine preference is `{best_san}` ({best_score}), but for {level_label} the tutor selects `{tutor_san}`. "
        "It stays practical while prioritizing {tag_text} and directly addressing {needs_text}.",
        "`{best_san}` is the strongest engine line at {best_score}, yet `{tutor_san}` is a better teaching fit for {level_label}. "
        "The trade favors practical execution through {tag_text} with focus on {needs_text}.",
        "For pure engine strength `{best_san}` leads ({best_score}), but the tutor recommends `{tutor_san}` for {level_label}. "
        "It keeps enough strength and gives a clearer practical plan around {tag_text} and {needs_text}.",
    ]
    template = _pick_template(templates, f"split|{analysis.board_fen}|{level.key}|{best.uci}|{tutor.uci}")
    return template.format(
        best_san=best.san,
        best_score=format_cp(best.score_cp),
        level_label=level.label,
        tutor_san=tutor.san,
        tag_text=tag_text,
        needs_text=needs_text,
    )


def build_move_explanation(move: CandidateMove, level: LevelProfile) -> str:
    theme_templates = [
        "Primary teaching theme: {theme}.",
        "Primary teaching theme remains {theme}.",
        "Main training focus in this move: {theme}.",
        "Core teaching idea here is {theme}.",
    ]
    theme_sentence = _pick_template(
        theme_templates,
        f"theme|{move.uci}|{move.primary_theme}|{level.key}",
    ).format(theme=_theme_label(move.primary_theme))

    supporting_sentence = ""
    if move.priorities_addressed:
        readable = _join_themes(move.priorities_addressed[:2])
        support_templates = [
            "Supporting teaching themes: {themes}.",
            "Secondary ideas reinforced by this move: {themes}.",
            "Additional coaching angles include {themes}.",
        ]
        supporting_sentence = _pick_template(
            support_templates,
            f"support-priority|{move.uci}|{readable}|{level.key}",
        ).format(themes=readable)
    elif move.tags:
        extras = [tag for tag in move.tags if tag != move.primary_theme]
        if extras:
            readable = _join_themes(extras[:2])
            support_templates = [
                "Supporting teaching themes: {themes}.",
                "Secondary ideas reinforced by this move: {themes}.",
                "Additional coaching angles include {themes}.",
            ]
            supporting_sentence = _pick_template(
                support_templates,
                f"support-tags|{move.uci}|{readable}|{level.key}",
            ).format(themes=readable)

    complexity = _build_complexity_sentence(move, f"complexity|{move.uci}|{level.key}")
    style_sentence = level.commentary_style

    return " ".join(
        part.strip()
        for part in (
            move.player_friendly_explanation,
            theme_sentence,
            supporting_sentence,
            complexity,
            style_sentence,
        )
        if part.strip()
    )


def build_engine_vs_tutor_story(analysis: PositionAnalysisReport, level: LevelProfile) -> str:
    tutor = analysis.tutor_move
    best = analysis.engine_best_move
    if tutor.uci == best.uci:
        templates = [
            "In this position the tutor and engine agree, which is useful evidence that the tutoring layer "
            "is not inventing weaker moves just to sound friendly.",
            "Tutor and engine agree in this position, which is a useful sign that the teaching layer is not sacrificing strength unnecessarily.",
            "Here the tutor matches the engine, showing that teaching guidance can align with top engine quality.",
            "This is a full agreement case: tutor and engine point to the same move, so practicality and strength line up cleanly.",
        ]
        return _pick_template(templates, f"story-agree|{analysis.board_fen}|{level.key}|{tutor.uci}")

    gap = max(0, best.score_cp - tutor.score_cp)
    needs_text = _join_themes(analysis.position_needs[:2]) or "piece coordination"
    templates = [
        "The tutor accepts about {gap_pawns} pawns of theoretical loss to make the move more teachable for {level_label}. "
        "The tradeoff is intentional: the tutor is trying to solve the position's main practical needs ({needs_text}) "
        "instead of only maximizing engine score.",
        "The tutor gives up about {gap_pawns} pawns of theoretical value to improve teachability for {level_label}. "
        "That tradeoff is intentional: it prioritizes practical needs ({needs_text}) over pure engine maximization.",
        "Compared with the engine line, the tutor accepts roughly {gap_pawns} pawns of loss for {level_label}. "
        "The goal is practical clarity around {needs_text}, not just top-line evaluation.",
        "The selected tutor move is about {gap_pawns} pawns below the engine peak, on purpose. "
        "For {level_label}, solving practical needs like {needs_text} can be more instructive than squeezing maximum eval.",
    ]
    template = _pick_template(templates, f"story-split|{analysis.board_fen}|{level.key}|{best.uci}|{tutor.uci}")
    return template.format(
        gap_pawns=f"{gap / 100:.1f}",
        level_label=level.label,
        needs_text=needs_text,
    )
