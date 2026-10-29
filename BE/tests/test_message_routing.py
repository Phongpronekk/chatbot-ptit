import unittest

from BE.message_routing import route_message, file_history


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.history = [
            {'role': 'user', 'text': 'tổng hợp', 'attachments': [{'id': 'report'}]},
            {'role': 'assistant', 'text': 'Báo cáo có nhắc KTX.', 'sources': [{'document_id': 'report'}]},
        ]

    def route(self, question, **kwargs):
        return route_message(question, document_ids=['report'], history=self.history, **kwargs)

    def test_new_ptit_subject_is_not_trapped_in_the_uploaded_report(self):
        for question in ('ktx', 'KÝ TÚC XÁ', 'ky tuc xa nam nay', 'KTX năm nay bao nhiêu tiền?',
                         'học phí', 'BHYT', 'câu lạc bộ', 'thư viện', 'Đăng ký học phần',
                         'KTX B2 ở đâu?', 'tra nguồn chính thức về học bổng'):
            with self.subTest(question=question):
                self.assertEqual(self.route(question), 'knowledge')

    def test_explicit_file_and_related_follow_up_queries(self):
        for question in ('KTX trong file này nói gì?', 'Tóm tắt file', 'tổng hợp', 'tong hop',
                         'điều kiện đó là gì?', 'GPA bao nhiêu?', 'còn hạn nộp?',
                         'giải thích nội dung trên', 'đọc tài liệu này', 'theo file PDF'):
            with self.subTest(question=question):
                self.assertEqual(self.route(question), 'documents')

    def test_explicit_scope_overrides_auto_and_new_uploads_use_the_attached_file(self):
        self.assertEqual(self.route('ktx', scope='documents'), 'documents')
        self.assertEqual(self.route('tóm tắt file', scope='knowledge'), 'knowledge')
        self.assertEqual(self.route('ktx', scope='knowledge', attachment_ids=['new']), 'documents')
        self.assertEqual(self.route('bỏ qua file, ktx'), 'knowledge')

    def test_summary_does_not_jump_back_to_a_file_after_a_ptit_turn(self):
        self.history += [{'role': 'user', 'text': 'ktx'},
                         {'role': 'assistant', 'text': 'Thông báo KTX', 'sources': [{'source_url': 'https://ptit.edu.vn'}]}]
        self.assertEqual(self.route('tổng hợp'), 'knowledge')
        self.assertEqual(self.route('tổng hợp file này'), 'documents')
        self.assertEqual(len(file_history(self.history, ['report'])), 2)
        self.assertEqual(file_history(self.history, ['other-file']), [])
