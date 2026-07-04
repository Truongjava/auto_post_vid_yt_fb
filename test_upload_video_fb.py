import requests
import os
import time

# ==========================================
# CẤU HÌNH THÔNG TIN CỦA BẠN TẠI ĐÂY
# ==========================================
PAGE_ID = '1136619726201474'
ACCESS_TOKEN = 'EAAOrOzEi4vkBRywSWysOi9TlLtdZANWBA8fdkRNIfMuXUoSeSL8lDZBmsieBPV5d9SbjYoesXQFALOgIed7Pl5GHP0JYZAbuPVP5wdSdbTTetCZCecHHzZCO3qZAmoOfQwaZCWZB8qd6AarE6LN08KAS9irHTJMOkmstRZB8u24uZADtWahr9nciytchoAVG1mJUU6FNCt'
VIDEO_PATH = 'Luật Bất Thành Văn Khi Thuê Phòng Khách Sạn Tại Đà Lạt 🏨 #shorts #dalat #biann.mp4'
VIDEO_TITLE = 'Video Thử Nghiệm Hệ Thống'
VIDEO_DESC = 'Đây là video được đăng tự động bằng Meta Graph API #automation #bot'

# Facebook Graph API Endpoint cho Video
GRAPH_VERSION = 'v25.0'  # Sử dụng phiên bản trùng với giao diện của bạn
GRAPH_URL = f'https://graph.facebook.com/{GRAPH_VERSION}/{PAGE_ID}/videos'
CHUNK_SIZE = 4 * 1024 * 1024  # Cắt nhỏ video thành mỗi phân đoạn 4MB

def test_auto_upload():
    if not os.path.exists(VIDEO_PATH):
        print(f"❌ Lỗi: Không tìm thấy file video tại đường dẫn: {VIDEO_PATH}")
        return

    file_size = os.path.getsize(VIDEO_PATH)
    print(f"🎬 Bắt đầu tiến trình upload file: {VIDEO_PATH} ({file_size / (1024*1024):.2f} MB)")

    # ---------------------------------------------------------
    # GIAI ĐOẠN 1: KHỞI TẠO PHIÊN UPLOAD (PHASE START)
    # ---------------------------------------------------------
    print("\n[Phase 1] Đang khởi tạo phiên làm việc với Facebook...")
    start_payload = {
        'access_token': ACCESS_TOKEN,
        'upload_phase': 'start',
        'file_size': file_size
    }
    
    try:
        response = requests.post(GRAPH_URL, data=start_payload)
        start_res = response.json()
    except Exception as e:
        print(f"❌ Không thể kết nối tới API: {e}")
        return

    if 'upload_session_id' not in start_res:
        print(f"❌ Khởi tạo thất bại. Phản hồi từ Facebook: {start_res}")
        return
        
    session_id = start_res['upload_session_id']
    end_offset = int(start_res.get('end_offset', 0))
    start_offset = int(start_res.get('start_offset', 0))
    print(f"✅ Khởi tạo thành công! Session ID: {session_id}")

    # ---------------------------------------------------------
    # GIAI ĐOẠN 2: TRUYỀN DỮ LIỆU PHÂN ĐOẠN (PHASE TRANSFER)
    # ---------------------------------------------------------
    print("\n[Phase 2] Bắt đầu cắt nhỏ và tải các phân đoạn video lên...")
    
    with open(VIDEO_PATH, 'rb') as f:
        chunk_index = 1
        while start_offset < file_size:
            # Đọc một đoạn dữ liệu từ vị trí start_offset hiện tại
            f.seek(start_offset)
            chunk_data = f.read(CHUNK_SIZE)
            
            print(f" 📦 Đang tải phân đoạn {chunk_index} (Vị trí dữ liệu: {start_offset} -> {start_offset + len(chunk_data)} bytes)...")
            
            transfer_payload = {
                'access_token': ACCESS_TOKEN,
                'upload_phase': 'transfer',
                'upload_session_id': session_id,
                'start_offset': start_offset
            }
            files = {'video_file_chunk': chunk_data}
            
            try:
                transfer_res = requests.post(GRAPH_URL, data=transfer_payload, files=files).json()
                if 'error' in transfer_res:
                    print(f"❌ Lỗi khi tải phân đoạn {chunk_index}: {transfer_res}")
                    return
                
                # Cập nhật vị trí con trỏ dữ liệu mới từ phản hồi của Facebook
                start_offset = int(transfer_res['start_offset'])
                end_offset = int(transfer_res['end_offset'])
                chunk_index += 1
                
                # Tính toán tiến trình (%)
                progress = (start_offset / file_size) * 100
                print(f"    ↳ Facebook đã nhận. Tiến độ tổng thể: {progress:.1f}%")
                
            except Exception as e:
                print(f"❌ Lỗi kết nối mạng ở phân đoạn {chunk_index}: {e}. Đang thử lại sau giây lát...")
                time.sleep(2)
                continue

    # ---------------------------------------------------------
    # GIAI ĐOẠN 3: HOÀN TẤT & XUẤT BẢN (PHASE FINISH)
    # ---------------------------------------------------------
    print("\n[Phase 3] Tất cả phân đoạn đã tải xong. Yêu cầu Facebook xử lý và xuất bản...")
    finish_payload = {
        'access_token': ACCESS_TOKEN,
        'upload_phase': 'finish',
        'upload_session_id': session_id,
        'title': VIDEO_TITLE,
        'description': VIDEO_DESC,
        'video_state': 'PUBLISHED'  # Video sẽ hiển thị công khai ngay lập tức
    }
    
    finish_res = requests.post(GRAPH_URL, data=finish_payload).json()
    
    if finish_res.get('success') or 'video_id' in finish_res:
        video_id = finish_res.get('video_id', 'N/A')
        print(f"\n🎉 THÀNH CÔNG RỰC RỠ!")
        print(f"🚀 Video đã được gửi lên Fanpage xử lý thành công.")
        print(f"🆔 ID Video trên Facebook: {video_id}")
        print(f"🔗 Bạn có thể kiểm tra Studio sáng tạo hoặc Nhật ký hoạt động của trang để xem video.")
    else:
        print(f"❌ Lỗi ở giai đoạn hoàn tất: {finish_res}")

if __name__ == '__main__':
    test_auto_upload()