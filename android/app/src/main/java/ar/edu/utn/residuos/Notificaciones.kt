package ar.edu.utn.residuos

import android.Manifest
import android.app.Application
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class ResiduosApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Avisos.app = this
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel("residuos", "Recolección y campañas", NotificationManager.IMPORTANCE_DEFAULT))
        val appId = getString(R.string.fcm_app_id)
        if (appId.isNotBlank()) {
            val options = FirebaseOptions.Builder().setApplicationId(appId)
                .setApiKey(getString(R.string.fcm_api_key)).setProjectId(getString(R.string.fcm_project_id))
                .setGcmSenderId(getString(R.string.fcm_sender_id)).build()
            FirebaseApp.initializeApp(this, options)
        }
    }
}

object Avisos {
    lateinit var app: Application
    var actualizar: (() -> Unit)? = null
    var conexion: ((Boolean) -> Unit)? = null
    @Volatile var enLinea = false
        private set
    @Volatile private var generacion = 0
    @Volatile private var stream: HttpURLConnection? = null
    private val handler = Handler(Looper.getMainLooper())
    private val conFcm get() = FirebaseApp.getApps(app).isNotEmpty()

    fun mostrar(titulo: String, texto: String, id: String) {
        if (Build.VERSION.SDK_INT >= 33 && app.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val intent = Intent(app, LoginActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val pending = PendingIntent.getActivity(app, 0, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = Notification.Builder(app, "residuos").setSmallIcon(R.drawable.ic_hoja)
            .setContentTitle(titulo).setContentText(texto).setStyle(Notification.BigTextStyle().bigText(texto))
            .setContentIntent(pending).setAutoCancel(true).build()
        app.getSystemService(NotificationManager::class.java).notify(id.hashCode(), n)
    }

    fun registrarFcm() {
        if (conFcm) FirebaseMessaging.getInstance().token.addOnSuccessListener { token ->
            if (Api.token.isNotEmpty()) Api.pedir("/dispositivos", "POST", JSONObject().put("token", token), {}, {})
        }
    }

    fun desvincularFcm(luego: () -> Unit) {
        if (!conFcm) { luego(); return }
        FirebaseMessaging.getInstance().token.addOnSuccessListener { token ->
            Api.pedir("/dispositivos", "DELETE", JSONObject().put("token", token), { luego() }, {
                FirebaseMessaging.getInstance().deleteToken()
                luego()
            })
        }.addOnFailureListener { luego() }
    }

    fun iniciar() {
        detener()
        registrarFcm()
        val actual = generacion
        val sesion = Api.token
        val servidor = Api.base
        Thread {
            var cursor = Api.cursorAvisos
            while (generacion == actual && Api.token == sesion && sesion.isNotEmpty()) {
                var c: HttpURLConnection? = null
                try {
                    c = URL("$servidor/eventos?desde=$cursor").openConnection() as HttpURLConnection
                    stream = c
                    c.setRequestProperty("Authorization", "Bearer $sesion")
                    c.connectTimeout = 10000
                    c.readTimeout = 15000
                    if (c.responseCode == 401) { enLinea = false; handler.post { conexion?.invoke(false) }; break }
                    c.inputStream.bufferedReader(Charsets.UTF_8).use { reader ->
                        enLinea = true; handler.post { conexion?.invoke(true) }
                        while (generacion == actual) {
                            val line = reader.readLine() ?: break
                            if (line.startsWith("data: ")) {
                                val aviso = JSONObject(line.substring(6))
                                cursor = aviso.getDouble("creado")
                                if (!conFcm) mostrar(aviso.texto("titulo"), aviso.texto("texto"), aviso.texto("id"))
                                handler.post { actualizar?.invoke() }
                            }
                        }
                    }
                } catch (_: Exception) { enLinea = false; handler.post { conexion?.invoke(false) } }
                finally { c?.disconnect() }
                if (generacion == actual) try { Thread.sleep(3000) } catch (_: InterruptedException) { break }
            }
        }.apply { name = "AvisosSSE"; isDaemon = true; start() }
    }

    fun detener() {
        generacion++; enLinea = false
        val anterior = stream; stream = null
        if (anterior != null) Thread { anterior.disconnect() }.apply { isDaemon = true; start() }
    }
}

class MensajeriaService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        if (Api.token.isNotEmpty()) Api.pedir("/dispositivos", "POST", JSONObject().put("token", token), {}, {})
    }
    override fun onMessageReceived(message: RemoteMessage) {
        message.notification?.let { Avisos.mostrar(it.title ?: "EcoBarrio", it.body ?: "Nuevo aviso", message.messageId ?: "fcm") }
    }
}
