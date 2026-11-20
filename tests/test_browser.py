"""Opt-in browser regression: RUN_BROWSER_TESTS=1 poetry run pytest tests/test_browser.py."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

from openpyxl import Workbook
import pytest

from booking_table import apply_changes
from storage import Store, append


def test_changes_follow_booking_ids_and_protect_source():
    rows = [{'ID': 'a', 'Status': 'offen', 'Person': '', 'Quelle: Seite': 1},
            {'ID': 'b', 'Status': 'offen', 'Person': '', 'Quelle: Seite': 2}]
    apply_changes(rows, {'b': {'Status': 'angefragt', 'Person': 'Henrik', 'Quelle: Seite': 99},
                         'a': {'Person': 'Sebastian'}, 'missing': {'Status': 'erledigt'}})
    assert rows[0]['Person'] == 'Sebastian'
    assert rows[1]['Status'] == 'angefragt'
    assert rows[1]['Person'] == 'Henrik'
    assert rows[1]['Quelle: Seite'] == 2


@pytest.mark.skipif(os.environ.get('RUN_BROWSER_TESTS') != '1', reason='Opt-in: requires Microsoft Edge')
def test_single_click_dropdown_keeps_dom_and_scroll(tmp_path, monkeypatch):
    from playwright.sync_api import expect, sync_playwright

    root = Path(__file__).parents[1]
    store = Store(tmp_path / 'data')
    source = tmp_path / 'source.xlsx'
    wb = Workbook()
    wb.active.title = 'Buchungen'
    append(wb.active, ['Datum', 'Buchungstext', 'Betrag'])
    for index in range(40):
        append(wb.active, ['2026-11-20', f'Buchung {index}', '127,50 +' if index == 7 else -10.5])
    wb.save(source)
    pdf = tmp_path / 'fixture.pdf'
    pdf.write_bytes(b'fixture')
    store.register(pdf, source, store.digest(pdf))
    ident = store.lists()[0]['ID']
    rows, _ = store.read(ident)
    wrapper = tmp_path / 'browser_app.py'
    wrapper.write_text(
        f'import sys, runpy\nsys.path.insert(0, {str(root)!r})\nimport storage\n'
        f'_store = storage.Store({str(store.root)!r})\nstorage.Store = lambda root: _store\n'
        f'runpy.run_path({str(root / "app.py")!r}, run_name="__main__")\n', encoding='utf-8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    monkeypatch.setenv('TEMP', str(tmp_path))
    monkeypatch.setenv('TMP', str(tmp_path))
    env = dict(os.environ, STREAMLIT_BROWSER_GATHER_USAGE_STATS='false')
    process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(wrapper),
                                '--server.address=127.0.0.1', f'--server.port={port}', '--server.headless=true'],
                               cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + '/_stcore/health', timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1280, 'height': 720}, color_scheme='dark')
            page.goto(url)
            table = page.get_by_role('table', name='Buchungen')
            table.wait_for()
            container = page.locator('.booking-scroll')
            # Components use a shadow root, which Playwright's locators traverse.
            assert table.locator('tbody tr').count() == 40
            assert container.evaluate('el => el.clientHeight >= el.scrollHeight - 1')
            expect(page.get_by_test_id('stApp')).to_have_css('background-color', 'rgb(255, 255, 255)')
            status = page.get_by_label(f"Status · {rows[7]['ID']}", exact=True)
            amount = page.get_by_label(f"Betrag · {rows[7]['ID']}", exact=True)
            assert amount.input_value() == '127,50 +'
            status.scroll_into_view_if_needed()
            position = 'el => [document.querySelector(\'[data-testid="stMain"]\').scrollTop, el.scrollTop, el.scrollLeft]'
            before = container.evaluate(position)
            expect(status).to_have_css('background-color', 'rgb(254, 226, 226)')
            status.evaluate("el => el.dataset.regressionMarker = 'same-control'")
            status.click()
            page.keyboard.press('ArrowDown')
            page.keyboard.press('Enter')
            page.get_by_text('Ungespeicherte Änderungen', exact=True).wait_for()
            page.wait_for_timeout(500)
            assert status.input_value() == 'angefragt'
            assert status.get_attribute('data-regression-marker') == 'same-control'
            assert container.evaluate(position) == before
            expect(status).to_have_css('background-color', 'rgb(255, 237, 213)')
            person = page.get_by_label(f"Person · {rows[7]['ID']}", exact=True)
            person.click()
            page.keyboard.press('End')
            page.keyboard.press('Enter')
            page.wait_for_timeout(500)
            assert person.input_value() == 'Henrik'
            assert container.evaluate(position) == before
            expect(person).to_have_css('background-color', 'rgb(255, 237, 213)')
            status.select_option('offen')
            expect(status).to_have_css('background-color', 'rgb(255, 237, 213)')
            status.select_option('erledigt')
            expect(status).to_have_css('background-color', 'rgb(220, 252, 231)')
            status.select_option('angefragt')
            expect(status).to_have_css('background-color', 'rgb(255, 237, 213)')
            page.get_by_role('button', name='Änderungen speichern', exact=True).click()
            page.get_by_text('Alle Änderungen gespeichert', exact=True).wait_for()
            saved, _ = store.read(ident)
            assert saved[7]['Status'] == 'angefragt'
            assert saved[7]['Person'] == 'Henrik'
            assert saved[7]['Betrag'] == '127,50 +'
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
