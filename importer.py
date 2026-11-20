from pathlib import Path
import os
import subprocess
import tempfile
import threading
import tomllib


class ImportJob:
    """One sequential import job per app process. UI reruns do not interrupt it."""
    def __init__(self):
        self.messages = []
        self.running = False
        self.guard = threading.Lock()

    def log(self, message):
        with self.guard:
            self.messages.append(message)

    def snapshot(self):
        with self.guard:
            return self.running, '\n'.join(self.messages)

    def start(self, store, root):
        with self.guard:
            if self.running:
                return
            self.running = True
            self.messages = []
        threading.Thread(target=self.run, args=(store, root), daemon=True).start()

    def run(self, store, root):
        try:
            config = tomllib.loads((root / 'config.toml').read_text(encoding='utf-8'))['import']
            if not Path(config['python']).is_file():
                raise ValueError('Import-Python fehlt. Bitte config.toml prüfen.')
            files = sorted(p for p in store.inbox.iterdir() if p.suffix.lower() == '.pdf' and p.is_file())
            if not files:
                self.log('Keine PDFs im Eingangsordner gefunden.')
            for pdf in files:
                try:
                    digest = store.digest(pdf)
                    if digest in {r['SHA256'] for r in store.lists()}:
                        self.log(f'{pdf.name}: bereits importiert, übersprungen.')
                        continue
                    self.log(f'{pdf.name}: Import läuft …')
                    with tempfile.TemporaryDirectory(dir=store.root) as work:
                        # Process a private snapshot so a changed inbox file cannot invalidate its hash.
                        snapshot = Path(work) / pdf.name
                        snapshot.write_bytes(pdf.read_bytes())
                        digest = store.digest(snapshot)
                        target = Path(work) / 'result.xlsx'
                        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
                                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
                        with subprocess.Popen([config['python'], '-u', str(root / 'import_worker.py'),
                                               str(snapshot), str(target)], cwd=root, env=env,
                                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                              text=True, encoding='utf-8', errors='replace') as process:
                            for line in process.stdout:
                                self.log(line.rstrip())
                            if process.wait() != 0:
                                raise ValueError('PDF-Erkennung fehlgeschlagen. Details siehe Protokoll; Modellpfad und CUDA prüfen.')
                        added = store.register(pdf, target, digest)
                        self.log(f'{pdf.name}: ' + ('erfolgreich aufgenommen.' if added else 'bereits vorhanden.'))
                except Exception as exc:
                    self.log(f'{pdf.name}: FEHLER – {exc}')
        except Exception as exc:
            self.log(f'FEHLER – {exc}')
        finally:
            with self.guard:
                self.running = False
