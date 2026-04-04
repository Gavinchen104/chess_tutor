# Frequently Asked Questions

## Q1: Why not just use Stockfish directly?

Stockfish always recommends the objectively strongest move. For a grandmaster, that is exactly what they need. But for a 600-rated beginner, the strongest move is often incomprehensible.

Consider this analogy: if you ask a world-class mathematician to teach addition to a first-grader, the "correct" approach (set theory axioms) is useless. The child needs to count on their fingers first. Our tutor does the same for chess — it picks moves the student can understand and learn from, even if those moves sacrifice a few centipawns of engine evaluation.

Concretely, the tutor score penalizes moves that require deep calculation (high difficulty), rewards moves that address the student's immediate weaknesses (like undeveloped pieces or an exposed king), and adjusts all of these tradeoffs based on the student's ELO level. None of this information exists in Stockfish's raw evaluation.

## Q2: How were the model parameters learned? Could they be wrong?

The parameters come from Bayesian inference on real Lichess games. Here is the pipeline:

1. We downloaded over 5,000 rated games (1,500+ per ELO band) from Lichess using their public API.
2. For each position in each game, we computed features using our heuristic engine — eval gap, difficulty, safety changes, center control, etc.
3. We fit a Bayesian conditional logit model (Model A) and a Bayesian logistic regression (Model B) using PyMC and MCMC sampling.
4. We verified convergence: all R-hat values are below 1.05 and effective sample sizes exceed 900.

The Bayesian framework gives us more than point estimates — it provides full posterior distributions. This means we know not just "what is the best weight for difficulty?" but "how confident are we in that weight?" If the 94% credible interval for a coefficient includes zero, we know that feature is not statistically important.

Could the parameters be wrong? Any model trained on finite data has uncertainty. That is precisely why we use a Bayesian approach — the posterior distributions quantify this uncertainty honestly. Additionally, the system falls back to the hand-tuned heuristic if learned parameters produce anomalous results, so it degrades gracefully.

## Q3: How do you know the tutor actually helps beginners improve?

We provide several lines of evidence:

**Quantitative evidence**: The Bayesian model predicts human move choices 2.6-2.8x better than random. This means the model has genuinely learned what real humans at each level do — a necessary condition for making useful recommendations.

**Behavioral differentiation**: The tutor gives different recommendations for different skill levels in the same position. A 600-rated player and a 1400-rated player facing the same board will often receive different move suggestions, each tailored to what that level of player can understand and execute.

**Comparison with heuristic**: The learned model disagrees with the hand-tuned heuristic on 53% of benchmark positions, generally preferring center-control and development moves for beginners — patterns that match established chess pedagogy.

**Aspirational training**: Model B's training signal uses moves that the next-higher ELO band of players actually choose. So the tutor isn't recommending what beginners already do — it recommends what slightly better players do, creating a learning trajectory.

Large-scale randomized controlled trials are outside this project's scope, but the statistical evidence supports the system's design rationale.

## Q4: Do the recommendations really differ between skill levels?

Yes, substantially. Here is a concrete example from the starting position after 1.e4 Nc6:

| ELO Level | Engine Best | Tutor Recommends | Why |
|-----------|-------------|-----------------|-----|
| 600  | Nc3 | Nc3 | Simple development, no calculation needed |
| 1000 | Nc3 | d4  | Center control — the next learning step |
| 1400 | Nc3 | d4  | Positional play with center occupation |
| 1800 | Nc3 | Nf3 | Near-engine move, comfortable complexity |

The system learns these differences from data. The complexity penalty weight for 600-rated players is 5x higher than for 1800-rated players, reflecting the empirical observation that beginners struggle with calculation-heavy moves.

## Q5: What are the limitations of this approach?

**Data representativeness**: Our training data comes from Lichess blitz/rapid games. Players may behave differently in classical games or over-the-board play. The 600-ELO band uses a proxy from the Lichess rating buckets, which may not perfectly represent true 600-rated players.

**Heuristic evaluation**: Without Stockfish, the system uses a simplified position evaluator. This is less accurate for complex tactical positions. With Stockfish available, analysis quality improves significantly.

**Static skill model**: The system assumes a fixed ELO level per session. In reality, a student's understanding changes as they play. An adaptive model that updates its belief about the student's level in real time would be more effective.

**Small position overlap**: For the aspirational training signal (Model B), we need positions that appear in both the current and next-higher ELO band's games. For the 600-to-1000 gap, only 19 positions overlapped, so we could not train that model.

**No opening-specific context**: The system treats each position independently without considering the opening being played or the student's opening repertoire.

Despite these limitations, the system successfully demonstrates that data-driven Bayesian methods can improve chess tutoring over pure heuristics or raw engine output.
