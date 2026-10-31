import subprocess
import sys
import os

if __name__ == "__main__":
    exe_path = os.path.join(os.path.dirname(__file__), "dist", "QuantClaw", "QuantClaw.exe")
    if os.path.exists(exe_path):
        print(f"Starting QuantClaw from {exe_path}...")
        proc = subprocess.Popen([exe_path])
        proc.wait()
    else:
        print("Starting QuantClaw via python module...")
        from quantclaw.main import main
        main()
