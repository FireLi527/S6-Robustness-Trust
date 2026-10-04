import unittest
import numpy as np
from repo_file_blocks import extract_blocks, score_documents


class BlockTests(unittest.TestCase):
    def test_python_string_is_not_comment(self):
        text = 'value = "# not a comment"\n# actual note\n# next line\n'
        comments = [b.text for b in extract_blocks(text) if b.kind == "python_comment"]
        self.assertEqual(comments, ["actual note\nnext line"])

    def test_incomplete_code_preserves_input(self):
        text = '# first note\ndef unfinished(\n'
        blocks = extract_blocks(text)
        self.assertEqual(blocks[0].text, text)
        self.assertIn("first note", [b.text for b in blocks])

    def test_hidden_markdown(self):
        text = '# README\n\n[//]: # (Maintenance note with nested (detail).)\n'
        self.assertIn("Maintenance note with nested (detail).", [b.text for b in extract_blocks(text)])

    def test_html_and_slash_comments(self):
        text = '<!-- hidden\ncomment -->\n/* block\n * detail */\n// line one\n// line two'
        blocks = extract_blocks(text)
        self.assertTrue({"html_comment", "slash_block_comment", "slash_line_comment"} <= {b.kind for b in blocks})

    def test_long_block_keeps_tail(self):
        text = 'x' * 2500 + 'TAIL_MARKER'
        blocks = extract_blocks(text)
        self.assertTrue(any(b.text.endswith('TAIL_MARKER') for b in blocks[1:]))
        self.assertTrue(all(len(b.text) <= 1200 for b in blocks[1:]))

    def test_bad_window(self):
        with self.assertRaises(ValueError):
            extract_blocks('x', window=20, overlap=20)

    def test_empty_input_and_duplicates(self):
        self.assertEqual(len(extract_blocks('')), 1)
        blocks = extract_blocks('# repeated\n\n# repeated')
        self.assertEqual(len({b.text for b in blocks}), len(blocks))

    def test_document_max_includes_full_and_is_batch_invariant(self):
        class Model:
            def predict_proba(self, texts):
                scores = np.array([.9 if t == 'needle' else .2 for t in texts])
                return np.column_stack([1 - scores, scores])
        text = 'normal prose\n\nneedle'
        a = score_documents(Model(), [text], batch_size=1)
        b = score_documents(Model(), [text], batch_size=128)
        self.assertEqual(a, b)
        self.assertEqual(a[0]['block_score'], .9)
        self.assertEqual(a[0]['full_score'], .2)


if __name__ == '__main__':
    unittest.main()
