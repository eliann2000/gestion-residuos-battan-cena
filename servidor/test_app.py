import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app import app
from ruteo import BASE, distancia, optimizar


class SistemaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.environ['SQLITE_PATH'] = self.temp.name + '/prueba.db'
        os.environ['OSRM_ENABLED'] = '0'
        os.environ['DEMO'] = '1'
        os.environ.pop('DATABASE_URL', None)
        self.context = TestClient(app)
        self.client = self.context.__enter__()
        self.vecino = self.login('vecino')
        self.autoridad = self.login('autoridad')
        self.equipo = self.login('equipo')
        self.especiales = self.login('especiales')

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.temp.cleanup()

    def login(self, nombre):
        r = self.client.post('/login', json={'email': nombre+'@demo.local', 'password': 'Demo2026!'})
        self.assertEqual(r.status_code, 200, r.text)
        return {'Authorization': 'Bearer ' + r.json()['token']}

    def solicitud(self, categoria='reciclables', **cambios):
        body = {'tipo': 'solicitud', 'categoria': categoria, 'cantidad': 10,
                'direccion': 'Av. del Libertador 250 (prueba)', 'lat': -31.424, 'lon': -62.081, 'nota': ''}
        body.update(cambios)
        return self.client.post('/registros', headers=self.vecino, json=body)

    def asignar(self, ids, equipo='equipo1'):
        return self.client.post('/rutas', headers=self.autoridad, json={'registros': ids, 'recolector': equipo})

    def panel(self, headers):
        r = self.client.get('/panel', headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_01_sin_sesion_y_clave_incorrecta(self):
        self.assertEqual(self.client.get('/panel').status_code, 401)
        self.assertEqual(self.client.post('/login', json={'email': 'vecino@demo.local', 'password': 'x'}).status_code, 401)

    def test_02_registro_ciudadano_sin_elevacion_de_rol(self):
        body = {'nombre': 'Persona de prueba', 'email': 'nuevo@demo.local', 'password': 'Prueba2026!', 'rol': 'autoridad'}
        self.assertEqual(self.client.post('/usuarios', json=body).status_code, 201)
        self.assertEqual(self.client.post('/usuarios', json=body).status_code, 409)
        self.assertEqual(self.panel(self.login_nuevo())['usuario']['rol'], 'ciudadano')

    def login_nuevo(self):
        r = self.client.post('/login', json={'email': 'nuevo@demo.local', 'password': 'Prueba2026!'})
        return {'Authorization': 'Bearer '+r.json()['token']}

    def test_03_registro_de_residuo_no_genera_retiro(self):
        self.assertEqual(self.solicitud('comunes', tipo='registro').status_code, 201)
        r = self.panel(self.vecino)['registros'][0]
        self.assertEqual(r['estado'], 'registrado')
        self.assertEqual(self.asignar([r['id']]).status_code, 409)

    def test_04_validaciones_cantidad_categoria_coordenadas(self):
        for cambio in [{'cantidad': 0}, {'cantidad': -5}, {'cantidad': 501}, {'lat': 0}, {'lon': 0}, {'categoria': 'otro'}, {'direccion': '   '}]:
            self.assertEqual(self.solicitud(**cambio).status_code, 422, cambio)
        self.assertEqual(self.solicitud('comunes').status_code, 422)

    def test_05_restricciones_de_roles(self):
        self.assertEqual(self.client.post('/rutas', headers=self.vecino, json={'registros': ['x'], 'recolector': 'equipo1'}).status_code, 403)
        self.assertEqual(self.client.post('/campanias', headers=self.equipo, json={'titulo': 'Campaña', 'texto': 'Prueba de campaña'}).status_code, 403)
        body = {'tipo': 'registro', 'categoria': 'comunes', 'cantidad': 1, 'direccion': 'Prueba 250', 'lat': -31.42, 'lon': -62.08}
        self.assertEqual(self.client.post('/registros', headers=self.autoridad, json=body).status_code, 403)

    def test_06_flujo_completo_y_confirmacion_unica(self):
        rid = self.solicitud().json()['id']
        self.assertEqual(self.asignar([rid]).status_code, 201)
        self.assertEqual(self.panel(self.equipo)['registros'][0]['estado'], 'asignado')
        url = '/registros/'+rid+'/confirmar'
        self.assertEqual(self.client.post(url, headers=self.equipo, json={'identificador': 'incorrecto'}).status_code, 422)
        self.assertEqual(self.client.post(url, headers=self.especiales, json={'identificador': rid[:8]}).status_code, 404)
        self.assertEqual(self.client.post(url, headers=self.equipo, json={'identificador': rid[:8]}).status_code, 200)
        self.assertEqual(self.client.post(url, headers=self.equipo, json={'identificador': rid[:8]}).status_code, 409)
        self.assertEqual(self.panel(self.vecino)['registros'][0]['estado'], 'recolectado')

    def test_07_visibilidad_por_propietario(self):
        self.solicitud()
        self.client.post('/usuarios', json={'nombre': 'Otra persona', 'email': 'nuevo@demo.local', 'password': 'Prueba2026!'})
        self.assertEqual(self.panel(self.login_nuevo())['registros'], [])
        self.assertEqual(self.panel(self.equipo)['registros'], [])
        self.assertEqual(len(self.panel(self.autoridad)['registros']), 1)

    def test_08_peligrosos_separados_y_equipo_habilitado(self):
        p = self.solicitud('peligrosos').json()['id']
        r = self.solicitud().json()['id']
        self.assertEqual(self.asignar([p]).status_code, 422)
        self.assertEqual(self.asignar([p, r], 'especiales').status_code, 422)
        self.assertEqual(self.asignar([p], 'especiales').status_code, 201)

    def test_09_capacidad_y_duplicados(self):
        a = self.solicitud(cantidad=300).json()['id']
        b = self.solicitud(cantidad=300).json()['id']
        self.assertEqual(self.asignar([a, b]).status_code, 422)
        self.assertEqual(self.asignar([a, a]).status_code, 422)
        self.assertEqual(self.asignar([a], 'inexistente').status_code, 422)

    def test_10_incidente_y_resolucion(self):
        rid = self.solicitud().json()['id']
        self.asignar([rid])
        body = {'registro': rid, 'detalle': 'Contenedor dañado en la tapa.'}
        self.assertEqual(self.client.post('/incidentes', headers=self.especiales, json=body).status_code, 403)
        r = self.client.post('/incidentes', headers=self.equipo, json=body)
        self.assertEqual(r.status_code, 201, r.text)
        iid = r.json()['id']
        self.assertEqual(self.client.post('/incidentes/'+iid+'/resolver', headers=self.equipo).status_code, 403)
        self.assertEqual(self.client.post('/incidentes/'+iid+'/resolver', headers=self.autoridad).status_code, 200)
        self.assertEqual(self.panel(self.autoridad)['incidentes'][0]['estado'], 'resuelto')
        self.assertEqual(self.panel(self.equipo)['avisos'][0]['titulo'], 'Incidente resuelto')
        self.assertEqual(self.panel(self.autoridad)['avisos'][0]['titulo'], 'Incidente resuelto')

    def test_11_campania_distribuida(self):
        r = self.client.post('/campanias', headers=self.autoridad, json={'titulo': 'Sábado de reciclaje', 'texto': 'Actividad de demostración de 9 a 12 h.'})
        self.assertEqual(r.status_code, 201)
        for u in [self.vecino, self.equipo, self.especiales]:
            self.assertEqual(self.panel(u)['avisos'][0]['titulo'], 'Sábado de reciclaje')

    def test_12_logout_revoca_token(self):
        self.assertEqual(self.client.post('/logout', headers=self.vecino).status_code, 200)
        self.assertEqual(self.client.get('/panel', headers=self.vecino).status_code, 401)

    def test_13_avisos_por_cambio_de_estado(self):
        rid = self.solicitud().json()['id']
        self.assertEqual(self.panel(self.autoridad)['avisos'][0]['titulo'], 'Nueva solicitud')
        self.asignar([rid])
        self.assertEqual(self.panel(self.vecino)['avisos'][0]['titulo'], 'Recolección asignada')
        self.assertEqual(self.panel(self.equipo)['avisos'][0]['titulo'], 'Nueva ruta asignada')
        self.assertEqual(self.panel(self.autoridad)['avisos'][0]['titulo'], 'Ruta asignada')

    def test_14_asignacion_concurrente_no_duplica(self):
        rid = self.solicitud().json()['id']
        with ThreadPoolExecutor(max_workers=2) as pool:
            estados = sorted(pool.map(lambda _: self.asignar([rid]).status_code, range(2)))
        self.assertEqual(estados, [201, 409])
        self.assertEqual(len(self.panel(self.autoridad)['rutas']), 1)

    def test_15_orden_y_estimacion_geografica(self):
        ps = [{'id': 'a', 'lat': -31.420, 'lon': -62.09}, {'id': 'b', 'lat': -31.43, 'lon': -62.08}, {'id': 'c', 'lat': -31.425, 'lon': -62.078}]
        ruta = optimizar(ps)
        self.assertEqual(set(ruta['orden']), {'a', 'b', 'c'})
        self.assertEqual(ruta['geometria'][0], list(reversed(BASE)))
        self.assertEqual(ruta['geometria'][0], ruta['geometria'][-1])
        self.assertGreater(ruta['metros'], 0)
        self.assertIsNone(ruta['segundos'])
        self.assertIn('no sigue calles', ruta['proveedor'])
        self.assertEqual(distancia(BASE, BASE), 0)

    def test_16_health_metricas_y_puntos(self):
        self.assertEqual(self.client.get('/health').json()['estado'], 'ok')
        self.assertIn('residuos_http_requests_total', self.client.get('/metrics').text)
        puntos = self.panel(self.vecino)['puntos']
        self.assertEqual(len(puntos), 3)
        self.assertTrue(all('demostrativo' in p['nombre'] for p in puntos))


if __name__ == '__main__':
    unittest.main(verbosity=2)
