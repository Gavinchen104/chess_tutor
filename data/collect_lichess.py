"""
Collect rated games from Lichess for different ELO bands.

Strategy:
1.  Browse recent Lichess arena tournaments to find players at each target
    rating range.
2.  Download their rated games in PGN format via the public game-export API.
3.  Filter games where BOTH players fall inside the target ELO window.
4.  Save one PGN file per ELO band under data/processed/.

The Lichess public API does not require authentication for game exports.

Usage (from chess_tutor/ directory):
    python -m data.collect_lichess
    python -m data.collect_lichess --games-per-band 500          # smaller run
    python -m data.collect_lichess --games-per-band 2000 --output-dir data/processed
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

import chess
import chess.pgn
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LICHESS_API = "https://lichess.org/api"

# Target ELO bands with acceptable rating windows for filtering
ELO_BANDS: dict[str, tuple[int, int]] = {
    "600":  (400, 800),
    "1000": (850, 1150),
    "1400": (1250, 1550),
    "1800": (1650, 1950),
}

# How many rated games to download per user
GAMES_PER_USER = 80

# Default number of games to collect per ELO band
DEFAULT_GAMES_PER_BAND = 1500

# Rate limiting (Lichess allows ~20 req/s unauthenticated, be conservative)
REQUEST_DELAY = 1.0

# Tournament search: how many finished tournaments to scan
MAX_TOURNAMENTS_TO_SCAN = 40

# Players per band: how many unique players to sample from
TARGET_PLAYERS_PER_BAND = 30

# Perf types that count as "standard" rated games
PERF_TYPES = ("blitz", "rapid", "classical")


# ---------------------------------------------------------------------------
# Lichess API helpers
# ---------------------------------------------------------------------------


def api_get_json(path: str, params: dict | None = None, timeout: int = 15) -> dict | list | None:
    """GET a Lichess API JSON endpoint."""
    url = f"{LICHESS_API}/{path}"
    headers = {"Accept": "application/json"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        if resp.status_code == 429:
            print("  [RATE-LIMITED] Backing off 30s ...")
            time.sleep(30)
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as err:
        print(f"  [API ERROR] {err}")
        return None


def api_get_ndjson(path: str, params: dict | None = None, max_lines: int = 200) -> list[dict]:
    """GET a Lichess API NDJSON-streaming endpoint."""
    url = f"{LICHESS_API}/{path}"
    headers = {"Accept": "application/x-ndjson"}
    results: list[dict] = []
    try:
        resp = requests.get(url, params=params, headers=headers, stream=True, timeout=30)
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            results.append(json.loads(line))
            if len(results) >= max_lines:
                break
    except requests.RequestException as err:
        print(f"  [API ERROR] {err}")
    return results


def download_user_games_pgn(
    username: str,
    max_games: int = GAMES_PER_USER,
    perf_type: str = "blitz",
) -> str:
    """
    Download rated games of a user as PGN text.

    Args:
        username: Lichess username.
        max_games: Maximum games to fetch.
        perf_type: Speed category.

    Returns:
        Raw PGN string (may contain multiple games).
    """
    url = f"{LICHESS_API}/games/user/{username}"
    params = {
        "max": max_games,
        "rated": "true",
        "perfType": perf_type,
        "opening": "false",
        "tags": "true",
    }
    headers = {"Accept": "application/x-chess-pgn"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as err:
        print(f"  [DOWNLOAD ERROR] {username}: {err}")
        return ""


# ---------------------------------------------------------------------------
# Find players at target rating levels from tournaments
# ---------------------------------------------------------------------------


def find_tournaments_for_rating(elo_low: int, elo_high: int) -> list[str]:
    """
    Find recent arena tournament IDs where participants fall in the target
    rating range.

    Returns:
        List of tournament IDs, most recent first.
    """
    data = api_get_json("tournament")
    if data is None:
        return []

    tournament_ids: list[str] = []
    for status in ("finished", "started", "created"):
        for t in data.get(status, []):
            # Check if tournament has a rating limit matching our range
            min_rating = t.get("minRating", {}).get("rating", 0)
            max_rating = t.get("maxRating", {}).get("rating", 9999)
            nb_players = t.get("nbPlayers", 0)

            # Accept tournaments where the rating range overlaps with our target
            if max_rating < elo_low or min_rating > elo_high:
                continue
            if nb_players < 5:
                continue

            tournament_ids.append(t["id"])
            if len(tournament_ids) >= MAX_TOURNAMENTS_TO_SCAN:
                break

    return tournament_ids


def find_players_at_rating(
    elo_low: int,
    elo_high: int,
    target_count: int = TARGET_PLAYERS_PER_BAND,
) -> list[str]:
    """
    Find Lichess usernames of players whose tournament rating falls in
    [elo_low, elo_high].

    Scans recent arena tournaments and extracts usernames from the standings.

    Returns:
        List of usernames (deduplicated).
    """
    tournament_ids = find_tournaments_for_rating(elo_low, elo_high)
    if not tournament_ids:
        # Fallback: scan general tournaments
        data = api_get_json("tournament")
        if data:
            for status in ("finished", "started"):
                for t in data.get(status, []):
                    tournament_ids.append(t["id"])
                    if len(tournament_ids) >= MAX_TOURNAMENTS_TO_SCAN:
                        break

    players: dict[str, int] = {}  # username -> rating

    for tid in tournament_ids:
        if len(players) >= target_count:
            break

        results = api_get_ndjson(f"tournament/{tid}/results", params={"nb": 100})
        time.sleep(REQUEST_DELAY)

        for entry in results:
            username = entry.get("username", "")
            rating = entry.get("rating", 0)
            if elo_low <= rating <= elo_high and username not in players:
                players[username] = rating
                if len(players) >= target_count:
                    break

    return list(players.keys())


# ---------------------------------------------------------------------------
# Main collection pipeline
# ---------------------------------------------------------------------------


def filter_games_by_elo(
    pgn_text: str,
    elo_low: int,
    elo_high: int,
) -> list[chess.pgn.Game]:
    """
    Parse PGN text and keep only games where BOTH players are in range.

    Args:
        pgn_text: Multi-game PGN string.
        elo_low: Minimum ELO (inclusive).
        elo_high: Maximum ELO (inclusive).

    Returns:
        List of chess.pgn.Game objects that pass the filter.
    """
    games: list[chess.pgn.Game] = []
    pgn_io = io.StringIO(pgn_text)

    while True:
        game = chess.pgn.read_game(pgn_io)
        if game is None:
            break

        try:
            white_elo = int(game.headers.get("WhiteElo", "0"))
            black_elo = int(game.headers.get("BlackElo", "0"))
        except ValueError:
            continue

        if elo_low <= white_elo <= elo_high and elo_low <= black_elo <= elo_high:
            games.append(game)

    return games


def collect_band(
    band_key: str,
    elo_range: tuple[int, int],
    target_games: int,
    output_dir: str,
) -> int:
    """
    Collect games for a single ELO band.

    Args:
        band_key: Band label (e.g. "600").
        elo_range: (low, high) rating window.
        target_games: Target number of games.
        output_dir: Directory to write PGN file.

    Returns:
        Number of games collected.
    """
    elo_low, elo_high = elo_range
    print(f"\n{'='*60}")
    print(f"Band {band_key} (ELO {elo_low}-{elo_high}), target: {target_games} games")
    print(f"{'='*60}")

    # Step 1: find players
    print("  Finding players ...")
    players = find_players_at_rating(elo_low, elo_high)
    print(f"  Found {len(players)} players at rating {elo_low}-{elo_high}")

    if not players:
        print(f"  [WARN] No players found for band {band_key}")
        return 0

    # Step 2: download and filter games
    all_games: list[chess.pgn.Game] = []

    for i, username in enumerate(players):
        if len(all_games) >= target_games:
            break

        # Try different perf types to maximize data
        for perf in PERF_TYPES:
            pgn_text = download_user_games_pgn(username, perf_type=perf)
            time.sleep(REQUEST_DELAY)

            if not pgn_text.strip():
                continue

            filtered = filter_games_by_elo(pgn_text, elo_low, elo_high)
            all_games.extend(filtered)

            if filtered:
                print(f"  [{i+1}/{len(players)}] {username} ({perf}): "
                      f"+{len(filtered)} games (total: {len(all_games)})")
                break  # Got games from this perf type, move to next user

        if len(all_games) >= target_games:
            break

    # Step 3: save to PGN file
    if all_games:
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"games_{band_key}.pgn")

        with open(output_path, "w") as fh:
            for game in all_games[:target_games]:
                print(game, file=fh)
                print(file=fh)  # blank line between games

        n_saved = min(len(all_games), target_games)
        print(f"  Saved {n_saved} games to {output_path}")
        return n_saved

    print(f"  [WARN] No games collected for band {band_key}")
    return 0


def print_summary(results: dict[str, int]) -> None:
    """Print collection summary."""
    print(f"\n{'='*60}")
    print("Collection Summary")
    print(f"{'='*60}")
    total = 0
    for band, count in results.items():
        elo_low, elo_high = ELO_BANDS[band]
        print(f"  Band {band} ({elo_low}-{elo_high}): {count} games")
        total += count
    print(f"  Total: {total} games")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect rated games from Lichess for Bayesian model training",
    )
    parser.add_argument(
        "--games-per-band", type=int, default=DEFAULT_GAMES_PER_BAND,
        help=f"Target games per ELO band (default: {DEFAULT_GAMES_PER_BAND})",
    )
    parser.add_argument(
        "--output-dir", type=str, default="data/processed",
        help="Output directory for PGN files (default: data/processed)",
    )
    parser.add_argument(
        "--bands", type=str, default=None,
        help="Comma-separated list of bands to collect (default: all)",
    )
    args = parser.parse_args()

    bands_to_collect = (
        args.bands.split(",") if args.bands
        else list(ELO_BANDS.keys())
    )

    results: dict[str, int] = {}
    for band_key in bands_to_collect:
        if band_key not in ELO_BANDS:
            print(f"[WARN] Unknown band '{band_key}', skipping")
            continue
        count = collect_band(
            band_key,
            ELO_BANDS[band_key],
            args.games_per_band,
            args.output_dir,
        )
        results[band_key] = count

    print_summary(results)
    print("\nData collection complete!")


if __name__ == "__main__":
    main()
