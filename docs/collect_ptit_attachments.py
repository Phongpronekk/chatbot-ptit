"""Download linked Office files and extract DOCX/XLSX XML without running macros."""
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from collect_ptit import ARCHIVE, ROOT, fetch


def extract_office(data, extension):
    with ZipFile(BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist()) > 100_000_000:
            raise ValueError('Uncompressed Office file exceeds 100 MB')
        if extension == '.docx':
            doc = ET.fromstring(z.read('word/document.xml'))
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            return '\n'.join(''.join(p.itertext()) for p in doc.findall('.//w:p', ns))
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', ns)]
        output = []
        for name in sorted(n for n in z.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')):
            output.append('### ' + name.rsplit('/', 1)[-1])
            root = ET.fromstring(z.read(name))
            for row in root.findall('.//s:sheetData/s:row', ns):
                values = []
                for c in row.findall('s:c', ns):
                    v = c.find('s:v', ns)
                    text = v.text or '' if v is not None else ''
                    if c.get('t') == 's' and text:
                        text = strings[int(text)]
                    elif c.get('t') == 'inlineStr':
                        inline = c.find('s:is', ns)
                        text = ''.join(inline.itertext()) if inline is not None else ''
                    if text:
                        values.append(c.get('r', '') + ': ' + text)
                if values:
                    output.append(' | '.join(values))
        return '\n'.join(output)


def main():
    path = ARCHIVE / 'report.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    folder = ARCHIVE / 'office'
    folder.mkdir(exist_ok=True)
    cache_path = folder / 'index.json'
    cache = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    urls = {a['url']: a for d in report['documents'] for a in d['attachments'] if a['type'] != '.pdf'}
    for index, (url, a) in enumerate(urls.items(), 1):
        if url in cache:
            continue
        result = {'status': 'downloaded_only'}
        try:
            data, _ = fetch(url)
            name = sha256(url.encode()).hexdigest()[:20]
            (folder / (name + a['type'])).write_bytes(data)
            result['file'] = name
            if a['type'] in ('.docx', '.xlsx'):
                text = extract_office(data, a['type'])
                if text.strip():
                    (folder / (name + '.txt')).write_text(text, encoding='utf-8')
                    result['status'] = 'office_text_extracted'
                else:
                    result['status'] = 'office_empty_text'
        except Exception as exc:
            result = {'status': 'error', 'error': str(exc)}
        cache[url] = result
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[{index}/{len(urls)}] {result["status"]}: {url[-110:]}', flush=True)
    for d in report['documents']:
        md = ROOT / 'data' / d['file']
        body = md.read_text(encoding='utf-8')
        for a in d['attachments']:
            if a['url'] not in cache:
                continue
            a.update(cache[a['url']])
            if a['status'] == 'office_text_extracted':
                marker = '<!-- office-source:' + sha256(a['url'].encode()).hexdigest() + ' -->'
                if marker not in body:
                    text = (folder / (a['file'] + '.txt')).read_text(encoding='utf-8')
                    body += f'\n\n{marker}\n\n## Tệp đính kèm {a["type"]}\n\nNguồn: {a["url"]}\n\n{text}\n'
        md.write_text(body, encoding='utf-8')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(Counter(v['status'] for v in cache.values())), ensure_ascii=False))


if __name__ == '__main__':
    main()
