"""
SCADA Server CLI Management Tool
METAL SORTING SCADA - 24/7 AUTOMATIC OPERATION
Provides commands: start, stop, restart, status, install, uninstall, url
"""

import os
import sys
import time
import json
import socket
import urllib.request
import subprocess

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
DAEMON_SCRIPT = os.path.join(BASE_DIR, "scada_daemon.py")
STATUS_FILE = os.path.join(BASE_DIR, "server_status.json")
PID_FILE = os.path.join(BASE_DIR, "server.pid")
STOP_SIGNAL = os.path.join(BASE_DIR, "stop.signal")
SERVER_LOG = os.path.join(BASE_DIR, "logs", "server.log")

PYTHON_EXE = sys.executable
PYTHONW_EXE = os.path.join(os.path.dirname(PYTHON_EXE), "pythonw.exe")
if not os.path.exists(PYTHONW_EXE):
    PYTHONW_EXE = PYTHON_EXE

TASK_NAME = "MetalSortingSCADA_AutoServer"
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
DAEMON_FLAGS = DETACHED_PROCESS | CREATE_NO_WINDOW

def is_pid_running(pid):
    if not pid or pid <= 0:
        return False
    try:
        out = subprocess.check_output(f'tasklist /FI "PID eq {pid}" /NH', shell=True).decode('utf-8', errors='ignore')
        return str(pid) in out
    except Exception:
        return False

def get_status_data():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def start_server():
    print("==========================================================")
    print("   METAL SORTING SCADA - KHỞI ĐỘNG HỆ THỐNG SERVER 24/7   ")
    print("==========================================================")
    
    # Check if already running
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            if is_pid_running(pid):
                print(f"[THÔNG BÁO] Server SCADA đang chạy ngầm (Daemon PID: {pid})!")
                show_quick_urls()
                return True
        except Exception:
            pass

    # Clean any stale stop signal
    if os.path.exists(STOP_SIGNAL):
        try: os.remove(STOP_SIGNAL)
        except Exception: pass

    print("[1/3] Đang khởi chạy tiến trình giám sát ngầm (scada_daemon.py)...")
    vbs_path = os.path.join(BASE_DIR, "launch_silent.vbs")
    subprocess.run(["wscript.exe", vbs_path], check=True)

    print("[2/3] Đang khởi động Backend Node-RED (Port 1880)...")
    print("[3/3] Đang khởi tạo đường hầm ngrok online...")
    
    # Wait for status to show running (up to 15s)
    started = False
    for i in range(15):
        time.sleep(1)
        data = get_status_data()
        if data and data.get("status") == "RUNNING" and data.get("backend_http_ready"):
            started = True
            break
        print(".", end="", flush=True)
    print()

    data = get_status_data()
    if started and data:
        print("\n>>> KHỞI ĐỘNG SERVER THÀNH CÔNG RỰC RỠ! <<<")
        print(f"  • Trạng thái hệ thống:    ĐANG HOẠT ĐỘNG (RUNNING)")
        print(f"  • Tiến trình Daemon:      PID {data.get('daemon_pid')}")
        print(f"  • Node-RED Backend:       PID {data.get('backend_pid')} (Port {data.get('backend_port')})")
        print(f"  • ngrok Tunnel:           PID {data.get('ngrok_pid')}")
        print("----------------------------------------------------------")
        print(f"  🌐 TRUY CẬP NỘI BỘ (LAN):  {data.get('backend_local_url')}")
        print(f"  🌍 TRUY CẬP INTERNET:      {data.get('public_ui_url')}")
        print("----------------------------------------------------------")
        print("[LƯU Ý] Hệ thống đang chạy nền 24/7. Bạn có thể đóng cửa sổ này.")
        return True
    else:
        print("\n[CẢNH BÁO] Server đang trong quá trình khởi tạo hoặc cần thêm thời gian.")
        print("Vui lòng chạy file CHECK_SERVER.bat sau vài giây để kiểm tra lại.")
        return False

def stop_server():
    print("==========================================================")
    print("      METAL SORTING SCADA - DỪNG HỆ THỐNG SERVER          ")
    print("==========================================================")

    data = get_status_data()
    daemon_pid = data.get("daemon_pid") if data else None

    # Write stop signal
    with open(STOP_SIGNAL, "w", encoding="utf-8") as f:
        f.write("STOP")

    print("[1/2] Đã gửi tín hiệu dừng an toàn tới Daemon Supervisor...")
    stopped = False
    for i in range(8):
        time.sleep(1)
        if not os.path.exists(PID_FILE) or (daemon_pid and not is_pid_running(daemon_pid)):
            stopped = True
            break
        print(".", end="", flush=True)
    print()

    # Force cleanup any lingering processes if necessary
    print("[2/2] Kiểm tra và giải phóng cổng kết nối & COM4 serial...")
    try:
        out = subprocess.check_output("netstat -ano", shell=True).decode('utf-8', errors='ignore')
        pids = set()
        for line in out.splitlines():
            if ":1880 " in line:
                parts = line.strip().split()
                if len(parts) >= 5 and parts[-1].isdigit():
                    pids.add(int(parts[-1]))
        for pid in pids:
            if pid > 0:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass

    # Kill ngrok if lingering
    subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)

    if os.path.exists(PID_FILE):
        try: os.remove(PID_FILE)
        except Exception: pass
    if os.path.exists(STOP_SIGNAL):
        try: os.remove(STOP_SIGNAL)
        except Exception: pass

    # Update status file
    if data:
        data["status"] = "STOPPED"
        data["daemon_pid"] = None
        data["backend_pid"] = None
        data["ngrok_pid"] = None
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception: pass

    print("\n>>> ĐÃ DỪNG TOÀN BỘ SERVER SCADA AN TOÀN! <<<")
    print("Toàn bộ dữ liệu sản xuất, lịch sử ca và flows.json được bảo toàn nguyên vẹn.")
    return True

def restart_server():
    print("Đang khởi động lại hệ thống SCADA Server...")
    stop_server()
    time.sleep(2)
    start_server()

def check_status():
    print("==========================================================")
    print("      METAL SORTING SCADA - TRẠNG THÁI HỆ THỐNG 24/7     ")
    print("==========================================================")

    data = get_status_data()
    daemon_pid = data.get("daemon_pid") if data else None
    daemon_running = is_pid_running(daemon_pid) if daemon_pid else False

    status_str = "RUNNING [ONLINE]" if (daemon_running and data and data.get("status") == "RUNNING") else "STOPPED [OFFLINE]"
    
    print(f"  • Trạng thái tổng thể:    {status_str}")
    if data:
        backend_alive = data.get("backend_alive") and is_pid_running(data.get("backend_pid"))
        ngrok_alive = data.get("ngrok_alive") and is_pid_running(data.get("ngrok_pid"))
        
        b_icon = "🟢 ONLINE" if backend_alive else "🔴 OFFLINE"
        n_icon = "🟢 ONLINE" if ngrok_alive else "🔴 OFFLINE"
        
        print(f"  • Daemon Supervisor:      PID {data.get('daemon_pid')} {'(HOẠT ĐỘNG)' if daemon_running else '(DỪNG)'}")
        print(f"  • Node-RED Backend:       PID {data.get('backend_pid')} | Port {data.get('backend_port')} -> {b_icon}")
        print(f"  • ngrok Cloud Tunnel:     PID {data.get('ngrok_pid')} -> {n_icon}")
        print(f"  • Thời gian chạy (Uptime): {data.get('uptime_seconds', 0)} giây")
        print(f"  • Số lần tự phục hồi:     Backend: {data.get('backend_restarts', 0)} | ngrok: {data.get('ngrok_restarts', 0)}")
        print("----------------------------------------------------------")
        print(f"  🌐 ĐỊA CHỈ NỘI BỘ (MÁY CHỦ): {data.get('backend_local_url')}")
        print(f"  🌍 ĐƯỜNG DẪN TRUY CẬP TỪ XA: {data.get('public_ui_url')}")
        print("----------------------------------------------------------")
    else:
        print("  • Chưa có dữ liệu trạng thái (Server chưa từng khởi động).")
        print("----------------------------------------------------------")

    # Print recent log lines
    if os.path.exists(SERVER_LOG):
        print("\n--- 8 DÒNG NHẬT KÝ HOẠT ĐỘNG GẦN NHẤT (server.log) ---")
        try:
            with open(SERVER_LOG, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for l in lines[-8:]:
                    print("  " + l.strip())
        except Exception:
            pass
    print("==========================================================")

def show_quick_urls():
    data = get_status_data()
    if data:
        print("----------------------------------------------------------")
        print(f"  🌐 LAN:      {data.get('backend_local_url')}")
        print(f"  🌍 INTERNET: {data.get('public_ui_url')}")
        print("----------------------------------------------------------")

def install_autostart():
    print("==========================================================")
    print("   CÀI ĐẶT TỰ ĐỘNG KHỞI ĐỘNG CÙNG WINDOWS (24/7 AUTOSTART)")
    print("==========================================================")

    # 1. Configure Windows Power to never sleep on AC
    print("\n[Bước 1/3] Cấu hình chế độ nguồn điện Windows (Không Sleep khi cắm sạc)...")
    try:
        subprocess.run(["powercfg", "/change", "standby-timeout-ac", "0"], check=True, creationflags=CREATE_NO_WINDOW)
        subprocess.run(["powercfg", "/change", "hibernate-timeout-ac", "0"], check=True, creationflags=CREATE_NO_WINDOW)
        # Display turns off after 10 min to save display panel
        subprocess.run(["powercfg", "/change", "monitor-timeout-ac", "10"], check=True, creationflags=CREATE_NO_WINDOW)
        print("  ✓ Đã thiết lập: Máy tính không bao giờ Sleep/Hibernate khi cắm sạc.")
        print("  ✓ Đã thiết lập: Màn hình tự tắt sau 10 phút để tiết kiệm điện (Server vẫn chạy ngầm).")
    except Exception as e:
        print(f"  ⚠ Lưu ý về nguồn điện: {e}")

    # 2. Register Windows Autostart via Windows Startup Folder
    print("\n[Bước 2/3] Thiết lập cơ chế tự khởi động cùng Windows (User-Level, không cần quyền Admin)...")
    startup_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
    if os.path.exists(startup_dir):
        vbs_launcher = os.path.join(startup_dir, "Start_SCADA_Server_Silent.vbs")
        try:
            with open(vbs_launcher, "w", encoding="utf-8") as f:
                f.write(f'Set WshShell = CreateObject("WScript.Shell")\n')
                f.write(f'WshShell.Run """{PYTHONW_EXE}"" ""{DAEMON_SCRIPT}""", 0, False\n')
            print(f"  ✓ Đã thiết lập launcher chạy ngầm tại thư mục Startup: Start_SCADA_Server_Silent.vbs")
            print("  ✓ Cơ chế hoạt động: Khi Windows khởi động, tiến trình Supervisor sẽ tự động chạy ngầm (Zero-window).")
        except Exception as e:
            print(f"  ⚠ Lỗi khi tạo file Startup: {e}")

    print("\n[Bước 3/3] Khởi động Server ngay lập tức để kiểm tra...")
    start_server()
    print("\n==========================================================")
    print(">>> HOÀN TẤT CÀI ĐẶT TỰ ĐỘNG KHỞI ĐỘNG SERVER 24/7! <<<")
    print("Kể từ bây giờ, mỗi khi máy tính bật nguồn hoặc khởi động lại,")
    print("Backend SCADA và ngrok sẽ TỰ ĐỘNG CHẠY NGẦM.")
    print("==========================================================")

def uninstall_autostart():
    print("==========================================================")
    print("   GỠ BỎ TỰ ĐỘNG KHỞI ĐỘNG CÙNG WINDOWS                  ")
    print("==========================================================")
    
    stop_server()

    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, "MetalSortingSCADA_AutoServer")
        winreg.CloseKey(key)
        print("  ✓ Đã xóa đăng ký tự khởi động tại Windows Registry.")
    except Exception:
        pass

    startup_vbs = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Start_SCADA_Server_Silent.vbs")
    if os.path.exists(startup_vbs):
        try:
            os.remove(startup_vbs)
            print("  ✓ Đã xóa shortcut dự phòng trong Startup folder.")
        except Exception:
            pass

    print(">>> ĐÃ GỠ BỎ TỰ ĐỘNG KHỞI ĐỘNG THÀNH CÔNG! <<<")

if __name__ == "__main__":
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "status"

    if action == "start":
        start_server()
    elif action == "stop":
        stop_server()
    elif action == "restart":
        restart_server()
    elif action == "status":
        check_status()
    elif action == "install":
        install_autostart()
    elif action == "uninstall":
        uninstall_autostart()
    elif action == "url":
        data = get_status_data()
        if data and data.get("public_ui_url"):
            print(data.get("public_ui_url"))
        else:
            print(f"https://{NGROK_DOMAIN}/ui/")
    else:
        print("Lệnh không hợp lệ. Các lệnh hỗ trợ: start, stop, restart, status, install, uninstall, url")
