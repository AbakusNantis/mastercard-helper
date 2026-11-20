from pathlib import Path

from openpyxl import Workbook
from streamlit.testing.v1 import AppTest

from storage import Store, append


def seed(tmp_path, monkeypatch):
    store = Store(tmp_path / 'data')
    generated = tmp_path / 'generated.xlsx'
    wb = Workbook()
    wb.active.title = 'Buchungen'
    append(wb.active, ['Datum', 'Buchungstext', 'Betrag'])
    append(wb.active, ['2026-11-20', 'Shop', -10])
    append(wb.active, ['2026-11-21', 'Weitere Buchung', -20])
    wb.save(generated)
    for number in range(2):
        pdf = tmp_path / f'{number}.pdf'
        pdf.write_bytes(str(number).encode())
        store.register(pdf, generated, store.digest(pdf))
    monkeypatch.setattr('storage.Store', lambda root: store)
    return store


def test_dropdown_above_table_and_unsaved_switch(tmp_path, monkeypatch):
    store = seed(tmp_path, monkeypatch)
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'app.py')).run()
    assert not app.exception
    assert app.selectbox[0].label == 'Abrechnung'
    first = app.session_state.active
    rows = app.session_state.draft
    rows[0]['Person'] = 'Henrik'
    rows[0]['Status'] = 'angefragt'
    app.session_state.draft = rows
    app.selectbox[0].select(store.lists()[1]['ID']).run()
    assert not app.exception
    assert app.warning
    assert app.session_state.active == first
    next(button for button in app.button if button.label == 'Speichern und wechseln').click().run()
    assert not app.exception
    assert app.session_state.active == store.lists()[1]['ID']
    assert store.read(first)[0][0]['Person'] == 'Henrik'


def test_empty_ui(tmp_path, monkeypatch):
    store = Store(tmp_path / 'data')
    monkeypatch.setattr('storage.Store', lambda root: store)
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'app.py')).run()
    assert not app.exception
    assert any('Noch keine Abrechnungen' in info.value for info in app.info)


def test_discard_switch(tmp_path, monkeypatch):
    store = seed(tmp_path, monkeypatch)
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'app.py')).run()
    first = app.session_state.active
    rows = app.session_state.draft
    rows[0]['Status'] = 'erledigt'
    app.session_state.draft = rows
    app.selectbox[0].select(store.lists()[1]['ID']).run()
    next(b for b in app.button if b.label == 'Verwerfen und wechseln').click().run()
    assert not app.exception
    assert store.read(first)[0][0]['Status'] == 'offen'


def test_complete_all_requires_confirmation_and_can_be_cancelled(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'app.py')).run()
    original = [dict(row) for row in app.session_state.draft]
    next(b for b in app.button if b.label == 'Alle Buchungen auf erledigt setzen').click().run()
    assert app.warning
    assert app.session_state.draft == original
    next(b for b in app.button if b.label == 'Abbrechen').click().run()
    assert not app.exception
    assert app.session_state.draft == original
    assert not any(b.label == 'Ja, alle auf erledigt setzen' for b in app.button)


def test_complete_all_includes_filtered_rows_and_only_current_statement(tmp_path, monkeypatch):
    store = seed(tmp_path, monkeypatch)
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'app.py')).run()
    ident = app.session_state.active
    rows = app.session_state.draft
    rows[0].update(Status='angefragt', Person='Henrik', Notiz='Notiz erhalten')
    app.session_state.draft = rows
    next(s for s in app.selectbox if s.label == 'Status filtern').select('angefragt').run()
    next(b for b in app.button if b.label == 'Alle Buchungen auf erledigt setzen').click().run()
    next(b for b in app.button if b.label == 'Ja, alle auf erledigt setzen').click().run()
    assert not app.exception
    assert all(row['Status'] == 'erledigt' for row in app.session_state.draft)
    assert app.session_state.draft[0]['Person'] == 'Henrik'
    assert app.session_state.draft[0]['Notiz'] == 'Notiz erhalten'
    assert all(row['Status'] == 'offen' for row in store.read(ident)[0])
    next(b for b in app.button if b.label == 'Änderungen speichern').click().run()
    assert not app.exception
    assert all(row['Status'] == 'erledigt' for row in store.read(ident)[0])
    other = store.lists()[1]['ID']
    assert all(row['Status'] == 'offen' for row in store.read(other)[0])


def test_statement_choices_sorted_alphabetically(tmp_path, monkeypatch):
    store = seed(tmp_path, monkeypatch)
    first, second = store.lists()
    store.rename(first['ID'], 'zebra November')
    store.rename(second['ID'], 'Alpha Dezember')
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'app.py')).run()
    assert not app.exception
    selector = next(s for s in app.selectbox if s.label == 'Abrechnung')
    assert selector.value == second['ID']
    assert selector.options[0].startswith('Alpha Dezember')
    assert selector.options[1].startswith('zebra November')
    export = next(m for m in app.multiselect if m.label == 'Abrechnungen für den Export')
    assert export.options == ['Alpha Dezember', 'zebra November']
