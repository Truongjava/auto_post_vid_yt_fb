import os
import json
import random
import time
import datetime
import subprocess
import threading
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
scheduler = BackgroundScheduler(timezone="UTC")

# Auth key bảo vệ endpoint manual trigger
AUTH_KEY = os.environ.get("AUTH_KEY", "biann2024")

# Biến trạng thái pipeline
pipeline_status = {
    "running": False,
    "last_run": None,
    "last_result": None,
    "last_error": None,
}


def delayed_run(window_name, delay_minutes_max):
    """Ngủ random trong khoảng thời gian cho phép, rồi mới chạy pipeline.
    Giúp tránh YouTube phát hiện đăng tự động theo giờ cố định."""
    delay_seconds = random.randint(0, delay_minutes_max * 60)
    print(f"⏳ [{window_name}] Đợi {delay_seconds // 60} phút {delay_seconds % 60} giây rồi chạy...")
    time.sleep(delay_seconds)
    run_pipeline()


def write_secrets():
    """Ghi secrets từ env vars ra file (giống GitHub Actions)."""
    client_secret = os.environ.get("CLIENT_SECRET_JSON", "")
    token = os.environ.get("TOKEN_JSON", "")

    if client_secret:
        with open("client_secret.json", "w") as f:
            f.write(client_secret)
        print("✅ Đã tạo client_secret.json")

    if token:
        with open("token.json", "w") as f:
            f.write(token)
        print("✅ Đã tạo token.json")


def run_pipeline():
    """Chạy pipeline trong subprocess riêng — khi kết thúc, OS thu hồi TOÀN BỘ RAM."""
    global pipeline_status
    if pipeline_status["running"]:
        print("⚠️ Pipeline đang chạy, bỏ qua lần này")
        return

    pipeline_status["running"] = True
    pipeline_status["last_run"] = datetime.datetime.now().isoformat()
    pipeline_status["last_error"] = None

    try:
        # Chạy trong process riêng → RAM được OS thu hồi triệt để khi xong
        result = subprocess.run(
            ["python", "pipeline.py"],
            capture_output=True,
            text=True,
            timeout=1800,  # 30 phút timeout
        )
        print(result.stdout)
        if result.stderr:
            print("[STDERR]", result.stderr)

        if result.returncode == 0:
            pipeline_status["last_result"] = "success"
            print(f"[{datetime.datetime.now()}] ✅ Pipeline hoàn thành")
        else:
            pipeline_status["last_result"] = "failed"
            pipeline_status["last_error"] = result.stderr or f"Exit code: {result.returncode}"
            print(f"[{datetime.datetime.now()}] ❌ Pipeline lỗi (exit {result.returncode})")
    except subprocess.TimeoutExpired:
        pipeline_status["last_result"] = "failed"
        pipeline_status["last_error"] = "Timeout sau 30 phút"
        print(f"[{datetime.datetime.now()}] ❌ Pipeline timeout")
    except Exception as e:
        pipeline_status["last_result"] = "failed"
        pipeline_status["last_error"] = str(e)
        print(f"[{datetime.datetime.now()}] ❌ Pipeline lỗi: {e}")
    finally:
        pipeline_status["running"] = False


# ==========================================
# ROUTES
# ==========================================

@app.route("/")
def health():
    """Health check cho UptimeRobot."""
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "next_run": next_run.isoformat() if next_run else None,
        })

    return jsonify({
        "status": "running",
        "timestamp": datetime.datetime.now().isoformat(),
        "pipeline": {
            "running": pipeline_status["running"],
            "last_run": pipeline_status["last_run"],
            "last_result": pipeline_status["last_result"],
            "last_error": pipeline_status["last_error"],
        },
        "scheduled_jobs": jobs,
    })


@app.route("/run")
def trigger():
    """Manual trigger pipeline (cần auth key)."""
    key = request.args.get("key", "")
    if key != AUTH_KEY:
        return jsonify({"error": "unauthorized", "hint": "thêm ?key=AUTH_KEY vào URL"}), 401

    if pipeline_status["running"]:
        return jsonify({"status": "already_running", "since": pipeline_status["last_run"]}), 409

    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()
    return jsonify({"status": "pipeline_started", "timestamp": datetime.datetime.now().isoformat()})


@app.route("/status")
def status():
    """Xem trạng thái pipeline."""
    return jsonify(pipeline_status)


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":
    print("=" * 50)
    print("  Auto Upload Pipeline - Web Service")
    print(f"  Started: {datetime.datetime.now()}")
    print("=" * 50)

    # Ghi secrets ra file
    write_secrets()

    # Setup scheduler với thời gian random trong khung giờ
    # Tránh YouTube phát hiện đăng tự động theo giờ cố định
    #
    # Chiến lược: Đăng đúng 2 khung giờ vàng nhiều view nhất của Mỹ
    #
    # 🥪 US Lunch    (12-1:30 PM EDT = 23:00-00:30 VN)
    #    Cron 16:00 UTC + random 0-90 phút
    # 🔥 US Prime    (7-10 PM EDT = 6:00-9:00 AM VN hôm sau)
    #    Cron 23:00 UTC + random 0-120 phút
    scheduler.add_job(
        lambda: threading.Thread(
            target=delayed_run, args=("🥪 Đêm 23:00-00:30 VN (US Lunch)", 90), daemon=True
        ).start(),
        "cron",
        hour=16,
        minute=0,
        id="us_lunch_window",
    )
    scheduler.add_job(
        lambda: threading.Thread(
            target=delayed_run, args=("🔥 Sáng 6:00-8:00 AM VN (US Prime Time)", 120), daemon=True
        ).start(),
        "cron",
        hour=23,
        minute=0,
        id="us_prime_window",
    )
    scheduler.start()
    print("⏰ Scheduler đã khởi động (2 khung giờ vàng Mỹ):")
    print("   🥪 Đêm  23:00-00:30 VN → US Lunch 12-1:30PM EDT")
    print("   🔥 Sáng 6:00-8:00 AM VN → US Prime 7-10PM EDT")

    # Start Flask server
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
