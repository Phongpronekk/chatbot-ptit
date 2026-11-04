"""Validate harvested files and produce a readable catalogue by topic."""
from collections import Counter
import json
from pathlib import Path
from urllib.parse import urlparse

import yaml
from collect_ptit import ARCHIVE, ROOT, classify


def main():
    report_path = ARCHIVE / 'report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    keep = []
    for item in report['documents']:
        path = ROOT / 'data' / item['file']
        assert path.resolve().parent == (ROOT / 'data').resolve()
        if item['title'].strip().lower() in ('sample page', 'hello world', 'hello world!'):
            path.unlink(missing_ok=True)
            report['skipped'].append({'url': item['url'], 'reason': 'WordPress demo content'})
            continue
        text = path.read_text(encoding='utf-8')
        _, front, body = text.split('---', 2)
        meta = yaml.safe_load(front)
        if '_quy_che_quy_dinh_' in item['file'] and not item['attachments']:
            original = json.loads((ARCHIVE / 'raw' / (item['file'][:-3] + '.json')).read_text(encoding='utf-8'))
            if not original.get('content', {}).get('rendered', '').strip() and len(body.strip()) < 600:
                path.unlink(missing_ok=True)
                report['skipped'].append({'url': item['url'], 'reason': 'Regulation page exposes title/date only; no body or attachment'})
                continue
        assert meta['source_url'] == item['url']
        assert body.strip(), path
        if not item['reference_page']:
            assert report['since'] <= meta['publish_date'] <= report['until'], path
        kind = meta.get('source_type', '')
        if not kind:
            raw_path = ARCHIVE / 'raw' / (item['file'][:-3] + '.json')
            kind = json.loads(raw_path.read_text(encoding='utf-8')).get('type', '')
        group = classify(item['title'], urlparse(item['url']).hostname, [meta.get('source_categories', '')], kind)
        if group != meta['topic_group']:
            meta['topic_group'] = group
            path.write_text('---\n' + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + '---' + body, encoding='utf-8')
        item['topic_group'] = group
        keep.append(item)
    report['documents'] = keep
    report['groups'] = dict(Counter(d['topic_group'] for d in keep))
    for host in report['sources']:
        report['sources'][host]['imported'] = sum(urlparse(d['url']).hostname == host for d in keep)
    attachments = {a['url']: a for d in keep for a in d['attachments']}
    report['attachment_summary'] = dict(Counter(a['status'] for a in attachments.values()))
    report['audit'] = {'documents_validated': len(keep), 'unique_attachments': len(attachments),
                       'reference_documents': sum(d['reference_page'] for d in keep)}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    catalogue = [f"# Kho dữ liệu PTIT từ {report['since']} đến {report['until']}", '',
                 'Phạm vi: bài đăng công khai trong khoảng thời gian trên; thêm trang tham chiếu và quy chế nền (có thể cũ hơn).',
                 'Ngày đăng không chứng minh ngày có hiệu lực. Không thu thập dữ liệu sau đăng nhập.', '',
                 '## Theo nguồn', '', '| Nguồn | Tài liệu đã nhập |', '|---|---:|']
    catalogue.extend(f"| {host} | {value['imported']} |" for host, value in report['sources'].items())
    catalogue += ['', '## Theo nhóm', '', '| Nhóm | Tài liệu |', '|---|---:|']
    catalogue.extend(f'| {group} | {count} |' for group, count in sorted(report['groups'].items()))
    catalogue += ['', '## Tệp đính kèm', '', 'Số lượng URL duy nhất: ' + str(len(attachments)), '',
                  '```json', json.dumps(report['attachment_summary'], ensure_ascii=False, indent=2), '```', '',
                  '`text_extracted`: đã trích lớp chữ PDF; `needs_ocr`: PDF scan, giữ bản gốc nhưng chưa đọc được nội dung;',
                  '`link_only`: giữ URL Word/Excel hoặc định dạng chưa hỗ trợ; `error`: tải/đọc lỗi, xem report.json.',
                  '`office_text_extracted`: đã trích chữ DOCX hoặc ô XLSX; `downloaded_only`: đã giữ bản gốc nhưng chưa trích được định dạng cũ.',
                  'Word giữ nội dung đoạn văn; Excel giữ địa chỉ ô và giá trị lưu sẵn, chưa diễn giải định dạng ngày tháng và không tính lại công thức.',
                  'Ảnh chụp, chữ trong hình và một số bảng PDF có thể chưa được trích đầy đủ. Không tự coi các tệp này là đã đọc hết.', '',
                  '## Chạy lại', '', '```powershell',
                  '.\\.venv\\Scripts\\python.exe -m pip install -r BE/requirements.txt -r docs/requirements-scrape.txt',
                  '.\\.venv\\Scripts\\python.exe docs/collect_ptit.py --since 2025-01-01 --until 2026-10-28',
                  '.\\.venv\\Scripts\\python.exe docs/audit_ptit_collection.py', '```', '',
                  'Có thể bổ sung Word/Excel rồi kiểm tra lại bằng:', '', '```powershell',
                  '.\\.venv\\Scripts\\python.exe docs/collect_ptit_attachments.py',
                  '.\\.venv\\Scripts\\python.exe docs/audit_ptit_collection.py', '```', '',
                  'Không có lịch chạy tự động. File Markdown giữ cùng tên theo website, loại và ID; bản gốc và PDF nằm tại raw/ và pdf/.',
                  'Cache PDF tránh tải lại URL đã đọc; khi tài liệu tại cùng URL thay đổi, cần bỏ entry tương ứng trong attachments.json trước khi cập nhật.', '',
                  '## Danh mục theo nhóm']
    for group in sorted(report['groups']):
        catalogue += ['', '### ' + group, '']
        for d in keep:
            if d['topic_group'] == group:
                label = d['title'].replace('[', '(').replace(']', ')')
                catalogue.append(f"- {d['publish_date']} — [{label}]({d['url']})")
    (ARCHIVE / 'README.md').write_text('\n'.join(catalogue) + '\n', encoding='utf-8')
    print(json.dumps({'audit': report['audit'], 'groups': report['groups'], 'attachments': report['attachment_summary']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
