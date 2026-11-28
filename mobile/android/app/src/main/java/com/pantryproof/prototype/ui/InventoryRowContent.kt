package com.pantryproof.prototype.ui

import android.content.Context
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.TextView
import com.pantryproof.prototype.R
import com.pantryproof.prototype.data.InventoryWarning

/** Gives names room to wrap and stacks the two columns when the measured width is too narrow. */
internal class InventoryRowContent(
    context: Context,
    private val ui: PantryUiComponents,
    name: String,
    quantity: String,
    expiry: String?,
    sessionSource: String?,
    warnings: List<Pair<InventoryWarning, String>>,
) : LinearLayout(context) {
    private val nameView = title(name)
    private val item = column(Gravity.START).apply {
        addView(nameView)
        expiry?.let { addView(supportingText(it)) }
        sessionSource?.let { addView(supportingText(it)) }
    }
    private val stock = column(Gravity.END).apply {
        addView(title(quantity).apply { gravity = Gravity.END }, LayoutParams(MATCH_PARENT, WRAP_CONTENT))
        if (warnings.isNotEmpty()) addView(WarningLabels(context, ui, warnings), LayoutParams(MATCH_PARENT, WRAP_CONTENT))
    }
    private val itemParams = LayoutParams(0, WRAP_CONTENT, 1.2f)
    private val stockParams = LayoutParams(0, WRAP_CONTENT, 1f)
    private val columnGap = ui.dimen(R.dimen.pantry_space_2)

    init {
        gravity = Gravity.START or Gravity.TOP
        isBaselineAligned = false
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        addView(item, itemParams)
        addView(stock, stockParams)
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        // Use the actual font size in pixels, including system text scaling.
        val stacked = MeasureSpec.getSize(widthMeasureSpec) < nameView.textSize * 15
        orientation = if (stacked) VERTICAL else HORIZONTAL
        itemParams.width = if (stacked) MATCH_PARENT else 0
        itemParams.weight = if (stacked) 0f else 1.2f
        stockParams.width = if (stacked) MATCH_PARENT else 0
        stockParams.weight = if (stacked) 0f else 1f
        stockParams.setMargins(
            if (!stacked && layoutDirection != LAYOUT_DIRECTION_RTL) columnGap else 0, 0,
            if (!stacked && layoutDirection == LAYOUT_DIRECTION_RTL) columnGap else 0, 0,
        )
        super.onMeasure(widthMeasureSpec, heightMeasureSpec)
    }

    private fun column(alignment: Int) = LinearLayout(context).apply {
        orientation = VERTICAL
        gravity = alignment
    }

    private fun title(value: String) = TextView(context, null, 0, R.style.TextAppearance_PantryProof_ItemTitle).apply {
        text = value
    }

    private fun supportingText(value: String) = TextView(context, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
        text = value
        includeFontPadding = false
        setTextColor(ui.color(R.color.pantry_on_surface_variant))
    }

    /** Inventory has at most one expiry warning and one stock warning. Wrap the pair if needed. */
    private class WarningLabels(
        context: Context,
        ui: PantryUiComponents,
        warnings: List<Pair<InventoryWarning, String>>,
    ) : LinearLayout(context) {
        private val gap = ui.dimen(R.dimen.pantry_space_1)

        init {
            gravity = Gravity.END
            isBaselineAligned = false
            warnings.forEach { (warning, label) ->
                val (fill, ink) = when (warning) {
                    InventoryWarning.EXPIRED, InventoryWarning.OUT_OF_STOCK ->
                        R.color.pantry_error_container to R.color.pantry_on_error_container
                    InventoryWarning.EXPIRES_TODAY, InventoryWarning.EXPIRING_SOON ->
                        R.color.pantry_secondary_container to R.color.pantry_on_secondary_container
                    InventoryWarning.LOW_STOCK -> R.color.pantry_low_stock_container to R.color.pantry_low_stock
                }
                addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
                    text = label
                    textSize = 13f
                    includeFontPadding = false
                    setTextColor(ui.color(ink))
                    setPaddingRelative(gap * 2, gap / 2, gap * 2, gap / 2)
                    background = GradientDrawable().apply {
                        cornerRadius = ui.dimen(R.dimen.pantry_touch_target).toFloat()
                        setColor(ui.color(fill))
                    }
                }, LayoutParams(WRAP_CONTENT, WRAP_CONTENT))
            }
        }

        override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
            val natural = MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED)
            var inlineWidth = 0
            for (index in 0 until childCount) {
                val label = getChildAt(index)
                label.measure(natural, natural)
                inlineWidth += label.measuredWidth
            }
            val wrap = inlineWidth + (childCount - 1) * gap > MeasureSpec.getSize(widthMeasureSpec)
            orientation = if (wrap) VERTICAL else HORIZONTAL
            for (index in 0 until childCount) {
                val params = getChildAt(index).layoutParams as LayoutParams
                val inlineGap = if (index > 0 && !wrap) gap else 0
                val rtl = layoutDirection == LAYOUT_DIRECTION_RTL
                params.setMargins(if (rtl) 0 else inlineGap, if (index > 0 && wrap) gap else 0,
                    if (rtl) inlineGap else 0, 0)
            }
            super.onMeasure(widthMeasureSpec, heightMeasureSpec)
        }
    }

    private companion object {
        const val MATCH_PARENT = LayoutParams.MATCH_PARENT
        const val WRAP_CONTENT = LayoutParams.WRAP_CONTENT
    }
}
