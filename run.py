import subprocess
import os
import sys
import time
from dotenv import load_dotenv

# Ensure configuration is loaded
load_dotenv()

def run():
    api_port = os.environ.get("API_PORT", "8000")

    # Add project root to path for both processes to prevent import issues
    os.environ["PYTHONPATH"] = os.getcwd()

    # 1. Spin up FastAPI backend process
    # Bind to 0.0.0.0 (not 127.0.0.1) so the API is reachable from other
    # devices on the LAN, e.g. when the frontend is opened via http://<lan-ip>:5173
    print(f"[*] Initializing FastAPI Backend on http://0.0.0.0:{api_port} (reachable on your LAN)...")
    backend_proc = subprocess.Popen([
        sys.executable, "-m", "uvicorn", "backend.app:app",
        "--host", "0.0.0.0",
        "--port", str(api_port)
    ])

    # Sleep to allow Uvicorn to bind and launch
    time.sleep(3)

    # 2. Spin up React + Vite frontend process
    print("[*] Initializing React Frontend (Vite)...")
    frontend_dir = os.path.join(os.getcwd(), "frontend")

    # On Windows, npm is a .cmd script and must be run through the shell.
    # On Unix, shell=False with a list is safer (no shell injection).
    is_windows = sys.platform == "win32"
    npm_cmd = "npm run dev -- --host 0.0.0.0" if is_windows else ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
    frontend_proc = subprocess.Popen(
        npm_cmd,
        cwd=frontend_dir,
        shell=is_windows
    )

    try:
        # Keep the runner running
        while True:
            # Audit status
            if backend_proc.poll() is not None:
                print("[!] Backend crashed or exited.")
                break
            if frontend_proc.poll() is not None:
                print("[!] Frontend crashed or exited.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] SIGINT received. Terminating servers...")
    finally:
        # Clean shutdown
        backend_proc.terminate()
        frontend_proc.terminate()
        backend_proc.wait()
        frontend_proc.wait()
        print("[*] DocuIntellect processes cleaned up.")

if __name__ == "__main__":
    run()
