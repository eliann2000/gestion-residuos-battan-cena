import hashlib
import json
import os
import urllib.request
import zipfile
from pathlib import Path

VERSION = '3.13.5'
SHA256 = '846398b50b90e02f69960342190a1d01bf9a335b3aeee69bfd6ead41d3a314c5'
DATOS = Path(os.getenv('ESCALA_DATOS', 'datos/monitoreo')).resolve()


def preparar():
    if os.name != 'nt':
        raise RuntimeError('Este lanzador portable es para Windows. Los otros entornos disponen de Docker Compose.')
    DATOS.mkdir(parents=True, exist_ok=True)
    carpeta = DATOS / ('prometheus-' + VERSION)
    exe = carpeta / 'prometheus.exe'
    if not exe.exists():
        archivo = DATOS / 'prometheus.zip'
        url = f'https://github.com/prometheus/prometheus/releases/download/v{VERSION}/prometheus-{VERSION}.windows-amd64.zip'
        print('Descargando Prometheus portable desde su repositorio oficial...', flush=True)
        urllib.request.urlretrieve(url, archivo)
        if hashlib.sha256(archivo.read_bytes()).hexdigest() != SHA256:
            raise RuntimeError('La descarga no coincide con la huella oficial. No se ejecutará.')
        carpeta.mkdir(exist_ok=True)
        with zipfile.ZipFile(archivo) as z:
            for nombre in ['prometheus.exe', 'promtool.exe', 'LICENSE', 'NOTICE']:
                item = next(n for n in z.namelist() if n.endswith('/'+nombre))
                (carpeta/nombre).write_bytes(z.read(item))
        archivo.unlink()
    (DATOS/'objetivos.json').write_text('[]', encoding='utf-8')
    config = '''global:
  scrape_interval: 2s
  evaluation_interval: 2s
scrape_configs:
  - job_name: balanceador
    static_configs:
      - targets: ['127.0.0.1:8090']
  - job_name: residuos
    file_sd_configs:
      - files: [OBJETIVOS]
        refresh_interval: 2s
'''.replace('OBJETIVOS', json.dumps(str(DATOS/'objetivos.json').replace('\\','/')))
    (DATOS/'prometheus.yml').write_text(config, encoding='utf-8')
    return exe


if __name__ == '__main__':
    print(preparar())
