import unittest
import unicodedata
from BE.search_text import canonical, normalize_query, terms, fold, KeywordIndex


class SearchTextTests(unittest.TestCase):
    def test_whitespace_and_unicode(self):
        self.assertEqual(normalize_query('  bảo\thiểm  y\n tế '), 'bảo hiểm y tế')
        self.assertEqual(canonical(unicodedata.normalize('NFD', 'BẢO HIỂM Y TẾ')), 'bảo hiểm y tế')

    def test_aliases_work_both_ways_across_domains(self):
        for full, short in [('bảo hiểm y tế','bhyt'), ('ký túc xá','ktx'),
                            ('câu lạc bộ','clb'), ('thực tập tốt nghiệp','tttn'),
                            ('đại học chính quy','dhcq'), ('công nghệ thông tin','cntt')]:
            self.assertEqual(terms(full), terms(short))
            self.assertEqual(terms(full), terms(fold(full)))

    def test_boundaries_negation_numbers_and_ambiguous_alias(self):
        self.assertEqual(canonical('bhytx TV'), 'bhytx TV')
        self.assertEqual(canonical('không có BHYT năm 2026'), 'không có bảo hiểm y tế năm 2026')
        self.assertIn('khong', terms('không có BHYT năm 2026'))
        self.assertIn('2026', terms('không có BHYT năm 2026'))

    def test_unlisted_accented_phrase_can_match_without_accents(self):
        index = KeywordIndex([{'text':'Lịch sử dụng phòng thực hành điện tử', 'metadata':{}}])
        results, _ = index.search('phong thuc hanh dien tu', 4)
        self.assertTrue(results[0]['strong'])
        self.assertFalse(any(r['strong'] for r in index.search('công thức bánh pizza', 4)[0]))


if __name__ == '__main__': unittest.main()
