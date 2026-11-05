package ar.edu.utn.residuos

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.view.View
import android.view.WindowInsets
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

open class Pantalla : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.decorView.setOnApplyWindowInsetsListener { v, insets ->
            if (android.os.Build.VERSION.SDK_INT >= 30) {
                val barras = insets.getInsets(WindowInsets.Type.systemBars())
                v.setPadding(barras.left, barras.top, barras.right, barras.bottom)
                WindowInsets.CONSUMED
            } else insets
        }
    }
    fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()
    fun aviso(m: String) { Toast.makeText(this, m, Toast.LENGTH_LONG).show() }
    fun texto(parent: LinearLayout, valor: String, size: Float = 16f, bold: Boolean = false): TextView {
        val t = TextView(this)
        t.text = valor
        t.textSize = size
        t.setTextColor(Color.rgb(35, 60, 47))
        if (bold) t.setTypeface(null, Typeface.BOLD)
        t.setPadding(0, dp(3), 0, dp(6))
        parent.addView(t)
        return t
    }
    fun boton(parent: LinearLayout, valor: String, action: () -> Unit): Button {
        val b = Button(this)
        b.text = valor
        b.setOnClickListener { action() }
        parent.addView(b)
        return b
    }
    fun tarjeta(parent: LinearLayout): LinearLayout {
        val box = LinearLayout(this)
        box.orientation = LinearLayout.VERTICAL
        box.setPadding(dp(16), dp(12), dp(16), dp(12))
        box.setBackgroundResource(R.drawable.tarjeta)
        box.layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(12) }
        parent.addView(box)
        return box
    }
    fun campo(parent: LinearLayout, hint: String, valor: String = ""): EditText {
        val e = EditText(this)
        e.hint = hint
        e.setText(valor)
        e.isSingleLine = true
        e.minHeight = dp(52)
        parent.addView(e)
        return e
    }
    fun margen(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(24), dp(12), dp(24), 0)
    }
}
