# Email Prompt-Injection Base

This base demonstrates how the S6 security layer can inspect untrusted email or
retrieved text before it reaches an orchestrator, a language model, or a privileged
tool. It includes a BIPIA data-preparation pipeline, an explainable rule-based
detector, a batch evaluation, and a local frontend connected to the Python backend.

## Folder layout

```text
prompt_injection/
├─ app.py                    Local HTTP backend
├─ detector.py               P1 rule engine: ALLOW / REVIEW / BLOCK policy
├─ semantic_detector.py      P2 semantic task-consistency detector
├─ prepare_bipia.py          Builds BIPIA attack samples
├─ prepare_splits.py         Freezes category-disjoint development/test splits
├─ tool_policy.py            P3 tool-call policy: ALLOW / HUMAN_REVIEW / DENY gate
├─ confused_deputy_scenarios.py  Hand-authored P3 demo/evaluation fixture
├─ eval_common.py            Shared dataset-loading and metric helpers
├─ evaluate_baseline.py      P1 group metrics, latency, and failure outputs
├─ evaluate_semantic.py      P2 rule/semantic/hybrid comparison
├─ evaluate_tool_policy.py   P3 harm-containment evaluation
├─ requirements-windows.txt  Windows data-processing dependencies
├─ start.cmd                 One-click launcher for this base
├─ tests/                    Unit and HTTP integration tests
└─ web/
   └─ index.html             Browser frontend
```

Large or generated data remains outside the code base:

```text
external/BIPIA/                    Upstream Microsoft repository
external/minilm_cache/             Cached MiniLM sentence-embedding model weights (P2)
data/bipia/generated/              Constructed JSONL samples
data/bipia/splits/                 Fixed attack manifests
data/bipia/semantic_embedding_cache.npz  Cached per-text MiniLM embeddings (P2)
results/bipia/                     Evaluation CSV and JSON results
```

## Quick start: frontend and backend together

Double-click this folder's `start.cmd`, or run it from a terminal.

The launcher starts the Python backend at:

```text
http://127.0.0.1:8765
```

It then opens the frontend in the default browser. Keep the terminal window open;
press `Ctrl+C` in that terminal to stop the backend.

### Using the frontend

1. Review detector identity, split sizes, and plain/stealth P1 metrics at the top.
2. Select development or test and plain or stealth sample form.
3. Load a random BIPIA sample and run the security detector.
4. Read the decision, risk score, reasons, and highlighted risky phrases.
5. Replace the sample with any email, webpage text, user input, or retrieved content.

`ALLOW` means that the current baseline did not find a configured signal. It does not
prove that the content is safe. `REVIEW` requires a second detector or human check.
`BLOCK` means the content should not influence model instructions or privileged actions.

## Running the backend manually

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\prompt_injection\app.py'
```

Useful options:

```text
--port 8765       Change the local port
--no-browser      Start the backend without opening a browser
```

### Backend endpoints

#### `GET /api/status`

Returns detector identity, thresholds, fixed split sizes, and the latest P1 summaries.

#### `GET /api/example`

Returns a random generated BIPIA email, its attack category, and insertion position.
It accepts, for example, `/api/example?split=development&encoding=stealth`.

#### `GET /api/tool-scenario`

Returns a random scenario from the P3 confused-deputy fixture: `scenario_id`,
`description`, `content`, `tool_name`, `target`, `parameters`, and a `ground_truth`
object (`triggered_by_untrusted_content`, `actually_harmful`). The ground truth is
shown for demo pedagogy only, since this is a small illustrative fixture, not a blind
evaluation of visitor input.

#### `POST /api/detect`

Request (`tool_name`/`target` are optional; omit or leave blank to skip the P3 check):

```json
{"text": "Untrusted email or retrieved content", "tool_name": "send_email", "target": "user@company.example"}
```

Response:

```json
{
  "decision": "BLOCK",
  "score": 6,
  "reasons": ["instruction-override language"],
  "detector": "s6-rule-prompt-injection",
  "version": "0.2.0",
  "config_hash": "...",
  "highlights": [
    {"start": 20, "end": 48, "label": "instruction override"}
  ],
  "tool_policy": {
    "detector": {"detector": "s6-tool-call-policy", "version": "0.1.0", "config_hash": "..."},
    "decision": "DENY",
    "reasons": ["high-impact action blocked: content detector flagged BLOCK"],
    "permission": "EXTERNAL_COMMUNICATION"
  }
}
```

The orchestrator can call this endpoint, or import `detect_prompt_injection` directly
from `detector.py`. The frontend never implements security decisions itself; it only
displays backend results. Every live `tool_name`-bearing request also appends a
ground-truth-free line to `results/bipia/tool_policy_audit.jsonl`.

## Preparing and evaluating BIPIA

First create the fixed attack manifests. Development uses BIPIA train categories except
`Language Translation`, which overlaps with test. Final test uses every BIPIA test
category, so the two selected category sets are disjoint:

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\prompt_injection\prepare_splits.py'
```

Then generate both EmailQA source splits:

```powershell
$python = 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe'
$prepare = 'E:\研究生\高级计算机项目\s6\prompt_injection\prepare_bipia.py'
& $python $prepare --task email --split train
& $python $prepare --task email --split test
```

Run the clean-versus-attacked evaluation:

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\prompt_injection\evaluate_baseline.py'
```

The evaluation writes:

- `email_p1_plain_summary.json`: grouped metrics, input hashes, detector version, and configuration hash.
- `email_p1_plain_decisions.csv`: per-sample decisions, reasons, and latency.
- `email_p1_plain_failures.csv`: missed attacks and clean false positives.

For rule detector v0.2.0, plain development contains 10,500 attacks with 65.71%
detection and 0% clean false positives. Test contains 11,250 attacks with 93.47%
detection and 2% clean false positives. With `--stealth`, which evaluates BIPIA's
Base64 form, detection is 98.57% and 96.08%, respectively. Report these results with
the grouped and latency data in the JSON file.

Run the automated tests with:

```powershell
Set-Location 'E:\研究生\高级计算机项目\s6\prompt_injection'
& '..\..\.venv-bipia\Scripts\python.exe' -B -m unittest discover -s tests -v
```

Other available upstream tasks include `table` and `code`. Web question answering and
summarisation require separate source datasets because of upstream licence restrictions.

## P2: semantic task-consistency detector

The P1 rule engine only flags a line if it *syntactically* looks like an instruction
(starts with an imperative verb). That is exactly why obfuscated attack categories such
as Anagramming, Misspelling Intentionally, and Space Removal & Grouping evade it:
scrambling or misspelling a line breaks the regex without breaking the instruction.

`semantic_detector.py` adds an independent signal that asks a different question: does
this instruction-like line actually relate to what the user asked for? It embeds the
user's real task (BIPIA's `question` field) and every sufficiently long, non-header line
of the untrusted email content with `sentence-transformers/all-MiniLM-L6-v2` (loaded via
plain `transformers`, no separate package required), then flags the record if the
*worst* (most dissimilar) candidate line falls below a similarity threshold. It never
receives BIPIA's attack label — only `question` and `context`, the same two things a
real deployment already has.

Run the three-system comparison (rule-only, semantic-only, and hybrid) with:

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\prompt_injection\evaluate_semantic.py'
```

The first run downloads and caches the ~90MB MiniLM model under `external/minilm_cache/`
and computes embeddings for every unique question/candidate-line string in the
development and unseen-test splits (a few hundred unique strings; a few seconds on CPU),
caching them in `data/bipia/semantic_embedding_cache.npz` for subsequent runs. Add
`--stealth` to evaluate the Base64-encoded attack form, matching `evaluate_baseline.py`.

Measured results (plain / stealth encoding, development / unseen-test splits):

| Split | Encoding | System | Attack detection | Clean FPR |
|---|---|---|---|---|
| development | plain | rule / semantic / hybrid | 65.71% / 43.66% / 79.78% | 0% / 4% / 4% |
| unseen_test | plain | rule / semantic / hybrid | 93.47% / 37.05% / 97.08% | 2% / 4% / 4% |
| development | stealth | rule / semantic / hybrid | 98.57% / 14.05% / 98.65% | 0% / 4% / 4% |
| unseen_test | stealth | rule / semantic / hybrid | 96.08% / 17.96% / 96.21% | 2% / 4% / 4% |

The hybrid system (worse of rule and semantic) improves recall over rule-alone on every
split and encoding, at a consistent cost: clean false positives rise from 0-2% to 4%
(one additional clean email out of 50 per split). The recall gain is largest on
plain-text attacks, where the semantic signal independently recovers records the rule
engine misses entirely, concentrated in the categories the roadmap flagged as rule
blind spots (Information Retrieval, Content Creation, Misspelling Intentionally,
Learning and Tutoring, Clickbait). On stealth attacks the rule engine's
`encoded_instruction` signal already catches almost everything, so the semantic-only
signal adds little there. See `s6/BASELINE_ROADMAP.md`'s P2 milestone for the full
writeup, including why the 4% clean-FPR figure (2 of 50 clean emails) carries wide
uncertainty at this sample size.

`REVIEW_SIMILARITY`/`BLOCK_SIMILARITY` in `semantic_detector.py` were calibrated on the
development split only, per the same experimental-integrity rule that governs P1 rule
changes: unseen-test results must not be used to retune them.

P2 is wired into `app.py`/`web/index.html`: providing a `question` alongside the
content runs the semantic and hybrid checks live, in addition to the standalone
evaluation script above.

## P3: action and permission containment

P1 and P2 both answer the same question — *is this content an injection?* — and both
can miss one. The roadmap's next question is different: *if an injection is missed,
can least privilege prevent it from causing real harm?* `tool_policy.py` answers this
independently of the content detectors: given only a content decision
(`ALLOW`/`REVIEW`/`BLOCK`) and a requested tool call (`tool_name`, `target`), it gates
high-impact actions (`WRITE`, `EXTERNAL_COMMUNICATION`, `SENSITIVE_DATA`) against a
registry of pre-approved trusted targets, returning `ALLOW` / `HUMAN_REVIEW` / `DENY`.
Read-only actions (`read_email`, `search_documents`) are exempt — content gating is
P1/P2's job, not this layer's. It never reads ground truth: `ToolCall` structurally has
no harm-related field, and `evaluate_tool_call`'s two-parameter signature is checked by
a unit test so neither can grow a hidden ground-truth input later.

`confused_deputy_scenarios.py` is a small, hand-authored fixture (18 scenarios, not a
`prepare_*.py`-generated corpus) covering all four permission tiers: benign requests to
trusted and untrusted targets, attacks P1 correctly blocks, and — the core
demonstration — attacks P1 *misses* (`ALLOW`) that target an untrusted destination, so
this layer still routes them to `HUMAN_REVIEW` instead of letting them execute.

Run the evaluation with:

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\prompt_injection\evaluate_tool_policy.py'
```

Measured results (18 scenarios, all evaluated — see "no split" note below):

| Metric | Value |
|---|---|
| Decisions (ALLOW / HUMAN_REVIEW / DENY) | 5 / 9 / 4 |
| Harmful-scenario success rate without this layer | 100.00% (by construction) |
| Harmful-scenario success rate with this layer | 11.11% |
| Content detector missed it, this layer still contained it | 3 of 9 harmful scenarios |
| Benign high-impact friction rate | 71.43% |

Least privilege substantially reduces harmful-action success (100% → 11.11%) at a real
cost: most benign high-impact requests to a not-yet-trusted target also get routed to
human review. This is reported plainly, not hidden, matching this project's convention
of always pairing a benefit metric with its friction cost.

Unlike P1/P2, no development/test split is used here. That split protects a *tunable
numeric threshold* (`REVIEW_THRESHOLD`/`BLOCK_THRESHOLD`, `REVIEW_SIMILARITY`/
`BLOCK_SIMILARITY`) from being fit to the data it is scored on. `tool_policy.py` has no
tunable threshold — its decision table is fixed by the roadmap's four permission
categories and a registry of pre-approved targets, not calibrated from this fixture —
so every scenario is evaluated and the fixture-vs-live-detector agreement is checked by
unit tests instead.

**Known containment gap**, demonstrated by one scenario in the fixture rather than left
implicit: if an injection both slips past the content detector (`ALLOW`) *and* directs
the action at an already pre-approved trusted target, this layer also returns `ALLOW`.
Least privilege narrows the blast radius of a missed injection; it does not close it.

P3 is wired into `app.py`/`web/index.html`: choosing a tool and target (or loading a
confused-deputy scenario) alongside the content runs this check live, alongside P1/P2.

## Security and research limitations

- The current detector is an explainable, hard-coded baseline.
- Keyword and pattern rules can be bypassed by paraphrasing or novel attacks.
- Aggregate BIPIA test results were already observed before v0.2.0. The new manifests
  are therefore a fixed prospective protocol for future versions, not a pristine blind
  test claim for v0.2.0.
- Clean email data is still limited to 50 train and 50 test records; a larger independent
  clean corpus remains necessary.
- Dataset performance must not be presented as universal real-world security.
- P3's least-privilege gate narrows the blast radius of a missed injection but does not
  close it: an injection that both evades P1/P2 and targets an already-trusted
  destination is not caught (see "known containment gap" above). Safe deployment also
  still benefits from independent tool authorisation, provenance, monitoring, and
  rollback beyond what this prototype implements.
- The server binds only to `127.0.0.1`; pasted content stays on the local machine.

For the Chinese guide, see [README_ZH.md](README_ZH.md).

The shared development plan is available in
[../BASELINE_ROADMAP.md](../BASELINE_ROADMAP.md).


## 2026-09-21：监督分类扩展

Email、Table、Code 已完成按原始正文分组的监督训练与独立测试，新增实验对照开关。该轻量分类器并非普遍优于已有规则，因此保留为独立研究对照，不替换工具门控。数据使用范围、排重、运行命令和结果限制见 [监督实验协议](SUPERVISED_PROTOCOL_ZH.md)。


## Automatic intent comparison (exploratory)

The console now has a separate comparison panel below the live check. It uses frozen MiniLM cosine similarity against six fixed task descriptions to infer a task type from content alone. The 18 existing authored tool scenarios supply proxy reference categories only after prediction. The panel shows agreement, macro class recall, a majority-class baseline, per-scenario results, and P2/Hybrid detection metrics under preset versus inferred tasks. These are not new BIPIA benchmark results or independently annotated user-intent accuracy.

GET `/api/intent-comparison` loads a signature-checked report; POST with `{}` runs the experiment if a current report is unavailable. Results live in `results/bipia/intent_comparison/`. The experiment never changes the live authorization policy.

The live form separately supports trusted task resolution: `/api/example` returns the original BIPIA question and an opaque content-bound context; `/api/tool-scenario` returns an explicitly labeled demo task preset. POST `/api/intent` previews the resolved source/category. `/api/detect` accepts `task_context` instead of a manual question. Manual `question` overrides the context. Editing sample content invalidates automatic context, and missing tasks do not become an automatic P2 ALLOW. These task categories are descriptive labels; P2 receives the complete question.
