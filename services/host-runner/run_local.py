"""Start the native host runner with this service's installed dependencies.

Also supports an alternate compatible Python interpreter when a Windows venv launcher
points at an interpreter that has moved. Always binds to loopback, never the LAN.
"""
import os
import sys
from pathlib import Path

service = Path(__file__).resolve().parent
dependencies = service / ".venv" / "Lib" / "site-packages"
if dependencies.is_dir():
    sys.path.insert(0, str(dependencies))
os.chdir(service)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8002)
