"""Collect public 2026 PTIT posts into five role-specific files.

Default writes staging only. --apply backs up and replaces exactly five files.
Never imports old reference pages simply because their titles mention 2026.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from hashlib import sha256
from html import unescape
import json
from pathlib import Path
import re
import ssl
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import httpx
import truststore
from bs4 import BeautifulSoup
from markdownify import markdownify
import yaml

ROOT=Path(__file__).resolve().parents[1]
HOSTS=['student.ptit.edu.vn','giaovu.ptit.edu.vn','daotao.ptit.edu.vn',
       'tuyensinh.ptit.edu.vn','ptit.edu.vn','lib.ptit.edu.vn']
ROLES={'clb.md':'Câu lạc bộ (CLB)','ktx.md':'Ký túc xá','quy_che_chung.md':'Quy chế chung',
       'thu_vien.md':'Thư viện','thuc_tap_viec_lam.md':'Thực tập / Việc làm'}
AGENT='PTIT-Student-KnowledgeCollector/2.0'
NOW=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
UNTIL=NOW.replace(tzinfo=None).isoformat(timespec='seconds')
ARCHIVE=ROOT/'docs'/'ptit_2026_five_files'


def classify(title,host):
    if re.search(r'thẩm định giá|mời thầu|đấu thầu|tuyển dụng.*(?:giảng viên|viên chức|pháp chế)|kỳ tuyển dụng viên chức|công nhận học vị',title,re.I):
        return None
    for file,pattern in [
        ('ktx.md',r'ký túc xá|\bktx\b|nội trú'),
        ('thu_vien.md',r'thư viện|văn hóa đọc|ngày sách|ngày hội đọc sách|cơ sở dữ liệu.*(?:sách|tạp chí)'),
        ('clb.md',r'câu lạc bộ|\bclb\b|đội (?:sinh viên|thanh niên|tình nguyện)|đoàn thanh niên|hội sinh viên|tiếp sức mùa thi|mùa hè xanh|hiến máu'),
        ('thuc_tap_viec_lam.md',r'thực tập|(?:cơ hội|ngày hội|tìm kiếm|tư vấn|giới thiệu) việc làm|tuyển dụng|hướng nghiệp|career|job fair'),
    ]:
        if re.search(pattern,title,re.I): return file
    if host=='lib.ptit.edu.vn': return 'thu_vien.md'
    if re.search(r'quy chế|quy định|quyết định.*(?:sinh viên|học|đào tạo)|thủ tục|biểu mẫu|học phí|học bổng|miễn giảm|bảo hiểm|\bbhyt\b|trợ cấp|chính sách.*sinh viên|đăng ký.*(?:học|môn)|học phần|lịch thi|thi kết thúc|học kỳ|học kì|học lại|bảo lưu|kế hoạch.*(?:học|thi|đào tạo)|chuẩn đầu ra|xét.*tốt nghiệp|cấp bằng|rèn luyện|xác nhận.*sinh viên|hồ sơ.*nhập học|thủ tục.*nhập học|sinh hoạt công dân',title,re.I):
        return 'quy_che_chung.md'
    return None


def clean(html,base):
    soup=BeautifulSoup(html,'html.parser')
    for tag in soup(['script','style','form','nav','iframe','noscript']):tag.decompose()
    attachments=[]
    for a in soup.find_all('a',href=True):
        a['href']=urljoin(base,a['href'])
        if re.search(r'\.(?:pdf|docx?|xlsx?)(?:[?#]|$)',a['href'],re.I):
            attachments.append({'url':a['href'],'label':a.get_text(' ',strip=True),'status':'link_only_not_extracted'})
    # Strip images: filenames and alt text do not establish their factual contents.
    for img in soup.find_all('img'):img.decompose()
    text=markdownify(str(soup),heading_style='ATX').strip()
    text=re.sub(r'\n{3,}','\n\n',text)
    return text,attachments


def collect_host(host):
    docs=[];skipped=[];errors=[];scanned=0
    with httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),timeout=25,
                      follow_redirects=True,headers={'User-Agent':AGENT}) as client:
        robots=RobotFileParser()
        try:
            rr=client.get(f'https://{host}/robots.txt')
            if rr.status_code==200:robots.parse(rr.text.splitlines())
            elif rr.status_code in (401,403):
                return docs,skipped,[{'host':host,'error':'robots access denied; skipped'}],scanned
            else:robots.parse(['User-agent: *','Allow: /'])
        except Exception as e:
            return docs,skipped,[{'host':host,'error':'robots unavailable: '+str(e)}],scanned
        for page in range(1,41):
            url=f'https://{host}/wp-json/wp/v2/posts'
            if not robots.can_fetch(AGENT,url):
                errors.append({'host':host,'error':'robots disallows posts endpoint'});break
            params={'after':'2026-01-01T00:00:00','before':UNTIL,'per_page':100,'page':page,
                    'orderby':'date','order':'asc','_fields':'id,date,link,title,content,excerpt,status'}
            try:
                time.sleep(.35)
                response=client.get(url,params=params)
                if response.status_code==400 and page>1:break
                response.raise_for_status();rows=response.json()
                if not isinstance(rows,list):raise ValueError('Unexpected posts listing')
                for post in rows:
                    scanned+=1
                    published=post.get('date','')
                    if not published.startswith('2026-') or published>UNTIL:continue
                    title=unescape(BeautifulSoup(post['title']['rendered'],'html.parser').get_text(' ',strip=True))
                    file=classify(title,host)
                    if not file:
                        skipped.append({'url':post['link'],'title':title,'reason':'outside five roles'});continue
                    if not robots.can_fetch(AGENT,post['link']):
                        skipped.append({'url':post['link'],'reason':'robots disallows article'});continue
                    content,attachments=clean(post.get('content',{}).get('rendered',''),post['link'])
                    if not content:
                        skipped.append({'url':post['link'],'title':title,'reason':'no text; image/attachment not extracted'});continue
                    docs.append({'url':post['link'],'title':title,'publish_date':published[:10],
                                 'date_evidence':'WordPress date field','file':file,'content':content,
                                 'attachments':attachments,'host':host})
                print(f'{host}: page {page}, scanned {scanned}, selected {len(docs)}',flush=True)
                if page>=int(response.headers.get('X-WP-TotalPages','1')) or not rows:break
            except Exception as e:
                errors.append({'host':host,'page':page,'error':str(e)});break
        else:errors.append({'host':host,'error':'page cap reached; not exhaustive'})
    return docs,skipped,errors,scanned


def collect_qldt():
    host='qldt.ptit.edu.vn';docs=[];skipped=[];errors=[];seen=set()
    base='https://'+host
    with httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),timeout=25,
                      headers={'User-Agent':AGENT}) as client:
        def api(method,payload):
            time.sleep(.35)
            r=client.post(base+'/api/web/'+method,json=payload);r.raise_for_status()
            value=r.json()
            if value.get('code')!=200:raise ValueError('Public QLDT API rejected request')
            return value['data']
        rr=client.get(base+'/robots.txt')
        robots=RobotFileParser();robots.parse(rr.text.splitlines() if rr.status_code==200 else ['User-agent: *','Allow: /'])
        if rr.status_code in (401,403) or not robots.can_fetch(AGENT,base+'/api/web/w-locdsbaidang'):
            return [],[],[{'host':host,'error':'robots denied'}],0
        try:
            for page in range(1,31):
                result=api('w-locdsbaidang',{'filter':{'ky_hieu':'','is_hien_thi':True,'is_hinh_dai_dien':False,
                    'is_quyen_xem':True,'is_noi_dung':False,'is_tom_tat':True},'additional':{'paging':{'limit':100,'page':page},
                    'ordering':[{'name':'ngay_dang_tin','order_type':1}]}})
                rows=[r for g in result.get('ds_bai_viet',[]) for r in g.get('ds_baiviet',[])]
                new=[r for r in rows if r['id'] not in seen]
                if not new:break
                for row in new:
                    seen.add(row['id']);published=row.get('ngay_dang_tin','')[:10];title=row['tieu_de']
                    if not published.startswith('2026-') or published>UNTIL[:10]:continue
                    file=classify(title,host)
                    if not file:
                        skipped.append({'title':title,'reason':'QLDT post outside five roles'});continue
                    detail=api('w-locdsbaidangbyid',{'filter':{'id':row['id'],'is_noi_dung':True},
                        'additional':{'paging':{'limit':1,'page':1},'ordering':[]}})['ds_bai_viet'][0]
                    url=f"{base}/#/home/listbaiviet/{row['ky_hieu']}/page/1/baivietct/{row['id']}"
                    content,attachments=clean(detail.get('noi_dung',''),base)
                    if content:docs.append({'url':url,'title':title,'publish_date':published,
                        'date_evidence':'Public QLDT ngay_dang_tin field','file':file,'content':content,'attachments':attachments,'host':host})
                if page>=int(result.get('total_pages',1)):break
            print(f'{host}: scanned {len(seen)}, selected {len(docs)}',flush=True)
        except Exception as e:errors.append({'host':host,'error':str(e)})
    return docs,skipped,errors,len(seen)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    stage=ARCHIVE/'staged';stage.mkdir(parents=True,exist_ok=True)
    report={'year':2026,'through':UNTIL,'fetched_date':NOW.date().isoformat(),'documents':[],
            'errors':[],'skipped':[],'hosts':{},'attachment_policy':'Links only; binary files, scans and images not extracted',
            'scope':'Public posts with verified publication date in 2026 through collection time; five role-specific groups, no login.'}
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(collect_host,h):h for h in HOSTS}
        jobs[pool.submit(collect_qldt)]='qldt.ptit.edu.vn'
        for future in as_completed(jobs):
            host=jobs[future]
            try:
                docs,skips,errors,scanned=future.result()
                report['documents']+=docs;report['skipped']+=skips;report['errors']+=errors
                report['hosts'][host]={'scanned':scanned,'selected':len(docs)}
            except Exception as e:report['errors'].append({'host':host,'error':str(e)})
    seen_urls=set();seen_content={};seen_titles={};unique=[]
    for item in sorted(report['documents'],key=lambda x:(-len(x['content']),x['url'])):
        digest=sha256(item['content'].encode()).hexdigest()
        title_key=(item['publish_date'],re.sub(r'\W+','',item['title'].casefold()))
        if item['url'] in seen_urls or digest in seen_content or title_key in seen_titles:
            report['skipped'].append({'url':item['url'],'reason':'duplicate URL, exact body or same-day title','canonical':seen_content.get(digest) or seen_titles.get(title_key)})
            continue
        seen_urls.add(item['url']);seen_content[digest]=item['url'];seen_titles[title_key]=item['url'];unique.append(item)
    unique.sort(key=lambda x:(x['publish_date'],x['url']))
    report['documents']=unique
    report['groups']=dict(Counter(d['file'] for d in unique))
    for file,role in ROLES.items():
        selected=[d for d in unique if d['file']==file]
        front={'source_url':'https://ptit.edu.vn/','fetched_date':report['fetched_date'],'topic_group':role,
               'collection_year':2026,'article_count':len(selected),
               'note':'Tổng hợp bài đăng năm 2026. Mỗi bài có metadata nguồn riêng. Ngày đăng không chứng minh ngày có hiệu lực; file đính kèm chỉ giữ link, chưa trích nội dung.'}
        parts=['---',yaml.safe_dump(front,allow_unicode=True,sort_keys=False).strip(),'---','']
        for d in selected:
            meta={k:d[k] for k in ['publish_date','title']}
            meta.update(source_url=d['url'],fetched_date=report['fetched_date'],topic_group=role,
                        note=f"Đăng ngày {d['publish_date']}. Nguồn {d['host']}. Chưa xác minh văn bản thay thế; tệp/ảnh đính kèm chưa trích nội dung.")
            parts += ['<!-- source_metadata: '+json.dumps(meta,ensure_ascii=False)+' -->',
                      '# '+d['title'],'',f"Ngày đăng: {d['publish_date']}  \nNguồn: {d['url']}",'',d['content'],'']
        (stage/file).write_text('\n'.join(parts),encoding='utf-8')
    if args.apply:
        if not unique:raise RuntimeError('No collected posts; refusing to replace dataset')
        backup=ROOT/'BE/storage/data_backups'/NOW.strftime('%Y%m%d_%H%M%S')
        backup.mkdir(parents=True,exist_ok=False)
        for file in ROLES:
            target=ROOT/'data'/file
            (backup/file).write_bytes(target.read_bytes())
        report['backup']=str(backup)
        for file in ROLES:(ROOT/'data'/file).write_bytes((stage/file).read_bytes())
    for d in report['documents']:d.pop('content')
    report['dataset_sha256']={f:sha256((stage/f).read_bytes()).hexdigest() for f in ROLES}
    (ARCHIVE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'groups':report['groups'],'errors':report['errors'],'apply':args.apply},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
