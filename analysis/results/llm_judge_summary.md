# LLM-as-judge A/B preference summary

- comparisons: **1572**
- models: claude-opus-4-6-agent
- personas: beginner_600, club_1400, intermediate_1000

## Overall preference (all personas, all positions)

| dimension | tutor | engine | tied |
|---|---|---|---|
| clearer | 98.9% | 0.4% | 0.7% |
| more_useful | 87.8% | 0.7% | 11.5% |
| less_overwhelming | 96.1% | 0.0% | 3.9% |

## Preference by persona

| persona | n | dimension | tutor | engine | tied |
|---|---|---|---|---|---|
| beginner_600 | 524 | clearer | 99.8% | 0.0% | 0.2% |
| beginner_600 | 524 | more_useful | 97.9% | 0.0% | 2.1% |
| beginner_600 | 524 | less_overwhelming | 100.0% | 0.0% | 0.0% |
| club_1400 | 524 | clearer | 98.9% | 0.6% | 0.6% |
| club_1400 | 524 | more_useful | 79.2% | 1.0% | 19.8% |
| club_1400 | 524 | less_overwhelming | 88.4% | 0.0% | 11.6% |
| intermediate_1000 | 524 | clearer | 98.1% | 0.6% | 1.3% |
| intermediate_1000 | 524 | more_useful | 86.3% | 1.1% | 12.6% |
| intermediate_1000 | 524 | less_overwhelming | 100.0% | 0.0% | 0.0% |

## Preference by level_key

| level_key | n | dimension | tutor | engine | tied |
|---|---|---|---|---|---|
| 1000 | 524 | clearer | 98.1% | 0.6% | 1.3% |
| 1000 | 524 | more_useful | 86.3% | 1.1% | 12.6% |
| 1000 | 524 | less_overwhelming | 100.0% | 0.0% | 0.0% |
| 1400 | 524 | clearer | 98.9% | 0.6% | 0.6% |
| 1400 | 524 | more_useful | 79.2% | 1.0% | 19.8% |
| 1400 | 524 | less_overwhelming | 88.4% | 0.0% | 11.6% |
| 600 | 524 | clearer | 99.8% | 0.0% | 0.2% |
| 600 | 524 | more_useful | 97.9% | 0.0% | 2.1% |
| 600 | 524 | less_overwhelming | 100.0% | 0.0% | 0.0% |

## Preference when tutor move equals / differs from engine best

| case | n | dimension | tutor | engine | tied |
|---|---|---|---|---|---|
| tutor_equals_engine | 1072 | clearer | 99.3% | 0.3% | 0.5% |
| tutor_equals_engine | 1072 | more_useful | 86.7% | 0.1% | 13.2% |
| tutor_equals_engine | 1072 | less_overwhelming | 94.3% | 0.0% | 5.7% |
| tutor_differs_from_engine | 500 | clearer | 98.2% | 0.6% | 1.2% |
| tutor_differs_from_engine | 500 | more_useful | 90.2% | 2.0% | 7.8% |
| tutor_differs_from_engine | 500 | less_overwhelming | 100.0% | 0.0% | 0.0% |

## Sample one-line reasons (most recent 12)

- **beginner_600** @ 600 (tutor=engine, pgn:pool_1.pgn:ply26): I don't know what eval or cp means but the habit tip tells me what to actually do.
- **intermediate_1000** @ 1000 (tutor=engine, pgn:pool_1.pgn:ply26): The habit tip helps but the advice feels generic; at least I know what to focus on.
- **club_1400** @ 1400 (tutor=engine, pgn:pool_1.pgn:ply26): Telling me options are 'similar strength' is more useful than cp gaps I can't interpret.
- **beginner_600** @ 600 (tutor≠engine, pgn:pool_1.pgn:ply27): The numbers mean nothing to me but the warning and habit tip are things I can remember.
- **intermediate_1000** @ 1000 (tutor≠engine, pgn:pool_1.pgn:ply27): I know basic principles so the coaching guidance connects better than raw eval numbers.
- **club_1400** @ 1400 (tutor≠engine, pgn:pool_1.pgn:ply27): I can calculate checks at my level, so skipping a strong check feels wrong despite the coaching.
- **beginner_600** @ 600 (tutor≠engine, pgn:pool_1.pgn:ply28): The numbers mean nothing to me but the warning and habit tip are things I can remember.
- **intermediate_1000** @ 1000 (tutor≠engine, pgn:pool_1.pgn:ply28): I know basic principles so the coaching guidance connects better than raw eval numbers.
- **club_1400** @ 1400 (tutor≠engine, pgn:pool_1.pgn:ply28): Explaining why the practical move differs from engine best is exactly what I need.
- **beginner_600** @ 600 (tutor=engine, pgn:pool_1.pgn:ply29): I don't know what eval or cp means but the habit tip tells me what to actually do.
- **intermediate_1000** @ 1000 (tutor=engine, pgn:pool_1.pgn:ply29): The habit tip helps but the advice feels generic; at least I know what to focus on.
- **club_1400** @ 1400 (tutor=engine, pgn:pool_1.pgn:ply29): Telling me options are 'similar strength' is more useful than cp gaps I can't interpret.

