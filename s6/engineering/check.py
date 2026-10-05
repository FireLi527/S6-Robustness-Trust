"""One root-level quality gate; isolate legacy baseline imports in subprocesses."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import uuid

from s6.engineering.artifacts import atomic_binary, file_sha256, new_run, read_json, require_hash, write_json

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).with_name("frozen_assets.json")
PROTECTED = [
    "s6/prompt_injection/semantic_detector.py", "s6/data_poisoning/semantic_detector.py",
    "s6/prompt_injection/tool_policy.py", "s6/prompt_injection/approval_policy.py",
    "s6/prompt_injection/train_repo_file_v1.py", "s6/prompt_injection/train_repo_file_v2_development.py",
    "s6/prompt_injection/experiment_native_pairs_v1.py", "s6/prompt_injection/experiment_joint_context_v1.py",
    "data/bipia/native_pairs_v1/protocol.json", "data/bipia/native_pairs_v1/samples.json",
    "results/bipia/native_pairs_v1/selection.json", "results/bipia/native_pairs_v1/summary.json",
    "results/bipia/native_pairs_v1/models.joblib", "results/bipia/repo_file_v1/model.joblib",
    "results/bipia/repo_file_v2_development/model.joblib",
    "results/fruitfly_poisoning/grouped_defense_v1/comparison.json",
    "results/fruitfly_poisoning/grouped_defense_v1/detection_summary.json",
]


def initialize_registry() -> None:
    """Explicit one-time migration snapshot, never an automatic repair operation."""
    if REGISTRY.exists():
        raise FileExistsError("Freeze registry exists; do not update hashes to bypass failures")
    files = {name: file_sha256(ROOT / name) for name in PROTECTED}
    write_json(REGISTRY, {"purpose": "Migration-point integrity guard; not retroactive provenance proof", "files": files})


def static_checks() -> list[str]:
    errors = []
    managed = list(Path(__file__).parent.glob("*.py"))
    managed.append(ROOT / "s6/prompt_injection/experiment_long_text_v1.py")
    managed.append(ROOT / "s6/prompt_injection/request_inputs.py")
    managed.append(ROOT / "s6/prompt_injection/prerequisite_review.py")
    managed.append(ROOT / "s6/prompt_injection/download_pair_sources_v1.py")
    managed.append(ROOT / "s6/prompt_injection/paired_source_audit.py")
    managed.append(ROOT / "s6/prompt_injection/download_secopd_v1.py")
    managed.append(ROOT / "s6/prompt_injection/repository_scope_review.py")
    managed.append(ROOT / "s6/prompt_injection/finalize_repository_scope_review.py")
    managed.append(ROOT / "s6/prompt_injection/download_qwen_training_v1.py")
    managed.append(ROOT / "s6/prompt_injection/relation_development_review_v2.py")
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("relation_scale_metrics_v1.py", "evaluate_relation_scale_v1.py", "verify_relation_scale_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("relation_annotation_audit_v1.py", "audit_relation_annotation_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("relation_contract_v3.py", "relation_targets_v3.py", "prepare_relation_targets_v3.py",
                    "rescore_relation_scale_v3.py", "relation_holdout_v3_catalog.py", "prepare_relation_holdout_v3.py",
                    "relation_holdout_v3_targets.py", "prepare_relation_holdout_v3_targets.py",
                    "relation_sft_v3_io.py", "prepare_relation_scale_training_v3.py",
                    "experiment_relation_scale_training_v3.py", "evaluate_relation_v3.py", "verify_relation_v3.py",
                    "relation_comparator_v1.py", "score_relation_decisions_v1.py", "register_relation_comparator_v1.py",
                    "evaluate_baseline_cross_source_v1.py", "prepare_call_alignment_v1.py", "call_alignment_v1.py",
                    "evaluate_call_alignment_v1.py", "prepare_agentdojo_alignment_v1.py", "agentdojo_alignment_v1.py",
                    "evaluate_agentdojo_alignment_v1.py", "agentdojo_alignment_v2.py",
                    "diagnose_agentdojo_alignment_v2.py", "prepare_asb_alignment_v1.py", "asb_alignment_v1.py",
                    "evaluate_asb_alignment_v1.py", "asb_trusted_manifest_v1.py",
                    "evaluate_asb_trusted_manifest_v1.py", "content_probe_v1.py",
                    "prepare_content_probe_v1.py", "download_content_classifier_v1.py",
                    "run_content_probe_v1.py", "run_content_probe_v1_compat.py",
                    "verify_content_probe_v1.py", "evaluate_content_controls_v1.py",
                    "evaluate_prompt_guard_2_v1.py", "content_fusion_v1.py",
                    "content_reviewer_runtime_v1.py", "experiment_content_fusion_v1.py",
                    "experiment_content_fusion_v1_compat.py", "reviewer_ablation_v1.py",
                    "experiment_reviewer_ablation_v1.py", "reviewer_priority_fusion_v1.py",
                    "experiment_reviewer_confirmation_v1.py", "experiment_reviewer_pressure_v2.py",
                    "reviewer_refinement_v2.py", "experiment_reviewer_refinement_v2.py",
                    "reviewer_refinement_v3.py", "experiment_reviewer_refinement_v3.py",
                    "trusted_review_route_v1.py", "experiment_trusted_review_route_v1.py",
                    "trusted_review_runtime_v1.py", "experiment_trusted_review_live_v1.py",
                    "trusted_route_candidates_v2.py", "prepare_trusted_route_candidates_v2.py",
                    "experiment_trusted_route_confirmation_v2.py", "approval_readiness_v1.py",
                    "experiment_approval_readiness_v1.py", "experiment_approval_readiness_validation_v1.py",
                    "approval_readiness_v2.py", "experiment_readiness_routing_v2.py",
                    "chinese_analysis_v3.py", "experiment_readiness_routing_v3.py",
                    "prepare_chinese_analysis_confirmation_v1.py", "prepare_chinese_analysis_confirmation_v1_compat.py",
                    "experiment_chinese_analysis_confirmation_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("relation_scale_targets_v1.py", "relation_scale_data_v1.py", "prepare_relation_scale_training_v1.py",
                    "experiment_relation_scale_training_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("relation_scale_catalog_v1.py", "prepare_relation_scale_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("relation_contract_v2.py", "relation_conversion_v2.py", "prepare_relation_sft_v2.py",
                    "relation_sft_v2_io.py", "relation_sft_v2_evaluation.py", "experiment_relation_sft_v2.py",
                    "verify_relation_sft_v2.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("relation_sft_io.py", "relation_sft_runtime.py", "experiment_relation_sft_v1.py",
                    "verify_relation_sft_v1.py", "evaluate_relation_sft_checkpoint_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("relation_expansion_conversion_v1.py", "prepare_relation_sft_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("relation_contract_v1.py", "relation_seed_conversion_v1.py",
                    "probe_relation_contract_v1.py", "relation_expansion_review_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("instruction_slot_fewshot.py", "instruction_slot_trial.py",
                    "instruction_slot_holdout_v2.py", "experiment_instruction_slots_v2.py",
                    "verify_instruction_slots_v2.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("instruction_slot_model.py", "instruction_slot_data.py",
                    "instruction_slot_evaluation.py", "experiment_instruction_slots_v1.py",
                    "verify_instruction_slots_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("authorization_slots.py", "authorization_slots_data.py",
                    "authorization_slots_evaluation.py", "experiment_authorization_slots_v1.py",
                    "verify_authorization_slots_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("authorization_relation_data.py", "authorization_relation_training.py",
                    "authorization_relation_run.py", "experiment_authorization_relation_v1.py",
                    "verify_authorization_relation_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("authorization_calibration_data.py", "authorization_calibration.py",
                    "experiment_authorization_calibration_v1.py", "verify_authorization_calibration_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("authorization_probe.py", "download_nli_probe_v1.py", "nli_authorization.py",
                    "experiment_authorization_probe_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("download_cross_source_v1.py", "cross_source_data.py", "prepare_cross_source_v1.py",
                    "cross_source_training.py", "experiment_cross_source_v1.py", "verify_cross_source_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("secopd_data.py", "prepare_secopd_v1.py", "secopd_training.py", "experiment_secopd_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("prerequisite_protocol.py", "experiment_prerequisite_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("aggregation_data.py", "risk_aggregation.py", "experiment_risk_aggregation_v1.py"))
    managed.extend(ROOT / "s6/prompt_injection" / name for name in
                   ("boundary_protocol.py", "experiment_boundary_transfer_v1.py"))
    for path in managed:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            problem = None
            if isinstance(node, ast.Assert):
                problem = "Use explicit exceptions for runtime integrity checks"
            elif isinstance(node, ast.ExceptHandler) and node.type is None:
                problem = "Bare except is prohibited"
            elif isinstance(node, ast.ImportFrom):
                if any(alias.name.startswith("_") for alias in node.names):
                    problem = "Do not import private APIs"
                if (node.module or "").split(".")[-1].startswith("experiment_"):
                    problem = "Do not import another experiment as a library"
            if problem:
                errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: {problem}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize-freeze", action="store_true")
    args = parser.parse_args()
    if args.initialize_freeze:
        initialize_registry()
        print("Initialized migration freeze registry")
        return 0
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    out = ROOT / "results/engineering/checks" / run_id
    with new_run(out, {"kind": "quality-gate", "code_sha256": file_sha256(Path(__file__))}):
        for name, expected in read_json(REGISTRY)["files"].items():
            require_hash(ROOT / name, expected)
        errors = static_checks()
        if errors:
            raise ValueError("\n".join(errors))
        suites = (("engineering", ROOT, "s6/engineering/tests"),
                  ("prompt_injection", ROOT / "s6/prompt_injection", "tests"),
                  ("data_poisoning", ROOT / "s6/data_poisoning", "tests"))
        results = {}
        env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
               "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"}
        for name, cwd, tests in suites:
            completed = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", tests],
                                       cwd=cwd, env=env, capture_output=True, timeout=300)
            output = completed.stdout + completed.stderr
            atomic_binary(out / f"{name}.log", lambda stream, data=output: stream.write(data))
            results[name] = {"returncode": completed.returncode, "log": f"{name}.log"}
            print(f"{name}: {'PASS' if completed.returncode == 0 else 'FAIL'}", flush=True)
        write_json(out / "checks.json", results)
        if any(item["returncode"] for item in results.values()):
            raise RuntimeError(f"Quality gate failed; inspect {out}")
    print(f"Quality gate complete: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
