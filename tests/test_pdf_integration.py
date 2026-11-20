"""Opt in: RUN_PDF_INTEGRATION=1 poetry run pytest -s tests/test_pdf_integration.py."""
from datetime import date, datetime
import os
from pathlib import Path
import subprocess
import tomllib

from openpyxl import load_workbook
import pytest

from storage import Store, records

ROOT = Path(__file__).parents[1]


@pytest.mark.skipif(os.environ.get('RUN_PDF_INTEGRATION') != '1', reason='Requires local models and CUDA')
@pytest.mark.parametrize('pdf', sorted((ROOT / 'prototype-data').glob('*.pdf')), ids=lambda p: p.stem)
def test_real_pdf_to_tracking(pdf, tmp_path):
    config = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))['import']
    target = tmp_path / 'result.xlsx'
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
               HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    subprocess.run([config['python'], '-u', str(ROOT / 'import_worker.py'), str(pdf), str(target)],
                   cwd=ROOT, env=env, check=True, timeout=1800)
    source = load_workbook(target)
    originals = records(source['Buchungen'])
    assert originals
    store = Store(tmp_path / 'data')
    store.register(pdf, target, store.digest(pdf))
    rows, issues = store.read(store.lists()[0]['ID'])
    assert len(rows) == len(originals)
    for original, row in zip(originals, rows):
        for key, value in original.items():
            if isinstance(value, (date, datetime)):
                value = value.strftime('%Y-%m-%d')
            assert row[key] == value
        assert row['Status'] == 'offen'
    print(f'{pdf.name}: {len(rows)} Buchungen, {len(issues)} Prüfhinweise; Werte unverändert übernommen.')
    source.close()
