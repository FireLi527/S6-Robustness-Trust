import unittest

import numpy as np

from evaluate_diptera_detection import classifier_signal
from fruitfly_group_detector import GroupedInput, signals
from prepare_diptera_poisoning import sample_id


class DipteraDetectionTests(unittest.TestCase):
    def fixture(self):
        rng = np.random.default_rng(7)
        records, embeddings = [], {}
        for group in range(30):
            label = str(group % 2)
            for view in range(2):
                sid = f'{group}_{view}'
                base = np.array([1., 0., 0., 0.]) if label == '0' else np.array([0., 1., 0., 0.])
                embeddings[sid] = base + rng.normal(0, .3, 4)
                # Flip a few labels so the classifier signal is not trivially zero.
                assigned = label if group % 7 else str(1 - int(label))
                records.append(GroupedInput(sid, sid, assigned, f'g{group}'))
        return records, embeddings

    def test_classifier_shortcut_matches_full_detector_column(self):
        records, embeddings = self.fixture()
        full, full_folds = signals(records, embeddings, c=10.)
        fast, fast_folds = classifier_signal(records, embeddings, 10.)
        np.testing.assert_array_equal(full_folds, fast_folds)
        np.testing.assert_allclose(full[:, 1], fast, atol=1e-12)

    def test_sample_id_does_not_reveal_source_folder(self):
        for relpath in ('Tephritidae/123.jpg', 'Diptera/123.jpg'):
            identifier = sample_id(relpath)
            self.assertNotIn('Tephritidae', identifier)
            self.assertNotIn('Diptera', identifier.removeprefix('diptera_'))
        self.assertNotEqual(sample_id('Tephritidae/123.jpg'), sample_id('Diptera/123.jpg'))


if __name__ == '__main__':
    unittest.main()
