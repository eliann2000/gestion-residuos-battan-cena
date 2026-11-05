package ar.edu.utn.residuos

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.Spinner
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject

class RegistroActivity : Pantalla() {
    private var enviando = false
    private val tipo get() = intent.getStringExtra("tipo") ?: "registro"
    private val categorias get() = if (tipo == "solicitud") listOf("reciclables", "voluminosos", "peligrosos") else listOf("comunes", "reciclables", "voluminosos", "peligrosos")
    private var listener: LocationListener? = null
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_registro)
        findViewById<TextView>(R.id.titulo).text = if (tipo == "solicitud") "Solicitar recolección" else "Registrar residuos"
        findViewById<Spinner>(R.id.categoria).adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, categorias.map { it.replaceFirstChar { c -> c.uppercase() } })
        findViewById<Button>(R.id.guardar).setOnClickListener { guardar() }
        findViewById<Button>(R.id.volver).setOnClickListener { finish() }
        findViewById<Button>(R.id.ubicacion).setOnClickListener {
            if (checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED)
                requestPermissions(arrayOf(Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION), 10)
            else localizar()
        }
        findViewById<Button>(R.id.verUbicacion).setOnClickListener {
            val lat = numero(R.id.latitud); val lon = numero(R.id.longitud)
            if (!valida(lat, lon)) { error("Ingresá coordenadas válidas de San Francisco."); return@setOnClickListener }
            val p = JSONObject().put("lat", lat).put("lon", lon).put("nombre", "Ubicación de tu solicitud")
            startActivity(Intent(this, MapaActivity::class.java).putExtra("puntos", JSONArray().put(p).toString()).putExtra("titulo", "Ubicación de recolección"))
        }
    }
    private fun valor(id: Int) = findViewById<EditText>(id).text.toString().trim()
    private fun numero(id: Int) = valor(id).replace(',', '.').toDoubleOrNull()
    private fun error(m: String) { findViewById<TextView>(R.id.error).text = m }
    private fun valida(lat: Double?, lon: Double?) = lat != null && lon != null && lat.isFinite() && lon.isFinite() && lat in -31.50..-31.35 && lon in -62.15..-62.0
    private fun guardar() {
        if (enviando) return
        val cantidad = numero(R.id.cantidad)
        val lat = numero(R.id.latitud); val lon = numero(R.id.longitud)
        if (cantidad == null || !cantidad.isFinite() || cantidad <= 0 || cantidad > 500) { error("Ingresá una cantidad mayor a 0 y de hasta 500 kg."); return }
        if (valor(R.id.direccion).length < 4) { error("Completá la dirección de recolección."); return }
        if (!valida(lat, lon)) { error("Ingresá las coordenadas de San Francisco o usá tu ubicación."); return }
        val data = JSONObject().put("tipo", tipo).put("categoria", categorias[findViewById<Spinner>(R.id.categoria).selectedItemPosition])
            .put("cantidad", cantidad).put("direccion", valor(R.id.direccion)).put("lat", lat).put("lon", lon).put("nota", valor(R.id.nota))
        enviando = true; findViewById<Button>(R.id.guardar).isEnabled = false
        Api.pedir("/registros", "POST", data, { aviso(it.texto("mensaje")); finish() }, {
            enviando = false; findViewById<Button>(R.id.guardar).isEnabled = true; error(it)
        })
    }
    override fun onRequestPermissionsResult(code: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(code, permissions, grantResults)
        if (code == 10 && checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED) localizar()
        else error("Podés ingresar las coordenadas manualmente sin conceder ubicación.")
    }
    @Suppress("MissingPermission")
    private fun localizar() {
        val manager = getSystemService(LocationManager::class.java)
        val providers = manager.getProviders(true).filter { it == LocationManager.GPS_PROVIDER || it == LocationManager.NETWORK_PROVIDER }
        if (providers.isEmpty()) { error("Activá la ubicación del dispositivo o ingresá las coordenadas."); return }
        error("Buscando ubicación…")
        val l = LocationListener { loc ->
            findViewById<EditText>(R.id.latitud).setText(loc.latitude.toString())
            findViewById<EditText>(R.id.longitud).setText(loc.longitude.toString())
            error(if (valida(loc.latitude, loc.longitude)) "Ubicación obtenida." else "La ubicación está fuera de San Francisco. Ingresá la del punto de recolección.")
            listener?.let { manager.removeUpdates(it) }; listener = null
        }
        listener?.let { manager.removeUpdates(it) }; listener = l
        providers.forEach { manager.requestLocationUpdates(it, 1000L, 0f, l) }
        findViewById<Button>(R.id.ubicacion).postDelayed({
            if (listener === l) { manager.removeUpdates(l); listener = null; error("No se obtuvo ubicación. Podés ingresar las coordenadas manualmente.") }
        }, 15000)
    }
    override fun onStop() {
        listener?.let { getSystemService(LocationManager::class.java).removeUpdates(it) }; listener = null
        super.onStop()
    }
}
