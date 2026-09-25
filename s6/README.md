> Current status (2026-09-25): the image console defaults to the **classmate fruit-fly dataset**; STL-10 is a toggleable 3-seed historical comparison; IP102 is frozen. Milestone status is in the snapshot at the top of [BASELINE_ROADMAP.md](BASELINE_ROADMAP.md).

# S6 Security Bases

The S6 prototype is organised as two independent, reusable bases:

1. [`prompt_injection`](prompt_injection/) — BIPIA email and retrieved-content security
   (P1 rules, P2 semantic task consistency, P3 tool permissions, P3.1 explicit approval;
   a supervised classifier is an optional research control).
2. [`data_poisoning`](data_poisoning/) — training-data manifest integrity and label-poisoning
   detection (fruit fly by default, STL-10 comparison, IP102 historical).

Each folder contains its own frontend, backend, detector, preparation/evaluation scripts,
English README, Chinese README, and `start.cmd`. The root `start.cmd` is a unified portal
(http://127.0.0.1:8764/) that only starts or reuses the two backends and implements no
detection logic. Large upstream datasets remain in `external`, generated data in `data`,
and evaluation evidence in `results`.

The applications use different local ports and can run at the same time:

- Unified portal: `http://127.0.0.1:8764`
- Email prompt injection: `http://127.0.0.1:8765`
- Image data poisoning: `http://127.0.0.1:8766`

See [README_ZH.md](README_ZH.md) for the Chinese overview.

Development milestones and acceptance criteria are defined in
[BASELINE_ROADMAP.md](BASELINE_ROADMAP.md).
