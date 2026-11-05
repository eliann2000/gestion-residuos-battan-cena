# Ejecución en Kubernetes

Se requiere un clúster con almacenamiento dinámico y Metrics Server. El HPA usa el consumo de CPU relativo al request de 100m. Sin Metrics Server no puede calcular esa utilización.

Ejemplo con un clúster local Minikube y Docker instalados:

```sh
minikube start
minikube addons enable metrics-server
docker build -t residuos-api:1.0 ../../servidor
minikube image load residuos-api:1.0
kubectl create namespace residuos
```

Crear un archivo local `config.env`, fuera del control de versiones, con valores propios:

```text
DB_PASSWORD=una_clave_propia_alfanumerica
DATABASE_URL=postgresql://residuos:una_clave_propia_alfanumerica@postgres:5432/residuos
```

La clave debe coincidir en ambas variables. Luego:

```sh
kubectl -n residuos create secret generic residuos-config --from-env-file=config.env
kubectl apply -f postgres.yaml
kubectl apply -f aplicacion.yaml
kubectl -n residuos rollout status statefulset/postgres
kubectl -n residuos rollout status deployment/api
kubectl -n residuos get pods,hpa
kubectl -n residuos port-forward service/api 8080:8080
```

En un registro remoto se reemplaza la imagen del Deployment por su nombre publicado. Para acceso público se agrega un Ingress o balanceador de la plataforma con TLS y un nombre DNS propio. El Service distribuye las conexiones entre pods disponibles. Una sesión SSE queda en un pod mientras está conectada; si se interrumpe, la app reconecta y consulta desde su último evento.

La base del ejemplo tiene una única instancia persistente: no ofrece alta disponibilidad de PostgreSQL. Una instalación municipal debería usar una base gestionada con respaldo, réplicas y recuperación probada. El HPA escala la API, no la base.

Para observar el escalado se puede ejecutar un generador de solicitudes autenticadas contra `/panel` y consultar `kubectl -n residuos get hpa -w` y `kubectl -n residuos top pods`. La cantidad de réplicas depende de la CPU medida; no se presupone que una carga pequeña dispare el HPA. Al retirar la carga, la reducción espera al menos 120 segundos.

El monitoreo del ejemplo Compose utiliza descubrimiento DNS para recolectar `/metrics` en cada réplica. En Kubernetes, el mismo panel puede conectarse a Prometheus instalado en el clúster y descubrir los pods con etiqueta `app=residuos-api`. El endpoint `/health` comprueba el acceso a la base. Un pod sin readiness queda fuera del servicio; liveness usa `/live`, que comprueba la respuesta del proceso sin depender de la base. Así se evitan reinicios durante una falla compartida de PostgreSQL.

Se proponen alertas por disponibilidad nula durante 1 minuto, más de 5 % de errores 5xx durante 5 minutos y latencia media superior a 2 segundos durante 5 minutos. Son umbrales iniciales a ajustar con mediciones; no representan alertas disparadas en un despliegue real de esta prueba.
