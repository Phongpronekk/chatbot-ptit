"""CLI script to synchronize source documents into MongoDB Atlas.

Usage:
    python -m BE.scripts.sync_mongo
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / "BE/.env", override=True, encoding="utf-8-sig")

from BE.mongo_store import (
    is_mongo_configured,
    get_mongo_uri,
    get_mongo_db_name,
    get_mongo_collection_name,
    sync_source_documents,
    check_mongo_connection,
)


def main():
    print("=" * 60)
    print("PTIT Chatbot - Đồng bộ tài liệu nguồn lên MongoDB Atlas")
    print("=" * 60)

    if not is_mongo_configured():
        print("LỖI: Chưa cấu hình MONGODB_URI trong file BE/.env.")
        print("Vui lòng mở file BE/.env và điền connection string MongoDB Atlas:")
        print("MONGODB_URI=mongodb+srv://<username>:<password>@cluster.mongodb.net")
        sys.exit(1)

    print(f"Database:   {get_mongo_db_name()}")
    print(f"Collection: {get_mongo_collection_name()}")
    print("Đang kiểm tra kết nối MongoDB Atlas...")

    status = check_mongo_connection()
    if not status.get("connected"):
        print(f"LỖI: Không kết nối được MongoDB Atlas: {status.get('error')}")
        sys.exit(1)

    print("Kết nối thành công! Đang đọc và đồng bộ các file trong data/ ...")
    result = sync_source_documents()

    if result.get("success"):
        print(f"Đã đồng bộ thành công {result['synced_count']} file nguồn ({result['total_bytes']:,} bytes):")
        for item in result["files"]:
            print(f"  - {item['filename']} ({item['topic_group']}): {item['article_count']} bài viết, {item['size_bytes']:,} bytes")
        print("\nHoàn tất! Các bản dữ liệu nguồn đã được lưu trữ an toàn trên MongoDB Atlas.")
    else:
        print(f"Thất bại: {result.get('message')}")
        sys.exit(1)


if __name__ == "__main__":
    main()

