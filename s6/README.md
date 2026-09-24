> Active image baseline: **STL-10** (2026-09-11). IP102 results are historical. See [current protocol](data_poisoning/README_ZH.md).

# S6 Security Bases

The S6 prototype is organised as two independent, reusable bases:

1. [`prompt_injection`](prompt_injection/) — BIPIA email and retrieved-content security.
2. [`data_poisoning`](data_poisoning/) — IP102 training-data and manifest integrity.

Each folder contains its own frontend, backend, detector, preparation/evaluation scripts,
English README, and Chinese README — including its own `start.cmd` launcher, so there is
no shared launcher at the project root. Large upstream datasets remain in `external`,
generated data in `data`, and evaluation evidence in `results`.

Both applications can run at the same time because they use different local ports:

- Email prompt injection: `http://127.0.0.1:8765`
- IP102 data poisoning: `http://127.0.0.1:8766`

See [README_ZH.md](README_ZH.md) for the Chinese overview.

Development milestones and acceptance criteria are defined in
[BASELINE_ROADMAP.md](BASELINE_ROADMAP.md).
