"""In VSCode öffnen und mit dem Python-Play-Button starten."""
from pathlib import Path
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


def main():
    python = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if not python.exists():
        raise SystemExit('Bitte zuerst im Projektordner ausführen: poetry install')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    env = dict(os.environ, STREAMLIT_BROWSER_GATHER_USAGE_STATS='false')
    process = subprocess.Popen([str(python), '-m', 'streamlit', 'run', str(ROOT / 'app.py'),
                                '--server.address=127.0.0.1', f'--server.port={port}',
                                '--server.headless=true', '--browser.gatherUsageStats=false'], cwd=ROOT, env=env)

    def open_browser():
        for _ in range(120):
            if process.poll() is not None:
                return
            try:
                with urllib.request.urlopen(url + '/_stcore/health', timeout=1) as response:
                    if response.status == 200:
                        webbrowser.open(url)
                        return
            except OSError:
                time.sleep(.5)
    threading.Thread(target=open_browser, daemon=True).start()
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
    return process.returncode


if __name__ == '__main__':
    sys.exit(main())
