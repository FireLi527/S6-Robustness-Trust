import unittest

import numpy as np
from sklearn.linear_model import LogisticRegression

from evaluate_diptera_detection import classifier_signal, iterative_classifier_signal
from fruitfly_group_detector import GroupedInput, fold_indices, group_weights, signals
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

    def test_iterative_signal_round_zero_matches_classifier_signal(self):
        records, embeddings = self.fixture()
        round0, folds0 = classifier_signal(records, embeddings, c=10.)
        iterative0, folds1 = iterative_classifier_signal(records, embeddings, c=10., q=0.9, rounds=0)
        np.testing.assert_array_equal(folds0, folds1)
        np.testing.assert_allclose(round0, iterative0, atol=1e-12)

    def test_iterative_signal_isolates_only_from_reference_not_held(self):
        records, embeddings = self.fixture()
        round0, folds0 = classifier_signal(records, embeddings, c=10.)
        q = float(np.median(round0))
        iterative, folds1 = iterative_classifier_signal(records, embeddings, c=10., q=q, rounds=1)
        np.testing.assert_array_equal(folds0, folds1)

        # cleaning_v3: round 1 refits each fold excluding samples whose round-0 risk >= q
        # from that fold's *reference* set only; the held set is untouched.
        features = np.stack([embeddings[r.sha256] for r in records]).astype(np.float64)
        features /= np.linalg.norm(features, axis=1, keepdims=True)
        labels = np.array([r.assigned_label for r in records])
        groups = np.array([r.group_id for r in records])
        isolated = round0 >= q
        self.assertTrue(np.any(isolated))
        expected = np.zeros(len(records))
        for reference, held in fold_indices(groups):
            ref = reference[~isolated[reference]]
            model = LogisticRegression(C=10., class_weight='balanced', max_iter=2000, random_state=2026)
            model.fit(features[ref], labels[ref], sample_weight=group_weights(groups[ref]))
            probs = model.predict_proba(features[held])
            class_index = {v: i for i, v in enumerate(model.classes_)}
            expected[held] = [1 - probs[k, class_index[labels[i]]] if labels[i] in class_index else 1.0
                              for k, i in enumerate(held)]
        np.testing.assert_allclose(iterative, expected, atol=1e-12)

    def test_sample_id_does_not_reveal_source_folder(self):
        for relpath in ('Tephritidae/123.jpg', 'Diptera/123.jpg'):
            identifier = sample_id(relpath)
            self.assertNotIn('Tephritidae', identifier)
            self.assertNotIn('Diptera', identifier.removeprefix('diptera_'))
        self.assertNotEqual(sample_id('Tephritidae/123.jpg'), sample_id('Diptera/123.jpg'))


if __name__ == '__main__':
    unittest.main()
