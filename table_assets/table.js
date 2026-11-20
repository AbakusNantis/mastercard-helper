export default function ({ parentElement, data, setStateValue }) {
    const table = parentElement.querySelector('table');
    // Keep the same DOM nodes, native controls, focus and scroll positions across reruns.
    const context = table.bookingContext ??= { changes: {}, signature: null };
    context.send = setStateValue;
    const updateColors = (tr) => {
        const status = tr.querySelector('[data-column="Status"] select');
        const person = tr.querySelector('[data-column="Person"] select');
        status.dataset.color = status.value === 'erledigt' ? 'green'
            : status.value === 'angefragt' || person.value ? 'orange' : 'red';
        person.dataset.color = person.value ? 'orange' : '';
    };
    const signature = JSON.stringify([data.columns, data.rows.map(row => row.ID), data.people, data.statuses]);
    const emit = (id, column, value) => {
        context.changes[id] ??= {};
        context.changes[id][column] = value;
        context.send('changes', structuredClone(context.changes));
    };
    if (context.signature !== signature) {
        context.signature = signature;
        table.replaceChildren();
        const header = table.createTHead().insertRow();
        for (const column of data.columns) {
            const th = document.createElement('th');
            th.textContent = column;
            header.append(th);
        }
        const body = table.createTBody();
        for (const row of data.rows) {
            const tr = body.insertRow();
            tr.dataset.id = row.ID;
            for (const column of data.columns) {
                const td = tr.insertCell();
                td.dataset.column = column;
                const readonly = column.startsWith('Quelle:') || column === 'Prüfhinweise';
                if (readonly) {
                    td.className = 'readonly';
                    td.textContent = row[column] ?? '';
                    continue;
                }
                let control;
                if (column === 'Status' || column === 'Person') {
                    control = document.createElement('select');
                    const options = column === 'Status' ? data.statuses : ['', ...data.people];
                    for (const value of options) {
                        const option = document.createElement('option');
                        option.value = value;
                        option.textContent = value || 'Nicht zugewiesen';
                        control.append(option);
                    }
                } else {
                    control = document.createElement('input');
                    // Uncertain original amounts may be text such as "127,50 +".
                    // A number input would silently display these as an empty field.
                    control.type = data.numeric.includes(column) && typeof row[column] !== 'string' ? 'number' : 'text';
                    if (data.numeric.includes(column)) control.inputMode = 'decimal';
                    if (control.type === 'number') control.step = 'any';
                }
                control.value = row[column] ?? '';
                control.setAttribute('aria-label', `${column} · ${row.ID}`);
                control.addEventListener('change', () => {
                    if (!control.checkValidity()) return;
                    const value = control.type === 'number'
                        ? (control.value === '' ? null : control.valueAsNumber)
                        : control.value;
                    updateColors(tr);
                    emit(row.ID, column, value);
                });
                td.append(control);
            }
        }
    }
    const byId = new Map(data.rows.map(row => [row.ID, row]));
    for (const tr of table.tBodies[0].rows) {
        const row = byId.get(tr.dataset.id);
        for (const td of tr.cells) {
            const control = td.firstElementChild;
            const column = td.dataset.column;
            const value = row[column] ?? '';
            // A rerun must not overwrite typing or a change still in transit.
            const pending = context.changes[row.ID]?.[column];
            if (pending !== undefined && pending !== row[column]) continue;
            if (control && parentElement.activeElement !== control && control.value !== String(value)) {
                control.value = value;
            }
        }
        updateColors(tr);
    }
}
