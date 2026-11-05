import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def clave(texto, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', texto.encode(), salt.encode(), 200_000).hex()
    return salt + ':' + digest


class Conexion:
    def __init__(self, raw, postgres):
        self.raw, self.postgres = raw, postgres

    def execute(self, sql, args=()):
        return self.raw.execute(sql.replace('?', '%s') if self.postgres else sql, args)


@contextmanager
def db(escritura=False):
    url = os.getenv('DATABASE_URL', '')
    if url:
        import psycopg
        from psycopg.rows import dict_row
        raw = psycopg.connect(url, row_factory=dict_row)
    else:
        path = Path(os.getenv('SQLITE_PATH', 'datos/residuos.db'))
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(path, timeout=15)
        raw.row_factory = sqlite3.Row
        raw.execute('PRAGMA foreign_keys=ON')
        if escritura:
            raw.execute('BEGIN IMMEDIATE')
    try:
        yield Conexion(raw, bool(url))
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def iniciar():
    tablas = [
        '''CREATE TABLE IF NOT EXISTS usuarios (id TEXT PRIMARY KEY, nombre TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL, clave TEXT NOT NULL, rol TEXT NOT NULL, peligrosos INTEGER NOT NULL DEFAULT 0)''',
        '''CREATE TABLE IF NOT EXISTS sesiones (token TEXT PRIMARY KEY, usuario TEXT NOT NULL REFERENCES usuarios(id), vence DOUBLE PRECISION NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS registros (id TEXT PRIMARY KEY, usuario TEXT NOT NULL REFERENCES usuarios(id),
        tipo TEXT NOT NULL, categoria TEXT NOT NULL, cantidad DOUBLE PRECISION NOT NULL, direccion TEXT NOT NULL,
        lat DOUBLE PRECISION NOT NULL, lon DOUBLE PRECISION NOT NULL, nota TEXT NOT NULL,
        estado TEXT NOT NULL, creado DOUBLE PRECISION NOT NULL, ruta TEXT)''',
        '''CREATE TABLE IF NOT EXISTS rutas (id TEXT PRIMARY KEY, recolector TEXT NOT NULL REFERENCES usuarios(id),
        creado DOUBLE PRECISION NOT NULL, datos TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS incidentes (id TEXT PRIMARY KEY, registro TEXT NOT NULL REFERENCES registros(id),
        autor TEXT NOT NULL REFERENCES usuarios(id), detalle TEXT NOT NULL, estado TEXT NOT NULL, creado DOUBLE PRECISION NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS avisos (id TEXT PRIMARY KEY, usuario TEXT NOT NULL REFERENCES usuarios(id),
        titulo TEXT NOT NULL, texto TEXT NOT NULL, creado DOUBLE PRECISION NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS dispositivos (token TEXT PRIMARY KEY, usuario TEXT NOT NULL REFERENCES usuarios(id))''',
        'CREATE INDEX IF NOT EXISTS idx_registros_usuario ON registros(usuario)',
        'CREATE INDEX IF NOT EXISTS idx_registros_ruta ON registros(ruta)',
        'CREATE INDEX IF NOT EXISTS idx_avisos_usuario_fecha ON avisos(usuario, creado)',
    ]
    with db(True) as c:
        if c.postgres:
            c.execute('SELECT pg_advisory_xact_lock(20261105)')
        for sql in tablas:
            c.execute(sql)
        if os.getenv('DEMO', '1') == '1':
            for uid, nombre, email, rol, especiales in [
                ('vecino', 'Vecino de prueba', 'vecino@demo.local', 'ciudadano', 0),
                ('autoridad', 'Coordinación municipal', 'autoridad@demo.local', 'autoridad', 0),
                ('equipo1', 'Equipo 1 - recolección general', 'equipo@demo.local', 'recolector', 0),
                ('especiales', 'Equipo 2 - residuos peligrosos', 'especiales@demo.local', 'recolector', 1),
            ]:
                c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?,?) ON CONFLICT (id) DO NOTHING',
                          (uid, nombre, email, clave('Demo2026!'), rol, especiales))
            c.execute('INSERT INTO avisos VALUES (?,?,?,?,?) ON CONFLICT (id) DO NOTHING',
                      ('bienvenida', 'vecino', 'Jornada de reciclaje',
                       'Campaña de demostración: sábado de 9 a 12 h. Separá papel, cartón y plástico limpios.', time.time()))
