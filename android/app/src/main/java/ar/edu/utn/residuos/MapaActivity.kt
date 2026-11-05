package ar.edu.utn.residuos

import android.os.Bundle
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.TextView
import org.json.JSONArray

class MapaActivity : Pantalla() {
    private lateinit var mapa: WebView
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_mapa)
        findViewById<TextView>(R.id.titulo).text = intent.getStringExtra("titulo") ?: "Mapa de recolección"
        findViewById<TextView>(R.id.detalle).text = intent.getStringExtra("detalle") ?: "Ubicación del punto de recolección."
        findViewById<Button>(R.id.volver).setOnClickListener { finish() }
        mapa = findViewById(R.id.mapa)
        mapa.settings.javaScriptEnabled = true
        mapa.settings.allowFileAccess = false
        mapa.settings.allowContentAccess = false
        mapa.settings.userAgentString += " EcoBarrioUTN/1.0"
        val html = assets.open("mapa/index.html").bufferedReader().use { it.readText() }
        mapa.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = true
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): android.webkit.WebResourceResponse? {
                if (request.url.host == "appassets.androidplatform.net") {
                    val name = request.url.lastPathSegment ?: return null
                    if (name !in listOf("leaflet.js", "leaflet.css", "mapa.js")) return null
                    return android.webkit.WebResourceResponse(if (name.endsWith("js")) "text/javascript" else "text/css", "UTF-8", assets.open("mapa/$name"))
                }
                return null
            }
            override fun onPageFinished(view: WebView, url: String) {
                val puntos = JSONArray(intent.getStringExtra("puntos") ?: "[]")
                val geometria = JSONArray(intent.getStringExtra("geometria") ?: "[]")
                view.evaluateJavascript("mostrar($puntos,$geometria)", null)
            }
        }
        mapa.loadDataWithBaseURL("https://appassets.androidplatform.net/mapa/", html, "text/html", "UTF-8", null)
    }
    override fun onDestroy() { if (::mapa.isInitialized) mapa.destroy(); super.onDestroy() }
}
