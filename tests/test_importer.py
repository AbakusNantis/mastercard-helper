from pathlib import Path

from importer import ImportJob
from storage import Store


def test_worker_failure_continues_and_creates_no_list(tmp_path, monkeypatch):
    store = Store(tmp_path / 'data')
    (store.inbox / 'broken.pdf').write_bytes(b'broken')
    (store.inbox / 'next.PDF').write_bytes(b'next')
    (tmp_path / 'config.toml').write_text("[import]\npython = '" + str(Path(__file__).resolve()) + "'\n")
    seen = []
    class FailedProcess:
        stdout = ['Modell konnte nicht geladen werden\n']
        def __init__(self, args, **kwargs):
            seen.append(args)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def wait(self):
            return 1
    monkeypatch.setattr('importer.subprocess.Popen', FailedProcess)
    job = ImportJob()
    job.running = True
    job.run(store, tmp_path)
    assert len(seen) == 2
    assert not store.lists()
    assert not job.running
    assert 'FEHLER' in job.snapshot()[1]


def test_empty_inbox_finishes(tmp_path):
    store = Store(tmp_path / 'data')
    (tmp_path / 'config.toml').write_text("[import]\npython = '" + str(Path(__file__).resolve()) + "'\n")
    job = ImportJob()
    job.running = True
    job.run(store, tmp_path)
    assert not job.running
    assert 'Keine PDFs' in job.snapshot()[1]
