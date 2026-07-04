import os
import re
import io
import time
import requests
from auth import authenticate
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SHEET_ID = os.environ.get("SHEET_ID", "1nJUjjmUYWWdCsd0A3XTvRzUsLSEhEMeq7-KNVHfUsKw")
SHEET_RANGE = os.environ.get("SHEET_RANGE", "Trang tính1")
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "1g7bn3uCTDv41aW-RpH8zH33_y4THHW4d")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

VIDEO_MIME_TYPES = [
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/x-ms-wmv", "video/x-flv",
    "video/webm", "video/mpeg", "video/3gpp", "video/x-m4v",
]

CATEGORY_ID = os.environ.get("CATEGORY_ID", "24")          # Entertainment
PRIVACY_STATUS = os.environ.get("PRIVACY_STATUS", "private")  # private / public

# Facebook config
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN", "")
FB_GRAPH_VERSION = os.environ.get("FB_GRAPH_VERSION", "v25.0")
FB_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB mỗi phân đoạn


def get_credentials():
    if os.path.exists("token.json"):
        return Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        raise Exception("Không tìm thấy token.json. Hãy chạy auth.py trước!")


def get_sheet_data(service):
    """Đọc toàn bộ dữ liệu từ Google Sheet."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SHEET_ID, range=SHEET_RANGE)
        .execute()
    )
    values = result.get("values", [])
    return values  # [header, row1, row2, ...]


def find_first_not_started(rows):
    """Tìm dòng đầu tiên có cột PUBLIC (D) = 'not started'."""
    for i, row in enumerate(rows):
        if len(row) >= 4 and row[3].strip().lower() == "not started":
            return i  # Vị trí trong mảng rows (0-indexed, không tính header)
    return None


def find_video_on_drive(service, title):
    """Tìm video trên Drive có tên khớp với Title từ Sheet."""
    # Chuẩn hóa title để so sánh: bỏ hashtag, dấu câu
    search_title = re.sub(r"#\S+", "", title).strip()  # Bỏ hashtag
    search_title = re.sub(r"[^\w\s]", "", search_title).strip().lower()

    mime_conditions = " or ".join([f"mimeType='{m}'" for m in VIDEO_MIME_TYPES])
    query = f"'{DRIVE_FOLDER_ID}' in parents and ({mime_conditions}) and trashed=false"

    page_token = None
    while True:
        results = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name)",
                pageSize=100,
                pageToken=page_token,
            )
            .execute()
        )
        for f in results.get("files", []):
            file_name_norm = re.sub(r"#\S+", "", f["name"]).strip()
            file_name_norm = re.sub(r"[^\w\s]", "", file_name_norm).strip().lower()
            file_name_norm = file_name_norm.replace(".mp4", "").strip()

            # So khớp: title trong file hoặc ngược lại
            if search_title in file_name_norm or file_name_norm in search_title:
                return f

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    return None


def download_video(service, file_id, output_path):
    """Tải video từ Google Drive về máy."""
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(output_path, "wb")
    downloader = MediaIoBaseDownload(fh, request)

    print(f"  Đang tải video từ Drive...")
    done = False
    while not done:
        status, done = downloader.next_chunk()
        print(f"  Tiến độ: {int(status.progress() * 100)}%")

    print(f"  Đã tải xong: {output_path}")
    return output_path


def extract_tags(title):
    """Tách hashtag từ Title thành list tags."""
    tags = re.findall(r"#(\w+)", title)
    return tags if tags else ["biann"]


def clean_title(title):
    """Làm sạch Title: bỏ hashtag để upload (YouTube không thích hashtag trong title upload)."""
    return title  # Giữ nguyên hashtag vì đó là một phần của tiêu đề Shorts


def upload_to_youtube(youtube, video_path, title, description, tags):
    """Upload video lên YouTube."""
    request_body = {
        "snippet": {
            "title": title[:100],  # YouTube giới hạn 100 ký tự
            "description": description[:5000],
            "tags": tags,
            "categoryId": CATEGORY_ID,
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

    print(f"  Đang upload lên YouTube...")
    print(f"  Tiêu đề: {title[:80]}...")
    print(f"  Tags: {tags}")
    print(f"  Chế độ: {PRIVACY_STATUS}")

    request = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media,
    )

    response = request.execute()
    video_id = response["id"]
    print(f"  ✅ Upload thành công!")
    print(f"  🔗 Link: https://youtu.be/{video_id}")
    return video_id


def upload_to_facebook(video_path, title, description):
    """Upload video lên Facebook Page qua Graph API (resumable upload 3 pha).
    Trả về (success: bool, video_id: str | None)"""
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        print("  ⚠️  Bỏ qua Facebook: thiếu FB_PAGE_ID hoặc FB_ACCESS_TOKEN")
        return False, None

    graph_url = f"https://graph.facebook.com/{FB_GRAPH_VERSION}/{FB_PAGE_ID}/videos"
    file_size = os.path.getsize(video_path)

    print(f"  🎬 Facebook: Bắt đầu upload ({file_size / (1024*1024):.2f} MB)")

    try:
        # --- Phase 1: Khởi tạo phiên upload ---
        print("  [FB Phase 1] Khởi tạo phiên...")
        start_payload = {
            "access_token": FB_ACCESS_TOKEN,
            "upload_phase": "start",
            "file_size": file_size,
        }
        start_res = requests.post(graph_url, data=start_payload).json()

        if "upload_session_id" not in start_res:
            print(f"  ❌ Facebook khởi tạo thất bại: {start_res}")
            return False, None

        session_id = start_res["upload_session_id"]
        start_offset = int(start_res.get("start_offset", 0))
        print(f"  ✅ Session ID: {session_id}")

        # --- Phase 2: Upload từng phân đoạn ---
        print("  [FB Phase 2] Upload phân đoạn...")
        with open(video_path, "rb") as f:
            chunk_index = 1
            while start_offset < file_size:
                f.seek(start_offset)
                chunk_data = f.read(FB_CHUNK_SIZE)

                transfer_payload = {
                    "access_token": FB_ACCESS_TOKEN,
                    "upload_phase": "transfer",
                    "upload_session_id": session_id,
                    "start_offset": start_offset,
                }
                transfer_res = requests.post(
                    graph_url, data=transfer_payload,
                    files={"video_file_chunk": chunk_data}
                ).json()

                if "error" in transfer_res:
                    print(f"  ❌ Lỗi phân đoạn {chunk_index}: {transfer_res}")
                    return False, None

                start_offset = int(transfer_res["start_offset"])
                progress = (start_offset / file_size) * 100
                print(f"  📦 Phân đoạn {chunk_index}: {progress:.1f}%")
                chunk_index += 1

        # --- Phase 3: Hoàn tất & xuất bản ---
        print("  [FB Phase 3] Hoàn tất & xuất bản...")
        finish_payload = {
            "access_token": FB_ACCESS_TOKEN,
            "upload_phase": "finish",
            "upload_session_id": session_id,
            "title": title,
            "description": description,
            "video_state": "PUBLISHED",
        }
        finish_res = requests.post(graph_url, data=finish_payload).json()

        if finish_res.get("success") or "video_id" in finish_res:
            fb_video_id = finish_res.get("video_id", "đang xử lý")
            print(f"  ✅ Facebook upload thành công! Video ID: {fb_video_id}")
            return True, fb_video_id
        else:
            print(f"  ❌ Facebook hoàn tất thất bại: {finish_res}")
            return False, None

    except Exception as e:
        print(f"  ❌ Facebook upload lỗi: {e}")
        return False, None


def update_sheet_status(service, row_index, new_status="done"):
    """Cập nhật cột PUBLIC của dòng thành 'done'."""
    # row_index là vị trí 0-indexed trong toàn bộ values (bao gồm header)
    # Trong Sheet API, dòng bắt đầu từ 1
    sheet_row = row_index + 1  # Chuyển sang 1-indexed
    range_to_update = f"{SHEET_RANGE}!D{sheet_row}"

    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=range_to_update,
        valueInputOption="USER_ENTERED",
        body={"values": [[new_status]]},
    ).execute()
    print(f"  ✅ Đã cập nhật Sheet: dòng {sheet_row} → '{new_status}'")


def main():
    creds = get_credentials()
    sheet_service = build("sheets", "v4", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)
    youtube = build("youtube", "v3", credentials=creds)

    # 1. Đọc Google Sheet
    print("=" * 60)
    print("📋 Đọc Google Sheet...")
    data = get_sheet_data(sheet_service)
    header = data[0]
    rows = data[1:]  # Bỏ header

    # 2. Tìm dòng đầu tiên có PUBLIC = 'not started'
    idx = find_first_not_started(rows)
    if idx is None:
        print("✅ Tất cả video đã được upload! Không còn dòng 'not started' nào.")
        return

    row = rows[idx]
    topic = row[0] if len(row) > 0 else ""
    title = row[1] if len(row) > 1 else ""
    description = row[2] if len(row) > 2 else ""

    print(f"📌 Tìm thấy dòng cần upload:")
    print(f"   TOPIC: {topic[:100]}...")
    print(f"   Title: {title}")
    print(f"   Description: {description[:80]}...")
    print()

    # 3. Tìm video tương ứng trên Drive
    print("🔍 Tìm video trên Google Drive...")
    video = find_video_on_drive(drive_service, title)
    if video is None:
        print(f"❌ Không tìm thấy video trên Drive khớp với: {title[:60]}...")
        return

    print(f"   Tìm thấy: {video['name']} (ID: {video['id']})")
    print()

    # 4. Tải video từ Drive về máy
    print("⬇️  Tải video từ Drive...")
    local_path = download_video(drive_service, video["id"], video["name"])
    print()

    # 5. Upload lên YouTube
    print("⬆️  Upload lên YouTube...")
    tags = extract_tags(title)
    video_id = upload_to_youtube(youtube, local_path, title, description, tags)
    print()

    # 6. Upload lên Facebook
    print("📘 Upload lên Facebook...")
    fb_ok, fb_video_id = upload_to_facebook(local_path, title, description)
    print()

    # 7. Cập nhật Sheet: not started → done
    print("📝 Cập nhật Google Sheet...")
    # idx là vị trí trong rows (0-indexed), cần +1 cho header
    update_sheet_status(sheet_service, idx + 1)

    # 8. Dọn dẹp: xóa file video đã tải về
    if os.path.exists(local_path):
        os.remove(local_path)
        print(f"  🗑️  Đã xóa file tạm: {local_path}")

    print()
    print("=" * 60)
    print("🎉 Hoàn thành!")
    print(f"   Video: {title[:60]}...")
    print(f"   YouTube: https://youtu.be/{video_id}")
    if fb_ok:
        print(f"   Facebook: Video ID {fb_video_id}")
    else:
        print(f"   Facebook: ⚠️  Không upload được (xem log lỗi phía trên)")
    print(f"   Sheet: dòng {idx + 2} → done")


if __name__ == "__main__":
    main()
