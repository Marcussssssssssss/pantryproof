package com.pantryproof.prototype.ui

import android.app.Activity
import android.app.Dialog
import android.content.res.Configuration
import android.graphics.Bitmap
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import com.pantryproof.prototype.R
import com.pantryproof.prototype.image.CropEdge
import com.pantryproof.prototype.image.ReceiptCrop
import com.pantryproof.prototype.image.ReceiptCropView
import kotlin.math.roundToInt

internal fun showSageCropEditor(
    activity: Activity,
    ui: PantryUiComponents,
    bitmap: Bitmap,
    initial: ReceiptCrop,
    initiallyExpanded: Boolean,
    onChange: (ReceiptCrop, Boolean) -> Unit,
    onApply: (ReceiptCrop) -> Unit,
    onDismiss: () -> Unit,
): Dialog {
    val dialog = Dialog(activity, R.style.Theme_PantryProof_Crop)
    val context = dialog.context
    val components = PantryUiComponents(context)
    val gutter = ui.pageGutter()
    val target = ui.dimen(R.dimen.pantry_touch_target)
    val gap = ui.dimen(R.dimen.pantry_space_2)
    val title = context.getString(R.string.crop_receipt)
    val editor = ReceiptCropView(context, bitmap, initial).apply {
        id = R.id.crop_editor_image
        contentDescription = context.getString(R.string.crop_editor_description)
        setBackgroundColor(ui.color(R.color.pantry_surface_container))
    }
    var expanded = initiallyExpanded
    val adjustments = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(gutter, 0, gutter, gap)
    }
    adjustments.addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
        setText(R.string.crop_editor_help)
    })
    val directions = listOf(
        CropNudge(R.id.crop_move_left, R.string.crop_move_left, R.drawable.ic_sage_move_left, -.05f, 0f),
        CropNudge(R.id.crop_move_right, R.string.crop_move_right, R.drawable.ic_sage_move_right, .05f, 0f),
        CropNudge(R.id.crop_move_up, R.string.crop_move_up, R.drawable.ic_sage_move_up, 0f, -.05f),
        CropNudge(R.id.crop_move_down, R.string.crop_move_down, R.drawable.ic_sage_move_down, 0f, .05f),
    )
    adjustments.addView(LinearLayout(context).apply {
        gravity = Gravity.CENTER_HORIZONTAL
        directions.forEach { nudge ->
            addView(components.iconButton(nudge.icon, context.getString(nudge.label), nudge.id) {
                editor.setCrop(editor.crop.move(nudge.dx, nudge.dy))
            })
        }
    })
    val edges = listOf(
        Triple(CropEdge.LEFT, R.string.crop_edge_left, R.id.crop_edge_left),
        Triple(CropEdge.TOP, R.string.crop_edge_top, R.id.crop_edge_top),
        Triple(CropEdge.RIGHT, R.string.crop_edge_right, R.id.crop_edge_right),
        Triple(CropEdge.BOTTOM, R.string.crop_edge_bottom, R.id.crop_edge_bottom),
    ).map { (edge, label, sliderId) ->
        adjustments.addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Label).apply {
            setText(label)
            labelFor = sliderId
        })
        SeekBar(context).apply {
            id = sliderId
            max = 100
            adjustments.addView(this, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, target))
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onStartTrackingTouch(seekBar: SeekBar) = Unit
                override fun onStopTrackingTouch(seekBar: SeekBar) = Unit
                override fun onProgressChanged(seekBar: SeekBar, progress: Int, fromUser: Boolean) {
                    if (fromUser) {
                        editor.setCrop(editor.crop.adjust(edge, progress / 100f))
                        editor.onCropChanged(editor.crop)
                    }
                }
            })
        }
    }
    editor.onCropChanged = { bounds ->
        bounds.values().forEachIndexed { index, position ->
            edges[index].progress = (position * 100f).roundToInt()
        }
        onChange(bounds, expanded)
    }
    editor.onCropChanged(initial)

    val scroll = ScrollView(context).apply { addView(adjustments) }
    val chevron = components.icon(R.drawable.ic_sage_down)
    lateinit var toggle: View
    fun updateDisclosure() {
        scroll.visibility = if (expanded) View.VISIBLE else View.GONE
        chevron.setImageResource(if (expanded) R.drawable.ic_sage_down else R.drawable.ic_sage_right)
        ViewCompat.setStateDescription(toggle, context.getString(
            if (expanded) R.string.sage_expanded else R.string.sage_collapsed,
        ))
    }
    toggle = components.actionRow(context.getString(R.string.v4_precise_crop), null, null, chevron) {
        expanded = !expanded
        updateDisclosure()
        onChange(editor.crop, expanded)
    }.apply {
        id = R.id.crop_precise_toggle
        setPaddingRelative(gutter, 0, gutter, 0)
    }
    updateDisclosure()

    val reset = components.actionButton(context.getString(R.string.crop_reset), PantryActionStyle.TERTIARY,
        viewId = R.id.crop_reset_action) { editor.setCrop(ReceiptCrop.FULL) }
    val close = components.iconButton(R.drawable.ic_sage_close, context.getString(R.string.v4_crop_close),
        R.id.crop_close) { dialog.cancel() }
    val root = LinearLayout(context).apply {
        id = R.id.crop_workspace
        orientation = LinearLayout.VERTICAL
        setBackgroundColor(ui.color(R.color.pantry_surface))
        ViewCompat.setAccessibilityPaneTitle(this, title)
        addView(components.appBar(title, showBack = false, end = reset, leading = close) { dialog.cancel() })
        if (resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE &&
            resources.configuration.screenWidthDp >= 560
        ) {
            addView(LinearLayout(context).apply {
                addView(editor, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1.2f))
                addView(LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    addView(toggle)
                    addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
                }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 0.8f))
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        } else {
            addView(editor, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1.2f))
            addView(toggle)
            addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 0.8f))
        }
        addView(LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(gutter, gap, gutter, gap)
            addView(components.actionButton(context.getString(R.string.crop_apply), PantryActionStyle.PRIMARY,
                viewId = R.id.crop_apply_action) {
                dialog.dismiss()
                onApply(editor.crop)
            })
        })
    }
    ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
        val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
        view.setPadding(bars.left, 0, bars.right, bars.bottom)
        insets
    }
    dialog.setContentView(root)
    dialog.setOnDismissListener { onDismiss() }
    dialog.window?.let { window ->
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = true
            isAppearanceLightNavigationBars = true
        }
    }
    dialog.show()
    dialog.window?.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
    ViewCompat.requestApplyInsets(root)
    return dialog
}

private data class CropNudge(val id: Int, val label: Int, val icon: Int, val dx: Float, val dy: Float)
