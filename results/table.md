| Configuration | L1 | L2 | L3 | L4 | L5 | L6 | L7 | L8 | L9 | L10 | Mean of levels run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-opus-5-5 · no shell | 1.00 | 1.00 | 0.93 | 0.97 | 0.79 | 0.86 | 0.90 | – | – | – | 0.92 |
| gpt-6.1-sol · Codex | 1.00 | 1.00 | 1.00 | 0.98 | 0.74 | 0.99 | 0.99 | 1.00 | 0.73 | 0.75 | 0.92 |
| claude-opus-5-5 · Claude Code | 1.00 | 1.00 | 0.98 | 0.98 | 0.69 | 0.93 | 0.80 | 1.00 | 0.69 | 0.59 | 0.87 |
| gpt-6-luna · Codex | 1.00 | 1.00 | 0.99 | 0.88 | 0.81 | 0.87 | 0.64 | 0.68 | 0.49 | 0.54 | 0.79 |
| claude-haiku-5-5 · Claude Code | 1.00 | 1.00 | 1.00 | 0.93 | 0.67 | 0.73 | 0.81 | 0.85 | 0.47 | 0.31 | 0.78 |
| claude-sonnet-5-5 · mini-SWE-agent | 0.89 | 1.00 | 1.00 | 0.99 | 0.67 | 0.80 | 0.66 | 0.74 | 0.61 | 0.31 | 0.77 |
| claude-sonnet-5-5 · Claude Code | 0.74 | 0.68 | 0.59 | 0.63 | 0.55 | 0.65 | 0.50 | 0.57 | 0.51 | 0.40 | 0.58 |
| reference script (knows the rules of the level) | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.99 | 0.99 | 0.99 | 1.00 | 1.00 | 1.00 |
| script that assumes nothing will change | 1.00 | 1.00 | 1.00 | 0.28 | 0.19 | 0.19 | 0.29 | 0.08 | 0.12 | 0.12 | 0.43 |
| earliest-legal-move script | 0.48 | 0.34 | 0.45 | 0.47 | 0.34 | 0.39 | 0.37 | 0.39 | 0.40 | 0.44 | 0.41 |

| Configuration | Games | Off L's list | On the list | Missed a deadline | Arrested |
|---|---|---|---|---|---|
| gpt-6.1-sol · Codex | 64 | 21 | 26 | 0 | 17 (27%) |
| claude-opus-5-5 · Claude Code | 64 | 19 | 24 | 1 | 20 (31%) |
| claude-sonnet-5-5 · mini-SWE-agent | 24 | 3 | 11 | 1 | 9 (38%) |
| claude-sonnet-5-5 · Claude Code | 24 | 2 | 12 | 0 | 10 (42%) |
| gpt-6-luna · Codex | 24 | 5 | 9 | 0 | 10 (42%) |
| claude-haiku-5-5 · Claude Code | 24 | 2 | 10 | 1 | 11 (46%) |
