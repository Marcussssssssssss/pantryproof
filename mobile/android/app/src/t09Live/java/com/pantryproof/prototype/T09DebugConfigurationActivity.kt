package com.pantryproof.prototype

import android.app.Activity
import android.content.pm.ApplicationInfo
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.pantryproof.prototype.data.T09ProcessingConfig
import com.pantryproof.prototype.ui.PantryActionStyle
import com.pantryproof.prototype.ui.PantryBannerTone
import com.pantryproof.prototype.ui.PantryUiComponents

internal class T09DebugConfigurationActivity : Activity() {
    private lateinit var bearerInput: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!T09ProcessingConfig.isCapable(packageName) ||
            applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE == 0
        ) {
            finish()
            return
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        @Suppress("DEPRECATION")
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        val ui = PantryUiComponents(this)
        val padding = ui.dimen(R.dimen.pantry_page_gutter)
        bearerInput = EditText(this).apply {
            setSingleLine()
            setHint(R.string.t09_debug_bearer_hint)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD or
                InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            imeOptions = EditorInfo.IME_ACTION_DONE or EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING or
                EditorInfo.IME_FLAG_NO_EXTRACT_UI
            isSaveEnabled = false
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                importantForContentCapture = View.IMPORTANT_FOR_CONTENT_CAPTURE_NO
            }
        }
        val form = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding, padding, padding)
            addView(ui.banner(
                "http://${T09ProcessingConfig.HOST}:${T09ProcessingConfig.PORT}",
                getString(R.string.t09_debug_configuration_instructions),
                PantryBannerTone.INFO,
            ))
            addView(bearerInput)
            addView(ui.actionButton(getString(R.string.t09_debug_configure), PantryActionStyle.PRIMARY) {
                applyConfiguration()
            })
            if (T09ProcessingConfig.isConfigured()) {
                addView(ui.actionButton("Clear session credential", PantryActionStyle.SECONDARY) {
                    T09ProcessingConfig.clear()
                    finish()
                })
            }
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(ui.appBar(title.toString(), showBack = true) { finish() })
            addView(ScrollView(this@T09DebugConfigurationActivity).apply { addView(form) })
            ViewCompat.setOnApplyWindowInsetsListener(this) { view, insets ->
                val bottom = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime()).bottom
                view.setPadding(0, 0, 0, bottom)
                insets
            }
        })
    }

    override fun onPause() {
        if (::bearerInput.isInitialized) bearerInput.text.clear()
        super.onPause()
    }

    private fun applyConfiguration() {
        val configured = try {
            T09ProcessingConfig.configure(
                "http", T09ProcessingConfig.HOST, T09ProcessingConfig.PORT, bearerInput.text.toString(),
            )
            true
        } catch (_: IllegalArgumentException) {
            false
        } finally {
            bearerInput.text.clear()
        }
        if (configured) {
            finish()
        } else {
            bearerInput.error = getString(R.string.t09_debug_invalid_bearer)
        }
    }
}
