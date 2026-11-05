package ar.edu.utn.residuos

import android.os.Handler
import android.os.Looper
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

object Api {
    var base = "http://10.0.2.2:8080"
    @Volatile var token = ""
    var usuario = JSONObject()
    var cursorAvisos = 0.0
    val executor = Executors.newFixedThreadPool(4)
    private val main = Handler(Looper.getMainLooper())

    fun pedir(path: String, method: String = "GET", body: JSONObject? = null,
              ok: (JSONObject) -> Unit, error: (String) -> Unit) {
        executor.execute {
            var conexion: HttpURLConnection? = null
            try {
                conexion = URL(base + path).openConnection() as HttpURLConnection
                conexion.requestMethod = method
                conexion.connectTimeout = 12000
                conexion.readTimeout = 20000
                conexion.setRequestProperty("Authorization", "Bearer $token")
                conexion.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                if (body != null) {
                    conexion.doOutput = true
                    conexion.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
                }
                val code = conexion.responseCode
                val stream = if (code in 200..299) conexion.inputStream else conexion.errorStream
                val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: "{}"
                val json = JSONObject(text)
                if (code !in 200..299) {
                    val detalle = json.opt("detail")
                    val mensaje = if (detalle is String) detalle else "Revisá los campos y la ubicación ingresada."
                    if (code == 401 && path != "/login") token = ""
                    main.post { error(mensaje) }
                } else main.post { ok(json) }
            } catch (e: Exception) {
                android.util.Log.w("ResiduosAPI", "Error de comunicación: ${e.javaClass.simpleName}", e)
                main.post { error("No se pudo conectar. Revisá el servidor y tu conexión.") }
            } finally { conexion?.disconnect() }
        }
    }
}

fun JSONArray.objetos(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
fun JSONObject.lista(nombre: String): List<JSONObject> = optJSONArray(nombre)?.objetos() ?: emptyList()
fun JSONObject.texto(nombre: String): String = optString(nombre, "")
fun codigo(id: String): String = id.take(8).uppercase()
