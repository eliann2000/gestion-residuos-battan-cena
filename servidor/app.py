import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from datos import clave, db, iniciar
from ruteo import optimizar


@asynccontextmanager
async def vida(app):
    iniciar()
    yield


app = FastAPI(title='Gestión de Residuos - San Francisco', version='1.0', lifespan=vida)
log = logging.getLogger('residuos')
metricas = {'total': 0, 'errores': 0, 'segundos': 0.0}
mutex = threading.Lock()


@app.middleware('http')
async def medir(request: Request, call_next):
    inicio = time.monotonic()
    estado = 500
    try:
        response = await call_next(request)
        estado = response.status_code
        return response
    finally:
        if request.url.path not in ['/metrics', '/health', '/live']:
            with mutex:
                metricas['total'] += 1
                metricas['errores'] += int(estado >= 500)
                metricas['segundos'] += time.monotonic() - inicio


def uid():
    return uuid.uuid4().hex


def usuario(authorization: str = Header(default='')):
    if not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Iniciá sesión para continuar.')
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with db() as c:
        u = c.execute('SELECT u.* FROM usuarios u JOIN sesiones s ON u.id=s.usuario WHERE s.token=? AND s.vence>?',
                      (digest, time.time())).fetchone()
    if not u:
        raise HTTPException(401, 'La sesión venció. Volvé a ingresar.')
    return dict(u)


def exigir(u, *roles):
    if u['rol'] not in roles:
        raise HTTPException(403, 'Tu perfil no puede realizar esta operación.')


def publico(u):
    return {k: u[k] for k in ['id', 'nombre', 'email', 'rol', 'peligrosos']}


def avisar(c, usuarios, titulo, texto):
    for persona in set(usuarios):
        c.execute('INSERT INTO avisos VALUES (?,?,?,?,?)', (uid(), persona, titulo, texto, time.time()))


def autoridades(c):
    return [x['id'] for x in c.execute("SELECT id FROM usuarios WHERE rol='autoridad'").fetchall()]


def push_fcm(usuarios, titulo, texto):
    archivo = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if not archivo:
        return
    try:
        import requests
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as AuthRequest
        cred = service_account.Credentials.from_service_account_file(
            archivo, scopes=['https://www.googleapis.com/auth/firebase.messaging'])
        cred.refresh(AuthRequest())
        with db() as c:
            tokens = [r['token'] for r in c.execute('SELECT token,usuario FROM dispositivos').fetchall()
                      if r['usuario'] in usuarios]
        for token in tokens:
            response = requests.post(f'https://fcm.googleapis.com/v1/projects/{cred.project_id}/messages:send',
                headers={'Authorization': 'Bearer ' + cred.token}, timeout=10,
                json={'message': {'token': token, 'notification': {'title': titulo, 'body': texto},
                                  'android': {'notification': {'channel_id': 'residuos'}}}})
            if response.status_code >= 400:
                log.warning('FCM no pudo entregar un aviso: HTTP %s', response.status_code)
    except Exception:
        log.exception('No se pudo enviar por FCM; el aviso permanece en la bandeja.')


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=100)


class Alta(Login):
    nombre: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=100)


@app.post('/login')
def login(data: Login):
    with db(True) as c:
        u = c.execute('SELECT * FROM usuarios WHERE email=?', (data.email.strip().lower(),)).fetchone()
        esperado = u['clave'] if u else clave('inexistente')
        if not hmac.compare_digest(esperado, clave(data.password, esperado.split(':')[0])) or not u:
            raise HTTPException(401, 'Correo o contraseña incorrectos.')
        token = secrets.token_urlsafe(32)
        c.execute('DELETE FROM sesiones WHERE vence<?', (time.time(),))
        c.execute('INSERT INTO sesiones VALUES (?,?,?)',
                  (hashlib.sha256(token.encode()).hexdigest(), u['id'], time.time()+86400))
    return {'token': token, 'usuario': publico(u), 'servidor_epoch': time.time()}


@app.post('/usuarios', status_code=201)
def registrar(data: Alta):
    email = data.email.strip().lower()
    if '@' not in email or not data.nombre.strip():
        raise HTTPException(422, 'Revisá el nombre y el correo.')
    with db(True) as c:
        if c.execute('SELECT id FROM usuarios WHERE email=?', (email,)).fetchone():
            raise HTTPException(409, 'Ese correo ya está registrado.')
        c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?,?)',
                  (uid(), data.nombre.strip(), email, clave(data.password), 'ciudadano', 0))
    return {'mensaje': 'Cuenta creada. Ya podés ingresar.'}


@app.post('/logout')
def logout(authorization: str = Header(default=''), u=Depends(usuario)):
    with db(True) as c:
        c.execute('DELETE FROM sesiones WHERE token=?', (hashlib.sha256(authorization[7:].encode()).hexdigest(),))
    return {'mensaje': 'Sesión cerrada.'}


PUNTOS = [
    {'id': 'P01', 'nombre': 'Punto demostrativo Centro', 'lat': -31.4275, 'lon': -62.082,
     'horario': 'Lunes a viernes, 8 a 18 h', 'materiales': 'Papel, cartón y plástico'},
    {'id': 'P02', 'nombre': 'Punto demostrativo Norte', 'lat': -31.4154, 'lon': -62.0841,
     'horario': 'Lunes a sábado, 9 a 17 h', 'materiales': 'Vidrio y metales'},
    {'id': 'P03', 'nombre': 'Punto demostrativo Este', 'lat': -31.4294, 'lon': -62.0693,
     'horario': 'Martes y jueves, 9 a 16 h', 'materiales': 'Papel y cartón'},
]


@app.get('/panel')
def panel(u=Depends(usuario)):
    with db() as c:
        sql = 'SELECT r.*,u.nombre AS vecino FROM registros r JOIN usuarios u ON r.usuario=u.id'
        args = ()
        if u['rol'] == 'ciudadano':
            sql += ' WHERE r.usuario=?'
            args = (u['id'],)
        elif u['rol'] == 'recolector':
            sql += ' WHERE r.ruta IN (SELECT id FROM rutas WHERE recolector=?)'
            args = (u['id'],)
        registros = [dict(x) for x in c.execute(sql+' ORDER BY r.creado DESC', args).fetchall()]
        rutas = [dict(x) for x in c.execute(
            'SELECT r.*,u.nombre AS equipo FROM rutas r JOIN usuarios u ON r.recolector=u.id' +
            (' WHERE r.recolector=?' if u['rol'] == 'recolector' else ' WHERE ?=?') + ' ORDER BY r.creado DESC',
            (u['id'],) if u['rol'] == 'recolector' else (u['rol'], 'autoridad')).fetchall()]
        for ruta in rutas:
            ruta['datos'] = json.loads(ruta['datos'])
        incidentes = [dict(x) for x in c.execute('SELECT i.*,r.direccion FROM incidentes i JOIN registros r ON i.registro=r.id ORDER BY i.creado DESC').fetchall()
                      if u['rol'] == 'autoridad' or x['registro'] in {r['id'] for r in registros}]
        equipos = [publico(x) for x in c.execute("SELECT * FROM usuarios WHERE rol='recolector'").fetchall()] if u['rol'] == 'autoridad' else []
        avisos = [dict(x) for x in c.execute('SELECT * FROM avisos WHERE usuario=? ORDER BY creado DESC LIMIT 50', (u['id'],)).fetchall()]
    return {'usuario': publico(u), 'registros': registros, 'rutas': rutas, 'incidentes': incidentes,
            'equipos': equipos, 'avisos': avisos, 'puntos': PUNTOS,
            'horarios': 'Ejemplo de servicio: residuos comunes de lunes a viernes, 20 a 22 h. Especiales con solicitud previa.'}


class Registro(BaseModel):
    tipo: Literal['registro', 'solicitud']
    categoria: Literal['comunes', 'reciclables', 'voluminosos', 'peligrosos']
    cantidad: float = Field(gt=0, le=500, allow_inf_nan=False)
    direccion: str = Field(min_length=4, max_length=160)
    lat: float = Field(ge=-31.50, le=-31.35, allow_inf_nan=False)
    lon: float = Field(ge=-62.15, le=-62.0, allow_inf_nan=False)
    nota: str = Field(default='', max_length=500)


@app.post('/registros', status_code=201)
def crear_registro(data: Registro, tareas: BackgroundTasks, u=Depends(usuario)):
    exigir(u, 'ciudadano')
    if not data.direccion.strip():
        raise HTTPException(422, 'Indicá la dirección.')
    if data.tipo == 'solicitud' and data.categoria == 'comunes':
        raise HTTPException(422, 'Los residuos comunes siguen el horario habitual.')
    rid = uid()
    with db(True) as c:
        c.execute('INSERT INTO registros VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                  (rid, u['id'], data.tipo, data.categoria, data.cantidad, data.direccion.strip(),
                   data.lat, data.lon, data.nota.strip(), 'pendiente' if data.tipo == 'solicitud' else 'registrado', time.time(), None))
        destinos = autoridades(c) if data.tipo == 'solicitud' else []
        avisar(c, destinos, 'Nueva solicitud', f'{data.categoria.capitalize()}: {data.direccion.strip()}')
    tareas.add_task(push_fcm, destinos, 'Nueva solicitud', data.direccion)
    return {'id': rid, 'mensaje': 'Solicitud creada.' if data.tipo == 'solicitud' else 'Residuo registrado.'}


class Asignacion(BaseModel):
    registros: list[str] = Field(min_length=1, max_length=20)
    recolector: str


@app.post('/rutas', status_code=201)
def asignar(data: Asignacion, tareas: BackgroundTasks, u=Depends(usuario)):
    exigir(u, 'autoridad')
    if len(set(data.registros)) != len(data.registros):
        raise HTTPException(422, 'No se pueden repetir solicitudes.')
    with db() as c:
        equipo = c.execute("SELECT * FROM usuarios WHERE id=? AND rol='recolector'", (data.recolector,)).fetchone()
        puntos = []
        for rid in data.registros:
            r = c.execute('SELECT * FROM registros WHERE id=?', (rid,)).fetchone()
            if not r or r['estado'] != 'pendiente' or r['tipo'] != 'solicitud':
                raise HTTPException(409, 'Una solicitud ya cambió de estado. Actualizá el panel.')
            puntos.append(dict(r))
    if not equipo:
        raise HTTPException(422, 'Seleccioná un recolector válido.')
    peligrosos = [p for p in puntos if p['categoria'] == 'peligrosos']
    if peligrosos and (not equipo['peligrosos'] or len(peligrosos) != len(puntos)):
        raise HTTPException(422, 'Los peligrosos requieren el equipo especial y una ruta separada.')
    if sum(p['cantidad'] for p in puntos) > 500:
        raise HTTPException(422, 'La capacidad demostrativa es de 500 kg por ruta.')
    datos = optimizar(puntos)
    ruta = uid()
    with db(True) as c:
        c.execute('INSERT INTO rutas VALUES (?,?,?,?)', (ruta, equipo['id'], time.time(), json.dumps(datos)))
        for p in puntos:
            cambio = c.execute("UPDATE registros SET estado='asignado',ruta=? WHERE id=? AND estado='pendiente'", (ruta, p['id']))
            if cambio.rowcount != 1:
                raise HTTPException(409, 'Otra autoridad ya asignó una solicitud. Actualizá el panel.')
        vecinos = [p['usuario'] for p in puntos]
        coordinacion = autoridades(c)
        destinos = vecinos + [equipo['id']] + coordinacion
        avisar(c, vecinos, 'Recolección asignada', 'Tu solicitud fue incluida en una ruta de recolección.')
        avisar(c, [equipo['id']], 'Nueva ruta asignada', f'Tenés {len(puntos)} puntos por atender.')
        avisar(c, coordinacion, 'Ruta asignada', f'Ruta {ruta[:8].upper()}: {equipo["nombre"]}.')
    tareas.add_task(push_fcm, destinos, 'Recolección asignada', f'Ruta {ruta[:8].upper()} disponible.')
    return {'id': ruta, 'datos': datos, 'mensaje': 'Ruta planificada y asignada.'}


class Confirmacion(BaseModel):
    identificador: str = Field(min_length=1, max_length=40)


@app.post('/registros/{rid}/confirmar')
def confirmar(rid: str, data: Confirmacion, tareas: BackgroundTasks, u=Depends(usuario)):
    exigir(u, 'recolector')
    with db(True) as c:
        r = c.execute('SELECT r.* FROM registros r JOIN rutas t ON r.ruta=t.id WHERE r.id=? AND t.recolector=?', (rid, u['id'])).fetchone()
        if not r:
            raise HTTPException(404, 'El punto no pertenece a tus rutas.')
        if data.identificador.strip().upper() != rid[:8].upper():
            raise HTTPException(422, 'El identificador no coincide con el punto.')
        if r['estado'] != 'asignado':
            raise HTTPException(409, 'Esta recolección ya fue registrada.')
        cambio = c.execute("UPDATE registros SET estado='recolectado' WHERE id=? AND estado='asignado'", (rid,))
        if cambio.rowcount != 1:
            raise HTTPException(409, 'Esta recolección ya fue registrada.')
        destinos = [r['usuario']] + autoridades(c)
        avisar(c, destinos, 'Recolección completada', r['direccion'])
    tareas.add_task(push_fcm, destinos, 'Recolección completada', r['direccion'])
    return {'mensaje': 'Recolección confirmada.'}


class Incidente(BaseModel):
    registro: str
    detalle: str = Field(min_length=5, max_length=500)


@app.post('/incidentes', status_code=201)
def incidente(data: Incidente, tareas: BackgroundTasks, u=Depends(usuario)):
    exigir(u, 'recolector', 'autoridad')
    with db(True) as c:
        r = c.execute('SELECT * FROM registros WHERE id=?', (data.registro,)).fetchone()
        if not r:
            raise HTTPException(404, 'El punto no existe.')
        if u['rol'] == 'recolector' and not c.execute('SELECT id FROM rutas WHERE id=? AND recolector=?', (r['ruta'], u['id'])).fetchone():
            raise HTTPException(403, 'El punto no pertenece a tus rutas.')
        if len(data.detalle.strip()) < 5:
            raise HTTPException(422, 'Describí el incidente.')
        iid = uid()
        c.execute('INSERT INTO incidentes VALUES (?,?,?,?,?,?)',
                  (iid, data.registro, u['id'], data.detalle.strip(), 'abierto', time.time()))
        destinos = autoridades(c)
        avisar(c, destinos, 'Incidente reportado', data.detalle.strip())
    tareas.add_task(push_fcm, destinos, 'Incidente reportado', data.detalle)
    return {'id': iid, 'mensaje': 'Incidente informado.'}


@app.post('/incidentes/{iid}/resolver')
def resolver(iid: str, tareas: BackgroundTasks, u=Depends(usuario)):
    exigir(u, 'autoridad')
    with db(True) as c:
        incidente = c.execute('SELECT autor FROM incidentes WHERE id=?', (iid,)).fetchone()
        r = c.execute("UPDATE incidentes SET estado='resuelto' WHERE id=? AND estado='abierto'", (iid,))
        if r.rowcount != 1:
            raise HTTPException(409, 'El incidente no existe o ya fue resuelto.')
        destinos = [incidente['autor']] + autoridades(c)
        texto = f'El incidente {iid[:8].upper()} fue marcado como resuelto.'
        avisar(c, destinos, 'Incidente resuelto', texto)
    tareas.add_task(push_fcm, destinos, 'Incidente resuelto', texto)
    return {'mensaje': 'Incidente resuelto.'}


class Campania(BaseModel):
    titulo: str = Field(min_length=4, max_length=80)
    texto: str = Field(min_length=5, max_length=500)


@app.post('/campanias', status_code=201)
def campania(data: Campania, tareas: BackgroundTasks, u=Depends(usuario)):
    exigir(u, 'autoridad')
    if len(data.titulo.strip()) < 4 or len(data.texto.strip()) < 5:
        raise HTTPException(422, 'Completá el título y el mensaje.')
    with db(True) as c:
        destinos = [x['id'] for x in c.execute('SELECT id FROM usuarios').fetchall()]
        avisar(c, destinos, data.titulo.strip(), data.texto.strip())
    tareas.add_task(push_fcm, destinos, data.titulo, data.texto)
    return {'mensaje': 'Campaña publicada.'}


class Dispositivo(BaseModel):
    token: str = Field(min_length=20, max_length=4096)


@app.post('/dispositivos')
def dispositivo(data: Dispositivo, u=Depends(usuario)):
    with db(True) as c:
        c.execute('INSERT INTO dispositivos VALUES (?,?) ON CONFLICT (token) DO UPDATE SET usuario=excluded.usuario', (data.token, u['id']))
    return {'mensaje': 'Dispositivo registrado.'}


@app.delete('/dispositivos')
def quitar_dispositivo(data: Dispositivo, u=Depends(usuario)):
    with db(True) as c:
        c.execute('DELETE FROM dispositivos WHERE token=? AND usuario=?', (data.token, u['id']))
    return {'mensaje': 'Dispositivo desvinculado.'}


@app.get('/eventos')
async def eventos(request: Request, desde: float = 0, u=Depends(usuario)):
    async def generar():
        cursor = desde
        yield ': conectado\n\n'
        while not await request.is_disconnected():
            with db() as c:
                filas = c.execute('SELECT * FROM avisos WHERE usuario=? AND creado>? ORDER BY creado', (u['id'], cursor)).fetchall()
            for r in filas:
                cursor = r['creado']
                yield 'data: ' + json.dumps(dict(r), ensure_ascii=False) + '\n\n'
            yield ': vivo\n\n'
            await asyncio.sleep(2)
    return StreamingResponse(generar(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.get('/health')
def salud():
    with db() as c:
        c.execute('SELECT 1').fetchone()
    return {'estado': 'ok'}


@app.get('/live')
def vivo():
    return {'estado': 'ok'}


@app.get('/metrics', response_class=PlainTextResponse)
def metrics():
    with mutex:
        m = dict(metricas)
    return (f'# TYPE residuos_http_requests_total counter\nresiduos_http_requests_total {m["total"]}\n'
            f'# TYPE residuos_http_errors_total counter\nresiduos_http_errors_total {m["errores"]}\n'
            f'# TYPE residuos_http_duration_seconds_sum counter\nresiduos_http_duration_seconds_sum {m["segundos"]}\n')
