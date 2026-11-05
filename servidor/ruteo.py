import json
import math
import os
import urllib.request

BASE = [-31.4275, -62.0820]


def distancia(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [*a, *b])
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6_371_000 * 2 * math.asin(math.sqrt(min(1, h)))


def optimizar(puntos):
    pendientes, orden, actual = list(puntos), [], BASE
    while pendientes:
        p = min(pendientes, key=lambda x: distancia(actual, [x['lat'], x['lon']]))
        orden.append(p)
        pendientes.remove(p)
        actual = [p['lat'], p['lon']]
    coords = [BASE] + [[p['lat'], p['lon']] for p in orden] + [BASE]
    # Una mejora 2-opt evita cruces innecesarios en el recorrido estimado.
    cambio = True
    while cambio:
        cambio = False
        for i in range(1, len(coords)-2):
            for j in range(i+1, len(coords)-1):
                antes = distancia(coords[i-1], coords[i]) + distancia(coords[j], coords[j+1])
                despues = distancia(coords[i-1], coords[j]) + distancia(coords[i], coords[j+1])
                if despues + .01 < antes:
                    coords[i:j+1] = reversed(coords[i:j+1])
                    orden[i-1:j] = reversed(orden[i-1:j])
                    cambio = True
    resultado = {'orden': [p['id'] for p in orden], 'geometria': [[b, a] for a, b in coords],
                 'metros': round(sum(distancia(a, b) for a, b in zip(coords, coords[1:]))),
                 'segundos': None, 'proveedor': 'Estimación geográfica; no sigue calles ni tráfico'}
    if os.getenv('OSRM_ENABLED', '1') == '0':
        return resultado
    host = os.getenv('OSRM_URL', 'https://router.project-osrm.org').rstrip('/')
    coords_in = [BASE] + [[p['lat'], p['lon']] for p in puntos]
    cadena = ';'.join(f'{lon},{lat}' for lat, lon in coords_in)
    url = f'{host}/trip/v1/driving/{cadena}?roundtrip=true&source=first&geometries=geojson&overview=full'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'GestionResiduosUTN/1.0 (academic prototype)'})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
        if data.get('code') != 'Ok' or len(data['trips']) != 1:
            return resultado
        orden_osrm = sorted(zip(data['waypoints'][1:], puntos), key=lambda x: x[0]['waypoint_index'])
        t = data['trips'][0]
        return {'orden': [p['id'] for _, p in orden_osrm], 'geometria': t['geometry']['coordinates'],
                'metros': round(t['distance']), 'segundos': round(t['duration']),
                'proveedor': 'OSRM - recorrido vial aproximado, sin tráfico en vivo'}
    except (OSError, ValueError, KeyError, IndexError):
        return resultado
