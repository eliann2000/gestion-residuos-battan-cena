import asyncio
import json
import time
from collections import Counter
from pathlib import Path

import httpx

BASE = 'http://127.0.0.1:8090'
PROM = 'http://127.0.0.1:9090'


async def probar():
    muestras, puertos, fallos = [], Counter(), []
    async with httpx.AsyncClient(timeout=15, trust_env=False) as c:
        acceso = await c.post(BASE+'/login', json={'email': 'vecino@demo.local', 'password': 'Demo2026!'})
        acceso.raise_for_status()
        headers = {'Authorization': 'Bearer '+acceso.json()['token']}
        dato = {'tipo': 'registro', 'categoria': 'reciclables', 'cantidad': 3,
                'direccion': 'Punto de prueba de escalado', 'lat': -31.427, 'lon': -62.081}
        registro = await c.post(BASE+'/registros', json=dato, headers=headers)
        registro.raise_for_status(); rid = registro.json()['id']

        async def muestra(fase):
            r = await c.get(BASE+'/_escala/estado'); r.raise_for_status()
            d = r.json()
            muestras.append({'fase': fase, 'fecha': time.time(), **d})
            print(f'{fase}: {len(d["replicas"])} instancias, {d["rps"]:.1f} solicitudes/s, errores={d["errores"]}', flush=True)
            return d

        async def peticiones():
            for _ in range(95):
                inicio = time.monotonic()
                try:
                    r = await c.get(BASE+'/panel', headers=headers)
                    if r.status_code != 200: fallos.append(r.status_code)
                    else:
                        puertos[r.headers.get('x-instancia-puerto')] += 1
                        if not any(x['id'] == rid for x in r.json()['registros']): fallos.append('registro no visible')
                except httpx.HTTPError as e: fallos.append(type(e).__name__)
                await asyncio.sleep(max(0, .4-(time.monotonic()-inicio)))

        await asyncio.sleep(12)
        inicial = await muestra('reposo')
        assert len(inicial['replicas']) == 1
        tareas = [asyncio.create_task(peticiones()) for _ in range(12)]
        for _ in range(10):
            await asyncio.sleep(4)
            await muestra('carga')
        await asyncio.gather(*tareas)
        for _ in range(30):
            await asyncio.sleep(2)
            fin = await muestra('recuperacion')
            if len(fin['replicas']) == 1 and fin['rps'] < 1: break
        assert max(len(m['replicas']) for m in muestras) == 3, 'No aumentó hasta tres instancias'
        assert len(fin['replicas']) == 1, 'No redujo al retirar la carga'
        assert len(puertos) == 3, 'El balanceador no distribuyó entre las tres instancias'
        assert not fallos, fallos[:10]
        assert fin['errores'] == 0
        await asyncio.sleep(4)
        metricas = await c.get(PROM+'/api/v1/query', params={'query': 'max_over_time(residuos_replicas_activas[5m])'})
        metricas.raise_for_status()
        assert float(metricas.json()['data']['result'][0]['value'][1]) == 3
        resultado = {'resultado': 'APROBADO', 'secuencia': '1 -> 3 -> 1', 'peticiones_por_instancia': dict(puertos),
                     'peticiones_comprobadas': sum(puertos.values()), 'errores': fallos,
                     'datos_compartidos': True, 'maximo_verificado_en_prometheus': 3,
                     'muestras': muestras, 'eventos': fin['eventos']}
        salida = Path('datos/monitoreo/resultado_escalado.json')
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
        print('APROBADO: autoescalado real 1 -> 3 -> 1, balanceo, sesión y datos compartidos.', flush=True)


if __name__ == '__main__':
    asyncio.run(probar())
