from datetime import datetime
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook, load_workbook
import pytest

import storage
from storage import Store, append


@pytest.fixture
def fixture(tmp_path):
    store = Store(tmp_path / 'data')
    pdf = tmp_path / 'statement.pdf'
    pdf.write_bytes(b'fixture')
    generated = tmp_path / 'generated.xlsx'
    wb = Workbook()
    wb.active.title = 'Buchungen'
    for row in [['Datum', 'Text', 'Betrag', 'Quelle: Seite'],
                [datetime(2026, 11, 1), '=Original', -12.5, 1],
                [datetime(2026, 11, 2), 'Shop', -20, 1],
                [datetime(2026, 11, 3), 'Bank', -30, 2]]:
        append(wb.active, row)
    for name in ['Originalwerte', 'Prüfung', 'Abrechnung', 'Anlagen']:
        ws = wb.create_sheet(name)
        append(ws, ['Hinweis'])
        append(ws, ['Original unverändert'])
    wb.save(generated)
    assert store.register(pdf, generated, store.digest(pdf))
    return store, store.lists()[0]['ID'], pdf, generated


def test_roundtrip_and_source_preservation(fixture):
    store, ident, _, _ = fixture
    before = load_workbook(store.path(ident))
    original = {name: list(before[name].values) for name in before.sheetnames if name != 'Bearbeitung'}
    before.close()
    rows, _ = store.read(ident)
    ids = [r['ID'] for r in rows]
    rows[0].update(Status='erledigt', Person='Henrik', Notiz='liegt vor', Text='Korrektur', Betrag=-14)
    store.save(ident, rows)
    fresh = Store(store.root)
    loaded, _ = fresh.read(ident)
    assert loaded[0]['Person'] == 'Henrik'
    assert loaded[0]['Status'] == 'erledigt'
    assert loaded[0]['Betrag'] == -14
    assert [r['ID'] for r in loaded] == ids
    after = load_workbook(store.path(ident))
    assert {name: list(after[name].values) for name in original} == original
    after.close()


def test_export_assignment_status_selection_and_literal_text(fixture):
    store, ident, pdf, generated = fixture
    rows, _ = store.read(ident)
    rows[0].update(Person='Henrik', Status='angefragt', Notiz='=nicht ausführen')
    rows[1].update(Person='Henrik', Status='erledigt')
    rows[2].update(Status='offen')
    store.save(ident, rows)
    pdf.write_bytes(b'second')
    store.register(pdf, generated, store.digest(pdf))
    second = store.lists()[1]['ID']
    other, _ = store.read(second)
    other[0].update(Person='Henrik', Status='offen')
    store.save(second, other)
    data, count = store.export('Henrik', [ident, second])
    assert count == 2
    wb = load_workbook(BytesIO(data))
    assert all(cell.data_type != 'f' for row in wb.active for cell in row)
    wb.close()
    assert store.export('Henrik', [ident])[1] == 1
    assert store.export('Sebastian', [ident, second])[1] == 0


def test_duplicate_people_and_rename(fixture):
    store, ident, pdf, generated = fixture
    assert not store.register(pdf, generated, store.digest(pdf))
    assert len(store.lists()) == 1
    store.add_person(' Anna ')
    assert 'Anna' in store.people()
    with pytest.raises(ValueError):
        store.add_person('anna')
    store.rename(ident, 'Mastercard November')
    assert store.lists()[0]['Name'] == 'Mastercard November'


def test_locked_excel_keeps_file_and_retry_works(fixture, monkeypatch):
    store, ident, _, _ = fixture
    rows, _ = store.read(ident)
    before = store.path(ident).read_bytes()
    rows[0]['Status'] = 'angefragt'
    replace = storage.os.replace
    def locked(*args):
        raise PermissionError('Excel file locked')
    monkeypatch.setattr(storage.os, 'replace', locked)
    with pytest.raises(PermissionError):
        store.save(ident, rows)
    assert store.path(ident).read_bytes() == before
    assert not list(store.statements.glob('tmp*.xlsx'))
    monkeypatch.setattr(storage.os, 'replace', replace)
    store.save(ident, rows)
    assert store.read(ident)[0][0]['Status'] == 'angefragt'


def test_rejects_invalid_status_person_and_removed_rows(fixture):
    store, ident, _, _ = fixture
    rows, _ = store.read(ident)
    rows[0]['Status'] = 'unknown'
    with pytest.raises(ValueError):
        store.save(ident, rows)
    rows[0]['Status'] = 'offen'
    rows[0]['Person'] = 'unbekannt'
    with pytest.raises(ValueError):
        store.save(ident, rows)
    with pytest.raises(ValueError):
        store.save(ident, rows[:1])


def test_date_corrections_validate_and_persist(fixture):
    store, ident, _, _ = fixture
    rows, _ = store.read(ident)
    rows[0]['Datum'] = '2026-02-30'
    with pytest.raises(ValueError, match='Datum'):
        store.save(ident, rows)
    rows[0]['Datum'] = '2026-12-01'
    store.save(ident, rows)
    assert store.read(ident)[0][0]['Datum'] == '2026-12-01'


def test_tracking_saves_with_original_text_credit_amount(fixture):
    store, ident, _, _ = fixture
    wb = load_workbook(store.path(ident))
    wb['Buchungen']['C3'] = '127,50 +'
    wb.save(store.path(ident))
    wb.close()
    rows, _ = store.read(ident)
    rows[1].update(Status='angefragt', Person='Henrik')
    store.save(ident, rows)
    saved, _ = store.read(ident)
    assert saved[1]['Status'] == 'angefragt'
    assert saved[1]['Person'] == 'Henrik'
    assert saved[1]['Betrag'] == '127,50 +'
    saved[1]['Betrag'] = '128,75 +'
    store.save(ident, saved)
    assert store.read(ident)[0][1]['Betrag'] == 128.75
    wb = load_workbook(store.path(ident))
    assert wb['Buchungen']['C3'].value == '127,50 +'
    wb.close()


@pytest.mark.parametrize('value, expected', [('127,50 +', 127.5), ('62,99 -', -62.99),
                                           ('1.234,56', 1234.56), ('-10,25', -10.25)])
def test_german_numeric_corrections(value, expected):
    assert storage.numeric_correction(value, 'Betrag') == expected


@pytest.mark.parametrize('value', ['unbekannt', 'NaN', 'inf', '-12,00 +', True])
def test_invalid_numeric_corrections(value):
    with pytest.raises(ValueError):
        storage.numeric_correction(value, 'Betrag')
