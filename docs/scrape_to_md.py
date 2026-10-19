"""
scrape_to_md.py - Cào 1 trang web và lưu thành file .md có front-matter
để bỏ vào data/ cho RAG.

Cài đặt:
    pip install requests beautifulsoup4 markdownify

Dùng:
    python scrape_to_md.py --url https://ptit.edu.vn/... --topic ktx --out data/ktx.md
    python scrape_to_md.py --url https://... --topic thu_vien --out data/thu_vien.md --selector "div.entry-content"
    python scrape_to_md.py --batch sources.json
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as to_md

HEADERS = {"User-Agent": "Mozilla/5.0 (PTIT-Chatbot-Student-Project)"}

# Các thẻ thường là rác, không phải nội dung chính
NOISE_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe", "svg"]
NOISE_HINTS = re.compile(r"(menu|sidebar|breadcrumb|footer|header|share|social|comment|banner|popup|advert)", re.I)


def fetch_html(url: str, insecure: bool = False) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30, verify=not insecure)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding  # tránh lỗi font tiếng Việt
    return resp.text


def pick_main_node(soup: BeautifulSoup, selector: str | None):
    if selector:
        node = soup.select_one(selector)
        if node is None:
            sys.exit(f"Không tìm thấy phần tử khớp selector: {selector}")
        return node
    for candidate in ("article", "main", "[role=main]"):
        node = soup.select_one(candidate)
        if node and len(node.get_text(strip=True)) > 200:
            return node
    # Fallback: khối div có nhiều chữ nhất
    divs = soup.find_all("div")
    return max(divs, key=lambda d: len(d.get_text(strip=True)), default=soup.body or soup)


def clean_node(node) -> None:
    for tag in node.find_all(NOISE_TAGS):
        tag.decompose()
    for tag in node.find_all(True):
        hint = " ".join([tag.get("id", "")] + (tag.get("class") or []))
        if hint and NOISE_HINTS.search(hint):
            tag.decompose()


def html_to_markdown(html: str, selector: str | None):
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "").strip()
    node = pick_main_node(soup, selector)
    clean_node(node)
    text = to_md(str(node), heading_style="ATX")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title, text


def build_document(url: str, topic: str, title: str, body: str) -> str:
    safe_title = title.replace('"', "'")
    front = (
        "---\n"
        f"source_url: {url}\n"
        f"fetched_date: {date.today().isoformat()}\n"
        f"topic_group: {topic}\n"
        f'title: "{safe_title}"\n'
        "---\n\n"
    )
    return front + body + "\n"


def scrape_one(url: str, topic: str, out: str, selector: str | None = None, insecure: bool = False) -> None:
    html = fetch_html(url, insecure)
    title, body = html_to_markdown(html, selector)
    if len(body) < 200:
        print(f"[CẢNH BÁO] {url}: nội dung rất ngắn ({len(body)} ký tự). "
              "Có thể trang tải bằng JavaScript hoặc selector chưa đúng.")
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_document(url, topic, title, body), encoding="utf-8")
    print(f"[OK] {url} -> {out_path} ({len(body)} ký tự)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cào web sang markdown cho RAG")
    parser.add_argument("--url")
    parser.add_argument("--topic", help="topic_group, ví dụ: ktx, thu_vien, clb")
    parser.add_argument("--out", help="đường dẫn file .md, ví dụ data/ktx.md")
    parser.add_argument("--selector", help="CSS selector của vùng nội dung chính")
    parser.add_argument("--batch", help="file JSON chứa danh sách nguồn")
    parser.add_argument("--insecure", action="store_true", help="bỏ qua kiểm tra SSL")
    args = parser.parse_args()

    if args.batch:
        sources = json.loads(Path(args.batch).read_text(encoding="utf-8"))
        for s in sources:
            try:
                scrape_one(s["url"], s["topic"], s["out"], s.get("selector"), args.insecure)
            except Exception as exc:  # một trang lỗi không làm dừng cả batch
                print(f"[LỖI] {s.get('url')}: {exc}")
    elif args.url and args.topic and args.out:
        scrape_one(args.url, args.topic, args.out, args.selector, args.insecure)
    else:
        parser.error("Cần --batch, hoặc đủ cả --url, --topic và --out")


if __name__ == "__main__":
    main()