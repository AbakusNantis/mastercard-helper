"""Excel storage. Source sheets are never changed by tracking edits."""
from contextlib import contextmanager
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import hashlib
import json
import math
import re
import os
import tempfile
import uuid

from openpyxl import Workbook, load_workbook

STATUSES = ['offen', 'angefragt', 'erledigt']
TRACKING = 'Bearbeitung'
HEADERS = ['ID', 'Status', 'Person', 'Notiz', 'Korrekturen']


def numeric_correction(value, column):
    """Accept decimal commas and statement-style trailing signs on edited values."""
    if isinstance(value, str):
        number = re.sub(r'\s+', '', value)
        trailing = number[-1:] if number[-1:] in ('+', '-') else ''
        if trailing:
            number = number[:-1]
            if number.startswith(('+', '-')):
                raise ValueError(f'{column}: Widersprüchliche Vorzeichen.')
        if ',' in number:
            if '.' in number and number.rfind('.') > number.rfind(','):
                number = number.replace(',', '')
            else:
                number = number.replace('.', '').replace(',', '.')
        if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', number):
            raise ValueError(f'{column}: Bitte einen gültigen Zahlenwert eingeben.')
        value = float(number) * (-1 if trailing == '-' else 1)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{column}: Bitte einen gültigen Zahlenwert eingeben.')
    return value


def text_cell(cell, value):
    cell.value = value
    if isinstance(value, str):
        cell.data_type = 's'


def append(ws, values):
    row = ws.max_row + 1 if ws.cell(1, 1).value is not None else 1
    for col, value in enumerate(values, 1):
        text_cell(ws.cell(row, col), value)


def atomic_save(wb, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix='.xlsx', dir=target.parent)
    os.close(fd)
    try:
        wb.save(name)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def records(ws):
    rows = list(ws.values)
    return [dict(zip(rows[0], values)) for values in rows[1:]] if rows else []


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.inbox = self.root / 'eingang'
        self.statements = self.root / 'abrechnungen'
        self.catalog = self.root / 'verwaltung.xlsx'
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.statements.mkdir(parents=True, exist_ok=True)
        if not self.catalog.exists():
            wb = Workbook()
            wb.active.title = 'Listen'
            append(wb.active, ['ID', 'Name', 'SHA256', 'Quelldatei'])
            ws = wb.create_sheet('Personen')
            for value in ['Name', 'Sebastian', 'Henrik']:
                append(ws, [value])
            atomic_save(wb, self.catalog)
            wb.close()

    @contextmanager
    def locked(self):
        lock = self.root / '.schreibsperre'
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise ValueError('Eine andere Aktion schreibt gerade Daten. Bitte erneut versuchen. Nach einem Absturz gegebenenfalls data/.schreibsperre entfernen.')
        try:
            os.close(fd)
            yield
        finally:
            lock.unlink(missing_ok=True)

    def lists(self):
        wb = load_workbook(self.catalog)
        try:
            return records(wb['Listen'])
        finally:
            wb.close()

    def people(self):
        wb = load_workbook(self.catalog)
        try:
            return [r['Name'] for r in records(wb['Personen'])]
        finally:
            wb.close()

    def add_person(self, name):
        name = name.strip()
        if not name:
            raise ValueError('Bitte einen Namen eingeben.')
        with self.locked():
            wb = load_workbook(self.catalog)
            try:
                if name.casefold() in [r['Name'].casefold() for r in records(wb['Personen'])]:
                    raise ValueError('Diese Person existiert bereits.')
                append(wb['Personen'], [name])
                atomic_save(wb, self.catalog)
            finally:
                wb.close()

    def rename(self, ident, name):
        if not name.strip():
            raise ValueError('Bitte einen Listennamen eingeben.')
        with self.locked():
            wb = load_workbook(self.catalog)
            try:
                for row in wb['Listen'].iter_rows(min_row=2):
                    if row[0].value == ident:
                        text_cell(row[1], name.strip())
                        break
                else:
                    raise ValueError('Abrechnung nicht gefunden.')
                atomic_save(wb, self.catalog)
            finally:
                wb.close()

    @staticmethod
    def digest(pdf):
        return hashlib.sha256(Path(pdf).read_bytes()).hexdigest()

    def register(self, pdf, generated, digest):
        with self.locked():
            if digest in {r['SHA256'] for r in self.lists()}:
                return False
            ident = uuid.uuid4().hex
            wb = load_workbook(generated)
            try:
                if 'Buchungen' not in wb.sheetnames or wb['Buchungen'].max_row < 2:
                    raise ValueError('Keine Buchungen erkannt; die PDF wurde nicht aufgenommen.')
                ws = wb.create_sheet(TRACKING)
                append(ws, HEADERS)
                for _ in range(2, wb['Buchungen'].max_row + 1):
                    append(ws, [uuid.uuid4().hex, 'offen', '', '', '{}'])
                atomic_save(wb, self.statements / f'{ident}.xlsx')
            finally:
                wb.close()
            # The catalog is the commit point; an interrupted import can leave only an unlisted workbook.
            catalog = load_workbook(self.catalog)
            try:
                append(catalog['Listen'], [ident, Path(pdf).stem, digest, Path(pdf).name])
                atomic_save(catalog, self.catalog)
            finally:
                catalog.close()
            return True

    def path(self, ident):
        if ident not in {r['ID'] for r in self.lists()}:
            raise ValueError('Unbekannte Abrechnung.')
        return self.statements / f'{ident}.xlsx'

    def read(self, ident):
        wb = load_workbook(self.path(ident))
        try:
            source = records(wb['Buchungen'])
            tracking = records(wb[TRACKING])
            if len(source) != len(tracking):
                raise ValueError('Buchungen und Bearbeitungsdaten passen nicht zusammen.')
            rows = []
            for raw, state in zip(source, tracking):
                corrections = json.loads(state.get('Korrekturen') or '{}')
                row = {**raw, **corrections}
                for key, value in row.items():
                    if isinstance(value, (date, datetime)):
                        row[key] = value.strftime('%Y-%m-%d')
                row.update({k: state.get(k) or '' for k in HEADERS[:4]})
                rows.append(row)
            return rows, records(wb['Prüfung']) if 'Prüfung' in wb.sheetnames else []
        finally:
            wb.close()

    def save(self, ident, rows):
        with self.locked():
            path = self.path(ident)
            wb = load_workbook(path)
            try:
                original = records(wb['Buchungen'])
                date_columns = {key for raw in original for key, value in raw.items()
                                if isinstance(value, (date, datetime))}
                number_columns = {key for raw in original for key, value in raw.items()
                                  if isinstance(value, (int, float)) and not isinstance(value, bool)}
                states = records(wb[TRACKING])
                by_id = {r['ID']: r for r in rows}
                if len(by_id) != len(states) or set(by_id) != {r['ID'] for r in states}:
                    raise ValueError('Buchungen dürfen nicht hinzugefügt oder entfernt werden.')
                people = self.people()
                output = []
                for raw, state in zip(original, states):
                    row = by_id[state['ID']]
                    if row['Status'] not in STATUSES or row['Person'] not in ['', *people]:
                        raise ValueError('Ungültiger Status oder unbekannte Person.')
                    corrections = {}
                    for key, value in raw.items():
                        if key.startswith('Quelle:') or key == 'Prüfhinweise':
                            continue
                        edited = row.get(key)
                        if isinstance(value, (date, datetime)):
                            value = value.strftime('%Y-%m-%d')
                        # Imported values can deliberately remain text when extraction is uncertain.
                        # Tracking changes must not require correcting unrelated original data.
                        if edited == value:
                            continue
                        if edited not in (None, '') and key in date_columns:
                            try:
                                date.fromisoformat(str(edited))
                            except ValueError:
                                raise ValueError(f'{key}: Bitte ein gültiges Datum als JJJJ-MM-TT eingeben.')
                        if edited not in (None, '') and key in number_columns:
                            edited = numeric_correction(edited, key)
                        if edited != value:
                            if isinstance(edited, (date, datetime)):
                                edited = edited.isoformat()
                            corrections[key] = edited
                    output.append([state['ID'], row['Status'], row['Person'], row['Notiz'],
                                   json.dumps(corrections, ensure_ascii=False, allow_nan=False)])
                ws = wb[TRACKING]
                ws.delete_rows(2, ws.max_row)
                for values in output:
                    append(ws, values)
                atomic_save(wb, path)
            finally:
                wb.close()

    def export(self, person, selected):
        if person not in self.people():
            raise ValueError('Bitte eine Person auswählen.')
        wb = Workbook()
        ws = wb.active
        ws.title = 'Fehlende Belege'
        combined = []
        for entry in self.lists():
            if entry['ID'] in selected:
                rows, _ = self.read(entry['ID'])
                combined.extend({'Abrechnung': entry['Name'], **r} for r in rows
                                if r['Person'] == person and r['Status'] in ['offen', 'angefragt'])
        columns = ['Abrechnung']
        for row in combined:
            for key in row:
                if key not in columns and key != 'ID' and not key.startswith('Quelle:'):
                    columns.append(key)
        if len(columns) == 1:
            columns += ['Status', 'Person', 'Notiz']
        append(ws, columns)
        for row in combined:
            append(ws, [row.get(k, '') for k in columns])
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 24
        data = BytesIO()
        wb.save(data)
        wb.close()
        return data.getvalue(), len(combined)
