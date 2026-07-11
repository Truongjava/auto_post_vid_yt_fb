import os
import glob
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Quyền (Scope) để tải video lên YouTube
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive", "openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"]


def find_client_secret():
    """Tự động tìm file client_secret*.json trong thư mục hiện tại."""
    # Tìm tất cả file client_secret*.json
    matches = glob.glob("client_secret*.json")
    if matches:
        return matches[0]  # Lấy file đầu tiên
    raise FileNotFoundError(
        "Không tìm thấy file client_secret*.json. "
        "Hãy đặt file credentials vào thư mục hiện tại."
    )


def authenticate():
    creds = None
    # Kiểm tra xem đã có file token.json (lưu thông tin đăng nhập cũ) chưa
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # Nếu chưa có hoặc token đã hết hạn
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())  # Tự động làm mới token chạy ngầm
        else:
            # Lần chạy đầu tiên sẽ vào nhánh này: Mở trình duyệt để bạn chọn kênh
            flow = InstalledAppFlow.from_client_secrets_file(
                find_client_secret(),
                SCOPES,
            )
            creds = flow.run_local_server(port=0)

        # Lưu lại token cho những lần chạy sau
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return creds
