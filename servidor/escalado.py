import asyncio
import json
import math
import os
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse

from preparar_monitor import DATOS, preparar

RAIZ = Path(__file__).resolve().parent
PROMETHEUS = 'http://127.0.0.1:9090'
OBJETIVO_RPS = 8
MAXIMAS = 3
ESTABILIZACION = 15
replicas = []
historial = []
total = errores = indice = 0
tasa = 0.0
cliente = None
ultimo_error = ''


def libre(puerto):
    with socket.socket() as s:
        s.bind(('127.0.0.1', puerto))


def evento(accion, instancia):
    fila = {'fecha': time.time(), 'accion': accion, 'replicas': len(replicas),
            'pid': instancia['proceso'].pid, 'puerto': instancia['puerto'], 'rps': round(tasa, 3)}
    historial.append(fila)
    with (DATOS/'eventos.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(fila)+'\n')
    (DATOS/'objetivos.json').write_text(json.dumps([{'targets': [f'127.0.0.1:{r["puerto"]}' for r in replicas]}]), encoding='utf-8')


async def agregar():
    puerto = next(p for p in range(8101, 8101+MAXIMAS) if all(r['puerto'] != p for r in replicas))
    libre(puerto)
    log = (DATOS/f'api-{puerto}.log').open('a', encoding='utf-8')
    proceso = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1',
        '--port', str(puerto), '--no-access-log'], cwd=RAIZ, stdout=log, stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        for _ in range(100):
            if proceso.poll() is not None:
                raise RuntimeError(f'La API del puerto {puerto} no arrancó. Consultá su registro.')
            try:
                r = await cliente.get(f'http://127.0.0.1:{puerto}/health', timeout=1)
                if r.status_code == 200:
                    instancia = {'puerto': puerto, 'proceso': proceso, 'activas': 0, 'log': log}
                    replicas.append(instancia); evento('inicio', instancia)
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(.2)
        raise RuntimeError('La nueva API no quedó lista dentro del tiempo previsto.')
    except Exception:
        proceso.terminate(); proceso.wait(timeout=10); log.close()
        raise


async def retirar(instancia):
    replicas.remove(instancia); evento('retiro', instancia)
    for _ in range(20):
        if instancia['activas'] == 0: break
        await asyncio.sleep(.2)
    proceso = instancia['proceso']
    proceso.terminate()
    try: await asyncio.to_thread(proceso.wait, timeout=8)
    except subprocess.TimeoutExpired:
        proceso.kill(); await asyncio.to_thread(proceso.wait)
    instancia['log'].close()


async def consultar(expresion):
    r = await cliente.get(PROMETHEUS+'/api/v1/query', params={'query': expresion}, timeout=3)
    r.raise_for_status()
    data = r.json()
    if data.get('status') != 'success': raise RuntimeError('Prometheus no pudo resolver la consulta.')
    resultados = data['data']['result']
    return float(resultados[0]['value'][1]) if resultados else 0.0


async def controlar():
    global tasa, ultimo_error
    bajo_desde = None
    while True:
        await asyncio.sleep(2)
        try:
            tasa = await consultar('sum(rate(residuos_proxy_requests_total[12s]))')
            deseadas = min(MAXIMAS, max(1, math.ceil(tasa/OBJETIVO_RPS)))
            if deseadas > len(replicas):
                bajo_desde = None
                await agregar()
            elif deseadas < len(replicas):
                bajo_desde = bajo_desde or time.monotonic()
                if time.monotonic()-bajo_desde >= ESTABILIZACION:
                    await retirar(min(replicas, key=lambda x: x['activas']))
                    bajo_desde = None
            else: bajo_desde = None
            ultimo_error = ''
        except Exception as e:
            ultimo_error = str(e)


@asynccontextmanager
async def vida(app):
    global cliente
    DATOS.mkdir(parents=True, exist_ok=True)
    cliente = httpx.AsyncClient(timeout=20, trust_env=False)
    tarea = None
    try:
        await agregar()
        tarea = asyncio.create_task(controlar())
        yield
    finally:
        if tarea:
            tarea.cancel()
            try: await tarea
            except asyncio.CancelledError: pass
        for instancia in list(replicas): await retirar(instancia)
        await cliente.aclose()


app = FastAPI(lifespan=vida, docs_url=None, redoc_url=None)


@app.get('/_escala/panel')
def panel():
    return FileResponse(RAIZ/'panel_monitoreo.html')


@app.get('/_escala/estado')
async def estado():
    try:
        disponibles = await consultar('sum(up{job="residuos"})')
        latencia = await consultar('sum(rate(residuos_http_duration_seconds_sum[12s])) / clamp_min(sum(rate(residuos_http_requests_total[12s])), 0.001)')
    except Exception:
        disponibles = latencia = None
    return {'replicas': [{'puerto': r['puerto'], 'pid': r['proceso'].pid, 'viva': r['proceso'].poll() is None,
                         'activas': r['activas']} for r in replicas],
            'rps': tasa, 'total': total, 'errores': errores, 'latencia_media': latencia,
            'disponibles_prometheus': disponibles, 'eventos': historial[-30:],
            'objetivo_rps_por_replica': OBJETIVO_RPS, 'maximas': MAXIMAS, 'estabilizacion_segundos': ESTABILIZACION,
            'error_monitor': ultimo_error}


@app.get('/metrics', response_class=PlainTextResponse)
def metrics():
    return (f'# TYPE residuos_proxy_requests_total counter\nresiduos_proxy_requests_total {total}\n'
            f'# TYPE residuos_proxy_errors_total counter\nresiduos_proxy_errors_total {errores}\n'
            f'# TYPE residuos_replicas_activas gauge\nresiduos_replicas_activas {len(replicas)}\n')


@app.api_route('/{ruta:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
async def proxy(ruta: str, request: Request):
    global total, errores, indice
    if not replicas: return JSONResponse({'detail': 'No hay instancias listas.'}, status_code=503)
    instancia = replicas[indice % len(replicas)]; indice += 1
    instancia['activas'] += 1; total += 1
    headers = {k: v for k,v in request.headers.items() if k.lower() not in ['host', 'connection', 'content-length']}
    url = f'http://127.0.0.1:{instancia["puerto"]}/{ruta}'
    if request.url.query: url += '?'+request.url.query
    try:
        req = cliente.build_request(request.method, url, headers=headers, content=await request.body())
        respuesta = await cliente.send(req, stream=True)
    except httpx.HTTPError:
        instancia['activas'] -= 1; errores += 1
        return JSONResponse({'detail': 'La instancia no respondió. Volvé a intentar.'}, status_code=503)
    if respuesta.status_code >= 500: errores += 1
    async def cuerpo():
        try:
            async for chunk in respuesta.aiter_bytes(): yield chunk
        finally:
            instancia['activas'] -= 1
            await respuesta.aclose()
    copia = {k:v for k,v in respuesta.headers.items() if k.lower() not in ['content-length','content-encoding','transfer-encoding','connection']}
    copia['X-Instancia-Puerto'] = str(instancia['puerto'])
    copia['X-Instancia-Pid'] = str(instancia['proceso'].pid)
    return StreamingResponse(cuerpo(), status_code=respuesta.status_code, headers=copia)


if __name__ == '__main__':
    libre(8090); libre(9090)
    exe = preparar()
    log = (DATOS/'prometheus.log').open('a', encoding='utf-8')
    prom = subprocess.Popen([str(exe), '--config.file='+str(DATOS/'prometheus.yml'),
        '--storage.tsdb.path='+str(DATOS/'series'), '--storage.tsdb.retention.time=1d',
        '--storage.tsdb.retention.size=128MB', '--web.listen-address=127.0.0.1:9090'], stdout=log, stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        print('Panel: http://127.0.0.1:8090/_escala/panel | Prometheus: http://127.0.0.1:9090', flush=True)
        uvicorn.run(app, host='127.0.0.1', port=8090, log_level='warning')
    finally:
        prom.terminate(); prom.wait(timeout=10); log.close()
