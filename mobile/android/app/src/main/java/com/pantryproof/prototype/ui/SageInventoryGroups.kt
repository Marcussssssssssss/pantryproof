package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryCategory
import com.pantryproof.prototype.data.InventoryItem

/** A category's single card can preserve global order only when its rows are contiguous. */
internal fun sageCategoryGroups(projected: List<InventoryItem>): Map<InventoryCategory, List<InventoryItem>>? {
    val groups = linkedMapOf<InventoryCategory, MutableList<InventoryItem>>()
    var previous: InventoryCategory? = null
    for (row in projected) {
        val category = row.household.category
        if (category != previous && category in groups) return null
        groups.getOrPut(category) { mutableListOf() }.add(row)
        previous = category
    }
    return groups
}
