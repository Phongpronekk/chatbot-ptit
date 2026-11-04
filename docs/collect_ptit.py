"""Harvest public PTIT WordPress articles/pages and linked PDF text.

python docs/collect_ptit.py --since 2025-01-01 --until 2026-10-28
"""
import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from html import unescape
from io import BytesIO
import json
from pathlib import Path
import re
import ssl
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from markdownify import markdownify
from pypdf import PdfReader
import yaml

ROOT = Path(__file__).resolve().parents[1]
HOSTS = ['student.ptit.edu.vn', 'giaovu.ptit.edu.vn', 'daotao.ptit.edu.vn', 'tuyensinh.ptit.edu.vn']
ARCHIVE = ROOT / 'docs' / 'ptit_collection'
RULES = [
    ('Ký túc xá', r'ký túc xá|\bktx\b'),
    ('Thư viện', r'thư viện'),
    ('Câu lạc bộ (CLB)', r'câu lạc bộ|\bclb\b'),
    ('Bảo hiểm / Y tế', r'bảo hiểm|\bbhyt\b|y tế|sức khỏe'),
    ('Học bổng / Chính sách hỗ trợ', r'học bổng|miễn\W*giảm học phí|hỗ trợ chi phí|trợ cấp|chính sách'),
    ('Học phí / Tài chính', r'học phí|lệ phí|khoản thu|tài chính|kinh phí'),
    ('Thực tập / Việc làm', r'thực tập|việc làm|tuyển dụng|doanh nghiệp'),
    ('Tiếng Anh / Ngoại ngữ', r'tiếng anh|ngoại ngữ|toeic|ielts|course|tiếng nhật'),
    ('Tốt nghiệp / Văn bằng', r'tốt nghiệp|văn bằng|cấp bằng|có bằng'),
    ('Tuyển sinh / Ngành đào tạo', r'tuyển sinh|xét tuyển|trúng tuyển|nhập học|chỉ tiêu|ngành học|chương trình đào tạo'),
    ('Quy chế chung', r'quy chế|quy định|quyết định|thủ tục|biểu mẫu'),
    ('Học vụ / Đăng ký học / Lịch thi', r'đăng ký|học phần|học vụ|lịch thi|thời khóa|thời khoá|kế hoạch|học kỳ|học kì|học lại|bảo lưu'),
    ('Công tác sinh viên / Hoạt động', r'sinh viên|đoàn|rèn luyện|hoạt động|cuộc thi|chương trình'),
]


def classify(title, host, categories, kind=''):
    if kind in ('chuong_trinh_dao_tao', 'de_an_tuyen_sinh'):
        return 'Tuyển sinh / Ngành đào tạo'
    for group, pattern in RULES:
        if re.search(pattern, title, re.I):
            return group
    combined = ' '.join(categories)
    for group, pattern in RULES:
        if re.search(pattern, combined, re.I):
            return group
    return 'Tuyển sinh / Ngành đào tạo' if host.startswith('tuyensinh.') else 'Thông tin chung / Tin tức'


def fetch(url):
    host = urlparse(url).hostname or ''
    if not (host == 'ptit.edu.vn' or host.endswith('.ptit.edu.vn')):
        raise ValueError('External attachment: reference link only')
    req = Request(url, headers={'User-Agent': 'PTIT-Student-KnowledgeCollector/1.0'})
    time.sleep(0.15)
    for attempt in range(3):
        try:
            with urlopen(req, timeout=35, context=ssl.create_default_context()) as r:
                if int(r.headers.get('Content-Length', '0')) > 30_000_000:
                    raise ValueError('Attachment larger than 30 MB')
                data = r.read(30_000_001)
                if len(data) > 30_000_000:
                    raise ValueError('Response larger than 30 MB')
                return data, dict(r.headers)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (TimeoutError, OSError):
            if attempt == 2:
                raise
        time.sleep(attempt + 1)


def listing(host, kind, params):
    page = 1
    while True:
        url = f'https://{host}/wp-json/wp/v2/{kind}?' + urlencode({**params, 'per_page': 100, 'page': page})
        raw, headers = fetch(url)
        rows = json.loads(raw)
        if not isinstance(rows, list):
            raise ValueError(f'Unexpected listing: {url}')
        yield from rows
        total_pages = next((v for k, v in headers.items() if k.lower() == 'x-wp-totalpages'), '1')
        if page >= int(total_pages) or not rows:
            break
        page += 1


def clean_html(html, base):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'form', 'nav', 'iframe']):
        tag.decompose()
    for tag in soup.find_all(['a', 'img']):
        key = 'href' if tag.name == 'a' else 'src'
        if tag.get(key):
            tag[key] = urljoin(base, tag[key])
    return soup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--since', default='2025-01-01')
    parser.add_argument('--until', default='2026-10-28')
    parser.add_argument('--supplement', action='store_true', help='Add custom content types to an existing report')
    args = parser.parse_args()
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    (ARCHIVE / 'raw').mkdir(exist_ok=True)
    (ARCHIVE / 'pdf').mkdir(exist_ok=True)
    cache_path = ARCHIVE / 'attachments.json'
    cache = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    report = {'since': args.since, 'until': args.until, 'fetched_date': datetime.now(timezone(timedelta(hours=7))).date().isoformat(),
              'documents': [], 'errors': [], 'skipped': [], 'sources': {}, 'groups': {},
              'scope': 'Published public posts within date range; public reference pages and student regulation index links also included. Dates are publication dates, not effective dates.'}
    hashes = {}
    if args.supplement:
        report = json.loads((ARCHIVE / 'report.json').read_text(encoding='utf-8'))
    imported_urls = {d['url'] for d in report['documents']}

    def save_report():
        report['groups'] = dict(Counter(x['topic_group'] for x in report['documents']))
        (ARCHIVE / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')

    def ingest(row, host, categories, reference=False):
        url = row['link'].split('?')[0]
        if url in imported_urls:
            return
        title = BeautifulSoup(row['title']['rendered'], 'html.parser').get_text(' ', strip=True)
        if title.strip().lower() in ('sample page', 'hello world', 'hello world!'):
            report['skipped'].append({'url': url, 'reason': 'WordPress demo content'})
            return
        html = row.get('content', {}).get('rendered', '')
        if not html.strip():
            raw, _ = fetch(url)
            page_soup = BeautifulSoup(raw, 'html.parser')
            main = next((node for selector in ['.ova_dir_content', 'article .post-content', '.entry-content', '#main-content', 'article']
                         if (node := page_soup.select_one(selector)) is not None), None)
            if main:
                html = str(main)
            if not BeautifulSoup(html, 'html.parser').get_text(' ', strip=True) and '.pdf' not in html:
                media = list(listing(host, 'media', {'parent': row['id']}))
                html += ''.join(f'<p><a href="{m["source_url"]}">{m["title"]["rendered"]}</a></p>'
                                for m in media if m.get('source_url'))
            if row['type'] == 'quy_che_quy_dinh' and not BeautifulSoup(html, 'html.parser').get_text(' ', strip=True):
                report['skipped'].append({'url': url, 'reason': 'Regulation page has no public body or attachment'})
                return
        soup = clean_html(html, url)
        text = soup.get_text(' ', strip=True)
        if not text and not soup.find(['a', 'img']):
            report['skipped'].append({'url': url, 'reason': 'empty content'})
            return
        digest = sha256(soup.encode()).hexdigest()
        if digest in hashes:
            report['skipped'].append({'url': url, 'reason': 'duplicate content', 'canonical': hashes[digest]})
            return
        hashes[digest] = url
        names = [categories.get(i, str(i)) for i in row.get('categories', [])]
        topic = classify(title, host, names, row['type'])
        attachments, sections = [], []
        for a in soup.find_all('a', href=True):
            href = a['href']
            suffix = Path(urlparse(href).path).suffix.lower()
            if suffix not in ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar'):
                continue
            if any(x['url'] == href for x in attachments):
                continue
            item = {'url': href, 'type': suffix, 'status': 'link_only'}
            if suffix == '.pdf':
                if href not in cache or cache[href]['status'] == 'error':
                    try:
                        data, _ = fetch(href)
                        name = sha256(href.encode()).hexdigest()[:20]
                        (ARCHIVE / 'pdf' / (name + '.pdf')).write_bytes(data)
                        pdf = PdfReader(BytesIO(data))
                        pages = [p.extract_text() or '' for p in pdf.pages]
                        status = 'text_extracted' if sum(len(p.strip()) for p in pages) > 100 else 'needs_ocr'
                        (ARCHIVE / 'pdf' / (name + '.txt')).write_text('\n\n'.join(f'### Trang {i}\n\n{t}' for i,t in enumerate(pages,1)), encoding='utf-8')
                        cache[href] = {'status': status, 'pages': len(pages), 'file': name}
                    except Exception as exc:
                        cache[href] = {'status': 'error', 'error': str(exc)}
                item.update(cache[href])
                if item['status'] == 'text_extracted':
                    pdf_text = (ARCHIVE / 'pdf' / (item['file'] + '.txt')).read_text(encoding='utf-8')
                    sections.append(f"\n\n## Tài liệu đính kèm: {a.get_text(' ', strip=True) or 'PDF'}\n\nNguồn: {href}\n\n{pdf_text}")
            attachments.append(item)
        body = markdownify(str(soup), heading_style='ATX')
        body = re.sub(r'\n{3,}', '\n\n', body).strip()
        published = row.get('date', '')[:10]
        metadata = {'source_url': url, 'fetched_date': report['fetched_date'], 'publish_date': published,
                    'topic_group': topic, 'title': title, 'source_site': host, 'source_id': str(row['id']), 'source_type': row['type'],
                    'updated_at': row.get('modified', ''), 'source_categories': ', '.join(names),
                    'reference_page': reference, 'content_sha256': digest,
                    'note': 'Nguồn công khai PTIT; phân nhóm tự động. Ngày đăng không phải ngày hiệu lực. Kiểm tra khóa, cơ sở, học kỳ trong nội dung. PDF chỉ trích lớp văn bản, chưa OCR ảnh.'}
        if reference:
            metadata['note'] += ' Trang/tài liệu tham chiếu có thể cũ hơn phạm vi thu thập; không tự khẳng định còn hiệu lực.'
        name = f"ptit_{host.split('.')[0]}_{row['type']}_{row['id']}.md"
        (ROOT / 'data' / name).write_text('---\n' + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False) + '---\n\n# ' + title + '\n\n' + body + ''.join(sections) + '\n', encoding='utf-8')
        (ARCHIVE / 'raw' / (name[:-3] + '.json')).write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding='utf-8')
        report['documents'].append({'file': name, 'url': url, 'title': title, 'publish_date': published,
                                    'topic_group': topic, 'reference_page': reference, 'attachments': attachments})
        imported_urls.add(url)
        save_report()
        print(f"[{len(report['documents'])}] {host}: {title[:100]}", flush=True)

    for host in HOSTS:
        start = len(report['documents'])
        try:
            categories = {c['id']: unescape(c['name']) for c in listing(host, 'categories', {})}
            rows = [] if args.supplement else list(listing(host, 'posts', {'after': args.since + 'T00:00:00', 'before': args.until + 'T23:59:59', 'orderby': 'date', 'order': 'desc'}))
            # All public static pages serve as reference material, with their original dates.
            pages = [] if args.supplement else list(listing(host, 'pages', {'before': args.until + 'T23:59:59'}))
            ids = {r['id'] for r in rows}
            if host == 'student.ptit.edu.vn' and not args.supplement:
                for cat_id, cat_name in categories.items():
                    if re.search(r'quy chế|quy định', cat_name, re.I):
                        for row in listing(host, 'posts', {'categories': cat_id, 'before': args.until + 'T23:59:59'}):
                            if row['id'] not in ids:
                                pages.append(row)
                                ids.add(row['id'])
            if not args.supplement:
                report['sources'][host] = {'posts_discovered': len(rows), 'reference_discovered': len(pages)}
            custom_types = {
                'student.ptit.edu.vn': ['quy_che_quy_dinh', 'ova_doc'],
                'daotao.ptit.edu.vn': ['chuong_trinh_dao_tao', 'de_an_tuyen_sinh'],
                'tuyensinh.ptit.edu.vn': ['de_an_tuyen_sinh'],
            }.get(host, [])
            for kind in custom_types:
                try:
                    params = {'before': args.until + 'T23:59:59'}
                    if kind != 'quy_che_quy_dinh':
                        params['after'] = args.since + 'T00:00:00'
                    custom = list(listing(host, kind, params))
                    report['sources'].setdefault(host, {})[kind + '_discovered'] = len(custom)
                    pages.extend(custom)
                except Exception as exc:
                    report['errors'].append({'host': host, 'kind': kind, 'error': str(exc)})
            for row in rows + pages:
                try:
                    ingest(row, host, categories, row in pages)
                except Exception as exc:
                    report['errors'].append({'url': row.get('link'), 'error': str(exc)})
                    save_report()
        except Exception as exc:
            report['errors'].append({'host': host, 'error': str(exc)})
        report['sources'].setdefault(host, {})['imported'] = sum(urlparse(d['url']).hostname == host for d in report['documents'])
        save_report()
    print(json.dumps({'sources': report['sources'], 'groups': report['groups'], 'errors': report['errors']}, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
