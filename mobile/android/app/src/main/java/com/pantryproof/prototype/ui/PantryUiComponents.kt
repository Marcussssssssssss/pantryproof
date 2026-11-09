package com.pantryproof.prototype.ui

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.view.ViewCompat
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
}

class PantryUiComponents(private val context: Context) {
    private val resources = context.resources

    fun appBar(title: String, showBack: Boolean, onBack: () -> Unit): View =
        LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(space(2), space(2), space(4), space(2))
            setBackgroundColor(color(R.color.pantry_green_dark))
            minimumHeight = dimen(R.dimen.pantry_app_bar_height)
            ViewCompat.setOnApplyWindowInsetsListener(this) { view, insets ->
                val statusBarTop = insets.getInsets(WindowInsetsCompat.Type.statusBars()).top
                view.setPadding(space(2), statusBarTop + space(2), space(4), space(2))
                insets
            }

            if (showBack) {
                addView(Button(context, null, android.R.attr.borderlessButtonStyle).apply {
                    id = R.id.app_bar_back
                    text = "‹"
                    setTextSize(TypedValue.COMPLEX_UNIT_DIP, 29f)
                    setTextColor(color(R.color.pantry_on_primary))
                    setAllCaps(false)
                    backgroundTintList = ColorStateList.valueOf(Color.TRANSPARENT)
                    stateListAnimator = null
                    elevation = 0f
                    minWidth = dimen(R.dimen.pantry_touch_target)
                    minHeight = dimen(R.dimen.pantry_touch_target)
                    contentDescription = context.getString(R.string.navigate_back)
                    setOnClickListener { onBack() }
                }, squareParams(R.dimen.pantry_touch_target))
            }

            addView(TextView(context).apply {
                text = title
                setTextColor(color(R.color.pantry_on_primary))
                textSize = 20f
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER_VERTICAL
                setPadding(space(2), 0, 0, 0)
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))

            addView(TextView(context).apply {
                text = context.getString(R.string.demo_label).uppercase()
                setTextColor(color(R.color.pantry_on_primary_container))
                textSize = 11f
                typeface = Typeface.DEFAULT_BOLD
                letterSpacing = 0.1f
                background = shape(
                    R.color.pantry_primary_container,
                    R.dimen.pantry_radius_control,
                )
                setPadding(space(2), space(1), space(2), space(1))
                contentDescription = context.getString(R.string.demo_label)
            })
        }

    fun progressHeader(step: Int, title: String, description: String): View =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            contentDescription = context.getString(R.string.progress_accessibility, step, title)

            addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Label).apply {
                text = context.getString(R.string.progress_visible, step)
                setTextColor(color(R.color.pantry_primary))
                letterSpacing = 0.12f
            })
            addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_ScreenTitle).apply {
                text = title
                setPadding(0, space(1), 0, space(1))
            })
            addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
                text = description
                setLineSpacing(0f, 1.15f)
            })
            addView(progressTrack(step), LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                space(1),
            ).apply {
                topMargin = space(3)
            })
        }

    fun banner(title: String, message: String, tone: PantryBannerTone): View {
        val (backgroundColor, foregroundColor) = when (tone) {
            PantryBannerTone.INFO -> R.color.pantry_info_container to R.color.pantry_on_info_container
            PantryBannerTone.DEMO -> R.color.pantry_secondary_container to R.color.pantry_on_secondary_container
            PantryBannerTone.SUCCESS -> R.color.pantry_primary_container to R.color.pantry_on_primary_container
            PantryBannerTone.ERROR -> R.color.pantry_error_container to R.color.pantry_on_error_container
        }
        return LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(space(4), space(3), space(4), space(3))
            background = shape(backgroundColor, R.dimen.pantry_radius_banner)
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
        }
    }

    fun actionButton(
        label: String,
        style: PantryActionStyle,
        enabled: Boolean = true,
        viewId: Int = View.NO_ID,
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
                R.color.pantry_on_surface_variant,
                null,
            )
        }
        setTextColor(color(foreground))
        backgroundTintList = null
        background = shape(fill, R.dimen.pantry_radius_control, stroke)
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
        setTextSize(TypedValue.COMPLEX_UNIT_DIP, 22f)
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(color(
            if (enabled) R.color.pantry_primary else R.color.pantry_outline,
        ))
        setAllCaps(false)
        minWidth = dimen(R.dimen.pantry_touch_target)
        minHeight = dimen(R.dimen.pantry_touch_target)
        isEnabled = enabled
        contentDescription = description
        backgroundTintList = null
        background = shape(
            if (enabled) R.color.pantry_primary_container else R.color.pantry_surface_container,
            R.dimen.pantry_radius_control,
            R.color.pantry_outline_variant,
        )
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

    fun homeHero(): View = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(space(6), space(6), space(6), space(6))
        background = shape(R.color.pantry_primary, R.dimen.pantry_radius_hero)
        addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Label).apply {
            text = context.getString(R.string.home_brand_eyebrow)
            setTextColor(color(R.color.pantry_primary_container))
            letterSpacing = 0.15f
        })
        addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Display).apply {
            text = context.getString(R.string.home_brand_title)
            setTextColor(color(R.color.pantry_on_primary))
            textSize = 29f
            setPadding(0, space(2), 0, space(2))
        })
        addView(TextView(context, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
            text = context.getString(R.string.home_brand_subtitle)
            setTextColor(color(R.color.pantry_primary_container))
        })
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

    fun color(resourceId: Int): Int = context.getColor(resourceId)

    fun dimen(resourceId: Int): Int = resources.getDimensionPixelSize(resourceId)

    private fun progressTrack(activeStep: Int): View = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        repeat(4) { index ->
            addView(View(context).apply {
                background = shape(
                    if (index < activeStep) R.color.pantry_primary else R.color.pantry_outline_variant,
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

    private fun squareParams(size: Int) = LinearLayout.LayoutParams(dimen(size), dimen(size))

    private fun space(multiplier: Int): Int =
        resources.getDimensionPixelSize(R.dimen.pantry_space_1) * multiplier
}
