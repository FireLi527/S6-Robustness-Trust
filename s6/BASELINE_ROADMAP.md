# S6 Baseline Development Roadmap

This roadmap covers the two current S6 prototypes:

1. **Email Prompt-Injection Baseline** using BIPIA.
2. **IP102 Data-Poisoning Baseline** using controlled label poisoning.

The immediate objective is to turn both working demonstrations into reproducible,
evidence-based security baselines. New large security modules should be postponed until
these two baselines have independent tests, defensible metrics, and stable interfaces.

## Shared definition of done

A baseline is considered complete when it has:

- A documented threat model and trust boundary.
- Separate development data and unseen evaluation data.
- Hidden ground truth that is unavailable to the detector.
- A reproducible preparation and evaluation command.
- Clean and attacked/poisoned control groups.
- Detection, false-positive, and latency measurements.
- An explainable `ALLOW`, `REVIEW`, or `BLOCK` response.
- Versioned detector configuration and audit evidence.
- A local frontend that displays real backend results.
- Documented limitations and failure cases.
- A stable interface that an orchestrator can call.

---

# Baseline 1: Email Prompt Injection

## Threat model

Untrusted email, webpage, retrieved document, or user-supplied content contains text that
the language model may interpret as an instruction. The attack may redirect the task,
control the answer format, request sensitive information, or trigger a privileged tool.

The S6 boundary sits between untrusted content and the orchestrator/model/tool layer.

## Current state — P1 protocol implemented

- Microsoft BIPIA repository and EmailQA data are installed locally.
- Plain and stealth EmailQA attacks have been generated for both BIPIA train and test.
- `data/bipia/splits/` freezes 14 development and 15 test attack categories with no
  category overlap.
- Development and test each use a separate 50-email clean set evaluated through the
  same interface as attacked records.
- An explainable rule detector returns `ALLOW`, `REVIEW`, or `BLOCK`.
- The backend returns scores, reasons, risky-text spans, detector version, and config hash.
- The frontend supports pasted text and random BIPIA samples.
- Evaluation stores per-sample decisions, misses/false positives, attack-family and
  insertion-position metrics, and median/p95 latency.
- Rule v0.2.0 detects 65.71% of plain development attacks with 0% clean false positives;
  test detection is 93.47% with 2% clean false positives.
- Automated unit and integration tests cover policy, split construction, metrics,
  status reporting, and HTTP detection flows.

These results describe the current dataset only and are not a claim of general security.
Because aggregate test results were seen before v0.2.0 development, this version is not
a pristine blind test. The frozen manifests are a prospective protocol for future versions.

## Milestone P1 — experimental separation (implemented)

### Research question

Does the detector recognise attacks that were not used to design its rules?

### Implemented

- Split attack families into development and unseen-test groups.
- Freeze the test group before changing detector rules.
- Expand clean controls from one 50-email set to separate 50-email train/test sets.
- Record results by attack family and insertion position.
- Store a version and configuration hash with every evaluation.

### Deliverables

- `splits/attack_development.json`
- `splits/attack_unseen_test.json`
- Versioned evaluation summary.
- False-positive examples and missed-attack examples.

### Rules for subsequent versions

- From v0.2.1 onward, test attacks and grouped test results are not read during rule development.
- Clean and attacked records are evaluated with the same interface.
- Results are reproducible with a fixed seed and command.
- A larger independent clean-email corpus is still needed to reduce uncertainty in the
  current false-positive estimate.

## Milestone P2 — semantic task-consistency detector (implemented)

### Research question

Can S6 identify an instruction that is harmless in isolation but conflicts with the
user's actual task?

### Implemented

- `semantic_detector.py` embeds the user's BIPIA `question` and every sufficiently long
  (>=25 characters), non-header line of the untrusted `context` with
  `sentence-transformers/all-MiniLM-L6-v2` (loaded via plain `transformers`, mean-pooled
  and L2-normalized; the detector's only inputs are `question` and `context` — it never
  receives `attack_name` or any ground-truth label).
- Candidate lines are found by content, not syntax: unlike the P1 rule engine's
  imperative-verb regex (`_PROMPT_LIKE_ENDING`), any long-enough, non-header line is a
  candidate, so semantic similarity — not sentence structure — decides suspicion. This
  is what lets the signal catch obfuscated/reordered instructions the rule engine's
  syntax-first filter misses.
- The minimum cosine similarity between the question and any candidate line drives an
  independent `ALLOW`/`REVIEW`/`BLOCK` decision (`REVIEW_SIMILARITY=0.03`,
  `BLOCK_SIMILARITY=0.00`), thresholds chosen by inspecting the development split's
  similarity distribution only, per the P1 experimental-integrity rule.
- `evaluate_semantic.py` scores three parallel systems — rule-only, semantic-only, and
  hybrid (worse-of-two wins) — over the same development/unseen-test splits P1 uses.

### Results

| Split | Encoding | System | Attack detection | Clean FPR | F1 |
|---|---|---|---|---|---|
| development | plain | rule | 65.71% | 0.0% | 0.793 |
| development | plain | semantic | 43.66% | 4.0% | 0.608 |
| development | plain | hybrid | 79.78% | 4.0% | 0.887 |
| unseen_test | plain | rule | 93.47% | 2.0% | 0.966 |
| unseen_test | plain | semantic | 37.05% | 4.0% | 0.541 |
| unseen_test | plain | hybrid | 97.08% | 4.0% | 0.985 |
| development | stealth | rule | 98.57% | 0.0% | 0.993 |
| development | stealth | semantic | 14.05% | 4.0% | 0.246 |
| development | stealth | hybrid | 98.65% | 4.0% | 0.993 |
| unseen_test | stealth | rule | 96.08% | 2.0% | 0.980 |
| unseen_test | stealth | semantic | 17.96% | 4.0% | 0.305 |
| unseen_test | stealth | hybrid | 96.21% | 4.0% | 0.981 |

- Hybrid improves recall over rule-alone on every split/encoding combination measured,
  at a consistent cost: the clean false-positive rate rises from 0-2% to 4% (2 of the 50
  clean emails in each split, in both encodings — the same two clean emails, since
  clean text is unaffected by attack encoding).
- The recall gain is largest on plain-text attacks (development +14.1pp, unseen_test
  +3.6pp), where the semantic signal independently recovers records the rule engine's
  syntax-first filter misses entirely, concentrated in exactly the categories the
  roadmap flagged as rule blind spots: Information Retrieval, Content Creation,
  Misspelling Intentionally, Learning and Tutoring, and Clickbait.
- On stealth (Base64-encoded) attacks the rule engine's `encoded_instruction` signal
  already catches almost everything, so semantic-only recall alone is much lower
  (14-18%) — a Base64 blob is not English-like prose the embedding model can meaningfully
  compare against the question — but hybrid still adds a small recall gain on top.
- Honest limitation: the 4% clean-FPR floor comes from only 2 of the 50-email clean set
  per split; with such a small clean sample, that rate has wide uncertainty and a larger
  independent clean corpus (already flagged as needed under P1) is the natural next step
  to pin it down.

### Deliverables

- `semantic_detector.py` — task-aware detection interface (`assess_task_consistency`,
  `combine_hybrid`, `extract_candidate_instructions`).
- `evaluate_semantic.py` — per-detector (rule/semantic/hybrid) comparison results,
  written to `results/bipia/email_p2_{plain,stealth}_{decisions,failures,summary}.{csv,json}`.
- `tests/test_semantic_detector.py`.
- Examples such as a payment question containing an unrelated translation or movie task
  are covered directly by the unit tests (`test_off_topic_instruction_is_flagged`).

### Acceptance criteria

- The semantic detector does not receive BIPIA's attack label — confirmed by
  construction (`assess_task_consistency`'s only inputs are `question` and `context`).
- It improves unseen-attack recall (93.47%→97.08% plain, 96.08%→96.21% stealth) at a
  measured, reported cost in clean false positives (2%→4%, i.e. one additional clean
  email out of 50) — judged an acceptable trade for this baseline, not an unmeasured one.
- Every `REVIEW`/`BLOCK` result includes a human-readable reason (e.g.
  `"instruction-like content is semantically unrelated to the user's task
  (similarity=0.01)"`).

## Milestone P3 — action and permission containment (implemented)

### Research question

If an injection is missed, can least privilege prevent it from causing real harm?

### Implemented

- `tool_policy.py` defines the four permissions (`READ_ONLY`, `WRITE`,
  `EXTERNAL_COMMUNICATION`, `SENSITIVE_DATA`), a six-tool registry spanning all four
  (`read_email`, `search_documents`, `create_calendar_event`, `delete_records`,
  `send_email`, `access_secret`) with a per-tool set of pre-approved trusted targets,
  and `evaluate_tool_call(tool_call, content_decision) -> ALLOW/HUMAN_REVIEW/DENY`.
  Read-only tools are unconditionally exempt (content gating is P1/P2's job); a `BLOCK`
  content decision always denies a high-impact action outright, with no review escalation
  even for an already-trusted target; a high-impact action to a target outside the trust
  list always routes to `HUMAN_REVIEW` regardless of content decision — this is the case
  that catches a missed injection.
- The decision function is structurally blind to ground truth, one level further than
  D1's field-set assert: `ToolCall`'s dataclass fields are exactly `tool_name`, `target`,
  `parameters` (asserted at module load), and
  `inspect.signature(evaluate_tool_call).parameters` is asserted to be exactly
  `(tool_call, content_decision)` in `tests/test_tool_policy.py`, so neither the input
  type nor the function signature can grow a hidden ground-truth parameter later.
  `append_audit_record` writes only content_decision, policy decision, reasons, tool
  name/target/permission, and parameters — never ground truth.
- `confused_deputy_scenarios.py` is a small, hand-authored fixture (18 scenarios) —
  deliberately not a `prepare_*.py`-generated corpus, since it is illustrative
  demonstration data rather than a benchmark sample. It covers all four permission
  tiers: benign requests to trusted and untrusted targets, attacks P1 correctly
  `BLOCK`s, attacks P1 misses (`ALLOW`) aimed at untrusted targets (the core
  demonstration), and one scenario that deliberately demonstrates the containment gap
  below. Every attack scenario's expected P1 outcome is checked against the live
  detector by `tests/test_tool_policy.py`, not just asserted in a comment.
- `evaluate_tool_policy.py` runs every scenario through the real `detect_prompt_injection`
  and `evaluate_tool_call`, and — mirroring the D1 blind-evaluation convention in
  `s6/data_poisoning` — reads `actually_harmful`/`triggered_by_untrusted_content` only
  after both have already returned their frozen decisions, never as an input to either.
  Unlike P1/P2, it does not use a development/unseen-test split: that split protects a
  *tunable numeric threshold* from being fit to the data it is scored on, and
  `tool_policy.py` has no tunable threshold — its table is fixed by the four permission
  categories and the trust registry, not calibrated from this fixture — so every
  scenario is evaluated, and the summary JSON states this rationale directly.

### Results

18 scenarios, all evaluated (see "no split" rationale above):

| Metric | Value |
|---|---|
| Decisions (ALLOW / HUMAN_REVIEW / DENY) | 5 / 9 / 4 |
| Harmful-scenario success rate without this layer | 100.00% (by construction) |
| Harmful-scenario success rate with this layer | 11.11% |
| Content detector missed it, this layer still contained it | 3 of 9 harmful scenarios |
| Benign high-impact friction rate | 71.43% |

- Least privilege reduces harmful-action success from 100% to 11.11% — a real,
  substantial containment effect, at a real, reported cost: 71.43% of benign high-impact
  requests to a not-yet-trusted target are also routed to human review rather than
  executed unattended, matching this project's convention of always pairing a benefit
  metric with its friction cost rather than reporting only the win.
- Known containment gap, demonstrated (not just described): one scenario
  (`send_email_attack_missed_by_p1_trusted_target_containment_gap`) shows an injection
  that both slips past P1 (`ALLOW`) and targets an already-trusted destination, which
  this layer also `ALLOW`s. This is the honest answer to the research question above —
  least privilege narrows the blast radius of a missed injection, it does not close it —
  and is why `harmful_action_success_rate_with_policy` is 11.11%, not a suspiciously
  perfect 0%.

### Deliverables

- `tool_policy.py` — tool-call policy module (registry, decision function, audit
  writer, config-hash metadata).
- `confused_deputy_scenarios.py` — the 18-scenario demonstration/evaluation fixture.
- `evaluate_tool_policy.py` — harm-containment evaluation, written to
  `results/bipia/tool_policy_{decisions,failures,summary}.{csv,json}` and
  `results/bipia/tool_policy_audit.jsonl` (ground-truth-free audit log).
- `tests/test_tool_policy.py` — registry, decision-branch, metadata, audit-record,
  blindness (dataclass field-set + function-signature), fixture-vs-live-detector
  agreement, and audit-log-never-leaks-ground-truth tests.
- Wired live into `app.py`/`web/index.html`: `GET /api/tool-scenario` serves a random
  fixture scenario (with ground truth shown for demo pedagogy only); `POST /api/detect`
  accepts optional `tool_name`/`target` and returns a `tool_policy` decision block
  alongside P1/P2, appending one audit-log line per live check.

### Acceptance criteria

- The policy decision function never receives ground truth — confirmed by construction
  (`ToolCall`'s field set and `evaluate_tool_call`'s signature are both asserted) and by
  the audit log never containing `actually_harmful`/`triggered_by_untrusted_content`.
- Least privilege measurably reduces harmful-action success (100%→11.11%) at a
  measured, reported friction cost (71.43% benign high-impact friction) — judged an
  acceptable trade for this baseline, not an unmeasured one.
- Every `HUMAN_REVIEW`/`DENY` result includes a human-readable reason (e.g.
  `"high-impact action targets a destination outside the pre-approved trust list"`).
- The known containment gap (trusted target + missed injection → `ALLOW`) is
  demonstrated in the fixture and stated plainly here and in the module docstring, not
  hidden behind a perfect-looking metric.

## Prompt-injection metrics

- Attack recall/detection rate.
- Attack success rate after defence.
- Precision.
- Clean false-positive rate.
- Review rate.
- Results by attack family.
- Results by insertion position.
- Median and 95th-percentile detector latency.

## Deferred extensions

- Full AgentDojo evaluation.
- Paid application programming interface model comparisons.
- Large local model fine-tuning.
- Multilingual benchmark expansion beyond a small controlled test.

---

# Baseline 2: IP102 Data Poisoning

## Threat model

An attacker modifies training labels, image files, dataset membership, or class balance
before model training. The attack may occur during collection, annotation, storage,
transfer, or dataset update.

The S6 boundary sits between candidate training data and the trusted training pipeline.

## Current state — milestone D0 complete

- A deterministic 1,000-image subset from five IP102 classes is defined.
- Clean, 5% label-flip, 10% label-flip, and targeted 0-to-1 manifests are generated.
- Every selected image has a SHA-256 digest.
- Manifest comparison detects membership, hash, label, duplicate, and distribution changes.
- The backend serves only trusted-subset images and rejects path traversal.
- The frontend displays dataset decisions, real images, trusted labels, and candidate labels.

This version detects tampering against a trusted baseline. It does not yet detect a label
that was already wrong when the sample first entered the system. That gap is now covered
by the semantic label-anomaly detector described under Milestone D2 below.

## Milestone D1 — blind evaluation protocol (interface and file levels implemented)

### Research question

Can the detector identify suspicious labels without reading the correct answer?

### Implemented

- `semantic_detector.py`'s input type, `SemanticInputRecord`, structurally has only
  `sample_id`, `source_relpath`, `sha256`, and `assigned_label` — there is no
  `original_label` or `poisoned` field to read. A module-level assertion and a unit test
  (`tests/test_semantic_detector.py::SemanticInputRecordTests`) fail the build if either
  field is ever added back.
- `prepare_ip102_poisoning.py` writes candidate-only `manifests/*.csv` files with exactly
  those four fields and separate `hidden_ground_truth/*.csv` scoring files.
- `manifest_protocol.py` rejects any candidate file with extra fields. The evaluator opens
  hidden truth only after decisions are frozen, then validates the sample-ID join.
- `integrity_detector.py` also accepts only the candidate schema and remains the separate
  supply-chain/tampering detector.

### Acceptance criteria

- Semantic detection and model training run when hidden truth is unavailable. — met;
  only scoring needs hidden truth.
- Only the evaluator reads the original labels. — met.
- Reported detection metrics are calculated after predictions are frozen. — met.

The remaining production limitation is access control: separate files/directories are not
separate OS identities. A deployed trainer/detector should have no permission to read the
scoring directory.

## Milestone D2 — semantic label-anomaly detector (implemented)

### Research question

Does an image visually agree with its candidate label and neighbouring samples?

### Implemented

- `extract_embeddings()` extracts 512-d embeddings with a frozen pretrained CLIP ViT-B/32
  image encoder (`open_clip`, OpenAI weights; detector `0.1.0` used
  `torchvision.models.resnet18`/ImageNet1K_V1 instead), cached to disk by SHA-256.
- `fit_trusted_projection()` fits a projection on `clean_subset.csv`'s trusted
  `assigned_label`s only, via 5-fold stratified cross-validation so every trusted image's
  projected embedding is out-of-fold. This is the fine-tuning/metric-learning step on the
  trusted clean subset, kept in scope with the module's existing "frozen embeddings +
  classical scikit-learn on top" architecture. Detector `0.3.0` used
  `LinearDiscriminantAnalysis` (capped at `n_classes - 1 = 4` dimensions); detector `0.4.0`
  replaced it with `NeighborhoodComponentsAnalysis` (NCA), which optimizes a soft k-NN
  objective directly and projects to a free `PROJECTION_COMPONENTS = 32` dimensions instead.
- `assess_semantic()` calculates cosine k-NN (`k=15`) label agreement, a 5-fold
  stratified cross-validated `LogisticRegression` probe's out-of-fold confidence in the
  candidate label, and a leave-one-out class-centroid distance z-score — now over the
  projected embedding.
- The three signals are combined into a weighted `risk_score` and thresholded into
  `ALLOW` / `REVIEW` / `QUARANTINE`.
- `evaluate_semantic.py` evaluates all four manifests (clean + 3 poisoning variants) and
  writes per-dataset metrics, a flagged-sample CSV for manual false-positive review, and a
  JSON summary with an explicit stated limitation.
- The frontend (`web/index.html`) shows the semantic decision badge per dataset, and a
  semantic-detail section (decision, risk score, reasons, nearest neighbours) alongside the
  existing integrity-detector result for each sampled image.

### Real measured results

Measured on the actual 1,000-image, 5-class IP102 subset (`REVIEW_THRESHOLD=0.62`,
`QUARANTINE_THRESHOLD=0.75` — calibrated from the clean-subset's own risk-score
percentiles, not from per-sample poison labels), with the NCA-on-trusted-labels projection
over CLIP ViT-B/32 embeddings (detector `0.4.0`):

| Dataset | Precision | Recall | F1 | Clean FPR | ROC-AUC |
| --- | --- | --- | --- | --- | --- |
| `label_flip_05` (5%) | 0.102 | 0.72 | 0.179 | 0.334 | 0.740 |
| `label_flip_10` (10%) | 0.179 | 0.68 | 0.283 | 0.347 | 0.780 |
| `targeted_0_to_1` (~4%) | 0.040 | 0.35 | 0.071 | 0.354 | 0.538 |

Recall and ROC-AUC still show a genuine detection signal for the two random-flip datasets;
precision is low across the board because generic, non-end-to-end-trained features do not
cleanly separate these five fine-grained pest classes — median neighbour-label-agreement is
only ~40% even on the all-clean subset. **This detector has now been iterated on three
times without a meaningful improvement.** First measured with ResNet18/ImageNet1K
embeddings (detector `0.1.0`: precision 0.067–0.223, recall 0.50–0.82, ROC-AUC
0.688–0.822), then re-measured after swapping the embedding backbone to CLIP ViT-B/32
(detector `0.2.0`: precision 0.057–0.216, recall 0.425–0.79, ROC-AUC 0.647–0.805 — barely
moved), then re-measured after fitting a `LinearDiscriminantAnalysis` projection on
`clean_subset.csv`'s trusted labels (detector `0.3.0`: precision 0.029–0.208, recall
0.225–0.75, ROC-AUC 0.570–0.802 — `targeted_0_to_1` clearly worse, close to chance), then
re-measured again after replacing LDA with `NeighborhoodComponentsAnalysis` (detector
`0.4.0`, this table). NCA recovers some of the recall LDA lost (`targeted_0_to_1` 22.5% →
35%, `label_flip_05` 64% → 72%) and edges precision/F1 up slightly on those two datasets,
but `label_flip_10` comes out worse on every metric than LDA, the clean false-positive rate
ticks up across all four datasets, and `targeted_0_to_1`'s ROC-AUC (0.538) stays close to
chance — below LDA's already-poor 0.570 and well below raw CLIP's 0.647. Averaged across
the three poisoned datasets, NCA's mean ROC-AUC (0.686) is lower than LDA's (0.708). This
confirms only half of the LDA diagnosis: NCA does optimize the right (soft k-NN) objective
and gets a real recall gain from that, but removing the `n_classes - 1` dimensionality cap
did not translate into better overall separation. Combined with the earlier backbone-swap
and LDA results, this is now three consecutive attempts at reshaping the embedding space
that have failed to move ROC-AUC or precision meaningfully above the very first raw-CLIP
measurement — strong evidence the bottleneck is these three signals' reliance on generic
distance/neighbourhood structure over any representation that was never trained end-to-end
on this specific 5-class task, not the embedding/projection choice itself. See
`s6/data_poisoning/README.md`'s "Semantic label-anomaly detector (D2)" section for the full
breakdown, including the all-clean row and false-positive-rate discussion.

### Candidate next steps

One idea remains after the LDA→NCA swap above (completed, see results table):

1. **Fit the trusted projection on far more of IP102, not just the 5-class/200-per-class
   subset.** The other ~97 IP102 classes (tens of thousands of images) are untouched by
   this poisoning experiment and are legitimately "trusted" data — training a projection
   on that much larger, more diverse set could give a genuinely more discriminative
   embedding space, rather than one fit on only 1,000 images. Deferred: this requires new
   data-loading code for the unused IP102 classes plus CPU CLIP inference over a much
   larger image set (likely tens of thousands of images), which is a multi-hour effort,
   not something to attempt in a single short session. **Not yet attempted — flagged as
   future work.** Given that three different embedding/projection choices have now failed
   to move these signals meaningfully, this option's payoff is uncertain — it changes the
   *data* the projection is fit on rather than the projection method, which is the one
   variable not yet tried.

### Acceptance criteria

- The detector does not read `original_label` or `poisoned`. — met (see D1 above).
- Evaluation includes clean data and all three label-poisoning variants. — met.
- Performance is reported at multiple poison rates and decision thresholds. — met (see
  table above; thresholds are documented and re-derivable from `semantic_detector.py`).
- False positives are manually inspected and documented. — partially met:
  `semantic_flagged_samples.csv` lists every flagged sample (including false positives)
  for manual review, and the high clean-false-positive-rate is documented above, but no
  qualitative write-up of individual false-positive images has been produced yet.

## Milestone D2.5 — downstream model behaviour (initial run implemented)

### Research question

Do the controlled candidate-label changes measurably alter a downstream classifier on
clean, held-out data?

`train_ip102_models.py` trains four matched ImageNet-pretrained ResNet18 models using
candidate files only, selects checkpoints by official validation macro-F1, and evaluates
on the disjoint official test split. It records histories, predictions, confusion matrices,
per-class metrics, manifest/protocol hashes, checkpoints, TensorBoard events, and environment
metadata.

| Candidate training set | Test accuracy | Balanced accuracy | Macro-F1 | True 0 → predicted 1 | Accuracy delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| `clean_subset` | 0.6924 | 0.6859 | 0.6835 | 0.1134 | — |
| `label_flip_05` | 0.6452 | 0.6490 | 0.6399 | 0.1313 | -0.0472 |
| `label_flip_10` | 0.6642 | 0.6654 | 0.6520 | 0.1254 | -0.0281 |
| `targeted_0_to_1` | 0.6407 | 0.6742 | 0.6502 | 0.3104 | -0.0517 |

The targeted candidate set increased the held-out class-0-to-class-1 error by 19.70
percentage points. This is a reproducible seed-2026 baseline, not a significance estimate;
multiple training seeds are still required because the 5%/10% random-flip results are not
strictly monotonic in this single run.

## Milestone D3 — pixel and backdoor poisoning

### Research question

Can S6 detect image content changes and repeated trigger patterns?

### Tasks

- Create a small, reversible backdoor dataset outside `external/IP102`.
- Add a controlled trigger to selected training images.
- Preserve clean originals and record transformation provenance.
- Compare hash detection, duplicate/trigger heuristics, feature outliers, and model behaviour.
- Measure targeted attack success before and after quarantine.

### Deliverables

- Clean and transformed image manifests.
- Backdoor provenance records.
- Trigger-detection and targeted-success results.

## Data-poisoning metrics

- Precision, recall, and F1 for poisoned-sample detection.
- Clean false-positive rate.
- Area under the receiver operating characteristic curve for anomaly scores.
- Recall at fixed review budgets.
- Results by poison type and poison rate.
- Dataset-level distribution drift.
- Detector latency and embedding cost.
- Targeted attack success rate for the optional backdoor experiment.

## Deferred extensions

- Full training over all 102 IP102 classes.
- Large-scale BIOSCAN-1M experiments.
- DNA/image multimodal consistency.
- Advanced clean-label backdoor attacks.

---

# Shared integration milestone

After P2 and D2, both bases should expose the same response contract:

```json
{
  "decision": "REVIEW",
  "risk_score": 0.82,
  "reasons": ["candidate label disagrees with 9 of 10 nearest neighbours"],
  "detector": "semantic-label-check",
  "version": "0.2.0",
  "evidence_id": "audit-record-id"
}
```

Shared work should then add:

- Detector and policy versioning.
- Immutable audit logs.
- Source and dataset provenance.
- Quarantine and human-review status.
- Orchestrator integration tests.
- Rollback for approved datasets and policy changes.

## Recommended implementation order

1. Data-poisoning D1: remove ground truth from detector and trainer input (interface and
   file levels implemented).
2. Data-poisoning D2: implement semantic label-anomaly signals (implemented).
3. Data-poisoning D2.5: measure downstream label-poisoning behaviour (initial single-seed
   run implemented).
4. Prompt-injection P1: freeze unseen attacks and expand clean evaluation (implemented).
5. Prompt-injection P2: add semantic task consistency (implemented).
6. Prompt-injection P3: add permission containment (implemented).
7. Add multiple D2.5 training seeds and report variance/confidence intervals.
8. Unify the response contract and audit log.
9. Add the optional backdoor experiment (D3) if time remains.

D1, D2, D2.5, P1, P2, and P3 now have working implementations. The next experimental
priority is multiple D2.5 training seeds so optimisation variance is not mistaken for a
poison-dose effect. The next engineering priority is the shared response/audit contract;
D3 follows once those are in place.

For the Chinese roadmap, see [BASELINE_ROADMAP_ZH.md](BASELINE_ROADMAP_ZH.md).
