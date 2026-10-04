import tempfile
import unittest
from pathlib import Path

import numpy as np

from s6.engineering.artifacts import atomic_binary, file_sha256, new_run, read_json, require_hash, write_json
from s6.engineering.metrics import binary_metrics, calibrate_threshold
from s6.engineering.text_embeddings import EncodingConfig, coverage_weights, token_windows


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_hash_mismatch_is_an_exception(self):
        path = self.root / "file.json"
        write_json(path, {"value": 1})
        require_hash(path, file_sha256(path))
        with self.assertRaises(ValueError):
            require_hash(path, "0" * 64)

    def test_atomic_failure_preserves_previous_file(self):
        path = self.root / "file.json"
        write_json(path, {"value": 1})
        def fail(stream):
            stream.write(b"incomplete")
            raise RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):
            atomic_binary(path, fail)
        self.assertEqual(read_json(path), {"value": 1})
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_failed_run_is_recorded_and_cannot_be_overwritten(self):
        path = self.root / "run"
        with self.assertRaises(ValueError):
            with new_run(path, {"seed": 2026}):
                raise ValueError("deliberate failure")
        self.assertEqual(read_json(path / "status.json")["state"], "FAILED")
        with self.assertRaises(FileExistsError):
            with new_run(path, {}):
                pass

    def test_successful_run_records_environment(self):
        path = self.root / "run"
        with new_run(path, {"seed": 2026}):
            pass
        self.assertEqual(read_json(path / "status.json")["state"], "COMPLETE")
        self.assertIn("packages", read_json(path / "protocol.json")["environment"])


class WindowTests(unittest.TestCase):
    def test_all_boundaries_cover_every_token(self):
        for length in (0, 1, 125, 126, 127, 253, 254, 255, 512, 4097):
            windows = token_windows(length, 254, 32)
            observed = set(i for start, end in windows for i in range(start, end))
            self.assertEqual(observed, set(range(length)))
            self.assertTrue(all(end - start <= 254 for start, end in windows))
            self.assertEqual(windows[-1][1], length)

    def test_overlap_weights_do_not_double_count_tokens(self):
        windows = token_windows(777, 254, 32)
        self.assertAlmostEqual(coverage_weights(777, windows).sum(), 777)

    def test_invalid_overlap_and_uncovered_tail_are_rejected(self):
        with self.assertRaises(ValueError):
            token_windows(500, 254, 254)
        with self.assertRaises(ValueError):
            coverage_weights(500, [(0, 128)])

    def test_config_rejects_unsupported_position_limit(self):
        for config in (EncodingConfig(window_tokens=513), EncodingConfig(overlap_tokens=254),
                       EncodingConfig(batch_size=0), EncodingConfig(strategy="unknown")):
            with self.assertRaises(ValueError):
                config.validate(512, 2)
        EncodingConfig().validate(512, 2)


class MetricsTests(unittest.TestCase):
    def test_undefined_denominators_are_not_zero(self):
        metrics = binary_metrics(np.array([0, 0]), np.array([0, 0]))
        self.assertIsNone(metrics["recall"])
        self.assertIsNone(metrics["precision"])
        self.assertEqual(metrics["fpr"], 0)

    def test_calibration_can_reject_all(self):
        threshold, metrics = calibrate_threshold(np.array([0, 1]), np.array([.9, .8]))
        self.assertGreater(threshold, .9)
        self.assertEqual(metrics["fp"], 0)

    def test_calibration_rejects_missing_class_and_nan(self):
        for labels, scores in (([1, 1], [.8, .9]), ([0, 1], [.1, np.nan])):
            with self.assertRaises(ValueError):
                calibrate_threshold(np.array(labels), np.array(scores))
