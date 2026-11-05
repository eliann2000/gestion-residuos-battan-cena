package ar.edu.utn.residuos

import android.Manifest
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class PanelActivity : Pantalla() {
    private var datos = JSONObject()
    private var pagina = "Inicio"
    private var cargando = false
    private var enLinea = false
    private val seleccion = mutableSetOf<String>()
    private lateinit var contenido: LinearLayout
    private val rol get() = Api.usuario.texto("rol")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Api.token.isEmpty()) { salirLocal(); return }
        setContentView(R.layout.activity_panel)
        pagina = savedInstanceState?.getString("pagina") ?: "Inicio"
        contenido = findViewById(R.id.contenido)
        val perfil = when (rol) { "autoridad" -> "Autoridades"; "recolector" -> "Personal de recolección"; else -> "Ciudadano" }
        findViewById<TextView>(R.id.perfil).text = "$perfil · ${Api.usuario.texto("nombre")}"
        val nav = findViewById<LinearLayout>(R.id.pestanas)
        val tabs = when (rol) {
            "autoridad" -> listOf("Inicio", "Solicitudes", "Rutas", "Incidentes", "Avisos")
            "recolector" -> listOf("Inicio", "Rutas", "Incidentes", "Avisos")
            else -> listOf("Inicio", "Mis residuos", "Puntos", "Avisos")
        }
        tabs.forEach { p -> boton(nav, p) { pagina = p; dibujar() }.apply { textSize = 13f; minWidth = dp(84) } }
        findViewById<Button>(R.id.actualizar).setOnClickListener { cargar() }
        findViewById<Button>(R.id.salir).setOnClickListener {
            AlertDialog.Builder(this).setMessage("¿Querés cerrar la sesión?").setNegativeButton("Cancelar", null)
                .setPositiveButton("Cerrar sesión") { _, _ ->
                    Avisos.desvincularFcm {
                        Api.pedir("/logout", "POST", null, { salirLocal() }, { salirLocal() })
                    }
                }.show()
        }
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED && !getPreferences(MODE_PRIVATE).getBoolean("avisoPedido", false)) {
            getPreferences(MODE_PRIVATE).edit().putBoolean("avisoPedido", true).apply()
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 30)
        }
    }
    override fun onResume() {
        super.onResume()
        if (!::contenido.isInitialized) return
        Avisos.actualizar = { cargar() }
        Avisos.conexion = { enLinea = it; estado() }
        enLinea = Avisos.enLinea
        cargar()
    }
    override fun onPause() { Avisos.actualizar = null; Avisos.conexion = null; super.onPause() }
    override fun onSaveInstanceState(outState: Bundle) { outState.putString("pagina", pagina); super.onSaveInstanceState(outState) }
    private fun salirLocal() {
        Avisos.detener(); Api.token = ""; Api.usuario = JSONObject()
        startActivity(Intent(this, LoginActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)); finish()
    }
    private fun estado(mensaje: String? = null) {
        findViewById<TextView>(R.id.estadoConexion).text = mensaje ?: if (enLinea) "En línea · actualizaciones automáticas" else "Datos actualizados · reconectando avisos…"
    }
    private fun cargar() {
        if (cargando || isFinishing) return
        cargando = true
        Api.pedir("/panel", ok = {
            cargando = false
            if (!isFinishing) {
                datos = it
                seleccion.retainAll(datos.lista("registros").filter { r -> r.texto("estado") == "pendiente" }.map { r -> r.texto("id") }.toSet())
                dibujar(); estado()
            }
        }, error = {
            cargando = false
            if (Api.token.isEmpty()) salirLocal() else { enLinea = false; estado(it); if (datos.length() == 0) texto(contenido, it) }
        })
    }
    private fun dibujar() {
        contenido.removeAllViews()
        texto(contenido, pagina, 25f, true)
        if (datos.length() == 0) { texto(contenido, "Cargando información…"); return }
        when (pagina) {
            "Inicio" -> inicio()
            "Mis residuos", "Solicitudes" -> registros()
            "Rutas" -> rutas()
            "Puntos" -> puntos()
            "Incidentes" -> incidentes()
            "Avisos" -> avisos()
        }
    }
    private fun inicio() {
        val rs = datos.lista("registros")
        val box = tarjeta(contenido)
        val titulo = when (rol) { "autoridad" -> "Coordinación de recolección"; "recolector" -> "Tu jornada de trabajo"; else -> "Cada residuo cuenta" }
        texto(box, titulo, 21f, true)
        if (rol == "ciudadano") {
            texto(box, "${rs.count { it.texto("tipo") == "registro" }} registros · ${rs.count { it.texto("tipo") == "solicitud" }} solicitudes")
            texto(box, "Separá tus residuos y solicitá el retiro de los especiales.")
            boton(box, "Registrar residuos") { nuevo("registro") }
            boton(box, "Solicitar recolección") { nuevo("solicitud") }
            boton(contenido, "Ver puntos de reciclaje") { pagina = "Puntos"; dibujar() }
        } else {
            texto(box, "${rs.count { it.texto("estado") == "pendiente" }} pendientes   ·   ${rs.count { it.texto("estado") == "asignado" }} asignadas", 17f, true)
            texto(box, "${rs.count { it.texto("estado") == "recolectado" }} recolecciones completadas")
            val abiertas = datos.lista("incidentes").count { it.texto("estado") == "abierto" }
            texto(box, "$abiertas incidentes abiertos")
            boton(box, if (rol == "autoridad") "Gestionar solicitudes" else "Ver mis rutas") { pagina = if (rol == "autoridad") "Solicitudes" else "Rutas"; dibujar() }
            boton(contenido, "Mapa de puntos de recolección") { mapa(rs, "Puntos de recolección") }
        }
        val horario = tarjeta(contenido)
        texto(horario, "Horarios del servicio", 18f, true)
        texto(horario, datos.texto("horarios"), 15f)
        texto(horario, "Horarios y puntos de demostración; no representan el servicio municipal vigente.", 12f)
        datos.lista("avisos").firstOrNull()?.let { aviso ->
            val a = tarjeta(contenido)
            texto(a, "Último aviso", 13f, true)
            texto(a, aviso.texto("titulo"), 18f, true)
            texto(a, aviso.texto("texto"), 15f)
        }
    }
    private fun nuevo(tipo: String) { startActivity(Intent(this, RegistroActivity::class.java).putExtra("tipo", tipo)) }
    private fun registros() {
        val rs = datos.lista("registros")
        if (rol == "ciudadano") {
            boton(contenido, "Registrar residuos") { nuevo("registro") }
            boton(contenido, "Solicitar recolección") { nuevo("solicitud") }
        } else {
            texto(contenido, "Seleccioná solicitudes pendientes para planificar una ruta. Capacidad: 500 kg; máximo 20 puntos.", 14f)
            boton(contenido, "Planificar ruta seleccionada") { planificar() }
            boton(contenido, "Ver mapa de solicitudes") { mapa(rs.filter { it.texto("tipo") == "solicitud" }, "Solicitudes de recolección") }
        }
        if (rs.isEmpty()) texto(contenido, "Todavía no hay residuos registrados.")
        rs.forEach { registro(it, contenido) }
    }
    private fun registro(r: JSONObject, parent: LinearLayout) {
        val box = tarjeta(parent)
        val id = r.texto("id")
        val esSolicitud = r.texto("tipo") == "solicitud"
        texto(box, (if (esSolicitud) "Solicitud" else "Registro") + " · " + codigo(id), 12f, true)
        texto(box, r.texto("categoria").replaceFirstChar { it.uppercase() } + " · " + r.optDouble("cantidad") + " kg", 19f, true)
        val estado = r.texto("estado").replaceFirstChar { it.uppercase() }
        texto(box, "Estado: $estado", 15f, true)
        texto(box, r.texto("direccion"), 15f)
        if (rol != "ciudadano") texto(box, r.texto("vecino"), 13f)
        if (r.texto("nota").isNotBlank()) texto(box, r.texto("nota"), 14f)
        if (rol == "autoridad" && r.texto("estado") == "pendiente") {
            val check = CheckBox(this)
            check.text = "Incluir en la ruta"
            check.isChecked = id in seleccion
            check.setOnCheckedChangeListener { _, checked -> if (checked) seleccion.add(id) else seleccion.remove(id) }
            box.addView(check)
        }
        if (rol == "recolector" && r.texto("estado") == "asignado") {
            boton(box, "Confirmar recolección") { confirmar(r) }
            boton(box, "Reportar incidente") { informar(r) }
        }
    }
    private fun planificar() {
        if (seleccion.isEmpty()) { aviso("Seleccioná al menos una solicitud pendiente."); return }
        val equipos = datos.lista("equipos")
        val nombres = equipos.map { it.texto("nombre") }.toTypedArray()
        AlertDialog.Builder(this).setTitle("Asignar equipo").setItems(nombres) { _, index ->
            val b = JSONObject().put("registros", JSONArray(seleccion.toList())).put("recolector", equipos[index].texto("id"))
            val dialog = AlertDialog.Builder(this).setMessage("Planificando el recorrido…").setCancelable(false).show()
            Api.pedir("/rutas", "POST", b, {
                dialog.dismiss(); seleccion.clear(); pagina = "Rutas"; aviso(it.texto("mensaje")); cargar()
            }, { dialog.dismiss(); aviso(it); cargar() })
        }.setNegativeButton("Cancelar", null).show()
    }
    private fun rutas() {
        val rutas = datos.lista("rutas")
        if (rutas.isEmpty()) texto(contenido, "No hay rutas asignadas.")
        rutas.forEach { ruta ->
            val box = tarjeta(contenido)
            val d = ruta.getJSONObject("datos")
            val orden = d.getJSONArray("orden")
            val rs = datos.lista("registros").associateBy { it.texto("id") }
            val puntos = (0 until orden.length()).mapNotNull { rs[orden.getString(it)] }
            texto(box, "Ruta " + codigo(ruta.texto("id")), 21f, true)
            texto(box, ruta.texto("equipo"), 15f, true)
            texto(box, "${puntos.count { it.texto("estado") == "recolectado" }} de ${puntos.size} puntos completados · ${String.format(Locale.getDefault(), "%.1f", d.optDouble("metros")/1000)} km")
            texto(box, d.texto("proveedor"), 12f)
            if (!d.isNull("segundos")) texto(box, "Tiempo de conducción estimado: ${d.optInt("segundos")/60} min", 13f)
            boton(box, "Ver recorrido en el mapa") { mapa(puntos, "Ruta " + codigo(ruta.texto("id")), d.optJSONArray("geometria"), d.texto("proveedor")) }
            puntos.forEachIndexed { i, p ->
                texto(box, "Parada ${i+1}", 13f, true)
                registro(p, box)
            }
        }
    }
    private fun confirmar(r: JSONObject) {
        val box = margen()
        texto(box, "Ingresá el identificador del punto para registrar la visita.", 15f)
        val code = campo(box, "Identificador del punto")
        val dialog = AlertDialog.Builder(this).setTitle("Confirmar punto ${codigo(r.texto("id"))}").setView(box)
            .setNegativeButton("Cancelar", null).setPositiveButton("Confirmar", null).create()
        dialog.setOnShowListener {
            val b = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
            b.setOnClickListener {
                b.isEnabled = false
                Api.pedir("/registros/${r.texto("id")}/confirmar", "POST", JSONObject().put("identificador", code.text.toString()), {
                    dialog.dismiss(); aviso(it.texto("mensaje")); cargar()
                }, { b.isEnabled = true; aviso(it) })
            }
        }; dialog.show()
    }
    private fun informar(r: JSONObject) {
        val box = margen()
        val detalle = campo(box, "Estado del contenedor o problema detectado")
        detalle.isSingleLine = false
        val dialog = AlertDialog.Builder(this).setTitle("Reportar incidente").setView(box).setNegativeButton("Cancelar", null).setPositiveButton("Informar", null).create()
        dialog.setOnShowListener {
            val b = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
            b.setOnClickListener {
                b.isEnabled = false
                Api.pedir("/incidentes", "POST", JSONObject().put("registro", r.texto("id")).put("detalle", detalle.text.toString()), {
                    dialog.dismiss(); aviso(it.texto("mensaje")); cargar()
                }, { b.isEnabled = true; aviso(it) })
            }
        }; dialog.show()
    }
    private fun incidentes() {
        val lista = datos.lista("incidentes")
        if (lista.isEmpty()) texto(contenido, "No hay incidentes informados.")
        lista.forEach { i ->
            val box = tarjeta(contenido)
            texto(box, i.texto("estado").replaceFirstChar { it.uppercase() }, 18f, true)
            texto(box, i.texto("direccion"), 15f, true)
            texto(box, i.texto("detalle"))
            if (rol == "autoridad" && i.texto("estado") == "abierto") {
                val b = boton(box, "Marcar como resuelto") { }
                b.setOnClickListener {
                    b.isEnabled = false
                    Api.pedir("/incidentes/${i.texto("id")}/resolver", "POST", null, { aviso(it.texto("mensaje")); cargar() }, { b.isEnabled = true; aviso(it) })
                }
            }
        }
    }
    private fun puntos() {
        texto(contenido, "Ubicaciones y horarios de demostración.", 14f)
        boton(contenido, "Ver puntos en el mapa") { mapa(datos.lista("puntos"), "Puntos de reciclaje", detalle = "Puntos de demostración; no son ubicaciones municipales verificadas.") }
        datos.lista("puntos").forEach { p ->
            val box = tarjeta(contenido)
            texto(box, p.texto("nombre"), 19f, true)
            texto(box, p.texto("materiales"))
            texto(box, p.texto("horario"), 14f)
        }
    }
    private fun avisos() {
        if (rol == "autoridad") boton(contenido, "Publicar campaña") { campania() }
        val lista = datos.lista("avisos")
        if (lista.isEmpty()) texto(contenido, "Todavía no hay avisos.")
        lista.forEach { a ->
            val box = tarjeta(contenido)
            texto(box, a.texto("titulo"), 19f, true)
            texto(box, a.texto("texto"))
            texto(box, SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.getDefault()).format(Date((a.optDouble("creado")*1000).toLong())), 12f)
        }
    }
    private fun campania() {
        val box = margen()
        val titulo = campo(box, "Título de la campaña")
        val mensaje = campo(box, "Mensaje para ciudadanos y recolectores").apply { isSingleLine = false }
        val dialog = AlertDialog.Builder(this).setTitle("Publicar campaña").setView(box).setNegativeButton("Cancelar", null).setPositiveButton("Publicar", null).create()
        dialog.setOnShowListener {
            val b = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
            b.setOnClickListener {
                b.isEnabled = false
                Api.pedir("/campanias", "POST", JSONObject().put("titulo", titulo.text.toString()).put("texto", mensaje.text.toString()), {
                    dialog.dismiss(); aviso(it.texto("mensaje")); cargar()
                }, { b.isEnabled = true; aviso(it) })
            }
        }; dialog.show()
    }
    private fun mapa(puntos: List<JSONObject>, titulo: String, geometria: JSONArray? = null, detalle: String = "Seleccioná un punto para consultar su información.") {
        startActivity(Intent(this, MapaActivity::class.java).putExtra("puntos", JSONArray(puntos).toString())
            .putExtra("titulo", titulo).putExtra("geometria", geometria?.toString()).putExtra("detalle", detalle))
    }
}
