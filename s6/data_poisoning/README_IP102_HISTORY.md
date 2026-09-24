# IP102 Image Data-Poisoning Base

This base demonstrates how the S6 security layer can validate a candidate training
dataset before model training or ingestion. It creates controlled IP102 label-poisoning
variants, compares them with an independently trusted manifest, and exposes the results
through a local Python backend and browser frontend.

## Folder layout

```text
data_poisoning/
├─ app.py                       Local HTTP backend
├─ integrity_detector.py        Manifest integrity policy (D0)
├─ manifest_protocol.py         D1 candidate/truth file-separation contract
├─ semantic_detector.py         Semantic label-anomaly policy (D2), blind to ground truth
├─ prepare_ip102_poisoning.py   Creates clean and poisoned manifests
├─ evaluate_manifests.py        Batch evaluation for integrity_detector.py
├─ evaluate_semantic.py         Batch evaluation for semantic_detector.py
├─ train_ip102_models.py        Five-class ResNet18 behaviour experiment
├─ verify_training_environment.py  WSL/CUDA environment smoke test
├─ requirements-windows.txt     torch/torchvision (CPU) + scikit-learn + pillow + open_clip_torch
├─ requirements-training-linux.txt  Pinned WSL/Linux training dependencies
├─ tests/                       Protocol, integrity, and semantic unit tests
├─ start.cmd                    One-click launcher for this base
└─ web/
   └─ index.html                Browser frontend
```

Large or generated data remains outside the code base:

```text
external/IP102/                        Immutable 3 GB source dataset
external/clip_cache/                   Cached pretrained CLIP ViT-B/32 weights (~580 MB)
data/ip102_poisoning/manifests/        Candidate-only CSV manifests
data/ip102_poisoning/hidden_ground_truth/  Scoring-only truth files
data/ip102_poisoning/embeddings/       Cached CLIP ViT-B/32 image embeddings (sha256-keyed)
results/ip102_poisoning/               Dataset and sample-level findings
~/s6-training-artifacts/               WSL checkpoints and TensorBoard events
```

The source IP102 files are never overwritten. Label poisoning changes only the
`assigned_label` field in generated manifests.

## Quick start: frontend and backend together

Double-click this folder's `start.cmd`, or run it from a terminal.

On the first run, the launcher creates the manifests if they are missing. It then starts
the backend at:

```text
http://127.0.0.1:8766
```

The frontend opens automatically. Keep the terminal open and press `Ctrl+C` to stop it.
It renders the fast manifest-integrity results first and then fills in semantic summaries.
When `semantic_sample_results.json` is present, the backend serves the frozen evaluation
directly instead of fitting NCA during page startup.

### Using the frontend

1. Review the four dataset-level decisions at the top of the page — each card shows both
   the integrity-detector badge and the semantic-detector badge side by side.
2. Select the clean, 5% flip, 10% flip, or targeted-poisoning manifest.
3. Select **Random sample**.
4. Compare the trusted original label with the candidate training label.
5. Inspect the actual IP102 image, SHA-256 digest, integrity decision, and — below it — the
   semantic decision, risk score, reasons, and nearest-neighbour samples.
6. Repeat to inspect different samples without restarting the backend.

For poisoned manifests, random sampling prioritises changed records so that the attack is
easy to inspect. The image can look completely normal because label poisoning changes
training metadata rather than image pixels.

## Running the backend manually

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\data_poisoning\app.py'
```

Useful options:

```text
--port 8766       Change the local port
--no-browser      Start the backend without opening a browser
```

### Backend endpoints

#### `GET /api/summary`

Re-evaluates every candidate manifest and returns dataset-level decisions, risk scores,
label changes, hash changes, missing/unknown samples, duplicates, and distribution drift.

#### `GET /api/sample?dataset=label_flip_05`

Returns a random sample from the selected dataset, including trusted and candidate labels,
hash status, class names, and a safe local image URL.

#### `GET /api/image?sample_id=...`

Returns an image only when its identifier belongs to the trusted experiment subset. Path
validation prevents the endpoint from reading arbitrary local files.

#### `GET /api/semantic?dataset=label_flip_05`

Returns the selected dataset's `ALLOW`/`REVIEW`/`QUARANTINE` distribution, mean risk
score, and detector metadata from a precomputed result whose configuration hash matches the
current detector. It falls back to running `semantic_detector.py` only when that result is
missing or stale.

`GET /api/sample` also embeds a `semantic` object for the returned sample: decision,
risk score, human-readable reasons, nearest-neighbour candidate labels/distances, and the
raw signal values (`neighbor_label_agreement`, `classifier_confidence`, `centroid_distance_z`).

The frontend does not decide whether data is safe. It only displays results produced by
`integrity_detector.py` and `semantic_detector.py` through the backend.

## Preparing the experiment

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\data_poisoning\prepare_ip102_poisoning.py'
```

The deterministic experiment uses five classes and 200 training images per class:

- `clean_subset`: 1,000 trusted records
- `label_flip_05`: 50 random label changes
- `label_flip_10`: 100 random label changes
- `targeted_0_to_1`: 40 class-0 samples relabelled as class 1

The generator now implements the D1 file-level protocol. `manifests/*.csv` contains
exactly `sample_id`, `source_relpath`, `sha256`, and `assigned_label`;
`hidden_ground_truth/*.csv` separately stores `original_label`, `poisoned`, and
`poison_type`. `manifest_protocol.py` rejects candidate files containing any extra field.

## Running the batch evaluation

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\data_poisoning\evaluate_manifests.py'
```

The candidate file physically has no `poisoned` answer column. The detector compares
candidate membership, SHA-256 digests, labels, duplicates, and class distributions with
the trusted manifest.

## Five-class model-behaviour experiment

Run all four matched experiments in the WSL training environment:

```bash
source ~/.venvs/s6-training/bin/activate
cd /mnt/e/研究生/高级计算机项目
python s6/data_poisoning/train_ip102_models.py --all \
  --epochs 20 --batch-size 32 --workers 4 --seed 2026 --pretrained --amp
```

The trainer accepts candidate-only manifests and evaluates on IP102's disjoint official
validation/test splits. Checkpoints and TensorBoard events default to the WSL/D-drive
path `~/s6-training-artifacts/`; small histories, predictions, confusion matrices, and
JSON summaries go under `results/ip102_poisoning/model_training/`.

| Candidate training set | Test accuracy | Balanced accuracy | Macro-F1 | True 0 → predicted 1 | Accuracy delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| `clean_subset` | 0.6924 | 0.6859 | 0.6835 | 0.1134 | — |
| `label_flip_05` | 0.6452 | 0.6490 | 0.6399 | 0.1313 | -0.0472 |
| `label_flip_10` | 0.6642 | 0.6654 | 0.6520 | 0.1254 | -0.0281 |
| `targeted_0_to_1` | 0.6407 | 0.6742 | 0.6502 | 0.3104 | -0.0517 |

The targeted set increased the held-out class-0-to-class-1 error by 19.70 percentage
points. These are initial seed-2026 measurements, not significance estimates: the
non-monotonic 5%/10% random-flip results show why multiple training seeds are still needed.

## Semantic label-anomaly detector (D2)

`integrity_detector.py` only works when a trusted baseline manifest exists — it is a diff
tool, not content inspection. `semantic_detector.py` instead asks whether an image's own
pixel content agrees with its candidate label, independent of any trusted manifest.

It is blind to ground truth at both the interface and file levels: its input type, `SemanticInputRecord`,
has only `sample_id`, `source_relpath`, `sha256`, and `assigned_label` — there is no
`original_label` or `poisoned` field to read, so the detector cannot access the hidden
answer even by accident. The candidate CSV has exactly the same four fields.
`evaluate_semantic.py` opens the separate hidden-truth file only after all decisions are
frozen, validates a one-to-one sample-ID join, and then scores them.

### Install the extra dependencies

The base dependencies (`bipia`'s own requirements) do not include a vision stack. Install
CPU-only PyTorch/TorchVision plus scikit-learn, Pillow, and open_clip into the shared venv:

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' -m pip install torch torchvision `
  --index-url https://download.pytorch.org/whl/cpu
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' -m pip install `
  -r 'E:\研究生\高级计算机项目\s6\data_poisoning\requirements-windows.txt'
```

This is a one-time ~300–400 MB download for the CPU PyTorch wheels, plus a separate
~580 MB download the first time `extract_embeddings()` runs, for the pretrained CLIP
ViT-B/32 (OpenAI weights) checkpoint. Both are cached: PyTorch wheels in the venv itself,
and the CLIP checkpoint under `external/clip_cache/` (redirected there via `cache_dir=`
so nothing lands in the user-wide `%USERPROFILE%\.cache\huggingface\` default, keeping the
repo's convention that `external/` holds every immutable third-party download).

### How it works

1. `extract_embeddings()` runs every unique image through a pretrained CLIP ViT-B/32
   image encoder (`open_clip`, OpenAI weights, quick-GELU variant to match the original
   checkpoint) to get a 512-dimensional feature vector, cached to disk by SHA-256 so the
   four manifests — which share the same 1,000 underlying images — only pay the CPU
   inference cost once. This replaces an earlier ResNet18/ImageNet1K version (detector
   `0.1.0`): generic ImageNet-supervised features gave weak separation between these five
   fine-grained pest classes, so `0.2.0` swapped in CLIP's contrastively-trained features to
   test whether they cluster the five classes more cleanly (they didn't — see below).
2. `fit_trusted_projection()` (detector `0.3.0`, revised in `0.4.0`) fits a projection
   *only* on `clean_subset.csv`'s trusted `assigned_label`s — the same file
   `integrity_detector.py` already treats as the trusted baseline — via 5-fold stratified
   cross-validation, so every trusted image's projected embedding comes from a model that
   never saw that image during fitting. `0.3.0` used `LinearDiscriminantAnalysis`, capped at
   `n_classes - 1 = 4` output dimensions; `0.4.0` replaced it with
   `NeighborhoodComponentsAnalysis` (NCA), which directly optimises a soft k-NN
   classification objective (matching what the neighbour-agreement signal below actually
   needs) and is not capped by class count, so it projects down to `PROJECTION_COMPONENTS =
   32` dimensions instead. This is the "fine-tuning / metric learning on the trusted clean
   subset" step, computed fresh each run (no extra cache file — it's a fast fit over 1,000
   512-d vectors). Because every candidate manifest shares the same 1,000 images (only
   `assigned_label` differs), the projected embedding for every sample is available from
   this one trusted fit.
3. `assess_semantic()` combines three independent signals per sample, now computed over the
   projected embedding instead of the raw CLIP one:
   - **Neighbour label agreement** — cosine k-NN (`k=15`) over the embeddings; what
     fraction of a sample's nearest neighbours share its candidate label.
   - **Cross-validated classifier disagreement** — a `LogisticRegression` probe evaluated
     with 5-fold stratified out-of-fold prediction (`cross_val_predict`), so no sample is
     ever scored by a model trained on itself; confidence assigned to the candidate label.
   - **Class-centroid distance** — leave-one-out distance from a sample's embedding to its
     candidate class's centroid, z-scored against that class's typical distance spread.
4. The three signals are weighted (`neighbor_disagreement` 0.4, `classifier_disagreement`
   0.4, `centroid_distance` 0.2) into a single `risk_score`, thresholded into
   `ALLOW` (`< 0.62`) / `REVIEW` (`< 0.75`) / `QUARANTINE` (`>= 0.75`).

### Run the evaluation

```powershell
& 'E:\研究生\高级计算机项目\.venv-bipia\Scripts\python.exe' `
  'E:\研究生\高级计算机项目\s6\data_poisoning\evaluate_semantic.py'
```

This writes `results/ip102_poisoning/semantic_assessments.csv` (dataset-level metrics),
`semantic_flagged_samples.csv` (every `REVIEW`/`QUARANTINE` sample, including false
positives, for manual inspection), `semantic_evaluation_summary.json`, and
`semantic_sample_results.json` (all 4,000 frozen per-sample detector outputs used by the
local dashboard).

### Real measured results

Measured on the actual 1,000-image, 5-class IP102 subset (`REVIEW_THRESHOLD=0.62`,
`QUARANTINE_THRESHOLD=0.75`, thresholds picked from the clean-subset risk-score
percentiles, not tuned against per-sample poison labels), with the NCA-on-trusted-labels
projection over CLIP ViT-B/32 embeddings (detector `0.4.0`):

| Dataset | ALLOW | REVIEW | QUARANTINE | Precision | Recall | F1 | Clean FPR | ROC-AUC |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `clean_subset` (0% poisoned) | 662 | 234 | 104 | — | — | — | 0.338 | — |
| `label_flip_05` (5%) | 646 | 246 | 108 | 0.102 | 0.72 | 0.178 | 0.335 | 0.740 |
| `label_flip_10` (10%) | 620 | 262 | 118 | 0.179 | 0.68 | 0.283 | 0.347 | 0.780 |
| `targeted_0_to_1` (~4%) | 646 | 238 | 116 | 0.040 | 0.35 | 0.071 | 0.354 | 0.538 |

**This is a third flat-to-mixed result — swapping LDA for `NeighborhoodComponentsAnalysis`
did not recover the raw-CLIP baseline (detector `0.2.0`: precision 0.057–0.216, recall
0.425–0.79, ROC-AUC 0.647–0.805), and only partially improved on the LDA projection
(detector `0.3.0`: precision 0.029–0.208, recall 0.225–0.75, ROC-AUC 0.570–0.802).**
NCA does recover some recall lost to LDA (`targeted_0_to_1` 22.5% → 35%,
`label_flip_05` 64% → 72%), and its precision/F1 on those same two datasets edge up
slightly. But `label_flip_10` comes out worse on every metric than LDA (precision 0.208 →
0.179, recall 0.75 → 0.68, ROC-AUC 0.802 → 0.780), the clean false-positive rate ticks up
on all four datasets (average ~0.34 vs LDA's ~0.33), and `targeted_0_to_1`'s ROC-AUC stays
close to chance (0.538, down slightly from LDA's already-poor 0.570 and well below raw
CLIP's 0.647). Averaged across the three poisoned datasets, NCA's mean ROC-AUC (0.686) is
lower than LDA's (0.708) and both sit below raw CLIP's (0.706 using the midpoints of its
reported range). This confirms the diagnosis from the LDA result was only half right:
NCA fixes the "wrong objective" half (it does optimise for k-NN-style neighbour agreement)
and gets a real recall gain from that, but removing the `n_classes - 1` dimensionality cap
did not translate into better overall separation. Combined with the earlier CLIP-vs-ResNet18
and LDA results, this is now three consecutive attempts at re-shaping the embedding space
(different backbone, then two different trusted-label projections) that have failed to
move ROC-AUC and precision meaningfully above the very first raw-CLIP measurement — strong
evidence the bottleneck is not the embedding/projection choice at all, but the three
signals' reliance on generic distance/neighbourhood structure over *any* frozen,
off-the-shelf-derived representation of these five visually similar pest classes. Closing
it further would likely need a model trained end-to-end for this exact classification
task, well beyond this baseline's scope.

Here, “beyond this baseline's scope” means replacing the D2 detector with an end-to-end
classifier. The new ResNet18 experiment instead treats that classifier as the downstream
victim whose behaviour is measured; it does not replace D2.

"Flagged" = `REVIEW` or `QUARANTINE` (anything short of `ALLOW`). Precision/recall/F1 are
computed against `poisoned` in the separate scoring file, but only *after* the detector's
decisions were frozen — see `evaluate_semantic.py`.

**Read these numbers carefully — the detector is a genuine but noisy signal, not a
reliable classifier at this scale.** Even correctly-labelled IP102 images look ambiguous
under this pipeline: on the all-clean `clean_subset`, the clean false-positive rate is
~34% at the `REVIEW` tier. Recall stays reasonable for the two random-flip datasets
(68–72%) but drops sharply for the targeted-flip one (35%, still below the 42.5% measured
before any projection was added), and ROC-AUC ranges 0.54–0.78 — still real separation for
the random-flip cases, but close to chance for the targeted one. Precision remains low
across the board (4.0–17.9%), so most individual `REVIEW`/`QUARANTINE` flags are false
alarms that a human reviewer would need to clear. This detector is best read as a
review-prioritisation signal, not an autonomous quarantine decision.

## Security and research limitations

- Exact label-change detection requires an independently trusted, access-controlled
  baseline manifest. If attackers can alter both manifests, direct comparison fails.
- Class-distribution drift alone cannot prove that an individual label is correct.
- The semantic detector's cross-validated classifier and class centroids are fit on each
  candidate manifest's *own* labels. At very high poison rates that reference statistic
  itself becomes contaminated — this detector has only been measured up to a 10%
  random-flip and a ~4%-of-subset targeted-flip rate, not at majority-poisoned data.
- Semantic precision is low (4.0–17.9% measured, see above) — real deployment would use it
  to prioritise a human review queue, not as a standalone auto-quarantine gate. Three
  successive attempts to fix this by reshaping the embedding space — swapping the backbone
  (ResNet18/ImageNet1K → CLIP ViT-B/32), fitting an LDA projection on the trusted clean
  subset (detector `0.3.0`), then replacing it with an NCA projection (detector `0.4.0`) —
  have not meaningfully improved it; the targeted-flip scenario in particular has stayed
  close to chance (ROC-AUC 0.54–0.65) across all three embedding changes. The ambiguity
  looks intrinsic to how these five classes sit under any frozen, off-the-shelf-derived
  representation, rather than an embedding-space problem this baseline's signals can fix.
- D1 now separates candidate and scoring files, but this is not operating-system access
  control; production should use separate trainer/scorer identities and permissions.
- Label-poisoning model behaviour has one measured seed; cross-seed variance and
  statistical significance remain unmeasured.
- Pixel backdoors still require a separate image transformation, trigger detector, and
  attack-success experiment.
- Production ingestion should also use signed manifests, role-based access, immutable
  audit logs, quarantine, approval workflows, and rollback.
- The server binds only to `127.0.0.1` and exposes only trusted-subset images.

For the Chinese guide, see [README_ZH.md](README_ZH.md).

The shared development plan is available in
[../BASELINE_ROADMAP.md](../BASELINE_ROADMAP.md).
