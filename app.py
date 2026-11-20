from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from importer import ImportJob
from storage import STATUSES, Store
from booking_table import render_table

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='Belegübersicht', page_icon='📋', layout='wide')
st.title('Belegübersicht')
st.caption('Mastercard und Bankkonto · fehlende Belege im Blick')


@st.cache_resource
def import_job():
    return ImportJob()


def load_draft(store, ident):
    rows, _ = store.read(ident)
    for row in rows:
        for key, value in row.items():
            if isinstance(value, (date, datetime)):
                row[key] = value.strftime('%Y-%m-%d')
    st.session_state.active = ident
    st.session_state.draft = rows
    st.session_state.saved = deepcopy(rows)
    st.session_state.epoch = st.session_state.get('epoch', 0) + 1
    st.session_state.pop('confirm_complete', None)


def dirty():
    return st.session_state.get('draft') != st.session_state.get('saved')


def save_draft(store):
    try:
        store.save(st.session_state.active, st.session_state.draft)
        st.session_state.saved = deepcopy(st.session_state.draft)
        st.success('Änderungen gespeichert.')
        return True
    except Exception as exc:
        st.error(f'Speichern fehlgeschlagen. Änderungen bleiben erhalten: {exc}')
        return False


try:
    store = Store(ROOT / 'data')
    entries = sorted(store.lists(), key=lambda entry: (entry['Name'].casefold(), entry['ID']))
    people = store.people()
except Exception as exc:
    st.error(f'Excel-Daten konnten nicht geöffnet werden: {exc}')
    st.stop()

job = import_job()
with st.expander('PDFs importieren'):
    st.write('PDFs in diesen Ordner legen:')
    st.code(str(store.inbox), language=None)
    running, _ = job.snapshot()
    if st.button('Eingangsordner importieren', disabled=running):
        job.start(store, ROOT)

    @st.fragment(run_every=2)
    def import_status():
        active, messages = job.snapshot()
        if active:
            st.info('Import läuft. Du kannst bestehende Buchungen weiter bearbeiten.')
        if messages:
            st.code(messages[-16000:], language=None)
        if not active and messages:
            if st.button('Abrechnungsauswahl aktualisieren'):
                st.rerun(scope='app')
    import_status()

if entries:
    names = {r['ID']: r['Name'] for r in entries}
    selected = st.selectbox('Abrechnung', list(names), format_func=lambda ident: f'{names[ident]} · {ident[:6]}',
                            key='statement_selection')
    if 'active' not in st.session_state:
        load_draft(store, selected)
    if selected != st.session_state.active:
        if dirty():
            st.warning('Die bisherige Abrechnung enthält ungespeicherte Änderungen. Bitte vor dem Wechsel speichern oder verwerfen.')
            left, right = st.columns(2)
            if left.button('Speichern und wechseln') and save_draft(store):
                load_draft(store, selected)
                st.rerun()
            if right.button('Verwerfen und wechseln'):
                load_draft(store, selected)
                st.rerun()
            st.stop()
        load_draft(store, selected)

    ident = st.session_state.active
    try:
        _, issues = store.read(ident)
    except Exception as exc:
        st.error(f'Abrechnung konnte nicht gelesen werden: {exc}')
        st.stop()
    errors = sum(i.get('Schwere') == 'error' for i in issues)
    warnings = sum(i.get('Schwere') == 'warning' for i in issues)
    if errors:
        st.error(f'Die PDF-Erkennung meldet {errors} Prüfprobleme. Bitte Prüfhinweise und Originalwerte kontrollieren.')
    elif warnings:
        st.warning(f'Die PDF-Erkennung meldet {warnings} Warnungen. Details unter „Prüfhinweise und Originaldaten“.')
    with st.expander('Abrechnung umbenennen'):
        name = st.text_input('Listenname', value=names[ident], key=f'name_{ident}')
        if st.button('Namen speichern'):
            try:
                store.rename(ident, name)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    rows = st.session_state.draft
    if st.button('Alle Buchungen auf erledigt setzen',
                 disabled=not any(row['Status'] != 'erledigt' for row in rows)):
        st.session_state.confirm_complete = ident
    if st.session_state.get('confirm_complete') == ident:
        st.warning(f'Wirklich alle {len(rows)} Buchungen in „{names[ident]}“ auf erledigt setzen? '
                   'Dies gilt auch für Buchungen, die durch Filter ausgeblendet sind. '
                   'Danach bitte die Änderungen speichern.')
        confirm, cancel = st.columns(2)
        if confirm.button('Ja, alle auf erledigt setzen', type='primary'):
            for row in rows:
                row['Status'] = 'erledigt'
            # Discard the component's accumulated edits so old status values cannot return.
            st.session_state.epoch += 1
            st.session_state.pop('confirm_complete', None)
            st.rerun()
        if cancel.button('Abbrechen'):
            st.session_state.pop('confirm_complete', None)
            st.rerun()
    filters = st.columns([1, 1, 2])
    status = filters[0].selectbox('Status filtern', ['Alle', *STATUSES])
    person = filters[1].selectbox('Person filtern', ['Alle', 'Nicht zugewiesen', *people])
    search = filters[2].text_input('Buchungen durchsuchen')
    displayed = [r for r in rows
                 if (status == 'Alle' or r['Status'] == status)
                 and (person == 'Alle' or r['Person'] == ('' if person == 'Nicht zugewiesen' else person))
                 and (not search or search.casefold() in ' '.join(str(v) for v in r.values()).casefold())]
    st.caption(f"{sum(r['Status'] != 'erledigt' for r in rows)} von {len(rows)} Buchungen offen · {len(displayed)} angezeigt")
    if displayed:
        key = f'editor_{ident}_{st.session_state.epoch}'
        render_table(displayed, people, STATUSES, key)
    else:
        st.info('Keine Buchungen für diese Filter.')

    a, b, c = st.columns([1, 1, 3])
    if a.button('Änderungen speichern', type='primary', disabled=not dirty()):
        save_draft(store)
    if b.button('Änderungen verwerfen', disabled=not dirty()):
        load_draft(store, ident)
        st.rerun()
    c.caption('Ungespeicherte Änderungen' if dirty() else 'Alle Änderungen gespeichert')
    st.caption('Datumsangaben bei Korrekturen als JJJJ-MM-TT eingeben. Vor dem Schließen des Browser-Tabs speichern.')

    with st.expander('Prüfhinweise und Originaldaten'):
        if issues:
            st.dataframe(pd.DataFrame(issues), hide_index=True, width='stretch')
        else:
            st.info('Keine Prüfhinweise vorhanden.')
        st.download_button('Arbeitsmappe mit Originalwerten herunterladen', store.path(ident).read_bytes(),
                           file_name=f'abrechnung_{ident[:8]}.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
else:
    st.info('Noch keine Abrechnungen vorhanden. Lege PDFs in den Eingangsordner und starte den Import.')

st.divider()
with st.expander('Fehlende Belege je Person exportieren', expanded=bool(entries)):
    export_person = st.selectbox('Belege anfordern von', people)
    chosen = st.multiselect('Abrechnungen für den Export', [r['ID'] for r in entries],
                            default=[r['ID'] for r in entries],
                            format_func=lambda value: next(r['Name'] for r in entries if r['ID'] == value))
    st.caption('Enthält gespeicherte Buchungen mit Status offen oder angefragt. Ungespeicherte Änderungen werden nicht exportiert.')
    try:
        data, count = store.export(export_person, chosen)
        st.download_button(f'Excel herunterladen · {count} fehlende Belege', data,
                           file_name=f'fehlende_belege_{people.index(export_person) + 1}.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', disabled=not chosen)
    except Exception as exc:
        st.error(f'Export fehlgeschlagen: {exc}')

with st.expander('Person hinzufügen'):
    with st.form('person_form', clear_on_submit=True):
        name = st.text_input('Name')
        if st.form_submit_button('Person hinzufügen'):
            try:
                store.add_person(name)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
