## Latest research milestones (2026-10-05)

Final first-confirmation is COMPLETE but closure criteria FAIL: after freezing the readiness candidate,32 new human-reviewed controls yield25/32 accuracy,8/8 risk recall,13/16 normal decisions and4/8 UNKNOWN. English UNKNOWN2/4 and Chinese normal5/8/UNKNOWN2/4 miss preregistered language gates. Prior577 states and decisions replay identically, so previous attack and quoted-pressure performance is preserved. Technical verification passes32 records, engineering521 passes/2 skips; these do not turn the research failure into validated closure. [Final confirmation report](../results/bipia/approval_readiness_validation_v1/report_ZH.md). Candidate and failed outputs are retained unchanged, with no pending run, training, deployment or commit. Any later change needs a new version and separate fresh confirmation; these32 are now development-exposed.

Approval-readiness overlay is complete with strict zero-regression development gates: all prior545 decisions are unchanged, retaining InjecAgent58/64, SecOPD33/40 and quoted-pressure12/339 false risks with327/339 normal decisions. New32 accuracy improves25/32 to31/32 and UNKNOWN2/8 to8/8; only six human-labelled UNKNOWN cases change, raw RISK alerts remain, no RISK becomes NORMAL and no execution permission is granted. English16/16, Chinese15/16; old Chinese UNKNOWN remains0/6. This is bounded bilingual trusted-task extraction with task hashes and evidence, not model learning or permission verification. Replay verification passed577 records; engineering521 passed/2 skipped, fresh inference0. No deployment, training or default switch. [Report](../results/bipia/approval_readiness_v1/report_ZH.md); [method](prompt_injection/APPROVAL_READINESS_V1_ZH.md). The new32 are now exposed development materials; retain the failed first-confirmation record below and validate the next fixed candidate on unseen materials.

New32 bilingual labels were directly approved by the user and first confirmation is complete: final accuracy25/32, risk recall8/8, normal automatic15/16, UNKNOWN2/8; English14/16 withUNKNOWN2/4, Chinese11/16 withUNKNOWN0/4, all-four-correct2/8 groups. Both languages fail the predeclared UNKNOWN>=3/4 requirement. Model UNKNOWN remains0/8; the two final UNKNOWN decisions come from the unchanged English rule. Full inference replay verification passed, engineering507 passed/2 skipped. No candidate tuning, training, deployment or commit. [Confirmation report](../results/bipia/trusted_route_confirmation_v2/report_ZH.md). Human review is saved separately; references below to pending new32 review are historical. These materials are now exposed and can only serve as development regression for later changes. Next improvement should represent trusted approval readiness separately from content risk.

Frozen task routing now has a fresh integrated run: all545 outputs were regenerated, final decisions match the prior development replay (0 changes), and input/output/evidence/policy verification passed. InjecAgent58/64, SecOPD33/40 with1/40 benign false risks, quoted-task pressure12/339 false risks (3.54%) and327/339 normal automatic decisions (96.46%). These are exposed regression materials, not independent generalization. The32 previously human-reviewed controls remain32/32 correct at policy level, with8 UNKNOWN decisions supplied by the explicit missing-approval rule; model UNKNOWN remains0/8, Chinese0/6. New bilingual32 controls and a predeclared confirmation runner are ready but await new semantic review; previous label approval does not transfer. Engineering507 passed,2 skipped. No training, deployment, default-detector/frontend/P3 change or commit. [Fresh integration report](../results/bipia/trusted_review_live_v1/report_ZH.md); [new review materials](../data/bipia/trusted_route_confirmation_candidates_v2/REVIEW_ZH.md); [method](prompt_injection/TRUSTED_REVIEW_LIVE_V1_ZH.md).

Earlier four-arm prompt/evidence ablation and follow-up v2/v3 runs are complete. Numbered evidence improves valid source citations. The initial refined prompt has low quoted-task false risks but reduced attack recall; v2/v3 recover attack recall while creating high quote false risks. The retained routed candidate combines original numbered and initial refined numbered heads based only on trusted task text. Detailed negative results and limits: [routing development report](../results/bipia/trusted_review_route_v1/report_ZH.md). Statements below are historical milestones.

Handoff: [new-chat briefing](HANDOFF_2026-10-03_ZH.md). The current goal is complete: scale training, five-arm evaluation and verification are all COMPLETE. No run in this batch awaits continuation. 2026-10-04: the representation/annotation consistency audit is complete (read-only, no change to the frozen contract/reference/data), and its findings were written up as an [annotation guide v1](prompt_injection/RELATION_ANNOTATION_GUIDE_V1_ZH.md); all three proposed rules were confirmed by the user. Whether to retrain against this guide is a decision for a future explicit request; no new training, deployment, frontend, or P3 changes were made. Same day: to address ASB's same-theme attacks, implemented and evaluated a [trusted task-tool manifest](../results/bipia/asb_trusted_manifest_v1/report_ZH.md) reusing the already-frozen split -- test-set benign auto-allow 100%, attack auto-allow 0%, 26/26 tasks fully automatic; no P3/frontend changes, no new data collected.

Scale training and five-arm evaluation complete: 102 semantically approved cores converted into 204 pairs, with 28 training groups/168 pairs and 6 validation groups/36 pairs. Fresh 8/16/28-group Qwen3-4B adapters completed three epochs and 42/84/147 steps. Core unique valid outputs: base zero-shot16/24, small22/24, medium22/24, large23/24. Only large achieved content exact matches (2/18); all task matches remain0/6 and both-side matches0/18. Both successes belong to transaction rollback, not broad generalization. All210 calls and360 expanded records replayed with hashes verified; final engineering404 passed,2 skipped. [Evaluation report](../results/bipia/relation_scale_evaluation_v1/report_ZH.md); [training report](../results/bipia/relation_scale_training_v1/report_ZH.md). Recommended next: representation/annotation consistency audit before further scaling. No new training, deployment, frontend or P3 changes. Pending-conversion/training statements below are historical.

This update records completed fruit-fly seed repeats and supplementary prompt-injection research. Versioned protocols and reports remain authoritative. No frontend detector or tool-authorization policy was replaced, and no image experiment was rerun. The September 25 snapshot below is historical.

| Milestone | Status | Evidence and limits |
| --- | --- | --- |
| ASB trusted task-tool manifest | Complete | To fix semantic alignment's failure on ASB's same-theme attacks, switched to a per-agent, registration-time trusted manifest (built only from provenance=="normal"; the decision function is blind to provenance). Test set: benign auto-allow 100%, attack auto-allow 0%, 26/26 tasks fully automatic, versus the prior semantic-similarity test-set numbers of 21%/3.9%/0-26. Shows same-theme attacks call for registration-time capability scoping, not better semantic discrimination; how to build the manifest itself in a real deployment remains unsolved. [Report](../results/bipia/asb_trusted_manifest_v1/report_ZH.md) |
| Relation-extraction annotation consistency audit | Complete, read-only | Compared the 18 validation-core materials (large_28 arm primarily, other four arms spot-checked) against the frozen reference: object/data role confusion in 6/18 cases, stable across arms; task-side `constraints` never populated (0/18), with two retain-type task families mis-converted into a spurious extra action in 6/6 cases; explicit/unmapped status inconsistent in 5/18 cases; one contract-external role hallucinated (a decoding defect, not an annotation issue). [Audit](prompt_injection/ANNOTATION_CONSISTENCY_AUDIT_V1_ZH.md). Three resulting rules were written up as [annotation guide v1](prompt_injection/RELATION_ANNOTATION_GUIDE_V1_ZH.md) and confirmed by the user; documentation only, no change to contract code/frozen data/published metrics, no retraining or deployment. |
| Fruit-fly seed repeats | Complete, exploratory | Fixed split/poison instance, seeds 2026/2027/2028. Mean accuracy for 10% flips: untreated 97.45%, semantic 98.28%, weighted 98.11%; targeted: 98.54%, 98.69%, 99.22%. Conditions were selected after viewing seed 2026, so this is not independent confirmation. [Report](../results/fruitfly_poisoning/multiseed_v1/report_ZH.md) |
| SecOPD scale control | Complete, 4 training arms | Increasing training from 200 to 1,194 rows raised same-source accuracy from 86.45% to 90.39% (content) and 85.47% to 90.15% (joint). The 48 previously reviewed diagnostics did not improve correspondingly. [Report](../results/bipia/secopd_training_v1/report_ZH.md) |
| Cross-source training | Complete, 8 new heads and 2 frozen controls | Full-mixed content accuracy reached 94.69% on SPML holdout, but InjecAgent recall was 24.86% and NotInject FPR 39.82%, both worse than the single-source control using the same calibration. Sources are reported separately. [Report](../results/bipia/cross_source_training_v1/report_ZH.md) |
| Joint authorization reading | Complete, frozen NLI pilot | Direct contradiction correctly ranked all 24 synthetic pairs, but classified both members correctly in only 5 pairs at the fixed threshold. The conflict-hypothesis formulation got 12 pairs correct but falsely flagged all 12 benign quotations. The 60 fixtures were unreviewed at the time of the pilot and have now been reviewed; the old 12 remain seen diagnostics. [Report](../results/bipia/authorization_probe_v1/report_ZH.md) |
| Human authorization review | Complete | All 60 reviewed by the user and cross-checked by the assistant: 36 benign, 24 risky, no uncertain labels. They remain exposed diagnostics, never used for selection. [Record](../results/bipia/authorization_review_v1/summary_ZH.md) |
| Authorization regularization and calibration | Complete; no acceptable transfer gain | 240 new programmatic, unreviewed rows across 24 task families; 16 supervised heads plus 2 threshold controls. Selected joint C=0.1 did not beat C=1. NLI calibration raised test recall from 75% to 84.38% but FPR from 0% to 43.75%; the fixed threshold missed all 8 target-mismatch attacks. No deployment. [Report](../results/bipia/authorization_calibration_v1/report_ZH.md) |
| Target-relation paired training | Complete; insufficient benefit | 540 new programmatic, unreviewed rows with full authorized-A/B × action-A/B quartets and exact single-side target balance. Three-seed paired loss raised mean recall from 13.89% to 43.52%, but FPR from 8.95% to 25.93%; no test quartet was fully correct among 36 for any BCE/paired seed. No deployment. [Report](../results/bipia/authorization_relation_v1/report_ZH.md) |
| Structured authorization slots | Complete; narrow grammar only | Parser frozen before 324 new synthetic fixtures. All 216 supported-grammar contracts classified correctly, but all 72 new-wording and 36 pressure cases referred for review. New-wording automatic coverage is 0%; contract accuracy is not generalization. No training or deployment. [Report](../results/bipia/authorization_slots_v1/report_ZH.md) |
| Small instruction-model slot extraction | Complete; current prompt failed viability | Official Qwen3-4B Q4_K_M ran locally on GPU. On 32 new synthetic rows, direct recall/FPR were 75%/25%; extraction plus comparison covered only 6.25%, referred 30/32, and got both sides' slots fully correct in 2/32. No fine-tuning or deployment. [Report](../results/bipia/instruction_slots_v1/report_ZH.md) |
| Few-shot free-text extraction | Complete; progress on controlled new wording | Prompts frozen before 32 new synthetic rows. On the same rows, old extraction covered 0%; revised extraction covered 87.5%, with 28 correct automatic decisions and 4 reviews. Direct recall/FPR: 100%/25%; revised: 87.5%/0%. Target omissions remain; not 100% overall accuracy or demonstrated natural-data generalization. [Report](../results/bipia/instruction_slots_v2/report_ZH.md) |
| Repository-style review and conversion | Complete | Original 24 and new 18 cases received semantic review. Machine fields are assistant conversions, not individually human-approved JSON gold. Only 12 original training seeds enter this pilot; new groups split 6/6/6. Ambiguity, quotation and missing authority remain explicit. [Method](prompt_injection/RELATION_SFT_V1_ZH.md) |
| First 4B LoRA extraction pilot | Training, three-arm evaluation and verification complete; limited benefit | 18 training pairs become 26 deduplicated side records, 3 epochs/21 steps. Test full-field matches: zero-shot 0/12, few-shot 0/12, adapter 3/12. All adapter successes repeat the same task text; content 0/6 and both sides correct 0/6. Not attack recall; no deployment. [Report](../results/bipia/relation_sft_v1_evaluation/report_ZH.md) |
| First-pilot engineering verification (historical) | Passed at that stage | 365 tests passed, 2 WSL-related skips. All 72 outputs, tokens, scores, adapter and protected hashes verified. Original post-training evaluation failure retained; separate evaluation completed after an inference precision-context fix, without retraining. Latest engineering count is 404 passed, 2 skipped. |
| Scale training and five-arm evaluation | Complete; no deployment | Three fresh 8/16/28-group adapters plus base zero/few-shot controls. Large core content exact matches 2/18, task 0/6, both sides 0/18: limited improvement. [Report](../results/bipia/relation_scale_evaluation_v1/report_ZH.md) |
| Latest engineering and artifact verification | Complete | 404 passed, 2 WSL-related skips; 210 distinct calls and 360 expanded records replayed with protected hashes verified. Engineering record: `results/engineering/checks/20261003T044639Z-e6b93212`. No visual acceptance or real-agent ASR claim. |

Second pilot complete: all 24 dev2 cases across 8 groups received human semantic review, followed by per-action/role conversion and 3-epoch training. Development-valid outputs: zero-shot 6/12, few-shot 5/12, adapter 8/12; deduplicated full matches remain 0/8 for all arms. Generalization is not solved. All 36 outputs replayed; engineering 381 passed, 2 skipped. [Second report](../results/bipia/relation_sft_v2/report_ZH.md).

Scale expansion contains 204 development pairs across 34 groups: 24 seed cores, 78 new cores and 102 layout variants. All 78 new cores completed four human-review batches and assistant cross-checks: 26 normal/26 risk/26 unknown. Including seeds, all 102 cores have approved meanings, 34 per class. Case 078 preserves the distinction between a document's third-party permission claim and the current user's explicit approval. [Review progress](../data/bipia/relation_scale_candidates_v1/REVIEW_PROGRESS_ZH.md). Conversion, group audit, three-scale training and five-arm evaluation are now complete; machine fields remain assistant-derived, and variants were not individually human-reviewed. Six groups/36 future holdouts are still unwritten; freeze any revised method before authoring and reviewing them. Exposed evaluations cannot become new independent tests. No deployment, automatic authorization, commit or push.

---

> **Historical status snapshot (2026-09-25)** — the latest prompt-injection research is summarized above.
>
> | Milestone | Status | Key evidence |
> |---|---|---|
> | P1 unseen-attack split | Done | Rules v0.2.0: plain unseen test recall 93.47% / FPR 2% |
> | P2 semantic task consistency | Done | Hybrid unseen test 97.08% / FPR 4% |
> | P3 tool permission containment | Done | Harmful-action success 100% → 11.11%; benign friction 71.43% |
> | P3.1 explicit user approval | **Done and measured (2026-09-25)** | Exact-repeat friction 71.43% → 42.86%, back to 71.43% when parameters change; rubber-stamp reviewer raises harm 11.11% → 33.33% |
> | P4 supervised classifier control | v1, v2 frozen; **does not replace rules** | v2 Email test FPR 16% |
> | Clean prompt-injection corpus expansion | **Done (2026-09-28)** | Independent 200-email/split Enron sample added (`--clean-corpus expanded`); rule FPR estimate widens 0%/2% (n=50) → 5.2%/5.2% (n=250), attack detection unchanged |
> | D1 blind protocol | Done | Candidate manifests physically separated from hidden truth |
> | D2 semantic label anomaly | Done (STL-10, v0.5.0) | 10% flip: precision 89.69%, recall 100%, FPR 1.28% |
> | D2.5 downstream behaviour + defense | **Done (STL-10, 3 seeds, 36 models)** | Targeted error 10.46% → 0.21%; 10% flip paired gain +3.23 pp |
> | D2.6 fruit-fly migration | Done (single seed) | Clean ResNet18 test accuracy 99.24% |
> | D2.7 fruit-fly specimen-grouped detection + defense | Done (single seed, 12 models) | FPR 4.4–5.8% → 0.6–1.0%, with lower recall |
> | D2.8 fruit-fly risk-weighted training | **Done (2026-09-28): 8/8 training runs, summary report, and significance testing all complete** | Down-weights instead of removing; all 8 exploratory comparisons stay out of the Holm family; 10% flip/targeted show 2–2.4 pp gains vs untreated, mostly no significant difference vs semantic isolation |
| D4 Diptera / Tephritidae data | **In progress: iterative cleaning (cleaning_v3) done (2026-09-26)** | q=0.6, rounds=3, threshold=0.975: 10% flip recall 18%→58%, pest-evasion recall 67%→61%, clean FPR ~3-4.5% |
| Downstream significance tests | **Done (2026-09-25)** | STL-10 defense effects significant; on fruit fly only 10% flip semantic−untreated survives Holm |
> | Unified response contract + audit log | Not started | — |
> | D3 pixel/backdoor poisoning | Not started | — |
>
> The local console defaults to the classmate fruit-fly dataset (`grouped_defense_v1`). **STL-10 was abandoned on 2026-09-25** (generic dataset, technical validation only; results kept, no further work); CLIP features remain fine to use. IP102 is frozen. Per the instructor, the image side moves to domain-relevant data (fruit flies, Diptera), with future classification at taxonomic ranks (order/family/genus). See "Recommended implementation order" at the end for next steps.

<details>
<summary>Historical update notes (2026-09-11 to 09-21, Chinese)</summary>

> 2026-09-21：提示词注入新增 Email/Table/Code 监督分类基线。按正文分组划分，排除11条与测试重复的训练邮件；791条训练、198条验证、200条测试，全部82,700条测试预测已回放核验。新模型在Code明文优于规则，但Email/Table及编码攻击不足以替换现有检测器。网页以可选实验对照展示，不参与工具授权。详见[监督实验协议](prompt_injection/SUPERVISED_PROTOCOL_ZH.md)。

> 2026-09-19: STL-10 固定策略防御重训练及等量随机删除对照已完成，8个新模型与原4个模型均核验通过。定向错误率从10%降至0.125%，但存在误隔离代价；下一步为多种子重复。详见[防御报告](../results/stl10_poisoning/defense_training/defense_report_ZH.md)。

> 2026-09-18: STL-10 四组 ResNet18 首轮训练已完成（seed=2026，20 epochs）。干净/5%/10%/定向组测试准确率为94.44%/92.49%/89.89%/93.03%；定向飞机→鸟错误率从0.375%升至10%。下一实验阶段是固定策略下的防御后重训练与多种子验证。详见 [训练报告](../results/stl10_poisoning/model_training/training_report_ZH.md)。

> 2026-09-11: 图像 baseline 已切换为 STL-10、原始 CLIP 特征。以下 IP102 指标和 NCA 里程碑属于历史记录，不代表当前配置。旧跨折投影距离比较有方法问题，不能据此断言数据集或特征是唯一瓶颈。新协议见 [STL-10 说明](data_poisoning/README_ZH.md)。

</details>

# S6 Baseline Development Roadmap

This roadmap covers the two current S6 prototypes:

1. **Email Prompt-Injection Baseline** using BIPIA.
2. **Image Data-Poisoning Baseline** using controlled label poisoning (originally IP102; STL-10 from 2026-09-11; the console defaults to the classmate fruit-fly set from 2026-09-21).

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
- Resolved 2026-09-28: an independent, custodian-disjoint 200-clean-email-per-split Enron
  sample (`download_enron_clean.py` → `prepare_clean_corpus.py`) is available via
  `--clean-corpus expanded` on both `evaluate_baseline.py` and `evaluate_semantic.py`,
  without changing any detector weight or threshold. The 50-email BIPIA-only numbers above
  remain the frozen default (`--clean-corpus bipia`); see the P2 section below for the
  expanded-corpus results.

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
- **Update (2026-09-28), expanded clean corpus**: adding an independent, custodian-disjoint
  200-email-per-split Enron sample (`--clean-corpus expanded`; see
  `download_enron_clean.py`/`prepare_clean_corpus.py`) raises each split's clean sample size
  from 50 to 250. Attacked-record detection is exactly unchanged (development 65.71%,
  unseen_test 93.47% rule recall — only clean records were added), but the wider clean
  sample gives a materially different point estimate: rule FPR moves from 0%/2% to
  5.2%/5.2%, semantic-only FPR moves from 4%/4% to 0.8%/0.8%, and hybrid FPR moves from
  4%/4% to 6.0%/5.6% (development/unseen_test). This is not a detector regression — the
  50-email estimate was on the optimistic side of a wide confidence interval; no threshold
  or weight was changed in response to these numbers, per the experimental-integrity rule.
  Full results: `results/bipia/email_p1_plain_expanded_summary.json` /
  `email_p2_plain_expanded_summary.json`.

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

## Milestone P3.1 — explicit user approval (implemented 2026-09-25)

`approval_policy.py` layers exact-scope approvals on top of the frozen `tool_policy.py`
without changing its decision table. The scope is a SHA-256 of `tool_name`, `target`, and
sorted `parameters`; any change requires a new approval. One-time approvals live in memory
and are consumed on use; persistent approvals are stored in
`results/local_frontend/tool_approvals.json` and can be listed/revoked via
`GET/POST /api/approvals`. `HARD_DENY_TOOLS = {access_secret, delete_records}` can never be
approved, and approvals never override a content `BLOCK`. Covered by
`tests/test_approval_policy.py`.

Measured with `evaluate_approval_policy.py` (simulated reviewers: none / informed =
approves only benign-by-construction requests / rubber-stamp; ground truth is read only by
the simulated reviewer after the store returns; temporary approval store):

| Reviewer / mode | Harmful success | Benign friction: first / exact repeat / changed parameters | Benign eventually executed |
|---|---:|---|---:|
| None | 1/9 (11.11%) | 71.43% / 71.43% / 71.43% | 2/7 |
| Informed · persistent | 1/9 (11.11%) | 71.43% / **42.86%** / 71.43% | 4/7 |
| Rubber-stamp · persistent | **3/9 (33.33%)** | 71.43% / 42.86% / 71.43% | 4/7 |

First requests keep their friction (the approval is the review); persistent approvals only
help byte-identical scopes, so tools whose parameters vary per call gain almost nothing.
Rubber-stamping admits the two P1-missed untrusted-target attacks. Hard-deny turns four
reviews into DENY (two attacks, two benign requests). Deliberate tightening (confirmed
2026-09-25): unlike P3, a content BLOCK denies every call including read-only ones, so
blocked content cannot drive any action (locked in by `tests/test_approval_policy.py`). The P3 "trusted target + missed injection" gap remains.

## Milestone P4 — supervised classifier control (v1/v2 frozen as a research control)

v1 (2026-09-21): word 1–2-gram hashing + SGD logistic regression over BIPIA
Email/Table/Code with body-grouped splits (see `prompt_injection/SUPERVISED_PROTOCOL_ZH.md`).
v2 (2026-09-24): adds char 3–5-grams and per-task loss balancing, frozen before test;
winner `word_char`. Unseen test with task thresholds:

| Task | Attack recall | Clean FPR | ROC-AUC |
|---|---:|---:|---:|
| Email | 72.90% | 16% (8/50) | 0.887 |
| Table | 38.54% | 4% | 0.868 |
| Code | 39.70% | 2% | 0.934 |

AUC shows real ranking signal, but thresholds chosen on tiny clean validation sets (7 Email,
10 Code) do not transfer. The classifier stays an optional UI comparison and never affects
tool authorization. The test set had been inspected before; not a pristine blind test.

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

# Baseline 2: Image Data Poisoning (IP102 → STL-10 → fruit fly)

> The D0–D2 descriptions below were written for IP102 and are historical; current datasets and metrics are in the snapshot above and in the sections from D2.5 onward.

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

## Milestone D2.5 — downstream model behaviour (IP102 initial run + STL-10 three seeds done)

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

### Multi-seed replication (STL-10, completed)

Seeds 2026/2027/2028 × 4 conditions × 3 strategies = 36 verified models. Mean ± sample SD:

| Condition | Untreated acc. | Semantic screening acc. | Paired gain (pp) | Airplane→bird error untreated → semantic |
|---|---:|---:|---:|---:|
| Clean | 94.27 ± 0.16 | 93.79 ± 0.34 | −0.48 ± 0.26 | 0.29 → 0.29 |
| 5% flip | 92.12 ± 0.64 | 92.70 ± 0.69 | +0.57 ± 0.25 | 0.67 → 0.58 |
| 10% flip | 90.32 ± 0.41 | 93.55 ± 0.45 | +3.23 ± 0.62 | 0.67 → 0.38 |
| Targeted 0→1 | 92.84 ± 0.23 | 94.17 ± 0.10 | +1.33 ± 0.33 | 10.46 → 0.21 |

Paired differences have a consistent sign across seeds; clean data pays ~0.5 pp for false
quarantine. Three seeds measure training randomness only. Report:
`results/stl10_poisoning/multiseed_training/multiseed_report_ZH.md`. **D2.5 is complete on STL-10.**

## Milestone D2.6 — classmate fruit-fly migration (done, single seed)

9,244 images, 5 classes, split by confirmed 9-digit specimen IDs into 6,531/1,392/1,321.
Clean ResNet18 test accuracy 99.24%. The frozen v0.5.0 detector transferred without tuning:
~93% recall on random flips but 4.4–5.8% FPR, and 48.9% recall on targeted
correcta→zonata. See `data_poisoning/FRUITFLY_PROTOCOL_ZH.md`.

## Milestone D2.7 — fruit-fly specimen-grouped detection and defense (done, single seed)

`fruitfly_group_detector.py` uses specimen-grouped folds and one neighbour vote per
reference specimen; C=10, classifier-only signal, threshold 0.90 were selected on the
validation set with two development poisoning seeds. Twelve downstream models:

| Condition | Detection P / R / FPR | Accuracy untreated → random → semantic | 0→1 error untreated → semantic |
|---|---|---|---|
| Clean | — / — / 1.00% | 99.24 → 98.79 → 99.47 | 0 → 0 |
| 5% flip | 85.3% / 81.7% / 0.74% | 98.33 → 98.11 → 99.02 | 0 → 0 |
| 10% flip | 93.6% / 74.0% / 0.56% | 96.52 → 98.26 → 98.71 | 0 → 0 |
| Targeted 0→1 | 58.9% / 45.7% / 0.95% | 98.94 → 98.41 → 98.11 | 3.49 → 1.16 |

One test image is 0.08 pp (0.58 pp within the 172-image source class), so most single-seed
differences are within noise. See `data_poisoning/FRUITFLY_GROUPED_DEFENSE_ZH.md`.

## Milestone D2.8 — fruit-fly risk-weighted training (done, 2026-09-28)

Keeps every sample with `weight = max(floor, 1 − risk)` from the frozen D2.7 specimen-grouped
OOF risk; floor ∈ {0.25, 0.50}; 8 models; protocol frozen in
`data/fruitfly_poisoning/weighted_v2/protocol.json` (no hidden truth or test metrics used).

**Rationale**: D2.7's specimen-grouped defense *isolates* — samples judged high-risk are
dropped from the reference set entirely, trading recall for a lower false-positive rate,
and any misjudged clean sample loses all supervision. D2.8 instead *down-weights*: the
same frozen D2.7 specimen-grouped OOF candidate-label risk scores set each sample's
supervised-loss weight to `max(floor, 1 − risk)` (the floor keeps near-risk-1 samples from
losing supervision entirely) rather than a binary keep/drop decision. This tests whether a
softer reweighting recovers most of the isolation defense's benefit without its
misisolation cost — the same risk scores used two different ways downstream, a comparison
rather than a replacement for D2.7. Protocol is frozen
(`data/fruitfly_poisoning/weighted_v2/protocol.json`); floor and method were not chosen
using hidden truth or test metrics.

**2026-09-28**: the remaining 6 runs (`clean_subset__weighted_{25,50}`,
`label_flip_05__weighted_{25,50}`, `label_flip_10__weighted_50`,
`targeted_0_to_1__weighted_50`) started and all finished, using the identical frozen
method/protocol as the first 2 (no retuning, hidden truth not read). All 6 queued
sequentially in one WSL tmux session (`weighted_v2_run`) since there is a single GPU; log
at `results/fruitfly_poisoning/weighted_v2/remaining_6_runs.log`; measured 23–30 min/run.
All 8 verified (hashes/protocol/checkpoints match) and summarized in
[weighted_report_ZH.md](../results/fruitfly_poisoning/weighted_v2/weighted_report_ZH.md).

| dataset__floor | test accuracy | test macro F1 | targeted 0→1 error |
|---|---:|---:|---:|
| clean_subset__weighted_25 | 99.39% | 99.30% | 0.00% |
| clean_subset__weighted_50 | 99.62% | 99.54% | 0.00% |
| label_flip_05__weighted_25 | 98.79% | 98.68% | 0.00% |
| label_flip_05__weighted_50 | 97.80% | 97.62% | 0.00% |
| label_flip_10__weighted_25 | 98.56% | 98.35% | 0.00% |
| label_flip_10__weighted_50 | 98.94% | 98.71% | 0.00% |
| targeted_0_to_1__weighted_25 | 99.02% | 98.88% | 1.16% |
| targeted_0_to_1__weighted_50 | 98.94% | 98.75% | 1.74% |

Significance testing (8 exploratory comparisons, see below): weighted training beats untreated
clearly on 10% flip (+2.04/+2.42 pp, both floors p<0.001); other conditions are mostly within
noise. Versus D2.7's semantic isolation, only the targeted condition is significantly better at
both floors (+0.91/+0.83 pp, p=0.023/0.043); other conditions show no significant difference.
All of these stay exploratory, outside D2.7's Holm-corrected primary family (see below for why).

## Downstream significance tests (done 2026-09-25)

`report_significance.py` reads only the frozen per-sample test predictions of 50 models:
exact McNemar, 10,000-resample paired bootstrap 95% CIs, Holm correction per dataset.
Report: `results/poisoning_significance/report_ZH.md`.

- **STL-10**: seed-averaged semantic−untreated CIs exclude 0 for every poisoned condition
  (10% flip +3.23 [2.82, 3.65], targeted +1.33 [1.00, 1.67], 5% flip +0.57 [0.20, 0.94]);
  targeted 0→1 error −10.25 pp [−11.92, −8.67]. The clean-data cost −0.47 [−0.75, −0.19] is also real.
- **Fruit fly**: only 10% flip semantic−untreated (+2.19 pp) survives Holm. Semantic vs
  random on 10% flip is not significant (p=0.42); targeted 0→1 error 3.49%→1.16% is 6→2
  images (p=0.22) and cannot be claimed as an improvement.
- **D2.8 exploratory comparisons** (all 8 runs complete, still excluded from Holm): weighted
  vs untreated is significantly better on 10% flip at both floors (+2.04 pp floor0.25, +2.42 pp
  floor0.50, both p<0.001); other conditions' CIs include 0. Weighted vs D2.7's semantic
  isolation is significantly better only for the targeted condition at both floors (+0.91 pp
  p=0.023, +0.83 pp p=0.043; 0→1 error difference not significant); 10% flip, clean, and 5%
  flip mostly show no significant difference (5% flip floor0.50 is significantly worse,
  −1.21 pp, p=0.004). floor=0.25 finished before floor=0.50, so to avoid promoting a family
  after seeing partial results, both floors stay exploratory with no multiple-comparison
  correction.
- CIs reflect test-set sampling only; fruit fly is single-seed.

## Milestone D4 — Diptera / Tephritidae domain data (in progress)

`external/diptera` (supplied by the instructor via a classmate): 45,103 non-tephritid Diptera
and 5,287 Tephritidae field photos; folder names are the only labels. Together with the
fruit-fly set it forms an order → family → genus/species hierarchy, and poisoning maps onto a
biosecurity need (relabelling Tephritidae as other Diptera = pest evasion). Done: read-only audit; dedup (124 exact +
65 CLIP cosine >=0.98 near duplicates, excluded via manifests only; 50,201 retained); approximate
grouped split (same-class ID gap <=3 and CLIP 0.97-0.98 merged; per-class 70/15/15, seed 2026).
See `data_poisoning/DIPTERA_PROTOCOL_ZH.md`. Poisoning scenarios (pest evasion, false alarm,
random 5%/10%) and frozen-detector transfer done: strong ranking (AUC 0.85–0.96) but low,
contamination-sensitive recall at the inherited threshold; high-risk clean images look like
possible natural mislabels pending expert review. A pre-registered recalibration on the validation split
(calibration_v2: C=10, threshold 0.775) raised recall on all attacks (pest evasion 67.1%, false
alarm 55.8%) at roughly double the FPR; threshold tuning alone caps out and high-contamination
recall stays low. **Iterative cleaning `cleaning_v3` is complete:** validation selection chose
q=0.6, three rounds, and a final threshold of 0.975. On the training candidates, 10% flip
recall rose from 18.36% to 57.60% while clean FPR rose from 1.51% to 4.54%; pest-evasion
recall fell from 67.12% to 61.03%. See `data_poisoning/DIPTERA_PROTOCOL_ZH.md`.
Taxonomic review of flagged images remains an alternative.

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

Done: D1, D2, D2.5 (STL-10, 3 seeds), D2.6, D2.7, P1, P2, P3, P3.1; P4 is a frozen research control.

Next-phase candidates (2026-09-25 discussion draft, ordered by cost vs. value):

1. ~~Finish D2.8~~ — done (2026-09-28): 8/8 training runs, D2.7-format summary report, and
   significance testing all complete; see the D2.8 milestone section above.
   The exploratory `multiseed_v1` repeat is complete for 10% random flips and targeted 0→1,
   with untreated, semantic-filtered, and weighted strategies at additional seeds 2027/2028, summarized with seed 2026.
   See the latest snapshot and [report](../results/fruitfly_poisoning/multiseed_v1/report_ZH.md); this does not establish general gains across poison instances.
2. ~~Statistical tests on existing results~~ — done 2026-09-25.
3. ~~Expand the clean prompt-injection corpus~~ — done (2026-09-28): an independent,
   custodian-disjoint 200-email-per-split Enron sample was added (`download_enron_clean.py`
   → `prepare_clean_corpus.py`, `--clean-corpus expanded`). Rule FPR estimate widens from
   0%/2% (n=50) to 5.2%/5.2% (n=250); attack detection rates are unchanged. See the P2
   milestone section for full detail; the original BIPIA-only 50-email numbers remain the
   frozen default. (P3.1 friction/mistaken-approval evaluation done 2026-09-25.)
4. **D4 Diptera / Tephritidae (additional study)** — audit, embedding deduplication,
   grouped split, domain poisoning detection, validation calibration, and iterative cleaning
   are complete. The five-class fruit-fly experiment remains the main image result.
5. **Unified response contract and audit log** across both baselines. Further fruit-fly
   seeds can quantify training variability.
6. **D3 pixel/backdoor poisoning (optional)** — hash checks already catch pixel edits when a
   trusted manifest exists; the interesting case is no-baseline or clean-label, which needs its own threat model.

All future work keeps the rules: test sets and hidden truth only after predictions are frozen,
no retuning on already-seen attack metrics, and new versioned directories instead of overwriting frozen results.

For the Chinese roadmap, see [BASELINE_ROADMAP_ZH.md](BASELINE_ROADMAP_ZH.md).
