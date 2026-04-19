"""
LLM-as-judge A/B preference study.

For each sampled position, three persona-conditioned LLM raters (a notional
600, 1000, and 1400 ELO player) see the same two blinded pieces of advice:

    Advice A: <engine-style or tutor-style, randomized>
    Advice B: <the other one>

and answer three forced-choice preference questions plus a short free-text
reason. Responses are appended to ``analysis/results/ab_feedback.jsonl`` with
an explicit ``rater_id`` of the form ``llm-judge:<model>:<persona>``, so they
are trivially separable from any human ratings collected via the interactive
CLI.

This script is intended as an *automated, complementary* source of anecdotal
evidence alongside (a) quantitative ``tutor_vs_engine`` metrics and (b) any
human A/B ratings. It is NOT a substitute for human feedback and is labelled
as such in both the data and the summaries.

Authentication: requires ``ANTHROPIC_API_KEY`` in the environment or in a
``.env`` file at the repo root. The default model is Claude Haiku for cost.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chess
import chess.pgn

from app.core.levels import LEVELS
from app.core.services import AnalysisService
from analysis.collect_ab_feedback import (
    render_engine_view,
    render_tutor_view,
    append_entry,
    load_entries,
)
from analysis.tutor_vs_engine import (
    iter_pgn_files,
    sample_positions_from_pgn,
    dedupe_positions,
    DEFAULT_PGN_SOURCES,
)

DEFAULT_POSITIONS_PATH = REPO_ROOT / "data" / "benchmarks" / "positions_v2.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "analysis" / "results" / "ab_feedback.jsonl"
DEFAULT_SUMMARY_PATH = REPO_ROOT / "analysis" / "results" / "llm_judge_summary.md"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_EXTRA_PGN_DIR = REPO_ROOT / "data" / "benchmarks" / "llm_judge_games"
DEFAULT_BATCH_DIR = REPO_ROOT / "analysis" / "results" / "llm_judge_batches"
DEFAULT_RESULTS_DIR = REPO_ROOT / "analysis" / "results" / "llm_judge_raw"

PERSONAS: dict[str, dict[str, str]] = {
    "beginner_600": {
        "level_key": "600",
        "description": (
            "You are rated 600 on Lichess, which is the site's rating floor. "
            "You know how pieces move and capture but you blunder about 9 times "
            "per game. You cannot see forks, pins, or skewers even when they are "
            "on the board. You do not know what centipawns are — a number like "
            "'+1.5' or 'gap 70 cp' is meaningless to you. You have no opening "
            "knowledge and no concept of pawn structure. You think one move at a "
            "time and often play moves just because they give check."
        ),
    },
    "intermediate_1000": {
        "level_key": "1000",
        "description": (
            "You are rated 1000 on Lichess, which is in the bottom quarter of "
            "active players. You can spot undefended pieces and mate-in-1, and "
            "you blunder 3-5 times per game. You know basic principles — develop, "
            "castle, control the center — but have no coherent plan after the "
            "opening. You cannot calculate more than 2 moves ahead. You see the "
            "evaluation bar go up or down but cannot translate engine numbers "
            "into concrete moves or plans. You know 1-2 opening names but not "
            "the ideas behind the moves."
        ),
    },
    "club_1400": {
        "level_key": "1400",
        "description": (
            "You are rated 1400 on Lichess, which is slightly below the site "
            "median. You blunder 1-3 times per game and can calculate 3-4 moves "
            "ahead in tactical positions. You recognize pins, forks, and discovered "
            "attacks. You know several openings but struggle when opponents deviate "
            "from book. You understand that '+1.5' means roughly a pawn and a half "
            "ahead, but you cannot translate that into a plan. A '70 centipawn gap' "
            "between two moves is meaningless to you — you cannot tell whether "
            "that is a big deal or negligible. In quiet positions without tactics, "
            "you often do not know what to do next."
        ),
    },
}

JUDGE_INSTRUCTION = """\
You are role-playing as the following chess player:

{persona}

Below is a chess position and two pieces of advice about it. The two pieces
of advice are BLINDED -- do NOT speculate about which one came from a chess
engine, a tutor, an LLM, or any other source. Judge strictly based on which
one would be more useful TO YOU as the player described above.

Answer three questions by picking "A", "B", or "tied" for each. Then give a
one-line reason (<= 25 words) that a player at your level would actually say.

Return ONLY a single JSON object, no prose, no markdown, no code fences.

The JSON schema is:
{{
  "clearer": "A" | "B" | "tied",
  "more_useful": "A" | "B" | "tied",
  "less_overwhelming": "A" | "B" | "tied",
  "reason": "<one-line reason in the voice of the persona>"
}}

Questions:
1. clearer: which piece of advice is CLEARER and easier to understand?
2. more_useful: which piece of advice would you actually FOLLOW in your next
   game as a {level_key} ELO player?
3. less_overwhelming: which piece of advice feels LESS OVERWHELMING?

POSITION
FEN: {fen}
Side to move: {side_to_move}

Board (White at bottom, lowercase = Black pieces):
{board_ascii}

=== Advice A ===
{view_a}

=== Advice B ===
{view_b}

Remember: return ONLY the JSON object.
"""


# ---------- position sampling ----------

def load_benchmark_positions(path: Path) -> list[dict]:
    """Load benchmark positions and tag them with a stable id."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for case in data:
        fen = case.get("fen")
        if not fen:
            continue
        out.append({
            "position_id": "bench_" + hashlib.md5(fen.encode()).hexdigest()[:8],
            "fen": fen,
            "source": "benchmark",
            "label": case.get("label", ""),
            "level_key_hint": case.get("level_key", ""),
            "theme": case.get("theme", ""),
        })
    return out


def load_pgn_positions(
    max_from_pgn: int,
    ply_start: int,
    ply_step: int,
    extra_pgn_dirs: list[Path] | None = None,
) -> list[dict]:
    sources = list(DEFAULT_PGN_SOURCES)
    if extra_pgn_dirs:
        sources.extend(extra_pgn_dirs)
    pgn_files = iter_pgn_files([Path(s) for s in sources])
    raw: list[dict] = []
    for pgn in pgn_files:
        raw.extend(
            sample_positions_from_pgn(
                pgn, ply_start=ply_start, ply_step=ply_step
            )
        )
    deduped = dedupe_positions(raw)
    out: list[dict] = []
    for pos in deduped[:max_from_pgn]:
        out.append({
            "position_id": "pgn_" + pos["position_id"],
            "fen": pos["fen"],
            "source": pos["source"],
            "label": f"pgn:{pos['source']}:ply{pos['ply']}",
            "level_key_hint": "",
            "theme": "",
        })
    return out


# ---------- view building ----------

def build_views(fen: str, level_key: str, service: AnalysisService):
    board = chess.Board(fen)
    if board.is_game_over():
        return None
    if not any(board.legal_moves):
        return None
    level = LEVELS[level_key]
    return service.analyze_position(board, level, candidate_limit=5)


def render_board_ascii(board: chess.Board) -> str:
    try:
        return str(board)
    except Exception:
        return board.fen()


# ---------- LLM call ----------

@dataclass
class LLMConfig:
    model: str
    temperature: float
    max_tokens: int
    max_retries: int
    sleep_between: float


def _ensure_env_loaded() -> None:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def build_client():
    _ensure_env_loaded()
    try:
        import anthropic
    except ImportError as exc:
        raise SystemExit("anthropic python package not installed. pip install anthropic") from exc
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "ANTHROPIC_API_KEY not set. Export it in your shell or add it to "
            f"{REPO_ROOT / '.env'} as ANTHROPIC_API_KEY=sk-ant-..."
        )
    return anthropic.Anthropic()


_JSON_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def _parse_judge_response(text: str) -> dict | None:
    text = text.strip()
    match = _JSON_PATTERN.search(text)
    if match is None:
        return None
    blob = match.group(0)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    for field in ("clearer", "more_useful", "less_overwhelming"):
        value = str(data.get(field, "")).strip().lower()
        if value in {"a", "b"}:
            data[field] = value
        elif value in {"tied", "t", "same", "equal"}:
            data[field] = "tied"
        else:
            return None
    data["reason"] = str(data.get("reason", "")).strip()[:240]
    return data


def call_judge(
    client,
    config: LLMConfig,
    prompt: str,
) -> dict | None:
    last_error: str | None = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = client.messages.create(
                model=config.model,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001 — SDK errors vary
            last_error = f"api_error: {type(exc).__name__}: {exc}"
            time.sleep(min(2 ** attempt, 10))
            continue
        text_blocks = [
            block.text for block in response.content
            if getattr(block, "type", "text") == "text"
        ]
        text = "".join(text_blocks)
        parsed = _parse_judge_response(text)
        if parsed is not None:
            parsed["_raw_model"] = response.model
            parsed["_stop_reason"] = response.stop_reason
            return parsed
        last_error = f"parse_error: {text[:180]!r}"
        time.sleep(config.sleep_between)
    if last_error:
        print(f"  ! judge failed after {config.max_retries} attempts: {last_error}")
    return None


# ---------- main loop ----------

def already_judged_keys(path: Path) -> set[tuple[str, str]]:
    """Return set of (rater_id, position_label) already present in the log."""
    seen: set[tuple[str, str]] = set()
    for entry in load_entries(path):
        key = (str(entry.get("rater_id", "")), str(entry.get("position_label", "")))
        seen.add(key)
    return seen


def preference_to_side(answer: str, assignment: dict[str, str]) -> str:
    if answer == "tied":
        return "tied"
    return assignment[answer.upper()]


def build_entry(
    *,
    rater_id: str,
    position: dict,
    level_key_for_tutor: str,
    report,
    assignment: dict[str, str],
    judgment: dict,
    model: str,
    persona_key: str,
    prompt_sha: str,
) -> dict:
    raw_prefs = {
        field: judgment[field]
        for field in ("clearer", "more_useful", "less_overwhelming")
    }
    mapped_prefs = {
        field: preference_to_side(ans, assignment)
        for field, ans in raw_prefs.items()
    }
    return {
        "rater_id": rater_id,
        "rater_type": "llm_judge",
        "llm_model": model,
        "persona": persona_key,
        "position_label": position.get("label", ""),
        "position_id": position.get("position_id", ""),
        "level_key": level_key_for_tutor,
        "theme": position.get("theme", ""),
        "fen": position["fen"],
        "source": position.get("source", ""),
        "assignment": assignment,
        "tutor_move_san": report.tutor_move.san,
        "engine_best_san": report.engine_best_move.san,
        "tutor_equals_engine": report.tutor_move.uci == report.engine_best_move.uci,
        "preferences": mapped_prefs,
        "raw_answers_AB": raw_prefs,
        "reason": judgment.get("reason", ""),
        "prompt_sha": prompt_sha,
        "stop_reason": judgment.get("_stop_reason", ""),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }


def run(
    *,
    positions: list[dict],
    personas: list[str],
    output: Path,
    config: LLMConfig,
    seed: int | None,
    max_total: int | None,
    resume: bool,
) -> int:
    client = build_client()
    service = AnalysisService()
    rng = random.Random(seed) if seed is not None else random.Random()

    already = already_judged_keys(output) if resume else set()

    plan: list[tuple[dict, str]] = []
    for pos in positions:
        for persona_key in personas:
            plan.append((pos, persona_key))

    if max_total is not None:
        plan = plan[:max_total]

    todo: list[tuple[dict, str, str]] = []
    for pos, persona_key in plan:
        rater_id = f"llm-judge:{config.model}:{persona_key}"
        if (rater_id, pos.get("label", "")) in already:
            continue
        todo.append((pos, persona_key, rater_id))

    if not todo:
        print("Nothing to do. All (position, persona) pairs already logged.")
        return 0

    print(
        f"LLM judge: {len(todo)} comparisons to run "
        f"(positions={len(positions)}, personas={len(personas)}, "
        f"model={config.model})"
    )

    saved = 0
    errors = 0
    for idx, (pos, persona_key, rater_id) in enumerate(todo, start=1):
        persona = PERSONAS[persona_key]
        level_key_for_tutor = persona["level_key"]
        try:
            report = build_views(pos["fen"], level_key_for_tutor, service)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{idx}/{len(todo)}] {pos['label']} {persona_key}: "
                  f"analyze failed ({type(exc).__name__}: {exc})")
            errors += 1
            continue
        if report is None:
            print(f"  [{idx}/{len(todo)}] {pos['label']} {persona_key}: "
                  f"skip (terminal/illegal position)")
            continue

        tutor_on_a = rng.random() < 0.5
        assignment = {
            "A": "tutor" if tutor_on_a else "engine",
            "B": "engine" if tutor_on_a else "tutor",
        }
        view_a = render_tutor_view(report) if tutor_on_a else render_engine_view(report)
        view_b = render_engine_view(report) if tutor_on_a else render_tutor_view(report)

        board = chess.Board(pos["fen"])
        prompt = JUDGE_INSTRUCTION.format(
            persona=persona["description"],
            level_key=persona["level_key"],
            fen=pos["fen"],
            side_to_move="White" if board.turn else "Black",
            board_ascii=render_board_ascii(board),
            view_a=view_a,
            view_b=view_b,
        )
        prompt_sha = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]

        judgment = call_judge(client, config, prompt)
        if judgment is None:
            errors += 1
            continue

        entry = build_entry(
            rater_id=rater_id,
            position=pos,
            level_key_for_tutor=level_key_for_tutor,
            report=report,
            assignment=assignment,
            judgment=judgment,
            model=config.model,
            persona_key=persona_key,
            prompt_sha=prompt_sha,
        )
        append_entry(entry, output)
        saved += 1
        raw = judgment
        print(
            f"  [{idx}/{len(todo)}] {pos['label']} {persona_key}: "
            f"saved (A_is_{assignment['A']}; "
            f"clear={raw['clearer']} use={raw['more_useful']} "
            f"over={raw['less_overwhelming']})"
        )
        time.sleep(config.sleep_between)

    print(f"\nJudge run complete. saved={saved}  errors={errors}")
    return 0


# ---------- agent-dispatch prepare / ingest ----------

def _build_task_record(
    *,
    position: dict,
    persona_key: str,
    rng: random.Random,
    service: AnalysisService,
) -> dict | None:
    persona = PERSONAS[persona_key]
    level_key_for_tutor = persona["level_key"]
    try:
        report = build_views(position["fen"], level_key_for_tutor, service)
    except Exception as exc:  # noqa: BLE001
        return {
            "_skip_reason": f"analyze_failed:{type(exc).__name__}:{exc}",
            "position_label": position.get("label", ""),
            "persona": persona_key,
        }
    if report is None:
        return {
            "_skip_reason": "terminal_or_illegal",
            "position_label": position.get("label", ""),
            "persona": persona_key,
        }

    tutor_on_a = rng.random() < 0.5
    assignment = {
        "A": "tutor" if tutor_on_a else "engine",
        "B": "engine" if tutor_on_a else "tutor",
    }
    view_a = render_tutor_view(report) if tutor_on_a else render_engine_view(report)
    view_b = render_engine_view(report) if tutor_on_a else render_tutor_view(report)
    board = chess.Board(position["fen"])

    task_id = hashlib.sha1(
        (position.get("position_id", "") + "|" + persona_key + "|" +
         position["fen"]).encode("utf-8")
    ).hexdigest()[:16]

    return {
        "task_id": task_id,
        "persona_key": persona_key,
        "persona_description": persona["description"],
        "level_key": level_key_for_tutor,
        "position_id": position.get("position_id", ""),
        "position_label": position.get("label", ""),
        "source": position.get("source", ""),
        "theme": position.get("theme", ""),
        "fen": position["fen"],
        "side_to_move": "White" if board.turn else "Black",
        "board_ascii": render_board_ascii(board),
        "view_a": view_a,
        "view_b": view_b,
        "assignment": assignment,
        "tutor_move_san": report.tutor_move.san,
        "engine_best_san": report.engine_best_move.san,
        "tutor_equals_engine": report.tutor_move.uci == report.engine_best_move.uci,
    }


def prepare_batches(
    *,
    positions: list[dict],
    personas: list[str],
    batch_size: int,
    batch_dir: Path,
    seed: int,
) -> dict:
    """Materialize all (position, persona) judge tasks into batch JSON files."""
    batch_dir.mkdir(parents=True, exist_ok=True)
    for old in batch_dir.glob("batch_*.json"):
        old.unlink()

    service = AnalysisService()
    rng = random.Random(seed)
    tasks: list[dict] = []
    skipped: list[dict] = []
    for pos in positions:
        for persona_key in personas:
            rec = _build_task_record(
                position=pos, persona_key=persona_key, rng=rng, service=service
            )
            if rec is None:
                continue
            if "_skip_reason" in rec:
                skipped.append(rec)
                continue
            tasks.append(rec)

    batches: list[Path] = []
    for i in range(0, len(tasks), batch_size):
        chunk = tasks[i: i + batch_size]
        batch_path = batch_dir / f"batch_{i // batch_size:03d}.json"
        batch_path.write_text(
            json.dumps(chunk, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        batches.append(batch_path)

    index = {
        "n_tasks": len(tasks),
        "n_batches": len(batches),
        "batch_size": batch_size,
        "batch_files": [str(p) for p in batches],
        "skipped": skipped,
        "personas": personas,
        "seed": seed,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    (batch_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return index


def _load_task_index_by_id(batch_dir: Path) -> dict[str, dict]:
    """Return {task_id: task_record} across all batch files."""
    out: dict[str, dict] = {}
    for batch_path in sorted(batch_dir.glob("batch_*.json")):
        data = json.loads(batch_path.read_text(encoding="utf-8"))
        for rec in data:
            out[rec["task_id"]] = rec
    return out


def _existing_task_ids(path: Path) -> set[str]:
    seen: set[str] = set()
    for entry in load_entries(path):
        tid = entry.get("task_id")
        if tid:
            seen.add(str(tid))
    return seen


def ingest_results(
    *,
    batch_dir: Path,
    results_dir: Path,
    output: Path,
    model_label: str,
) -> dict:
    """Read result files and append to ab_feedback.jsonl, avoiding duplicates."""
    tasks_by_id = _load_task_index_by_id(batch_dir)
    existing = _existing_task_ids(output)
    ingested = 0
    skipped_dupe = 0
    missing_task = 0
    parse_errors: list[str] = []

    for result_path in sorted(results_dir.glob("batch_*.json")):
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            parse_errors.append(f"{result_path.name}: {exc}")
            continue
        if not isinstance(data, list):
            parse_errors.append(f"{result_path.name}: not a list")
            continue
        for judgment in data:
            task_id = judgment.get("task_id")
            task = tasks_by_id.get(task_id)
            if task is None:
                missing_task += 1
                continue
            # Validate answer shape
            normalized: dict = {}
            bad = False
            for field in ("clearer", "more_useful", "less_overwhelming"):
                raw = str(judgment.get(field, "")).strip().lower()
                if raw in {"a", "b"}:
                    normalized[field] = raw
                elif raw in {"tied", "t", "same", "equal"}:
                    normalized[field] = "tied"
                else:
                    bad = True
                    break
            if bad:
                parse_errors.append(f"{result_path.name}:{task_id}:bad_answer")
                continue
            rater_id = f"llm-judge:{model_label}:{task['persona_key']}"
            if task_id in existing:
                skipped_dupe += 1
                continue
            mapped_prefs = {
                field: preference_to_side(ans, task["assignment"])
                for field, ans in normalized.items()
            }
            entry = {
                "rater_id": rater_id,
                "rater_type": "llm_judge",
                "llm_model": model_label,
                "persona": task["persona_key"],
                "position_label": task["position_label"],
                "position_id": task["position_id"],
                "level_key": task["level_key"],
                "theme": task["theme"],
                "fen": task["fen"],
                "source": task["source"],
                "assignment": task["assignment"],
                "tutor_move_san": task["tutor_move_san"],
                "engine_best_san": task["engine_best_san"],
                "tutor_equals_engine": task["tutor_equals_engine"],
                "preferences": mapped_prefs,
                "raw_answers_AB": normalized,
                "reason": str(judgment.get("reason", ""))[:240],
                "task_id": task_id,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
            append_entry(entry, output)
            existing.add(task_id)
            ingested += 1

    return {
        "ingested": ingested,
        "skipped_dupe": skipped_dupe,
        "missing_task": missing_task,
        "parse_errors": parse_errors,
    }


# ---------- summary ----------

def summarize_llm_judge(path: Path) -> dict:
    entries = [
        e for e in load_entries(path)
        if e.get("rater_type") == "llm_judge"
    ]
    summary: dict = {
        "n_comparisons": len(entries),
        "models": sorted({str(e.get("llm_model", "?")) for e in entries}),
        "personas": sorted({str(e.get("persona", "?")) for e in entries}),
        "overall": {},
        "by_persona": {},
        "by_level": {},
        "by_agreement": {},
        "sample_quotes": [],
    }
    if not entries:
        return summary

    fields = ("clearer", "more_useful", "less_overwhelming")

    def _pct(group: list[dict]) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        total = len(group)
        if total == 0:
            return {f: {"tutor": 0.0, "engine": 0.0, "tied": 0.0} for f in fields}
        for f in fields:
            counts = {"tutor": 0, "engine": 0, "tied": 0}
            for e in group:
                side = e.get("preferences", {}).get(f)
                if side in counts:
                    counts[side] += 1
            out[f] = {k: round(v / total * 100, 1) for k, v in counts.items()}
        return out

    summary["overall"] = _pct(entries)

    by_persona: dict[str, list[dict]] = {}
    for e in entries:
        by_persona.setdefault(str(e.get("persona", "?")), []).append(e)
    summary["by_persona"] = {
        p: {"n": len(rows), "preference_pct": _pct(rows)}
        for p, rows in by_persona.items()
    }

    by_level: dict[str, list[dict]] = {}
    for e in entries:
        by_level.setdefault(str(e.get("level_key", "?")), []).append(e)
    summary["by_level"] = {
        k: {"n": len(rows), "preference_pct": _pct(rows)}
        for k, rows in by_level.items()
    }

    agree_rows = [e for e in entries if e.get("tutor_equals_engine")]
    diff_rows = [e for e in entries if not e.get("tutor_equals_engine")]
    summary["by_agreement"] = {
        "tutor_equals_engine": {"n": len(agree_rows), "preference_pct": _pct(agree_rows)},
        "tutor_differs_from_engine": {"n": len(diff_rows), "preference_pct": _pct(diff_rows)},
    }

    quotes: list[dict] = []
    for e in entries:
        reason = str(e.get("reason", "")).strip()
        if not reason:
            continue
        quotes.append({
            "persona": e.get("persona"),
            "level": e.get("level_key"),
            "position": e.get("position_label"),
            "tutor_vs_engine": (
                "tutor=engine" if e.get("tutor_equals_engine") else "tutor≠engine"
            ),
            "reason": reason,
        })
    summary["sample_quotes"] = quotes[-12:]
    return summary


def format_markdown(summary: dict) -> str:
    lines: list[str] = []
    lines.append("# LLM-as-judge A/B preference summary\n")
    lines.append(f"- comparisons: **{summary['n_comparisons']}**")
    lines.append(f"- models: {', '.join(summary['models']) or '-'}")
    lines.append(f"- personas: {', '.join(summary['personas']) or '-'}\n")

    def _table(title: str, block: dict) -> None:
        lines.append(f"## {title}\n")
        lines.append("| dimension | tutor | engine | tied |")
        lines.append("|---|---|---|---|")
        for field in ("clearer", "more_useful", "less_overwhelming"):
            dist = block.get(field, {"tutor": 0, "engine": 0, "tied": 0})
            lines.append(
                f"| {field} | {dist['tutor']:.1f}% | "
                f"{dist['engine']:.1f}% | {dist['tied']:.1f}% |"
            )
        lines.append("")

    if summary["overall"]:
        _table("Overall preference (all personas, all positions)", summary["overall"])

    if summary["by_persona"]:
        lines.append("## Preference by persona\n")
        lines.append("| persona | n | dimension | tutor | engine | tied |")
        lines.append("|---|---|---|---|---|---|")
        for persona, data in sorted(summary["by_persona"].items()):
            for field in ("clearer", "more_useful", "less_overwhelming"):
                d = data["preference_pct"][field]
                lines.append(
                    f"| {persona} | {data['n']} | {field} | "
                    f"{d['tutor']:.1f}% | {d['engine']:.1f}% | {d['tied']:.1f}% |"
                )
        lines.append("")

    if summary["by_level"]:
        lines.append("## Preference by level_key\n")
        lines.append("| level_key | n | dimension | tutor | engine | tied |")
        lines.append("|---|---|---|---|---|---|")
        for level, data in sorted(summary["by_level"].items()):
            for field in ("clearer", "more_useful", "less_overwhelming"):
                d = data["preference_pct"][field]
                lines.append(
                    f"| {level} | {data['n']} | {field} | "
                    f"{d['tutor']:.1f}% | {d['engine']:.1f}% | {d['tied']:.1f}% |"
                )
        lines.append("")

    if summary["by_agreement"]:
        lines.append("## Preference when tutor move equals / differs from engine best\n")
        lines.append("| case | n | dimension | tutor | engine | tied |")
        lines.append("|---|---|---|---|---|---|")
        for case_name, data in summary["by_agreement"].items():
            for field in ("clearer", "more_useful", "less_overwhelming"):
                d = data["preference_pct"][field]
                lines.append(
                    f"| {case_name} | {data['n']} | {field} | "
                    f"{d['tutor']:.1f}% | {d['engine']:.1f}% | {d['tied']:.1f}% |"
                )
        lines.append("")

    if summary["sample_quotes"]:
        lines.append("## Sample one-line reasons (most recent 12)\n")
        for q in summary["sample_quotes"]:
            lines.append(
                f"- **{q['persona']}** @ {q['level']} ({q['tutor_vs_engine']}, "
                f"{q['position']}): {q['reason']}"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


# ---------- CLI ----------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--summary-out", type=Path, default=DEFAULT_SUMMARY_PATH,
        help="Path to write the Markdown summary."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--max-tokens", type=int, default=400)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument(
        "--sleep", type=float, default=0.3,
        help="Seconds between successful API calls (rate-limit buffer)."
    )
    parser.add_argument(
        "--personas", nargs="+", default=list(PERSONAS.keys()),
        help=f"Subset of personas to run. Available: {list(PERSONAS.keys())}"
    )
    parser.add_argument(
        "--positions-json", type=Path, default=DEFAULT_POSITIONS_PATH,
        help="Benchmark positions JSON to include."
    )
    parser.add_argument(
        "--max-pgn", type=int, default=500,
        help="Max additional positions to sample from PGN files."
    )
    parser.add_argument(
        "--ply-start", type=int, default=2,
        help="First ply to sample from each PGN game."
    )
    parser.add_argument(
        "--ply-step", type=int, default=1,
        help="Sample every N-th half-move in each game."
    )
    parser.add_argument(
        "--max-total", type=int, default=None,
        help="Hard cap on total (position, persona) comparisons."
    )
    parser.add_argument("--seed", type=int, default=20260419)
    parser.add_argument(
        "--no-resume", action="store_true",
        help="Do not skip (rater_id, position) pairs already in the log."
    )
    parser.add_argument(
        "--summary-only", action="store_true",
        help="Just read the JSONL and print/save a fresh summary; no API calls."
    )
    parser.add_argument(
        "--skip-pgn", action="store_true",
        help="Only use the benchmark JSON, skip PGN sampling."
    )
    parser.add_argument(
        "--extra-pgn-dir", type=Path, action="append",
        help="Additional PGN directory to include when sampling positions "
             f"(default: {DEFAULT_EXTRA_PGN_DIR})",
    )
    parser.add_argument(
        "--prepare", action="store_true",
        help="Agent-dispatch mode: build batch JSON files under --batch-dir "
             "instead of calling the Anthropic API."
    )
    parser.add_argument(
        "--ingest", action="store_true",
        help="Agent-dispatch mode: read agent-produced result JSONs from "
             "--results-dir and append to --output."
    )
    parser.add_argument(
        "--batch-dir", type=Path, default=DEFAULT_BATCH_DIR,
        help="Directory for prepared task batches."
    )
    parser.add_argument(
        "--results-dir", type=Path, default=DEFAULT_RESULTS_DIR,
        help="Directory where subagents will write result JSON files."
    )
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="How many (position, persona) tasks per batch file."
    )
    parser.add_argument(
        "--max-positions-total", type=int, default=None,
        help="Hard cap on total unique positions considered (after dedupe)."
    )
    args = parser.parse_args()

    if args.summary_only:
        summary = summarize_llm_judge(args.output)
        md = format_markdown(summary)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(md, encoding="utf-8")
        print(md)
        print(f"Summary saved to {args.summary_out}")
        return 0

    if args.ingest:
        outcome = ingest_results(
            batch_dir=args.batch_dir,
            results_dir=args.results_dir,
            output=args.output,
            model_label=args.model,
        )
        print(f"Ingest done: {outcome}")
        summary = summarize_llm_judge(args.output)
        md = format_markdown(summary)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(md, encoding="utf-8")
        print(f"Summary saved to {args.summary_out}")
        return 0

    bad_personas = [p for p in args.personas if p not in PERSONAS]
    if bad_personas:
        raise SystemExit(f"Unknown persona(s): {bad_personas}. "
                         f"Available: {list(PERSONAS.keys())}")

    positions: list[dict] = []
    positions.extend(load_benchmark_positions(args.positions_json))
    extra_dirs = args.extra_pgn_dir or [DEFAULT_EXTRA_PGN_DIR]
    if not args.skip_pgn:
        positions.extend(load_pgn_positions(
            max_from_pgn=args.max_pgn,
            ply_start=args.ply_start,
            ply_step=args.ply_step,
            extra_pgn_dirs=[Path(d) for d in extra_dirs],
        ))

    seen_fens: set[str] = set()
    unique_positions: list[dict] = []
    for pos in positions:
        if pos["fen"] in seen_fens:
            continue
        seen_fens.add(pos["fen"])
        unique_positions.append(pos)

    if args.max_positions_total is not None:
        unique_positions = unique_positions[: args.max_positions_total]

    if not unique_positions:
        raise SystemExit("No positions available to judge.")

    print(f"Prepared {len(unique_positions)} unique positions "
          f"({sum(1 for p in unique_positions if p['source'] == 'benchmark')} benchmark, "
          f"{sum(1 for p in unique_positions if p['source'] != 'benchmark')} from PGN).")

    if args.prepare:
        index = prepare_batches(
            positions=unique_positions,
            personas=args.personas,
            batch_size=args.batch_size,
            batch_dir=args.batch_dir,
            seed=args.seed,
        )
        print(
            f"Prepared {index['n_tasks']} tasks across "
            f"{index['n_batches']} batch files in {args.batch_dir}"
        )
        if index["skipped"]:
            print(f"  (skipped {len(index['skipped'])} position×persona pairs "
                  f"due to analyze errors or terminal positions)")
        return 0

    config = LLMConfig(
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        max_retries=args.max_retries,
        sleep_between=args.sleep,
    )

    run(
        positions=unique_positions,
        personas=args.personas,
        output=args.output,
        config=config,
        seed=args.seed,
        max_total=args.max_total,
        resume=not args.no_resume,
    )

    summary = summarize_llm_judge(args.output)
    md = format_markdown(summary)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"Summary saved to {args.summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
