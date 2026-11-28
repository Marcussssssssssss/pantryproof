package com.pantryproof.prototype.ui

import android.app.Dialog
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.RippleDrawable
import android.graphics.drawable.StateListDrawable
import android.graphics.drawable.GradientDrawable
import android.util.TypedValue
import android.view.Gravity
import android.view.Window
import android.view.WindowManager
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckedTextView
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ListPopupWindow
import android.widget.Spinner
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.view.AccessibilityDelegateCompat
import androidx.core.view.ViewCompat
import androidx.core.view.accessibility.AccessibilityNodeInfoCompat
import androidx.core.view.WindowInsetsCompat
import com.pantryproof.prototype.R

enum class PantryBannerTone {
    INFO,
    DEMO,
    SUCCESS,
    ERROR,
}

enum class PantryActionStyle {
    PRIMARY,
    SECONDARY,
    TERTIARY,
    DESTRUCTIVE,
}

class PantryUiComponents(private val context: Context) {
    private val resources = context.resources

    fun appBar(
        title: String,
        showBack: Boolean,
        brand: Boolean = false,
        end: View? = null,
        leading: View? = null,
        onBack: () -> Unit,
    ): View =
        LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            val gutter = pageGutter()
            val vertical = if (brand) space(1) else space(2)
            setPadding(gutter, vertical, gutter, vertical)
            minimumHeight = if (brand) space(8) + space(6) else dimen(R.dimen.pantry_app_bar_height)
            ViewCompat.setOnApplyWindowInsetsListener(this) { view, insets ->
                val top = insets.getInsets(WindowInsetsCompat.Type.statusBars() or WindowInsetsCompat.Type.displayCutout()).top
                view.setPadding(gutter, top + vertical, gutter, vertical)
                insets
            }
            if (leading != null) {
                addView(leading)
            } else if (showBack) {
                addView(iconButton(R.drawable.ic_sage_back, context.getString(R.string.navigate_back), R.id.app_bar_back, onBack))
            }
            if (brand) {
                addView(FrameLayout(context).apply {
                    id = R.id.pantry_brand_logo
                    importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                    background = shape(R.color.pantry_surface, R.dimen.pantry_brand_radius)
                    clipToOutline = true
                    // The original tile spans 92 of the vector's 108 units. Trim only its transparent margin.
                    val tileSize = dimen(R.dimen.pantry_brand_size)
                    val canvasSize = (tileSize * 108 + 46) / 92
                    addView(icon(R.drawable.ic_pantryproof), FrameLayout.LayoutParams(canvasSize, canvasSize, Gravity.CENTER))
                }, squareParams(R.dimen.pantry_brand_size))
            }
            addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_ScreenTitle).apply {
                text = title
                if (brand) textSize = 26f
                if (showBack || brand || leading != null) setPaddingRelative(space(2), 0, 0, 0)
                ViewCompat.setAccessibilityHeading(this, true)
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            end?.let { addView(it, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { marginStart = space(2) }) }
        }

    fun progressHeader(step: Int, title: String): View =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            val label = TextView(context, null, 0, R.style.TextAppearance_PantryProof_Label).apply {
                text = context.getString(R.string.sage_step_count, step)
                setTextColor(color(R.color.pantry_on_surface))
            }
            addView(LinearLayout(context).apply {
                gravity = Gravity.CENTER_VERTICAL
                addView(label, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Label).apply {
                    text = title
                    setTextColor(color(R.color.pantry_on_surface))
                    setPaddingRelative(space(2), 0, 0, 0)
                })
                contentDescription = context.getString(R.string.progress_accessibility, step, title)
                isFocusable = true
                label.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                getChildAt(1).importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            })
            addView(progressTrack(step), LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, space(1),
            ).apply { topMargin = space(2) })
        }

    fun banner(title: String, message: String, tone: PantryBannerTone): View {
        val (backgroundColor, foregroundColor) = when (tone) {
            PantryBannerTone.INFO -> R.color.pantry_info_container to R.color.pantry_on_info_container
            PantryBannerTone.DEMO -> R.color.pantry_secondary_container to R.color.pantry_on_secondary_container
            PantryBannerTone.SUCCESS -> R.color.pantry_primary_container to R.color.pantry_on_primary_container
            PantryBannerTone.ERROR -> R.color.pantry_error_container to R.color.pantry_on_error_container
        }
        val iconResource = when (tone) {
            PantryBannerTone.INFO -> R.drawable.ic_sage_info
            PantryBannerTone.DEMO, PantryBannerTone.ERROR -> R.drawable.ic_sage_warn
            PantryBannerTone.SUCCESS -> R.drawable.ic_sage_check
        }
        return LinearLayout(context).apply {
            gravity = Gravity.TOP
            setPadding(space(3), space(3), space(3), space(3))
            background = shape(backgroundColor, R.dimen.pantry_radius_banner)
            addView(icon(iconResource).apply { setColorFilter(color(foregroundColor)) },
                squareParams(R.dimen.pantry_space_6).apply { marginEnd = space(2) })
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Label).apply {
                    text = title
                    setTextColor(color(foregroundColor))
                })
                addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
                    text = message
                    setTextColor(color(foregroundColor))
                    setPadding(0, space(1), 0, 0)
                    setLineSpacing(0f, 1.12f)
                })
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
    }

    fun actionButton(
        label: String,
        style: PantryActionStyle,
        enabled: Boolean = true,
        viewId: Int = View.NO_ID,
        iconResource: Int? = null,
        action: () -> Unit,
    ): Button = Button(context).apply {
        id = viewId
        text = label
        textSize = 15f
        typeface = Typeface.DEFAULT_BOLD
        setAllCaps(false)
        minHeight = dimen(R.dimen.pantry_button_height)
        isEnabled = enabled
        contentDescription = label

        val (fill, foreground, stroke) = when (style) {
            PantryActionStyle.PRIMARY -> Triple(
                R.color.pantry_primary,
                R.color.pantry_on_primary,
                null,
            )
            PantryActionStyle.SECONDARY -> Triple(
                R.color.pantry_surface_bright,
                R.color.pantry_primary,
                R.color.pantry_primary,
            )
            PantryActionStyle.TERTIARY -> Triple(
                android.R.color.transparent,
                R.color.pantry_on_surface,
                null,
            )
            PantryActionStyle.DESTRUCTIVE -> Triple(android.R.color.transparent, R.color.pantry_error, null)
        }
        setTextColor(ColorStateList(
            arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
            intArrayOf(color(R.color.pantry_on_surface), color(foreground)),
        ))
        backgroundTintList = null
        stateListAnimator = null
        background = controlBackground(fill, stroke)
        setPaddingRelative(space(3), space(2), space(3), space(2))
        iconResource?.let {
            val icon = context.getDrawable(it)?.mutate()
            icon?.setTint(color(foreground))
            setCompoundDrawablesRelativeWithIntrinsicBounds(icon, null, null, null)
            compoundDrawablePadding = space(2)
        }
        setOnClickListener { action() }
    }

    fun quantityButton(
        label: String,
        description: String,
        enabled: Boolean,
        viewId: Int = View.NO_ID,
        action: () -> Unit,
    ): Button = Button(context).apply {
        id = viewId
        text = label
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(ColorStateList(
            arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
            intArrayOf(color(R.color.pantry_on_surface), color(R.color.pantry_primary)),
        ))
        setAllCaps(false)
        minWidth = dimen(R.dimen.pantry_touch_target)
        minHeight = dimen(R.dimen.pantry_touch_target)
        isEnabled = enabled
        contentDescription = description
        backgroundTintList = null
        stateListAnimator = null
        background = controlBackground(R.color.pantry_primary_container)
        setOnClickListener { action() }
    }

    fun card(
        backgroundColor: Int = R.color.pantry_surface_bright,
        content: LinearLayout.() -> Unit,
    ): LinearLayout = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(space(4), space(4), space(4), space(4))
        background = shape(
            backgroundColor,
            R.dimen.pantry_radius_card,
            R.color.pantry_outline_variant,
        )
        content()
    }

    fun navigationCard(
        title: String,
        description: String,
        actionLabel: String,
        badge: String? = null,
        viewId: Int = View.NO_ID,
        action: () -> Unit,
    ): View = card {
        id = viewId
        isClickable = true
        isFocusable = true
        minimumHeight = dimen(R.dimen.pantry_touch_target)
        contentDescription = listOf(
            title.trim().trimEnd('.'),
            description.trim().trimEnd('.'),
            actionLabel.trim().trimEnd('.'),
        ).joinToString(". ")
        setOnClickListener { action() }

        val stackMetadata = resources.configuration.fontScale >= 1.3f ||
            resources.configuration.screenWidthDp < 360
        val heading = LinearLayout(context).apply {
            orientation = if (stackMetadata) LinearLayout.VERTICAL else LinearLayout.HORIZONTAL
            gravity = if (stackMetadata) Gravity.START else Gravity.CENTER_VERTICAL
        }
        val titleView = TextView(context, null, 0, R.style.TextAppearance_PantryProof_ItemTitle).apply {
            text = title
        }
        heading.addView(
            titleView,
            if (stackMetadata) {
                LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                )
            } else {
                LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            },
        )
        badge?.let { badgeText ->
            heading.addView(statusChip(badgeText), LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply {
                if (stackMetadata) topMargin = space(2)
            })
        }
        addView(heading)
        addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
            text = description
            setPadding(0, space(2), space(2), 0)
            setLineSpacing(0f, 1.12f)
        })
        addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Label).apply {
            text = context.getString(R.string.action_arrow, actionLabel)
            setTextColor(color(R.color.pantry_primary))
            setPadding(0, space(3), 0, 0)
        })
    }

    fun unavailableAction(title: String, message: String): View = card(
        backgroundColor = R.color.pantry_surface_container,
    ) {
        val stackMetadata = resources.configuration.fontScale >= 1.3f ||
            resources.configuration.screenWidthDp < 360
        addView(LinearLayout(context).apply {
            orientation = if (stackMetadata) LinearLayout.VERTICAL else LinearLayout.HORIZONTAL
            gravity = if (stackMetadata) Gravity.START else Gravity.CENTER_VERTICAL
            val titleView = TextView(context, null, 0, R.style.TextAppearance_PantryProof_ItemTitle).apply {
                text = title
            }
            addView(
                titleView,
                if (stackMetadata) {
                    LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.WRAP_CONTENT,
                    )
                } else {
                    LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                },
            )
            addView(
                statusChip(context.getString(R.string.add_receipt_camera_unavailable)),
                LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                ).apply {
                    if (stackMetadata) topMargin = space(2)
                },
            )
        })
        addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
            text = message
            setPadding(0, space(2), 0, 0)
        })
        contentDescription = "$title. $message"
    }

    fun statePanel(title: String, message: String, tone: PantryBannerTone): View =
        banner(title, message, tone)

    fun statusChip(label: String): TextView = TextView(
        context,
        null,
        0,
        R.style.TextAppearance_PantryProof_Label,
    ).apply {
        text = label
        setTextColor(color(R.color.pantry_on_secondary_container))
        background = shape(
            R.color.pantry_secondary_container,
            R.dimen.pantry_radius_control,
        )
        setPadding(space(2), space(1), space(2), space(1))
    }

    fun pageGutter(): Int = dimen(if (resources.configuration.screenWidthDp >= 600)
        R.dimen.pantry_page_gutter_wide else R.dimen.pantry_page_gutter)

    fun stacked(): Boolean = resources.configuration.fontScale >= 1.5f ||
        resources.configuration.screenWidthDp < 360

    fun icon(resource: Int, tile: Boolean = false): ImageView = ImageView(context).apply {
        setImageResource(resource)
        scaleType = ImageView.ScaleType.FIT_CENTER
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        if (tile) {
            val size = space(10)
            layoutParams = LinearLayout.LayoutParams(size, size)
            val inset = space(2)
            setPadding(inset, inset, inset, inset)
            background = shape(R.color.pantry_primary_container, R.dimen.pantry_radius_control)
        }
    }

    fun iconButton(resource: Int, label: String, viewId: Int = View.NO_ID, action: () -> Unit): View =
        ImageButton(context).apply {
            id = viewId
            val size = dimen(R.dimen.pantry_touch_target)
            layoutParams = LinearLayout.LayoutParams(size, size)
            setImageResource(resource)
            contentDescription = label
            background = ripple(shape(android.R.color.transparent, R.dimen.pantry_radius_control))
            setOnClickListener { action() }
        }

    fun floatingScanAction(action: () -> Unit): View = ImageButton(context).apply {
        id = R.id.home_add_receipt
        setImageResource(R.drawable.ic_sage_scan)
        imageTintList = ColorStateList.valueOf(color(R.color.pantry_on_primary))
        contentDescription = context.getString(R.string.home_add_receipt)
        background = ripple(shape(R.color.pantry_primary, R.dimen.pantry_radius_card))
        elevation = space(1).toFloat()
        setOnClickListener { action() }
    }

    fun styleFilterControl(control: View, active: Boolean) {
        control.isSelected = active
        control.background = ripple(shape(
            if (active) R.color.pantry_primary_container else android.R.color.transparent,
            R.dimen.pantry_radius_control,
        ))
    }

    fun sourceCard(label: String, supporting: String, iconResource: Int, viewId: Int, action: () -> Unit): View =
        card {
            id = viewId
            gravity = Gravity.CENTER
            minimumHeight = space(8) * 3 + space(4)
            addView(icon(iconResource, tile = true))
            addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_ItemTitle).apply {
                text = label
                gravity = Gravity.CENTER
                setPadding(0, space(2), 0, 0)
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            })
            addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
                text = supporting
                gravity = Gravity.CENTER
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            })
            contentDescription = "$label. $supporting"
            markButton(this)
            setOnClickListener { action() }
        }

    fun toolbarAction(label: String, resource: Int, viewId: Int, action: () -> Unit): Button =
        actionButton(label, PantryActionStyle.TERTIARY, viewId = viewId, action = action).apply {
            setTextColor(color(R.color.pantry_primary))
            setTextAppearance(R.style.TextAppearance_PantryProof_Label)
            setTextColor(ColorStateList(
                arrayOf(intArrayOf(-android.R.attr.state_enabled), intArrayOf()),
                intArrayOf(color(R.color.pantry_on_surface_variant), color(R.color.pantry_primary)),
            ))
            setCompoundDrawablesRelativeWithIntrinsicBounds(0, resource, 0, 0)
            compoundDrawablePadding = space(1)
            setPaddingRelative(space(1), space(2), space(1), space(2))
        }

    fun showChoicePopup(
        anchor: View, labels: Array<String>, selected: Int, listId: Int = R.id.inventory_sort_choices,
        onSelected: (Int) -> Unit,
    ) {
        val surface = popupSurface()
        val bounds = android.graphics.Rect()
        anchor.getWindowVisibleDisplayFrame(bounds)
        val availableWidth = bounds.width().takeIf { it > 0 } ?: resources.displayMetrics.widthPixels
        val popup = ListPopupWindow(context, null, android.R.attr.listPopupWindowStyle).apply {
            anchorView = anchor
            isModal = true
            inputMethodMode = ListPopupWindow.INPUT_METHOD_NEEDED
            setDropDownGravity(Gravity.END)
            verticalOffset = space(1)
            setBackgroundDrawable(surface)
            setListSelector(context.getDrawable(R.drawable.sage_popup_selector))
            setContentWidth(minOf(space(10) * 8, availableWidth - pageGutter() * 2))
            setAdapter(object : ArrayAdapter<String>(context, android.R.layout.simple_list_item_1, labels) {
                override fun getView(position: Int, recycled: View?, parent: ViewGroup): View =
                    choiceRow(labels[position], position == selected, recycled)
            })
        }
        popup.setOnItemClickListener { _, _, position, _ ->
            onSelected(position)
            popup.dismiss()
        }
        popup.show()
        popup.listView?.apply {
            id = listId
            setDrawSelectorOnTop(true)
            choiceMode = android.widget.ListView.CHOICE_MODE_SINGLE
            setItemChecked(selected, true)
        }
    }

    fun styleDropdown(spinner: Spinner, options: Array<String>) {
        spinner.setPopupBackgroundDrawable(popupSurface())
        spinner.adapter = object : ArrayAdapter<String>(context, android.R.layout.simple_spinner_item, options) {
            override fun getDropDownView(position: Int, recycled: View?, parent: ViewGroup): View =
                choiceRow(options[position], position == spinner.selectedItemPosition, recycled)
        }
    }

    private fun popupSurface() = context.getDrawable(R.drawable.sage_popup_background)

    private fun choiceRow(label: String, checked: Boolean, recycled: View?): CheckedTextView =
        ((recycled as? CheckedTextView) ?: CheckedTextView(context)).apply {
            setTextAppearance(R.style.TextAppearance_PantryProof_Body)
            text = label
            isChecked = checked
            minimumHeight = dimen(R.dimen.pantry_touch_target)
            gravity = Gravity.CENTER_VERTICAL
            setPaddingRelative(space(4), space(2), space(3), space(2))
            setTextColor(color(if (checked) R.color.pantry_primary else R.color.pantry_on_surface))
            setBackgroundColor(color(if (checked) R.color.pantry_primary_container else R.color.pantry_surface_bright))
            setCheckMarkDrawable(if (checked) context.getDrawable(R.drawable.ic_sage_check) else null)
        }

    fun compactToolbarAction(label: String, resource: Int, viewId: Int, action: () -> Unit): Button =
        toolbarAction(label, resource, viewId, action).apply {
            minHeight = dimen(R.dimen.pantry_touch_target)
            minimumHeight = dimen(R.dimen.pantry_touch_target)
            minWidth = 0
            minimumWidth = 0
            setPaddingRelative(space(1), space(1), space(1), space(1))
        }

    fun actionRow(
        title: String, subtitle: String?, resource: Int?, chevron: ImageView,
        inventoryRow: Boolean = false, action: () -> Unit,
    ): View =
        LinearLayout(context).apply {
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = dimen(R.dimen.pantry_touch_target)
            resource?.let { addView(icon(it, tile = true)) }
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                if (resource != null) setPaddingRelative(space(if (inventoryRow) 4 else 3), 0, 0, 0)
                val titleAppearance = if (inventoryRow) R.style.TextAppearance_PantryProof_InventoryCategoryTitle
                    else R.style.TextAppearance_PantryProof_ItemTitle
                addView(TextView(context, null, 0, titleAppearance).apply {
                    id = R.id.sage_action_title
                    text = title
                })
                addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
                    id = R.id.sage_action_subtitle
                    text = subtitle
                    visibility = if (subtitle == null) View.GONE else View.VISIBLE
                    if (inventoryRow) setTextColor(color(R.color.pantry_on_surface_variant))
                })
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(chevron, squareParams(R.dimen.pantry_space_6).apply { marginStart = space(2) })
            contentDescription = listOfNotNull(title, subtitle).joinToString(". ")
            markButton(this, inventoryRow)
            if (inventoryRow) setPaddingRelative(paddingStart, space(1), paddingEnd, space(1))
            setOnClickListener { action() }
        }

    fun updateActionRowLabel(header: View, title: String, subtitle: String?) {
        val description = listOfNotNull(title, subtitle).joinToString(". ")
        if (header.contentDescription == description) return
        header.findViewById<TextView>(R.id.sage_action_title).text = title
        header.findViewById<TextView>(R.id.sage_action_subtitle).apply {
            text = subtitle
            visibility = if (subtitle == null) View.GONE else View.VISIBLE
        }
        header.contentDescription = description
    }

    fun markButton(view: View, inventoryRow: Boolean = false) {
        view.isFocusable = true
        if (inventoryRow) {
            // Draw touch feedback under the content. A released row has no touch animation to retain.
            view.background = StateListDrawable().apply {
                addState(intArrayOf(android.R.attr.state_enabled, android.R.attr.state_pressed),
                    shape(R.color.pantry_inventory_pressed, R.dimen.pantry_radius_control))
                addState(intArrayOf(android.R.attr.state_enabled, android.R.attr.state_focused,
                    android.R.attr.state_window_focused),
                    shape(R.color.pantry_surface_bright, R.dimen.pantry_radius_control, R.color.pantry_primary))
                addState(intArrayOf(), shape(R.color.pantry_surface_bright, R.dimen.pantry_radius_control))
            }
        } else view.foreground = ripple(ColorDrawable(Color.TRANSPARENT))
        ViewCompat.setAccessibilityDelegate(view, object : AccessibilityDelegateCompat() {
            override fun onInitializeAccessibilityNodeInfo(host: View, info: AccessibilityNodeInfoCompat) {
                super.onInitializeAccessibilityNodeInfo(host, info)
                info.className = Button::class.java.name
            }
        })
    }

    fun bottomSheet(title: String, content: View, footer: View? = null, onDismiss: (() -> Unit)? = null): Dialog {
        val dialog = Dialog(context)
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)
        val anchor = (context as? android.app.Activity)?.currentFocus
        val root = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pageGutter(), space(2), pageGutter(), space(3))
            val radius = dimen(R.dimen.pantry_radius_sheet).toFloat()
            background = GradientDrawable().apply {
                setColor(color(R.color.pantry_surface_bright))
                cornerRadii = floatArrayOf(radius, radius, radius, radius, 0f, 0f, 0f, 0f)
            }
            ViewCompat.setAccessibilityPaneTitle(this, title)
            addView(View(context).apply {
                background = shape(R.color.pantry_soft_sage, R.dimen.pantry_radius_control)
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            }, LinearLayout.LayoutParams(space(8), space(1)).apply { gravity = Gravity.CENTER_HORIZONTAL })
            addView(LinearLayout(context).apply {
                gravity = Gravity.CENTER_VERTICAL
                addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_ScreenTitle).apply {
                    text = title
                    ViewCompat.setAccessibilityHeading(this, true)
                }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                addView(iconButton(R.drawable.ic_sage_close, context.getString(R.string.sage_close)) { dialog.dismiss() })
            })
            addView(ScrollView(context).apply {
                isFillViewport = false
                addView(content)
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            footer?.let { addView(it, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)) }
        }
        dialog.setContentView(root)
        dialog.setOnDismissListener {
            if (anchor?.isAttachedToWindow == true) anchor.requestFocus()
            onDismiss?.invoke()
        }
        @Suppress("DEPRECATION")
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            setGravity(Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL)
            setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE or WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN)
        }
        dialog.show()
        dialog.window?.setLayout(
            if (resources.configuration.screenWidthDp > 640) dimen(R.dimen.pantry_form_max_width)
            else ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
        )
        return dialog
    }

    fun inventorySuccess(title: String, message: String, dismiss: () -> Unit): View = LinearLayout(context).apply {
        id = R.id.inventory_success
        gravity = Gravity.CENTER_VERTICAL
        setPaddingRelative(space(2), space(1), 0, space(1))
        background = shape(R.color.pantry_primary_container, R.dimen.pantry_radius_control)
        elevation = space(1) / 2f
        addView(FrameLayout(context).apply {
            background = shape(R.color.pantry_primary, R.dimen.pantry_radius_navigation)
            addView(icon(R.drawable.ic_sage_check).apply {
                setColorFilter(color(R.color.pantry_on_primary))
            }, FrameLayout.LayoutParams(space(4), space(4), Gravity.CENTER))
        }, squareParams(R.dimen.pantry_space_6))
        addView(LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPaddingRelative(space(2), space(1), 0, space(1))
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
            addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Label).apply { text = title })
            if (message.isNotBlank()) addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
                text = message
            })
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        addView(iconButton(R.drawable.ic_sage_close, context.getString(R.string.sage_dismiss),
            R.id.inventory_success_dismiss, dismiss))
    }

    fun color(resourceId: Int): Int = context.getColor(resourceId)

    fun dimen(resourceId: Int): Int = resources.getDimensionPixelSize(resourceId)

    private fun progressTrack(activeStep: Int): View = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        repeat(3) { index ->
            addView(View(context).apply {
                background = shape(
                    if (index < activeStep) R.color.pantry_primary else R.color.pantry_primary_container,
                    R.dimen.pantry_space_1,
                )
            }, LinearLayout.LayoutParams(0, space(1), 1f).apply {
                if (index > 0) marginStart = space(1)
            })
        }
    }

    private fun shape(fillColor: Int, radius: Int, strokeColor: Int? = null): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(color(fillColor))
            cornerRadius = resources.getDimension(radius)
            strokeColor?.let { setStroke(dimen(R.dimen.pantry_stroke), color(it)) }
        }

    private fun controlBackground(fill: Int, stroke: Int? = null) = StateListDrawable().apply {
        addState(intArrayOf(-android.R.attr.state_enabled),
            shape(R.color.pantry_surface_container, R.dimen.pantry_radius_control))
        addState(intArrayOf(), ripple(shape(fill, R.dimen.pantry_radius_control, stroke)))
    }

    private fun ripple(content: android.graphics.drawable.Drawable): RippleDrawable =
        RippleDrawable(ColorStateList.valueOf(color(R.color.pantry_soft_sage)), content,
            shape(R.color.pantry_surface_bright, R.dimen.pantry_radius_control))

    private fun squareParams(size: Int) = LinearLayout.LayoutParams(dimen(size), dimen(size))

    private fun space(multiplier: Int): Int =
        resources.getDimensionPixelSize(R.dimen.pantry_space_1) * multiplier
}
