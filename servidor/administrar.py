import argparse
import getpass

from datos import clave, db, iniciar
from app import uid

p = argparse.ArgumentParser(description='Crear una cuenta del sistema')
p.add_argument('--nombre', required=True)
p.add_argument('--email', required=True)
p.add_argument('--rol', choices=['ciudadano', 'autoridad', 'recolector'], required=True)
p.add_argument('--peligrosos', action='store_true')
a = p.parse_args()
password = getpass.getpass('Contraseña (mínimo 8 caracteres): ')
if len(password) < 8:
    p.error('La contraseña es demasiado corta.')
iniciar()
with db(True) as c:
    c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?,?)',
              (uid(), a.nombre, a.email.strip().lower(), clave(password), a.rol, int(a.peligrosos)))
print('Cuenta creada.')
