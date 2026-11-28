package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryCategory
import com.pantryproof.prototype.data.InventoryItem

/** Keep category headers in first-seen inventory order, independent of sorting or filtering. */
internal fun sageCategoryGroups(
    inventory: List<InventoryItem>,
    projected: List<InventoryItem>,
): Map<InventoryCategory, List<InventoryItem>> {
    val byCategory = projected.groupBy { it.household.category }
    val categoryOrder = inventory.map { it.household.category }.distinct()
    return buildMap {
        categoryOrder.forEach { category -> byCategory[category]?.let { put(category, it) } }
    }
}
