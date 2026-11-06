import unittest
import unicodedata
from BE.search_text import canonical, normalize_query, terms, fold, KeywordIndex, is_greeting, greeting_response


class SearchTextTests(unittest.TestCase):
    def test_greeting_detection(self):
        positives = [
            'chao', 'chào', 'Chào', 'CHÀO', 'chào!', 'chào bạn', 'chao ban', 'chào bot', 'chao bot',
            'xin chào', 'xin chao', 'Xin chào bạn', 'dạ chào bạn', 'chào bạn nhé', 'chào bạn nha',
            'chào bạn ạ', 'chào nhé', 'chào nha', 'chào bot ơi', 'chào em', 'chào anh', 'chào chị',
            'chào buổi sáng', 'chào buổi chiều', 'chào buổi tối',
            'hello', 'Hello', 'HELLO', 'hello!', 'hello bot', 'hello bạn', 'helo', 'hế lô',
            'hi', 'Hi', 'HI', 'hi!', 'hi bot', 'hi bạn', 'hii', 'hiii', 'hey', 'hey bot',
            'alo', 'a lô', 'alo bot', 'alo bot ơi', 'good morning', 'good afternoon', 'good evening',
            'Chào bạn! 😊', 'Hello bot 👋', 'Hi! 🌟', 'chào bạn nhé ạ :))', 'alo bot ơi!!!',
            'chao ban ^_^', 'hello <3', '  !! CHÀO BẠN :D  ', 'xin chào ạ ^^',
            'dạ em chào thầy ạ', 'dạ em chào cô', 'chào ad nhé', 'hello admin', 'hey there'
        ]
        for greeting in positives:
            with self.subTest(greeting=greeting):
                self.assertTrue(is_greeting(greeting), f"Failed to recognize greeting: {greeting}")

        negatives = [
            'chào bạn, KTX B2 phí bao nhiêu?',
            'chào bot, cho mình hỏi về học phí',
            'hello bot, thủ tục đăng ký học phần thế nào?',
            'hi, bảo hiểm y tế nộp khi nào?',
            'chào tân sinh viên là ngày nào?',
            'ngày hội chào tân sinh viên',
            'thư viện chào đón tân sinh viên',
            'cháo gà',
            'KTX',
            'bảo hiểm y tế',
            'tôi muốn hỏi về học bổng'
        ]
        for non_greeting in negatives:
            with self.subTest(non_greeting=non_greeting):
                self.assertFalse(is_greeting(non_greeting), f"Mistakenly recognized as greeting: {non_greeting}")

        self.assertIn("Chào bạn!", greeting_response())
        self.assertIn("PTIT", greeting_response())

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
