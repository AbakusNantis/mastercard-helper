"""Run in the existing Nantislib GPU environment, separate from the UI."""
from pathlib import Path
import sys
import tomllib


def main():
    sys.dont_write_bytecode = True
    config = tomllib.loads((Path(__file__).parent / 'config.toml').read_text(encoding='utf-8'))['import']
    sys.path.insert(0, config['library'])
    from nantislib.statement_reader import StatementReader
    with StatementReader(model_path=config['model'], ocr_rec_model_path=config['ocr']) as reader:
        result = reader.read(sys.argv[1])
        result.check()
        if not result.complete:
            raise ValueError('Nicht alle PDF-Seiten wurden verarbeitet. Import abgebrochen.')
        result.to_excel(sys.argv[2])
        print(f'Erkannt: {len(result.rows)} Buchungen. Prüfhinweise bitte in der Oberfläche kontrollieren.', flush=True)


if __name__ == '__main__':
    main()
