package com.pantryproof.prototype.ui

import android.content.Context
import android.view.View
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import androidx.core.view.ViewCompat
import com.pantryproof.prototype.R

/** Keeps the existing bound fields in place when their presentation is collapsed. */
internal class SageExpandableSections(
    private val context: Context,
    private val ui: PantryUiComponents,
    private val collapsed: MutableSet<String>,
    private val onToggled: (String, Boolean) -> Unit = { _, _ -> },
) {
    private data class Section(
        val key: String,
        val header: View,
        val chevron: ImageView,
        val issue: View,
        val body: View,
        val labelForState: ((Boolean) -> Pair<String, String?>)?,
    )

    private val sections = mutableListOf<Section>()
    private var allAction: Button? = null

    fun allAction(): View = ui.actionButton(
        context.getString(R.string.sage_collapse_all), PantryActionStyle.TERTIARY,
        viewId = R.id.sage_expand_all,
    ) {
        val expand = sections.all { it.key in collapsed }
        sections.forEach { setExpanded(it, expand) }
    }.also { allAction = it; updateAllAction() }

    fun add(
        key: String, title: String, body: View, subtitle: String? = null, icon: Int? = null,
        compact: Boolean = false, inventoryRow: Boolean = false, labelForState: ((Boolean) -> Pair<String, String?>)? = null,
    ): View {
        val chevron = ui.icon(R.drawable.ic_sage_down)
        lateinit var section: Section
        val header = ui.actionRow(title, subtitle, icon, chevron, inventoryRow) {
            setExpanded(section, key in collapsed)
        }
        val issue = ui.statusChip(context.getString(R.string.sage_needs_review)).apply {
            visibility = View.GONE
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        section = Section(key, header, chevron, issue, body, labelForState)
        sections += section
        setExpanded(section, key !in collapsed)
        return ui.card {
            if (compact) {
                val padding = ui.dimen(R.dimen.pantry_space_2)
                setPadding(padding, 0, padding, padding)
            }
            addView(header)
            addView(issue, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT,
            ))
            addView(body)
        }
    }

    fun refreshLabels() {
        sections.forEach(::refreshLabel)
    }

    private fun refreshLabel(section: Section) {
        val (title, subtitle) = section.labelForState?.invoke(section.key !in collapsed) ?: return
        ui.updateActionRowLabel(section.header, title, subtitle)
    }

    fun issues(affectedFields: Collection<View>) {
        sections.forEach { section ->
            section.issue.visibility =
                if (affectedFields.any { field -> contains(section, field) }) View.VISIBLE else View.GONE
        }
    }

    fun reveal(field: View) {
        sections.firstOrNull { contains(it, field) }?.let { setExpanded(it, true) }
    }

    private fun contains(section: Section, view: View): Boolean =
        generateSequence(view) { it.parent as? View }.any { it === section.body }

    private fun setExpanded(section: Section, expanded: Boolean) {
        val changed = expanded == (section.key in collapsed)
        if (expanded) collapsed.remove(section.key) else collapsed.add(section.key)
        if (changed) onToggled(section.key, expanded)
        if (!expanded && section.body.hasFocus()) section.header.requestFocus()
        section.body.visibility = if (expanded) View.VISIBLE else View.GONE
        section.chevron.setImageResource(if (expanded) R.drawable.ic_sage_down else R.drawable.ic_sage_right)
        refreshLabel(section)
        ViewCompat.setStateDescription(section.header,
            context.getString(if (expanded) R.string.sage_expanded else R.string.sage_collapsed))
        updateAllAction()
    }

    private fun updateAllAction() {
        allAction?.apply {
            isEnabled = sections.isNotEmpty()
            val label = context.getString(if (sections.all { it.key in collapsed })
                R.string.sage_expand_all else R.string.sage_collapse_all)
            text = label
            contentDescription = label
        }
    }
}
