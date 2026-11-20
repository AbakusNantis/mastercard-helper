# Belegübersicht

Lokale Browseroberfläche für fehlende Belege zu Mastercard-Abrechnungen und Bankbewegungen. Alle Arbeitsdaten liegen in Excel-Dateien unter `data/`.

## Einrichtung mit Poetry

Voraussetzung: Python 3.12 und Poetry 2.x.

```powershell
poetry install
poetry run python start.py
```

Falls Poetry noch nicht installiert ist, kann es ohne globale Installation über uv ausgeführt werden:

```powershell
uv --cache-dir .cache/uv tool run --from poetry poetry install
uv --cache-dir .cache/uv tool run --from poetry poetry run python start.py
```

Poetry legt die Projektumgebung in `.venv` an. In VSCode `start.py` öffnen und oben den Python-Play-Button drücken. Alternativ die Startkonfiguration **Belegübersicht starten** verwenden. Der Launcher nutzt automatisch die Projektumgebung und öffnet den Browser, sobald der lokale Server bereit ist. Zum Beenden im Terminal Strg+C drücken.

## PDFs importieren

1. PDFs in `data/eingang` ablegen; der Ordner wird beim ersten Start erzeugt.
2. In **PDFs importieren** auf **Eingangsordner importieren** klicken.
3. Nach Abschluss **Abrechnungsauswahl aktualisieren** drücken.
4. Oben die Abrechnung auswählen und die Prüfhinweise kontrollieren.

Die vorhandenen Beispieldateien unter `prototype-data` werden nicht automatisch importiert. Sie können zum Ausprobieren in den Eingangsordner kopiert werden. Identische PDFs werden übersprungen, unabhängig vom Dateinamen. Jede andere PDF wird als eigene Liste aufgenommen. Quelldateien bleiben unverändert.

`config.toml` enthält den vorhandenen Qwen-Modellpfad, OCR-Modellpfad, den Nantislib-Quellpfad und den Python-Interpreter der bereits eingerichteten Nantislib-GPU-Umgebung. Nur der Import läuft in dieser Umgebung; Poetry verwaltet die Oberfläche und Tests. Das Nantislib-Repository wird nicht verändert. Für Scans und unbekannte Layouts benötigt der Reader die funktionierende NVIDIA-/CUDA-Umgebung. Während der Verarbeitung werden keine Modelle heruntergeladen.

Der Import läuft im Hintergrund und kann mehrere Minuten dauern. Fehler und Fortschritt erscheinen im Protokoll. Unvollständig verarbeitete PDFs werden nicht aufgenommen. Erkannte Buchungen mit Prüfproblemen werden samt Prüfhinweisen übernommen; diese müssen anhand des Originals kontrolliert werden. Ein erfolgreicher Import garantiert keine fehlerfreie Erkennung.

## Bearbeitung und Export

Die Abrechnungsauswahl liegt oben, die Tabelle darunter. Status und Person sind unabhängig: **offen**, **angefragt**, **erledigt** sowie optional Sebastian, Henrik oder eine ergänzte Person. Neue Buchungen starten offen. Auch Gutschriften und Sammelabbuchungen werden nicht automatisch erledigt.

Status und Person lassen sich direkt mit einem einfachen Klick auf das Auswahlfeld öffnen. Die Tabelle behält bei Änderungen ihre Scrollposition und die bestehenden Eingabefelder bei.

Die Tabelle zeigt alle gefilterten Buchungszeilen ohne eigenes vertikales Scrollfenster. Standardmäßig wird das helle Design verwendet. Der Status ist grün für erledigt, orange für angefragt oder eine noch offene Zuweisung und rot für offen ohne Zuweisung. Eine ausgewählte Person wird orange markiert; erledigte Buchungen behalten ihren grünen Status.

**Alle Buchungen auf erledigt setzen** setzt nach einer zusätzlichen Bestätigung sämtliche Buchungen der ausgewählten Abrechnung auf erledigt, einschließlich ausgefilterter Zeilen. Personen und Notizen bleiben erhalten. Anschließend **Änderungen speichern** klicken; bis dahin können die Änderungen verworfen werden.

Datum, Text und Beträge können in der Tabelle korrigiert werden. Datumsangaben werden als `JJJJ-MM-TT` dargestellt. Originalwerte und Prüfhinweise bleiben in den ursprünglichen Excel-Blättern erhalten. Änderungen explizit speichern. Beim Abrechnungswechsel bietet die Oberfläche Speichern oder Verwerfen an. Vor Browser-Refresh, Schließen des Tabs oder Beenden der Anwendung speichern; ungespeicherte Änderungen liegen nur in der Browsersitzung.

Der Personenexport enthält ausschließlich gespeicherte, zugewiesene und noch nicht erledigte Buchungen. Standardmäßig sind alle Abrechnungen ausgewählt. Die heruntergeladene Excel-Datei kann anschließend weitergegeben werden; die Anwendung versendet nichts.

Die Excel-Dateien nicht gleichzeitig außerhalb der Anwendung bearbeiten. Ist eine Datei in Excel gesperrt, Excel schließen und das Speichern erneut versuchen. Alle Änderungen bleiben bei einem Speicherfehler in der Oberfläche erhalten.

## Daten und Tests

- `data/verwaltung.xlsx`: Personen und Abrechnungsverzeichnis.
- `data/abrechnungen/<ID>.xlsx`: Nantislib-Originalblätter und zusätzliches Blatt `Bearbeitung` mit stabilen Buchungs-IDs und Korrekturen.
- `data/eingang`: ursprüngliche PDFs.

Den gesamten Ordner `data` regelmäßig sichern. Private PDFs und Laufzeitdaten sind von Git ausgeschlossen. Die Anwendung bindet ausschließlich an `127.0.0.1` und ist für lokale Einzelnutzung vorgesehen.

```powershell
poetry run pytest
```

Den zusätzlichen Browser-Test mit installiertem Microsoft Edge unter PowerShell starten:

```powershell
$env:RUN_BROWSER_TESTS = "1"
poetry run pytest tests/test_browser.py
```
