| Configuration | L1 | L2 | L3 | L4 | L5 | L6 | L7 | L8 | L9 | Mean of levels run |
|---|---|---|---|---|---|---|---|---|---|---|
| gpt-6.1-sol · Codex | 1.00 | 1.00 | 1.00 | 0.98 | 0.74 | 0.99 | 0.99 | 1.00 | 0.73 | 0.94 |
| claude-opus-5-5 · no shell | 1.00 | 1.00 | 0.93 | 0.97 | 0.79 | 0.86 | 0.90 | – | – | 0.92 |
| claude-opus-5-5 · Claude Code | 1.00 | 1.00 | 0.98 | 0.98 | 0.69 | 0.93 | 0.80 | 0.99 | 0.70 | 0.90 |
| claude-haiku-5-5 · Claude Code | 1.00 | 1.00 | 1.00 | 0.93 | 0.67 | 0.73 | 0.81 | 0.82 | 0.47 | 0.83 |
| gpt-6-luna · Codex | 1.00 | 1.00 | 0.99 | 0.88 | 0.81 | 0.87 | 0.64 | 0.64 | 0.49 | 0.81 |
| claude-sonnet-5-5 · mini-SWE-agent | 0.89 | 1.00 | 1.00 | 0.99 | 0.67 | 0.80 | 0.66 | 0.66 | 0.63 | 0.81 |
| claude-sonnet-5-5 · Claude Code | 0.74 | 0.68 | 0.59 | 0.63 | 0.55 | 0.65 | 0.50 | 0.50 | 0.51 | 0.59 |
| reference script (knows the rules of the level) | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.99 | 0.99 | 1.00 | 1.00 | 1.00 |
| script that assumes nothing will change | 1.00 | 1.00 | 1.00 | 0.28 | 0.19 | 0.19 | 0.29 | 0.08 | 0.12 | 0.43 |
| earliest-legal-move script | 0.48 | 0.34 | 0.45 | 0.47 | 0.34 | 0.39 | 0.37 | 0.39 | 0.40 | 0.41 |

| Configuration | Games | Off L's list | On the list | Missed a deadline | Arrested |
|---|---|---|---|---|---|
| claude-sonnet-5-5 · mini-SWE-agent | 15 | 3 | 7 | 1 | 4 (27%) |
| gpt-6.1-sol · Codex | 48 | 17 | 18 | 0 | 13 (27%) |
| claude-opus-5-5 · Claude Code | 47 | 16 | 17 | 0 | 14 (30%) |
| claude-sonnet-5-5 · Claude Code | 16 | 2 | 8 | 0 | 6 (38%) |
| claude-haiku-5-5 · Claude Code | 16 | 1 | 8 | 0 | 7 (44%) |
| gpt-6-luna · Codex | 16 | 3 | 6 | 0 | 7 (44%) |
