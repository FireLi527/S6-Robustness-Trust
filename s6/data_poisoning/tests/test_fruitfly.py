import unittest
from prepare_fruitfly import safe_name,group_split

class FruitflyProtocolTests(unittest.TestCase):
    def test_rejects_zip_path_traversal_and_unknown_names(self):
        for name in ('../evil.jpg','/evil.jpg','C:/evil.jpg','folder/x.jpg','unknown.jpg'):
            with self.assertRaises(ValueError):safe_name(name)
        self.assertEqual(safe_name('021001001111101_1-rectangle.jpg'),'021001001111101_1-rectangle.jpg')

    def test_duplicates_merged_and_groups_stay_disjoint(self):
        rows=[dict(label=l,filename_group=f'{l}-{i}',pixel_sha256=f'{l}-{i}-{j}',status='valid')
              for l in range(5) for i in range(12) for j in range(2)]
        rows[2]['pixel_sha256']=rows[0]['pixel_sha256']
        kept=group_split(rows)
        self.assertEqual(len(kept),len(rows)-1)
        self.assertEqual(rows[2]['status'],'duplicate_pixels')
        self.assertEqual(rows[3]['group'],rows[0]['group'])
        self.assertEqual(rows[3]['split'],rows[0]['split'])
        sets={s:{r['group'] for r in kept if r['split']==s} for s in ('train','val','test')}
        self.assertFalse(sets['train'] & sets['test'])
        self.assertFalse(sets['train'] & sets['val'])
        self.assertFalse(sets['val'] & sets['test'])

    def test_conflicting_labels_excluded(self):
        rows=[dict(label=l,filename_group=f'{l}-{i}',pixel_sha256=f'{l}-{i}',status='valid')
              for l in range(5) for i in range(12)]
        rows[12]['pixel_sha256']=rows[0]['pixel_sha256']
        kept=group_split(rows)
        self.assertEqual(len(kept),len(rows)-2)
        self.assertEqual(rows[0]['status'],'conflicting_label')
        self.assertEqual(rows[12]['status'],'conflicting_label')
