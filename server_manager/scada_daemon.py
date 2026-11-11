"""
SCADA Server Supervisor & Watchdog Daemon
METAL SORTING SCADA - 24/7 AUTOMATIC OPERATION
Monitors Node-RED Backend (port 1880) and ngrok tunnel
Provides auto-restart, health-checking, logging, and state synchronization.
"""

import os
import sys
import time
import json
import signal
import socket
import urllib.request
import urllib.error
import subprocess
from datetime import datetime

# Configure UTF-8 encoding safely (sys.stdout is None when running under pythonw.exe)
if sys.stdout is not None:
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

if sys.stderr is not None:
    try: sys.stderr.reconfigure(encoding='utf-8')
    except Exception: pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

SERVER_LOG = os.path.join(LOG_DIR, "server.log")
BACKEND_LOG = os.path.join(LOG_DIR, "backend.log")
NGROK_LOG = os.path.join(LOG_DIR, "ngrok.log")
STATUS_FILE = os.path.join(BASE_DIR, "server_status.json")
PID_FILE = os.path.join(BASE_DIR, "server.pid")
STOP_SIGNAL = os.path.join(BASE_DIR, "stop.signal")

NODE_EXE = r"C:\Program Files\nodejs\node.exe"
RED_JS = os.path.expandvars(r"%APPDATA%\npm\node_modules\node-red\red.js")
USER_DIR = os.path.expandvars(r"%USERPROFILE%\.node-red")
NGROK_EXE = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ngrok.exe")
if not os.path.exists(NGROK_EXE):
    import shutil
    NGROK_EXE = shutil.which("ngrok") or "ngrok"

NGROK_DOMAIN = "motto-skeletal-gambling.ngrok-free.dev"
BACKEND_PORT = 1880
HEALTH_INTERVAL = 5  # seconds
MAX_RESTARTS_IN_WINDOW = 5
RESTART_WINDOW_SECONDS = 300

CREATE_NO_WINDOW = 0x08000000

def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    entry = f"[{timestamp}] [{level}] {msg}"
    if sys.stdout is not None:
        try:
            print(entry)
        except Exception:
            pass
    try:
        with open(SERVER_LOG, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass

def write_status(data):
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Failed to write status file: {e}", "WARN")

def is_port_in_use(port, host='127.0.0.1'):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0

def check_backend_http(timeout=2.0):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{BACKEND_PORT}/", headers={'User-Agent': 'SCADA-Watchdog'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in [200, 301, 302]
    except Exception:
        return False

def check_ngrok_api(timeout=2.0):
    try:
        req = urllib.request.Request("http://127.0.0.1:4040/api/tunnels", headers={'User-Agent': 'SCADA-Watchdog'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            tunnels = data.get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    return t.get("public_url")
            if tunnels:
                return tunnels[0].get("public_url")
            return None
    except Exception:
        return None

def kill_process_by_pid(pid):
    if not pid:
        return
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass

def kill_orphaned_node_red():
    """Ensure no previous orphaned node.exe or connection is occupying port 1880."""
    try:
        out = subprocess.check_output("netstat -ano", shell=True).decode('utf-8', errors='ignore')
        pids = set()
        for line in out.splitlines():
            if f":{BACKEND_PORT} " in line:
                parts = line.strip().split()
                if len(parts) >= 5 and parts[-1].isdigit():
                    pids.add(int(parts[-1]))
        for pid in pids:
            if pid > 0:
                log(f"Releasing port {BACKEND_PORT} from process PID {pid}...", "WARN")
                kill_process_by_pid(pid)
        if pids:
            time.sleep(1.5)
    except Exception as e:
        log(f"Error checking port: {e}", "WARN")

class ServerDaemon:
    def __init__(self):
        self.backend_proc = None
        self.ngrok_proc = None
        self.backend_restart_times = []
        self.ngrok_restart_times = []
        self.running = True
        self.start_time = time.time()
        self.public_url = f"https://{NGROK_DOMAIN}"

    def start_backend(self):
        log("Starting Node-RED Backend process...", "INFO")
        kill_orphaned_node_red()
        
        backend_log_file = open(BACKEND_LOG, "a", encoding="utf-8")
        backend_log_file.write(f"\n--- Node-RED Started at {datetime.now().isoformat()} ---\n")
        backend_log_file.flush()

        cmd = [NODE_EXE, RED_JS, "--userDir", USER_DIR]
        self.backend_proc = subprocess.Popen(
            cmd,
            stdout=backend_log_file,
            stderr=subprocess.STDOUT,
            cwd=USER_DIR,
            creationflags=CREATE_NO_WINDOW
        )
        log(f"Node-RED started with PID {self.backend_proc.pid}", "INFO")

        # Wait up to 25s for HTTP readiness
        ready = False
        for _ in range(25):
            time.sleep(1)
            if check_backend_http():
                ready = True
                break
            if self.backend_proc.poll() is not None:
                log(f"Node-RED exited prematurely with code {self.backend_proc.returncode}!", "ERROR")
                break
        
        if ready:
            log(f"Node-RED Backend verified ONLINE at http://localhost:{BACKEND_PORT}/ui/", "INFO")
        else:
            log("Node-RED started but port check timed out (still starting up).", "WARN")
        return ready

    def start_ngrok(self):
        log(f"Starting ngrok tunnel for domain: {NGROK_DOMAIN} -> localhost:{BACKEND_PORT}...", "INFO")
        
        ngrok_log_file = open(NGROK_LOG, "a", encoding="utf-8")
        ngrok_log_file.write(f"\n--- ngrok Started at {datetime.now().isoformat()} ---\n")
        ngrok_log_file.flush()

        cmd = [NGROK_EXE, "http", f"--url={NGROK_DOMAIN}", str(BACKEND_PORT), "--log=stdout"]
        self.ngrok_proc = subprocess.Popen(
            cmd,
            stdout=ngrok_log_file,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW
        )
        log(f"ngrok started with PID {self.ngrok_proc.pid}", "INFO")

        # Wait up to 15s for tunnel readiness
        tunnel_url = None
        for _ in range(15):
            time.sleep(1)
            tunnel_url = check_ngrok_api()
            if tunnel_url:
                break
            if self.ngrok_proc.poll() is not None:
                log(f"ngrok exited prematurely with code {self.ngrok_proc.returncode}!", "ERROR")
                break

        if tunnel_url:
            self.public_url = tunnel_url
            log(f"ngrok tunnel ONLINE: {self.public_url} -> http://localhost:{BACKEND_PORT}", "INFO")
        else:
            log("ngrok started, waiting for tunnel registration...", "WARN")
        return bool(tunnel_url)

    def can_restart(self, restart_times_list, name):
        now = time.time()
        # Keep only timestamps within window
        valid = [t for t in restart_times_list if now - t < RESTART_WINDOW_SECONDS]
        restart_times_list.clear()
        restart_times_list.extend(valid)
        
        if len(restart_times_list) >= MAX_RESTARTS_IN_WINDOW:
            log(f"Flapping detected for {name}! Exceeded {MAX_RESTARTS_IN_WINDOW} restarts in {RESTART_WINDOW_SECONDS}s. Backing off 30s.", "ERROR")
            time.sleep(30)
            return False
        return True

    def update_status(self):
        backend_alive = self.backend_proc is not None and self.backend_proc.poll() is None
        ngrok_alive = self.ngrok_proc is not None and self.ngrok_proc.poll() is None
        
        data = {
            "status": "RUNNING" if (backend_alive and ngrok_alive) else ("DEGRADED" if (backend_alive or ngrok_alive) else "STOPPED"),
            "daemon_pid": os.getpid(),
            "backend_pid": self.backend_proc.pid if backend_alive else None,
            "backend_alive": backend_alive,
            "backend_http_ready": check_backend_http(timeout=1.0),
            "backend_port": BACKEND_PORT,
            "backend_local_url": f"http://localhost:{BACKEND_PORT}/ui/",
            "ngrok_pid": self.ngrok_proc.pid if ngrok_alive else None,
            "ngrok_alive": ngrok_alive,
            "public_url": self.public_url,
            "public_ui_url": f"{self.public_url}/ui/",
            "uptime_seconds": int(time.time() - self.start_time),
            "started_at": datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%d %H:%M:%S"),
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "backend_restarts": len(self.backend_restart_times),
            "ngrok_restarts": len(self.ngrok_restart_times)
        }
        write_status(data)

    def shutdown(self):
        log("Received shutdown request. Terminating child processes cleanly...", "INFO")
        self.running = False

        if self.ngrok_proc and self.ngrok_proc.poll() is None:
            log("Stopping ngrok process...", "INFO")
            kill_process_by_pid(self.ngrok_proc.pid)

        if self.backend_proc and self.backend_proc.poll() is None:
            log("Stopping Node-RED process...", "INFO")
            kill_process_by_pid(self.backend_proc.pid)

        data = {
            "status": "STOPPED",
            "daemon_pid": None,
            "backend_pid": None,
            "ngrok_pid": None,
            "public_url": self.public_url,
            "stopped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        write_status(data)
        
        if os.path.exists(PID_FILE):
            try: os.remove(PID_FILE)
            except Exception: pass
            
        if os.path.exists(STOP_SIGNAL):
            try: os.remove(STOP_SIGNAL)
            except Exception: pass

        log("SCADA Server Daemon stopped completely.", "INFO")

    def run(self):
        # Remove any stale stop signal from previous runs
        if os.path.exists(STOP_SIGNAL):
            try: os.remove(STOP_SIGNAL)
            except Exception: pass

        # Write PID
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

        log(f"SCADA Server Watchdog Daemon initialized (PID: {os.getpid()})", "INFO")
        
        # 1. Start Backend first
        self.start_backend()
        
        # 2. Start ngrok second
        self.start_ngrok()
        
        self.update_status()

        log("Entering Watchdog Supervisor loop (Interval: 5s)...", "INFO")

        while self.running:
            try:
                # Check for stop signal file
                if os.path.exists(STOP_SIGNAL):
                    log("Detected stop.signal file. Initiating clean stop.", "INFO")
                    break

                # 1. Health check Backend
                backend_died = (self.backend_proc is None) or (self.backend_proc.poll() is not None)
                if backend_died:
                    log(f"ALERT: Node-RED Backend crashed or stopped unexpectedly! (ExitCode: {self.backend_proc.returncode if self.backend_proc else 'None'})", "ERROR")
                    if self.can_restart(self.backend_restart_times, "Backend"):
                        self.backend_restart_times.append(time.time())
                        log(f"Self-recovery: Restarting Node-RED Backend (Attempt {len(self.backend_restart_times)})...", "WARN")
                        self.start_backend()
                else:
                    # Deep check: is port responsive?
                    if not check_backend_http(timeout=3.0):
                        log("WARNING: Node-RED process is alive but port 1880 HTTP check timed out.", "WARN")

                # 2. Health check ngrok
                ngrok_died = (self.ngrok_proc is None) or (self.ngrok_proc.poll() is not None)
                tunnel_url = check_ngrok_api(timeout=2.0)
                
                if ngrok_died or not tunnel_url:
                    if ngrok_died:
                        log(f"ALERT: ngrok process died unexpectedly! (ExitCode: {self.ngrok_proc.returncode if self.ngrok_proc else 'None'})", "ERROR")
                    else:
                        log("ALERT: ngrok process is running but tunnel dropped from local API!", "ERROR")
                    
                    if self.can_restart(self.ngrok_restart_times, "ngrok"):
                        self.ngrok_restart_times.append(time.time())
                        if self.ngrok_proc and self.ngrok_proc.poll() is None:
                            kill_process_by_pid(self.ngrok_proc.pid)
                        log(f"Self-recovery: Restarting ngrok tunnel (Attempt {len(self.ngrok_restart_times)})...", "WARN")
                        self.start_ngrok()
                else:
                    self.public_url = tunnel_url

                self.update_status()
                time.sleep(HEALTH_INTERVAL)

            except KeyboardInterrupt:
                log("Received keyboard interrupt (SIGINT).", "INFO")
                break
            except Exception as e:
                log(f"Watchdog loop encountered exception: {e}", "ERROR")
                time.sleep(HEALTH_INTERVAL)

        self.shutdown()

if __name__ == "__main__":
    import traceback
    try:
        daemon = ServerDaemon()
        daemon.run()
    except Exception as e:
        log(f"FATAL CRASH in daemon main: {e}\n{traceback.format_exc()}", "CRITICAL")
        try:
            with open(os.path.join(LOG_DIR, "crash.log"), "a", encoding="utf-8") as f_crash:
                f_crash.write(f"--- Crash at {datetime.now().isoformat()} ---\n")
                f_crash.write(traceback.format_exc())
        except Exception:
            pass
