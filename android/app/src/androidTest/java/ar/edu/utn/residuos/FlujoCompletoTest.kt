package ar.edu.utn.residuos

import android.graphics.Bitmap
import android.os.SystemClock
import android.view.View
import android.widget.Button
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.*
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.*
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.hamcrest.Matcher
import org.hamcrest.Matchers.allOf
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject

@RunWith(AndroidJUnit4::class)
class FlujoCompletoTest {
    private fun esperar(matcher: Matcher<View>) {
        val fin = SystemClock.elapsedRealtime() + 25000
        while (true) {
            try { onView(matcher).check(matches(isDisplayed())); return }
            catch (e: Throwable) { if (SystemClock.elapsedRealtime() > fin) throw e; SystemClock.sleep(250) }
        }
    }
    private fun tocar(text: String) { onView(allOf(withText(text), isAssignableFrom(Button::class.java))).perform(scrollTo(), click()) }
    private fun foto(nombre: String) {
        SystemClock.sleep(800)
        val inst = InstrumentationRegistry.getInstrumentation()
        val dir = File(inst.targetContext.getExternalFilesDir(null), "capturas").apply { mkdirs() }
        val bitmap = inst.uiAutomation.takeScreenshot()
        File(dir, "$nombre.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
    private fun cuenta(nombre: String) {
        esperar(withId(R.id.email))
        onView(withText("$nombre  ›")).perform(scrollTo(), click())
        onView(withId(R.id.ingresar)).perform(scrollTo(), click())
        esperar(withText("Cada residuo cuenta").takeIf { nombre == "Ciudadano" }
            ?: withText(if (nombre == "Autoridad") "Coordinación de recolección" else "Tu jornada de trabajo"))
    }
    private fun salir() {
        onView(withId(R.id.salir)).perform(click())
        onView(withId(android.R.id.button1)).perform(click())
        esperar(withId(R.id.email))
    }
    private fun campo(id: Int, value: String) { onView(withId(id)).perform(scrollTo(), replaceText(value), closeSoftKeyboard()) }
    private fun api(path: String, body: JSONObject, token: String = ""): JSONObject {
        val c = URL("http://10.0.2.2:8080$path").openConnection() as HttpURLConnection
        try {
            c.requestMethod = "POST"; c.connectTimeout = 10000; c.readTimeout = 20000
            c.setRequestProperty("Content-Type", "application/json")
            c.setRequestProperty("Authorization", "Bearer $token")
            c.doOutput = true; c.outputStream.use { it.write(body.toString().toByteArray()) }
            check(c.responseCode in 200..299) { "HTTP ${c.responseCode}" }
            return JSONObject(c.inputStream.bufferedReader().use { it.readText() })
        } finally { c.disconnect() }
    }
    @Test fun circuitoCiudadanoAutoridadRecolector() {
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        if (android.os.Build.VERSION.SDK_INT >= 37) automation.executeShellCommand("pm grant ar.edu.utn.residuos android.permission.ACCESS_LOCAL_NETWORK").close()
        if (android.os.Build.VERSION.SDK_INT >= 33) automation.executeShellCommand("pm grant ar.edu.utn.residuos android.permission.POST_NOTIFICATIONS").close()
        SystemClock.sleep(500)
        ActivityScenario.launch(LoginActivity::class.java).use {
            foto("01_acceso")
            cuenta("Ciudadano")
            foto("02_inicio_ciudadano")
            tocar("Registrar residuos")
            campo(R.id.cantidad, "2.5")
            campo(R.id.direccion, "Belgrano 850 - prueba")
            campo(R.id.latitud, "-31.4285"); campo(R.id.longitud, "-62.0805")
            onView(withId(R.id.guardar)).perform(scrollTo(), click())
            esperar(withText("Cada residuo cuenta"))
            tocar("Solicitar recolección")
            campo(R.id.cantidad, "12")
            campo(R.id.direccion, "Av. Libertador 250 - prueba")
            campo(R.id.latitud, "-31.4245"); campo(R.id.longitud, "-62.0801")
            campo(R.id.nota, "Carton y botellas separados y limpios.")
            foto("03_solicitud_formulario")
            onView(withId(R.id.guardar)).perform(scrollTo(), click())
            esperar(withText("Cada residuo cuenta"))
            tocar("Mis residuos")
            esperar(withText("Av. Libertador 250 - prueba"))
            foto("04_solicitud_pendiente")
            tocar("Puntos")
            tocar("Ver puntos en el mapa")
            esperar(withId(R.id.mapa)); SystemClock.sleep(10000)
            foto("05_puntos_reciclaje")
            onView(withId(R.id.volver)).perform(click())
            salir()
            cuenta("Autoridad")
            foto("06_panel_autoridades")
            tocar("Gestionar solicitudes")
            esperar(withText("Incluir en la ruta"))
            onView(withText("Incluir en la ruta")).perform(scrollTo(), click())
            tocar("Planificar ruta seleccionada")
            onView(withText("Equipo 1 - recolección general")).perform(click())
            esperar(withText("Ver recorrido en el mapa"))
            foto("07_ruta_asignada")
            tocar("Ver recorrido en el mapa")
            esperar(withId(R.id.mapa)); SystemClock.sleep(10000)
            foto("08_recorrido_mapa")
            onView(withId(R.id.volver)).perform(click())
            salir()
            cuenta("Recolector")
            tocar("Ver mis rutas")
            esperar(withText("Reportar incidente"))
            foto("09_ruta_recolector")
            tocar("Reportar incidente")
            onView(isAssignableFrom(android.widget.EditText::class.java)).perform(replaceText("Contenedor con tapa danada. Requiere mantenimiento."), closeSoftKeyboard())
            onView(withId(android.R.id.button1)).perform(click())
            SystemClock.sleep(1500)
            tocar("Confirmar recolección")
            val dialog = arrayOfNulls<String>(1)
            onView(isAssignableFrom(android.widget.EditText::class.java)).check { view, _ ->
                val root = view.rootView
                fun buscar(v: View) {
                    if (v is android.widget.TextView && v.text.toString().startsWith("Confirmar punto ")) dialog[0] = v.text.toString().removePrefix("Confirmar punto ")
                    if (v is android.view.ViewGroup) for (i in 0 until v.childCount) buscar(v.getChildAt(i))
                }
                buscar(root)
            }
            onView(isAssignableFrom(android.widget.EditText::class.java)).perform(replaceText(checkNotNull(dialog[0])), closeSoftKeyboard())
            onView(withId(android.R.id.button1)).perform(click())
            esperar(withText("Estado: Recolectado"))
            foto("10_recoleccion_confirmada")
            salir()
            cuenta("Autoridad")
            tocar("Incidentes")
            esperar(withText("Marcar como resuelto"))
            foto("11_incidente_autoridad")
            tocar("Marcar como resuelto")
            esperar(withText("Resuelto"))
            salir()
            cuenta("Ciudadano")
            val auth = api("/login", JSONObject().put("email", "autoridad@demo.local").put("password", "Demo2026!")).getString("token")
            api("/campanias", JSONObject().put("titulo", "Jornada de reciclaje barrial").put("texto", "Actividad de prueba: sabado de 9 a 12 h. Acerca papel, carton y plastico limpios."), auth)
            tocar("Avisos")
            esperar(withText("Jornada de reciclaje barrial"))
            foto("12_campania_recibida")
        }
    }
}
