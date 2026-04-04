# Executive Summary: A Chess Tutor You Don't Want to Punch in the Face

## The Problem

Chess engines like Stockfish can tell you the best move in any position. But for a beginner, "best" and "useful" are not the same thing. A 600-rated player told to play a 12-move tactical combination will learn nothing — the move is correct but incomprehensible. What beginners need is a tutor that recommends moves they can actually understand, execute, and learn from.

## Our Solution

We built an interactive chess tutor that separates two questions: "What is the strongest move?" and "What is the most useful move for this player right now?" Every legal move receives two scores — an engine score measuring objective strength and a tutor score measuring teaching value for the student's current skill level. When these scores disagree, the system explains why, giving the student insight into the gap between where they are and where they're headed.

The system supports four skill levels (600, 1000, 1400, and 1800 ELO) and provides three modes of interaction: a position analyzer for studying specific board states, a play-against-bot mode with move-by-move coaching, and a post-game review that identifies recurring weaknesses.

## How the Tutor Score Works

Rather than hand-picking weights for the tutor scoring formula, we trained the system on real human chess games from Lichess, one of the world's largest online chess platforms. We collected over 5,000 rated games across all four skill levels and extracted features for each move — how much it helps with piece safety, center control, development, and so on.

We then used Bayesian statistical models to learn two things from this data:

1. **What moves do humans at each level actually play?** A conditional choice model captures which features predict human move selection. For example, beginners strongly favor captures and checks, while intermediate players weight positional features more heavily.

2. **What makes a good teaching move?** A second model identifies moves that players at the next skill level would choose — aspirational but reachable. These "stepping stone" moves form the training signal for the tutor score.

The result is a scoring system grounded in real human behavior rather than programmer intuition. The Bayesian approach also gives us uncertainty estimates for every weight, so we know how confident we are in each recommendation.

## Evidence That It Works

We compared the learned model against both the raw engine and the initial hand-tuned heuristic:

- **Prediction accuracy**: The Bayesian model predicts actual human moves 2.6 to 2.8 times better than random guessing across all skill levels.
- **Different from the engine**: The tutor recommends a different move than the engine in over 50% of positions — confirming that it genuinely adapts recommendations to the player's level.
- **Different from the heuristic**: On benchmark positions, the learned model disagrees with the hand-tuned version 53% of the time, with the learned model favoring center-control and development moves that match real beginner play patterns.
- **Level-appropriate**: The system recommends different moves for different skill levels in the same position. A 600-rated player might be told to castle for safety, while a 1400-rated player facing the same board is encouraged to seize the initiative.

## Future Work

Several extensions would strengthen the system:

- **Live user studies** with actual novice players to measure ELO improvement over time
- **Adaptive difficulty** that adjusts in real time as the student improves within a session
- **Opening repertoire tracking** to build on what the student already knows
- **Deeper integration with Stockfish** for accurate evaluation in complex positions
- **Hierarchical Bayesian model** that shares information across ELO bands for more robust parameter estimates

## Conclusion

This project demonstrates that probabilistic machine learning can meaningfully improve chess tutoring. By learning from data how real players at different levels choose moves, the system produces recommendations that are both statistically principled and pedagogically appropriate — bridging the gap between what an engine thinks and what a human can learn.
