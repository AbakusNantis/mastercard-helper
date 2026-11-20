"""Stable HTML controls: native selects open on the first click."""
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).parent / 'table_assets'
table_component = st.components.v2.component(
    'booking_table',
    html='<div class="booking-scroll"><table aria-label="Buchungen"></table></div>',
    css=(ASSETS / 'table.css').read_text(encoding='utf-8'),
    js=(ASSETS / 'table.js').read_text(encoding='utf-8'),
)


def apply_changes(rows, changes):
    by_id = {r['ID']: r for r in rows}
    for ident, fields in (changes or {}).items():
        if ident not in by_id:
            continue
        for name, value in fields.items():
            if name in by_id[ident] and name != 'ID' and not name.startswith('Quelle:') and name != 'Prüfhinweise':
                by_id[ident][name] = value


def render_table(rows, people, statuses, key):
    columns = ['Status', 'Person', 'Notiz'] + [c for c in rows[0] if c not in ['ID', 'Status', 'Person', 'Notiz']]
    numeric = [c for c in columns if any(isinstance(r.get(c), (int, float)) for r in rows)]

    def changed():
        apply_changes(st.session_state.draft, st.session_state[key].get('changes'))

    return table_component(
        data={'rows': rows, 'columns': columns, 'people': people, 'statuses': statuses, 'numeric': numeric},
        default={'changes': {}}, key=key, on_changes_change=changed,
        height='content', width='stretch',
    )
