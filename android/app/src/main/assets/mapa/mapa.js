const mapa = L.map('mapa').setView([-31.4275, -62.0820], 14);
const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>', maxZoom: 19
}).addTo(mapa);
tiles.on('tileerror', () => document.getElementById('mensaje').style.display = 'block');
tiles.on('tileload', () => document.getElementById('mensaje').style.display = 'none');
window.mostrar = function(puntos, geometria) {
  const limites = [];
  puntos.forEach((p, i) => {
    const icono = L.divIcon({className: 'punto', html: String(i+1), iconSize: [28,28]});
    const nodo = document.createElement('div');
    const titulo = document.createElement('strong');
    titulo.textContent = p.nombre || p.direccion || 'Punto de recolección';
    nodo.append(titulo, document.createElement('br'));
    const detalle = document.createElement('span');
    detalle.textContent = p.horario || ((p.categoria || '') + ' · ' + (p.estado || ''));
    nodo.append(detalle);
    L.marker([p.lat,p.lon], {icon: icono}).addTo(mapa).bindPopup(nodo);
    limites.push([p.lat,p.lon]);
  });
  if (geometria.length) {
    const linea = geometria.map(p => [p[1],p[0]]);
    L.polyline(linea, {color:'#167550',weight:5}).addTo(mapa);
    limites.push(...linea);
  }
  if (limites.length) mapa.fitBounds(limites, {padding:[35,35],maxZoom:15});
};
