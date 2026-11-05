package ar.edu.utn.residuos

import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject
import java.net.URI

class LoginActivity : Pantalla() {
    private var enviando = false
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Api.token.isNotEmpty()) { abrir(); return }
        setContentView(R.layout.activity_login)
        val servidor = findViewById<EditText>(R.id.servidor)
        servidor.setText(getPreferences(MODE_PRIVATE).getString("servidor", Api.base))
        val email = findViewById<EditText>(R.id.email)
        val password = findViewById<EditText>(R.id.password)
        val accesos = findViewById<LinearLayout>(R.id.accesos)
        listOf("Ciudadano" to "vecino", "Autoridad" to "autoridad", "Recolector" to "equipo", "Equipo de peligrosos" to "especiales").forEach { (titulo, cuenta) ->
            val t = texto(accesos, titulo + "  ›", 15f, true)
            t.minHeight = dp(44)
            t.setOnClickListener { email.setText("$cuenta@demo.local"); password.setText("Demo2026!") }
        }
        findViewById<Button>(R.id.ingresar).setOnClickListener {
            if (!validarServidor() || enviando) return@setOnClickListener
            if (email.text.isBlank() || password.text.isBlank()) { error("Completá el correo y la contraseña."); return@setOnClickListener }
            enviando = true
            it.isEnabled = false
            Api.pedir("/login", "POST", JSONObject().put("email", email.text.toString()).put("password", password.text.toString()), {
                enviando = false
                Api.token = it.getString("token")
                Api.usuario = it.getJSONObject("usuario")
                Api.cursorAvisos = it.optDouble("servidor_epoch", System.currentTimeMillis()/1000.0)
                Avisos.iniciar()
                abrir()
            }, { m -> enviando = false; findViewById<Button>(R.id.ingresar).isEnabled = true; error(m) })
        }
        findViewById<Button>(R.id.crearCuenta).setOnClickListener { if (validarServidor()) registrar() }
    }
    private fun validarServidor(): Boolean {
        val url = findViewById<EditText>(R.id.servidor).text.toString().trim().trimEnd('/')
        val valid = runCatching { val u = URI(url); u.scheme in listOf("http", "https") && u.host != null && u.userInfo == null && u.path.isNullOrEmpty() }.getOrDefault(false)
        if (!valid) { error("Ingresá una URL válida, por ejemplo http://10.0.2.2:8080"); return false }
        val host = URI(url).host
        val local = host == "localhost" || host == "127.0.0.1" || host.startsWith("10.") || host.startsWith("192.168.") || host.startsWith("172.")
        if (local && android.os.Build.VERSION.SDK_INT >= 37 && checkSelfPermission("android.permission.ACCESS_LOCAL_NETWORK") != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            error("Permití el acceso a la red local para conectarte al servidor de prueba.")
            requestPermissions(arrayOf("android.permission.ACCESS_LOCAL_NETWORK"), 20)
            return false
        }
        Api.base = url
        getPreferences(MODE_PRIVATE).edit().putString("servidor", url).apply()
        return true
    }
    private fun error(m: String) { findViewById<TextView>(R.id.error).text = m }
    override fun onRequestPermissionsResult(code: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(code, permissions, grantResults)
        if (code == 20) error(if (grantResults.firstOrNull() == android.content.pm.PackageManager.PERMISSION_GRANTED) "Permiso concedido. Volvé a intentar." else "Sin ese permiso no se puede acceder al servidor local. También podés usar un servidor HTTPS público.")
    }
    private fun abrir() { startActivity(Intent(this, PanelActivity::class.java)); finish() }
    private fun registrar() {
        val box = margen()
        val nombre = campo(box, "Nombre y apellido")
        val email = campo(box, "Correo electrónico").apply { inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS }
        val password = campo(box, "Contraseña (mínimo 8 caracteres)").apply { inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD }
        val dialog = AlertDialog.Builder(this).setTitle("Crear cuenta ciudadana").setView(box).setNegativeButton("Cancelar", null).setPositiveButton("Crear", null).create()
        dialog.setOnShowListener {
            val b = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
            b.setOnClickListener {
                b.isEnabled = false
                Api.pedir("/usuarios", "POST", JSONObject().put("nombre", nombre.text.toString()).put("email", email.text.toString()).put("password", password.text.toString()), {
                    findViewById<EditText>(R.id.email).setText(email.text)
                    aviso(it.texto("mensaje")); dialog.dismiss()
                }, { b.isEnabled = true; aviso(it) })
            }
        }
        dialog.show()
    }
}
