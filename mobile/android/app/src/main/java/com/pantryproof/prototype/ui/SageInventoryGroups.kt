package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryItem

/** Returns source groups only when flattening them reproduces the projected order. */
internal fun sageSourceGroups(
    projected: List<InventoryItem>,
): Map<InventoryBrowseProjection.Source, List<InventoryItem>>? {
    val groups = linkedMapOf<InventoryBrowseProjection.Source, MutableList<InventoryItem>>()
    var previous: InventoryBrowseProjection.Source? = null
    for (row in projected) {
        val source = InventoryBrowseProjection.sourceOf(row)
        if (source != previous && source in groups) return null
        groups.getOrPut(source) { mutableListOf() }.add(row)
        previous = source
    }
    return groups
}
