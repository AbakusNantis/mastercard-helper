import subprocess
import threading

import start


def test_real_server_opens_browser_after_health_check(monkeypatch):
    processes = []
    urls = []
    popen = subprocess.Popen
    def record_process(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        # Bound the test even if startup fails.
        timer = threading.Timer(30, lambda: process.terminate() if process.poll() is None else None)
        timer.daemon = True
        timer.start()
        return process
    def open_browser(url):
        urls.append(url)
        processes[0].terminate()
    monkeypatch.setattr(start.subprocess, 'Popen', record_process)
    monkeypatch.setattr(start.webbrowser, 'open', open_browser)
    start.main()
    assert len(urls) == 1
    assert urls[0].startswith('http://127.0.0.1:')
    assert processes[0].poll() is not None
