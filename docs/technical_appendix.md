# Technical Appendix

## 1. System Architecture

The chess tutor has a layered architecture:

```
Layer 1: Board (python-chess wrapper)
    |
Layer 2: MoveEngine (evaluation + tutor scoring)
         Diagnostics (tactical/strategic analysis)
    |
Layer 3: Services (analysis, coaching, review)
         Commentary (natural language generation)
    |
Layer 4: ChessTutor facade
    |
Layer 5: Streamlit UI (3 tabs)
```

All source code is under `chess_tutor/app/core/`.

## 2. Data Collection

### Source
Rated games from Lichess, downloaded via the public API (`lichess.org/api/games/user/{username}`).

### Pipeline
1. **Player discovery** (`data/collect_lichess.py`): Scans recent Lichess arena tournaments to find players at each target ELO range using the tournament results API.
2. **Game download**: Downloads up to 1,500 rated games per ELO band (blitz/rapid/classical).
3. **Filtering**: Only games where both players fall within the target rating window are kept.

### ELO Bands and Rating Windows

| Band | Rating Window | Games Collected |
|------|---------------|-----------------|
| 600  | 400–800       | ~1,500          |
| 1000 | 850–1150      | ~1,500          |
| 1400 | 1250–1550     | ~1,500          |
| 1800 | 1650–1950     | ~1,500          |

### Feature Extraction (`data/extract_features.py`)
For each position sampled from the games (every 3rd half-move):
1. The heuristic MoveEngine evaluates all legal moves (top 10 candidates).
2. For each candidate move, features are computed from `PositionSnapshot` and `MoveDelta`.
3. The human's actual move is labeled with `is_human_move=1`.

### Feature Definitions

| Feature | Type | Description |
|---------|------|-------------|
| `eval_gap` | Continuous | Centipawn difference from the best move |
| `difficulty` | Continuous | Estimated calculation complexity (0.4–5.0) |
| `safety_change` | Continuous | Change in piece safety (hanging piece value) |
| `center_change` | Continuous | Change in center square control |
| `king_safety_change` | Continuous | Change in king safety score |
| `development_change` | Discrete | Change in developed minor piece count |
| `mobility_change` | Continuous | Change in legal move count |
| `material_change` | Continuous | Change in material balance (centipawns) |
| `opponent_pressure_change` | Continuous | Change in pressure on opponent's king |
| `is_capture` | Binary | Whether the move captures a piece |
| `is_check` | Binary | Whether the move gives check |
| `is_castling` | Binary | Whether the move is castling |
| `num_preferred_tags` | Discrete | Count of level-preferred tags this move has |
| `num_priorities` | Discrete | Count of position priorities the move addresses |

### Dataset Size

| Band | Feature Rows | Unique Positions | Human Moves |
|------|-------------|------------------|-------------|
| 600  | 30,745      | 2,814            | 3,155       |
| 1000 | 36,804      | 3,395            | 3,755       |
| 1400 | 41,455      | 3,786            | 4,175       |
| 1800 | 51,585      | 4,856            | 5,281       |

## 3. Bayesian Models

### Model A: Human Move Prediction (Conditional Logit)

**Problem**: Given a position with $K$ candidate moves, each described by a feature vector $\mathbf{x}_j \in \mathbb{R}^{14}$, predict which move the human will choose.

**Model**:
$$U_j = \mathbf{x}_j^\top \boldsymbol{\beta}$$
$$P(\text{choose } j \mid \text{position}) = \frac{\exp(U_j)}{\sum_{k=1}^{K} \exp(U_k)}$$

**Priors**: $\beta_f \sim \mathcal{N}(0, 5)$ for all features $f$.

**Inference**: NUTS sampler via PyMC. 2 chains, 800 tuning + 1,500 sampling iterations each. Positions subsampled to 400 per band for tractable computation.

**Convergence**:

| Band | R-hat Range | ESS (bulk) Min | Converged? |
|------|-------------|----------------|------------|
| 600  | [1.000, 1.000] | 1,664 | Yes |
| 1000 | [1.000, 1.000] | 1,318 | Yes |
| 1400 | [1.000, 1.000] | 1,784 | Yes |
| 1800 | [1.000, 1.000] | 936   | Yes |

**Predictive accuracy** (top-1, in-sample):

| Band | Accuracy | Random Baseline | Lift |
|------|----------|-----------------|------|
| 600  | 31.5%    | 11.2%           | 2.8x |
| 1000 | 28.9%    | 11.0%           | 2.6x |
| 1400 | 28.1%    | 10.7%           | 2.6x |
| 1800 | —        | —               | —    |

### Model B: Tutor Score Weight Learning (Bayesian Logistic Regression)

**Problem**: Learn the optimal weights for the tutor scoring formula at each ELO band.

**Training signal**: A move is labeled "aspirational" if it was chosen by humans at the next higher ELO band (e.g., for band 1000, the target is which moves band-1400 humans play). This captures moves that are achievable improvements.

**Model**:
$$P(\text{aspirational} \mid \mathbf{x}) = \sigma(\mathbf{x}^\top \mathbf{w} + b)$$

**Features**: 8 features mapping to tutor score components (eval_gap, num_preferred_tags, num_priorities, safety_change, king_safety_change, center_change, opponent_pressure_change, difficulty).

**Priors**: $w_f \sim \mathcal{N}(0, 5)$, $b \sim \mathcal{N}(0, 5)$.

**Inference**: NUTS sampler, `target_accept=0.9` to reduce divergences. 2 chains, 800 tune + 1,500 draws.

**Results**: Models trained for bands 1000 and 1400.

### Key Learned Parameters (Selected)

**Model A: What predicts human move choice?**

| Feature | ELO 600 | ELO 1000 | ELO 1400 |
|---------|---------|----------|----------|
| `is_capture` | +1.57 | +1.34 | +1.08 |
| `is_check` | +2.38 | +2.10 | +2.83 |
| `difficulty` | -0.29 | -0.57 | -0.34 |
| `development_change` | +0.24 | -0.25 | +0.40 |
| `is_castling` | -0.60 | +0.45 | +1.25 |

Interpretation: Captures and checks strongly predict human choices at all levels. Difficulty is penalized more at 1000 ELO than at 600 (perhaps because 1000-rated players have just enough awareness to avoid complex moves). Castling becomes increasingly preferred as ELO rises.

**Model B: What makes a good teaching move?**

| Feature | Band 1000 | Band 1400 |
|---------|-----------|-----------|
| `difficulty` | -5.01 | — |
| `opponent_pressure_change` | -5.12 | — |
| `num_preferred_tags` | +1.10 | — |
| `center_change` | +0.38 | — |
| `king_safety_change` | +0.19 | — |

Interpretation: For 1000-rated players, difficulty is heavily penalized in good teaching moves. Moves matching preferred tags (safety, development) are rewarded. Pressure on the opponent's king is penalized — likely because such moves require tactical calculation that 1000-rated players cannot execute.

## 4. Integration

Learned parameters are stored in `data/trained_models/learned_params.json` and loaded by `app/core/learned_params.py` (lazy singleton pattern). Two functions are modified:

- `compute_tutor_score()` in `move_engine.py`: Uses Model B weights when available, heuristic fallback otherwise.
- `compute_human_plausibility()` in `diagnostics.py`: Uses Model A coefficients when available, heuristic fallback otherwise.

The fallback mechanism ensures the system works identically to the original when no trained parameters exist.

## 5. Comparison Results

### Benchmark Positions (15 curated positions)
- Agreement between learned and heuristic: **46.7%**
- The learned model prefers center-control and development moves for intermediate players
- For beginners (600), both models largely agree

### Held-out Game Positions (300 per band)
- Both models achieve 10-16% match rate with actual human play
- These rates are comparable because both models optimize for teaching value, not predicting exact human moves

## 6. Reproducibility

All results can be reproduced from scratch:

```bash
cd chess_tutor/

# 1. Install dependencies
pip install -r requirements.txt

# 2. Collect data from Lichess (~30 min)
python -m data.collect_lichess --games-per-band 1500

# 3. Extract features (~2 min)
python -m data.extract_features --max-games 200

# 4. Train models (in Jupyter notebook, ~5 min)
jupyter notebook notebooks/model_training.ipynb

# 5. Run comparison experiment
python analysis/compare_models.py

# 6. Run the app
streamlit run app/main.py
```

Raw data: Lichess public game database (free, no authentication needed for game exports). The PGN files are included in `data/processed/` for convenience.

## 7. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| python-chess | >=1.999 | Chess rules, PGN parsing, Stockfish interface |
| streamlit | >=1.50.0 | Web UI |
| pymc | >=5.10.0 | Bayesian inference (MCMC sampling) |
| arviz | >=0.17.0 | MCMC diagnostics and visualization |
| pandas | >=2.1.0 | Data manipulation |
| numpy | >=1.24.0 | Numerical computation |
| matplotlib | >=3.8.0 | Visualization |
| requests | >=2.31.0 | Lichess API calls |

No GPU required. All MCMC runs on CPU in under 5 minutes total.
