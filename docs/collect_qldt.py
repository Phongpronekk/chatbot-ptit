"""Collect public QLDT posts by publication year; never authenticate.

Run: .venv/Scripts/python.exe docs/collect_qldt.py --year 2026
Dependencies: BE/requirements.txt and docs/requirements-scrape.txt.
"""
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import ssl
import time
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from markdownify import markdownify
from pypdf import PdfReader
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://qldt.ptit.edu.vn'
GROUPS = ['Câu lạc bộ (CLB)', 'Quy chế chung', 'Ký túc xá', 'Thư viện', 'Thực tập / Việc làm']


def request(path, payload=None):
    url = urljoin(BASE, path)
    if urlparse(url).hostname != 'qldt.ptit.edu.vn':
        raise ValueError('Only public QLDT URLs are permitted')
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=data, headers={
        'User-Agent': 'PTIT-Chatbot-KnowledgeCollector/1.0', 'Content-Type': 'application/json',
    })
    with urlopen(req, timeout=45, context=ssl.create_default_context()) as response:
        return response.read()


def api(path, payload):
    result = json.loads(request('/api/web/' + path, payload))
    if result.get('code') != 200 or not result.get('result'):
        raise RuntimeError(f'Public API rejected request: {result.get("code")}')
    return result['data']


def classify(title):
    for group, pattern in [
        (GROUPS[0], r'câu lạc bộ|\bclb\b'),
        (GROUPS[2], r'ký túc xá|\bktx\b'),
        (GROUPS[3], r'thư viện'),
        (GROUPS[4], r'thực tập|việc làm|tuyển dụng'),
    ]:
        if re.search(pattern, title, re.I):
            return group
    return GROUPS[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, default=2026)
    parser.add_argument('--until', default='2026-10-28')
    args = parser.parse_args()
    fetched = datetime.now(timezone(timedelta(hours=7))).date().isoformat()
    archive = ROOT / 'docs' / f'qldt_{args.year}'
    archive.mkdir(parents=True, exist_ok=True)
    report = {'year': args.year, 'until': args.until, 'fetched_date': fetched,
              'source': BASE, 'groups': {g: 0 for g in GROUPS}, 'documents': [], 'errors': [],
              'scope': 'Public homepage posts only; no authenticated student notifications; publication-date filter.'}
    seen = set()
    for page in range(1, 21):
        listing = api('w-locdsbaidang', {
            'filter': {'ky_hieu': '', 'is_hien_thi': True, 'is_hinh_dai_dien': False,
                       'is_quyen_xem': True, 'is_noi_dung': False, 'is_tom_tat': True},
            'additional': {'paging': {'limit': 50, 'page': page},
                           'ordering': [{'name': 'ngay_dang_tin', 'order_type': 1}]},
        })
        rows = [p for g in listing.get('ds_bai_viet', []) for p in g.get('ds_baiviet', [])]
        new = [r for r in rows if r['id'] not in seen]
        if not new:
            break
        for row in new:
            seen.add(row['id'])
            published = row.get('ngay_dang_tin', '')[:10]
            if not published.startswith(f'{args.year}-') or published > args.until:
                continue
            try:
                time.sleep(0.5)
                detail = api('w-locdsbaidangbyid', {
                    'filter': {'id': row['id'], 'is_noi_dung': True},
                    'additional': {'paging': {'limit': 1, 'page': 1}, 'ordering': []},
                })['ds_bai_viet'][0]
                html = detail.get('noi_dung', '')
                soup = BeautifulSoup(html, 'html.parser')
                for tag in soup(['script', 'style', 'iframe', 'form']):
                    tag.decompose()
                attachments = []
                pdf_sections = []
                for a in soup.find_all('a', href=True):
                    a['href'] = urljoin(BASE, a['href'])
                    url = a['href']
                    if urlparse(url).path.lower().endswith('.pdf'):
                        attachment = {'url': url, 'status': 'link_only'}
                        if urlparse(url).hostname == 'qldt.ptit.edu.vn':
                            try:
                                time.sleep(0.5)
                                raw = request(url)
                                name = sha256(url.encode()).hexdigest()[:12] + '.pdf'
                                (archive / name).write_bytes(raw)
                                reader = PdfReader(BytesIO(raw))
                                pages = [p.extract_text() or '' for p in reader.pages]
                                if sum(len(p.strip()) for p in pages) < 100:
                                    raise ValueError('PDF needs OCR; text was not imported')
                                pdf_sections.append('\n\n## Tài liệu đính kèm: ' + a.get_text(' ', strip=True)
                                                    + '\n\nNguồn PDF: ' + url + '\n\n'
                                                    + '\n\n'.join(f'### Trang {i}\n\n{text}' for i, text in enumerate(pages, 1)))
                                attachment.update(status='text_extracted', pages=len(pages), file=name)
                            except Exception as exc:
                                attachment['error'] = str(exc)
                        attachments.append(attachment)
                body = markdownify(str(soup), heading_style='ATX')
                body = re.sub(r'\n{3,}', '\n\n', body).strip()
                if not body:
                    raise ValueError('Empty post body')
                group = classify(row['tieu_de'])
                source = f"{BASE}/#/home/listbaiviet/{row['ky_hieu']}/page/1/baivietct/{row['id']}"
                metadata = {
                    'source_url': source, 'fetched_date': fetched, 'publish_date': published,
                    'topic_group': group, 'title': row['tieu_de'], 'source_id': row['id'],
                    'updated_at': row.get('ngay_hieu_chinh', ''),
                    'note': 'Bài đăng công khai QLĐT. Ngày đăng không phải ngày hiệu lực; chỉ áp dụng theo khóa/học kỳ/cơ sở trong nội dung. Phân nhóm tự động theo tiêu đề.',
                    'content_sha256': sha256(html.encode()).hexdigest(),
                }
                filename = f"qldt_{args.year}_{row['id'].lstrip('-')}.md"
                document = '---\n' + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False) + '---\n\n'
                document += '# ' + row['tieu_de'] + '\n\n' + body + ''.join(pdf_sections) + '\n'
                (ROOT / 'data' / filename).write_text(document, encoding='utf-8')
                (archive / f"{row['id'].lstrip('-')}.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding='utf-8')
                report['groups'][group] += 1
                report['documents'].append({'file': filename, 'title': row['tieu_de'], 'publish_date': published,
                                             'topic_group': group, 'url': source, 'attachments': attachments})
                print('Imported:', published, row['tieu_de'], flush=True)
            except Exception as exc:
                report['errors'].append({'id': row['id'], 'error': str(exc)})
        if page >= (listing.get('total_pages') or 1):
            break
    report['listed_posts'] = len(seen)
    (archive / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'groups': report['groups'], 'errors': report['errors']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
