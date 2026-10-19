pip install requests beautifulsoup4 markdownify

# Cào 1 trang
python scrape_to_md.py --url https://ptit.edu.vn/... --topic ktx --out data/ktx.md

# Trang có nhiều rác, chỉ định vùng nội dung bằng CSS selector (xem bằng F12)
python scrape_to_md.py --url https://... --topic thu_vien --out data/thu_vien.md --selector "div.entry-content"

# Cào nhiều trang cùng lúc từ file sources.json
python scrape_to_md.py --batch sources.json

[
  {"url": "https://ptit.edu.vn/...", "topic": "ktx", "out": "data/ktx.md"},
  {"url": "https://lib.ptit.edu.vn/...", "topic": "thu_vien", "out": "data/thu_vien.md", "selector": "div.content"}
]