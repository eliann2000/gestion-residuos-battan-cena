# EcoBarrio - Gestión de residuos urbanos

Prototipo para Arquitecturas Móviles, UTN Facultad Regional San Francisco.
Integrantes: Battan Matias y Cena Elian.

## Ejecución local

Requisitos: Python 3.12 o superior y Android Studio con SDK 37. La configuración de Gradle selecciona JDK 25 para ejecutar el daemon. El proyecto usa Kotlin y vistas XML; AGP 9.4 incorpora Kotlin sin un plugin adicional. El Gradle Wrapper está incluido.

1. Ejecutar `iniciar_servidor.bat` en Windows. Crea un entorno virtual, instala las dependencias e inicia la API en el puerto 8080. En otros sistemas:

   ```sh
   cd servidor
   python -m venv .venv
   # Activar el entorno virtual según el sistema operativo.
   python -m pip install -r requirements.txt
   python -m uvicorn app:app --host 0.0.0.0 --port 8080
   ```

2. Abrir la carpeta `android` desde Android Studio, sincronizar y ejecutar el módulo `app` en un emulador. La dirección del servidor es `http://10.0.2.2:8080`.
3. En Android 17, aceptar el permiso de red local cuando se solicita al ingresar. Luego volver a pulsar Ingresar. La ubicación y las notificaciones son permisos independientes.

Para un teléfono conectado por USB: ejecutar `adb reverse tcp:8080 tcp:8080` y usar `http://127.0.0.1:8080` en el acceso. Para un servidor remoto, usar HTTPS. HTTP queda limitado a las direcciones locales de desarrollo declaradas en `network_security_config.xml`.

## Cuentas de demostración

| Perfil | Correo | Contraseña |
| --- | --- | --- |
| Ciudadano | vecino@demo.local | Demo2026! |
| Autoridad | autoridad@demo.local | Demo2026! |
| Recolector general | equipo@demo.local | Demo2026! |
| Recolector de peligrosos | especiales@demo.local | Demo2026! |

Los accesos de demostración de la pantalla inicial completan los campos. También se pueden crear nuevas cuentas ciudadanas. Los roles de autoridad y recolector se crean desde `servidor/administrar.py`, no desde el registro público.

## Flujo de uso

El ciudadano registra categoría y cantidad en kg o solicita el retiro de reciclables, voluminosos o peligrosos. Completa la dirección y sus coordenadas; puede obtenerlas con el permiso de ubicación o ingresarlas manualmente. El área admitida es San Francisco: latitud entre -31.50 y -31.35, longitud entre -62.15 y -62.0.

La autoridad selecciona solicitudes pendientes, pulsa Planificar ruta seleccionada y elige un equipo. Cada recorrido admite hasta 20 puntos y 500 kg estimados. Los peligrosos van en una ruta separada con el equipo habilitado.

El recolector consulta el recorrido y sus paradas, informa incidentes y confirma la visita ingresando el identificador de ocho caracteres mostrado en el punto. La autoridad puede resolver incidentes y publicar campañas. El ciudadano ve los cambios de su solicitud y recibe los avisos.

Los puntos de reciclaje, la base operativa y los horarios son ejemplos para el prototipo. Las direcciones escritas no se geocodifican: el mapa usa las coordenadas ingresadas. No se solicita permiso de cámara porque se implementó la alternativa de ingreso de identificador prevista por la consigna.

## Mapas y recorridos

Leaflet 1.9.4 se incluye localmente con su licencia. El fondo utiliza OpenStreetMap y requiere Internet. El mapa conserva la atribución del proveedor. El servidor consulta OSRM Trip al planificar la ruta; guarda el orden, la geometría vial, la distancia y el tiempo de conducción estimado. El proveedor público es de demostración y no informa tráfico en vivo.

Si OSRM no responde, se aplica vecino más cercano y una mejora 2-opt con distancias geográficas. La pantalla identifica expresamente esa estimación: sus líneas no representan calles ni un recorrido transitable. No se inventa una duración vial. `OSRM_ENABLED=0` fuerza esta alternativa y `OSRM_URL` permite conectar un servidor propio.

## Avisos y Firebase Cloud Messaging

La bandeja y los eventos SSE funcionan con el servidor local sin cuentas externas. SSE actualiza los paneles y genera notificaciones Android mientras el proceso de la app y su conexión siguen activos. Puede recuperar eventos al reconectar. No garantiza recepción cuando Android termina el proceso.

Para push con la app cerrada se incluye la integración FCM. Requiere un proyecto Firebase propio, habilitar la API HTTP v1 de Cloud Messaging y registrar la aplicación Android `ar.edu.utn.residuos`:

- Completar los cuatro recursos `fcm_app_id`, `fcm_api_key`, `fcm_project_id` y `fcm_sender_id` de `strings.xml` con los valores de la configuración pública de esa aplicación Firebase.
- Configurar `GOOGLE_APPLICATION_CREDENTIALS` en el servidor con la ruta a una cuenta de servicio autorizada para enviar mensajes FCM. Esa credencial privada se conserva fuera del proyecto y del APK. En contenedores se monta como secreto de solo lectura.
- Compilar de nuevo, ingresar en el teléfono y permitir notificaciones. La app registra su token en `/dispositivos`. Al cerrar sesión lo desvincula.

FCM se activa solo cuando se completan esos recursos. Los avisos también quedan guardados si el envío externo falla. La integración está incluida; la entrega externa por FCM requiere credenciales y no forma parte de las pruebas locales registradas. SSE y la bandeja sí se prueban con el servidor real.

## Persistencia y seguridad

Por defecto se usa SQLite en `servidor/datos/residuos.db`. Al reiniciar el servidor los datos permanecen. `SQLITE_PATH` permite elegir otro archivo. Las instancias de la demostración local comparten ese archivo en una sola computadora. Con `DATABASE_URL` se usa PostgreSQL mediante la misma capa de acceso para el despliegue distribuido.

Las contraseñas se guardan con PBKDF2-SHA256 y sal aleatoria. Los tokens de sesión vencen a las 24 horas y se almacenan como huellas SHA-256 en la base. Los permisos se comprueban en el servidor. La app conserva el token en memoria y pide iniciar sesión si su proceso se reinicia. No guarda contraseñas ni permite copias de seguridad de datos privados.

`DEMO=0` evita crear las cuentas de prueba. Para crear una cuenta administrativa:

```sh
cd servidor
python administrar.py --nombre "Coordinacion" --email autoridad@ejemplo.local --rol autoridad
```

La contraseña se solicita sin mostrarla. Para producción se requieren HTTPS, secretos propios, copias de seguridad y controles operativos de acceso. El prototipo no es un sistema municipal en servicio.

## Contenedores y escalado

La carpeta `infraestructura` contiene Docker Compose, balanceo Nginx, PostgreSQL, Prometheus, un panel Grafana y manifiestos Kubernetes con dos réplicas iniciales, HPA de 2 a 5 réplicas al 60 % de CPU y probes de salud. Las sesiones y avisos residen en PostgreSQL; las réplicas no necesitan afinidad de sesión. Cada SSE lee los eventos del usuario desde la base compartida.

Con Docker instalado:

```sh
cd infraestructura
copy .env.example .env
# Reemplazar las dos contraseñas de ejemplo en .env.
docker compose up --build --scale api=2
```

La entrada está en el puerto 8080. Prometheus: `http://localhost:9090`. Grafana: `http://localhost:3000`, usuario `docente` y la contraseña configurada. El panel se carga automáticamente. Las métricas incluyen cantidad de solicitudes, errores HTTP 5xx, latencia media y disponibilidad por instancia. Las contraseñas de PostgreSQL del ejemplo no deben contener caracteres que requieran codificación en una URL.

El procedimiento de Kubernetes está en `infraestructura/k8s/LEEME.md`. Los manifiestos describen el despliegue con contenedores. La prueba local de autoescalado que sigue usa procesos de la API, sin ejecutar Kubernetes.

## Monitoreo y autoescalado local sin cuentas externas

En Windows, ejecutar `iniciar_escalado.bat`. Usa Python y las dependencias del servidor. La primera vez descarga Prometheus 3.13.5 LTS portable desde el repositorio oficial y comprueba su SHA-256 antes de extraerlo. No instala servicios del sistema ni requiere una cuenta. El paquete oficial ocupa aproximadamente 103 MiB de descarga; los ejecutables y la base de métricas necesitan espacio adicional. Las descargas y series quedan en `servidor/datos/monitoreo`, fuera de las fuentes.

- Panel: `http://127.0.0.1:8090/_escala/panel`.
- Prometheus: `http://127.0.0.1:9090`.
- API balanceada: `http://127.0.0.1:8090`. En el emulador usar `http://10.0.2.2:8090` en el campo del servidor. En un teléfono USB usar `adb reverse tcp:8090 tcp:8090` y `http://127.0.0.1:8090`.

Los puertos 8090, 9090 y 8101 a 8103 deben estar libres. El servidor simple del puerto 8080 puede permanecer activo. Para detener el entorno usar Ctrl+C en su consola: el lanzador cierra los procesos que inició.

`escalado.py` inicia una instancia real de la misma API y reparte las solicitudes por turnos entre las instancias listas. Prometheus recolecta métricas cada dos segundos y descubre las réplicas a partir de un archivo de objetivos. El controlador consulta la tasa de solicitudes de los últimos 12 segundos y calcula `ceil(solicitudes_por_segundo / 8)`, con un mínimo de una instancia y un máximo de tres. Aumenta de una en una; antes de retirar cada instancia espera 15 segundos de demanda baja. Los umbrales son demostrativos para esta computadora, no una capacidad garantizada para una ciudad.

El cambio crea y termina procesos del sistema operativo: no simula contadores de instancias. Las sesiones y los registros se leen desde la misma base SQLite local. Esta base compartida es adecuada para la demostración en una sola computadora; el diseño distribuido usa PostgreSQL. Una conexión SSE de una instancia retirada puede reconectarse automáticamente.

Con el entorno activo, abrir otra consola y ejecutar, dentro de `servidor`, usando el entorno virtual:

```bat
.venv\Scripts\python.exe probar_escalado.py
```

El script utiliza la cuenta ciudadana de demostración, crea un registro y envía consultas reales a `/panel`. Comprueba el aumento 1 -> 3, el retorno 3 -> 1, el balanceo entre tres puertos, la sesión compartida y la visibilidad del registro desde todas las instancias. Guarda `datos/monitoreo/resultado_escalado.json`. Requiere las cuentas de demostración activas (`DEMO=1`, valor por defecto).

En la ejecución registrada se atendieron 1.140 consultas sin errores: 548, 320 y 272 en las tres instancias. Prometheus confirmó un máximo de tres réplicas. El panel muestra los PID reales y el historial de altas y retiros. No se ejecutó un clúster Kubernetes ni se configuraron servicios de nube para obtener estos resultados.

## Pruebas

```sh
cd servidor
python -m pip install httpx==0.28.1
python -m unittest -v test_app
```

Las pruebas usan una base SQLite temporal independiente. Para el recorrido instrumentado, iniciar el servidor con una base de demostración nueva, iniciar un emulador y ejecutar desde `android`:

```sh
gradlew.bat connectedDebugAndroidTest
```

El test realiza registros, una solicitud, su asignación, el reporte de un incidente, la confirmación y la recepción de una campaña. Guarda capturas sin modificar en el almacenamiento externo privado de la app.
