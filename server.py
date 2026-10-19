"""Servidor de agenda con persistencia SQLite (solo biblioteca estándar)."""
import json
import os
import re
import sqlite3
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('AGENDA_DB', str(ROOT.parent / 'agenda-data' / 'agenda.sqlite3')))
FIELDS = ('id', 'case', 'court', 'type', 'room', 'crime', 'date', 'start', 'end', 'status', 'judge', 'specialist', 'site', 'organ')


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.execute('CREATE TABLE IF NOT EXISTS hearings (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    return db


def validate(item):
    reservation = isinstance(item, dict) and item.get('kind') == 'reservation'
    if reservation:
        item = {**item, 'case': 'Reserva de sala', 'court': 'Reserva', 'type': 'Bloqueo', 'crime': 'Reserva', 'judge': 'Sin asignar', 'specialist': 'Sin asignar'}
    if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip() or len(item[k]) > 500 for k in FIELDS):
        raise ValueError('Todos los campos son obligatorios (máximo 500 caracteres).')
    if not reservation and not re.fullmatch(r'\d{5}-\d{4}-\d-JR-PE-\d{2}', item['case']):
        raise ValueError('Formato de expediente inválido.')
    date.fromisoformat(item['date'])
    for k in ('start', 'end'):
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', item[k]):
            raise ValueError('Hora inválida.')
    if not '07:00' <= item['start'] < item['end'] <= '20:00':
        raise ValueError('El horario debe estar entre 07:00 y 20:00 y el fin debe ser posterior al inicio.')
    choices = {
        'status': ['Pendiente', 'Atendida', 'Caducada', 'Anulada'],
        'room': [f'SALA_0{i}_{kind}' for kind in ('JIP', 'JUP') for i in range(1, 6)],
        'site': ['Sede Central', 'Sede Iquitos'],
        'organ': ['Investigación Preparatoria', 'Juzgado Unipersonal'],
        'type': ['Prueba Anticipada', 'Control de Acusación', 'Prisión Preventiva'],
        'judge': ['Dra. María Torres', 'Dr. José Ramírez', 'Dra. Elena Ríos'],
        'specialist': ['Ana López', 'Carlos Medina', 'Lucía Díaz'],
    }
    if any(item[k] not in values for k, values in choices.items() if not (reservation and k in ('type', 'judge', 'specialist'))):
        raise ValueError('Selección inválida.')
    return {**{k: item[k] for k in FIELDS}, **({'kind': 'reservation'} if reservation else {})}


def check_conflict(item, existing):
    for other in existing:
        if (item['status'] != 'Anulada' and other['status'] != 'Anulada'
            and item['id'] != other['id'] and item['date'] == other['date']
            and item['start'] < other['end'] and item['end'] > other['start']
            and ((item['site'] == other['site'] and item['room'] == other['room'])
                 or (item.get('kind') != 'reservation' and other.get('kind') != 'reservation'
                     and (item['judge'] == other['judge'] or item['specialist'] == other['specialist'])))):
            raise ValueError(f"Cruce de horario con {other['case']} ({other['start']}–{other['end']}): sala, juez o especialista ocupado.")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def reply(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/api/audiencias':
            with connect() as db:
                self.reply(200, [json.loads(row[0]) for row in db.execute('SELECT data FROM hearings')])
        elif self.path.split('?')[0] in ('/', '/index.html'):
            super().do_GET()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path not in ('/api/audiencias', '/api/initialize'):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1_000_000:
                raise ValueError('Tamaño de solicitud inválido.')
            payload = json.loads(self.rfile.read(length))
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                existing = [json.loads(row[0]) for row in db.execute('SELECT data FROM hearings')]
                if self.path == '/api/initialize':
                    if not isinstance(payload, list):
                        raise ValueError('Se esperaba una lista de audiencias.')
                    items = [] if existing else payload
                else:
                    items = [payload]
                for raw in items:
                    item = validate(raw)
                    check_conflict(item, existing)
                    db.execute('INSERT INTO hearings VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (item['id'], json.dumps(item, ensure_ascii=False)))
                    existing = [e for e in existing if e['id'] != item['id']] + [item]
            self.reply(200, existing)
        except (ValueError, TypeError, KeyError) as exc:
            self.reply(400, {'error': str(exc)})
        except sqlite3.Error:
            self.reply(503, {'error': 'No se pudo acceder a la base de datos. Intenta de nuevo.'})


if __name__ == '__main__':
    with connect():
        pass
    print('Agenda SQLite disponible en el puerto 8000', flush=True)
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
