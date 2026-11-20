package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryItem
import java.util.Locale

/** Session UI controls only. Projection returns original items without changing stock or order. */
internal class InventoryBrowseProjection(
    var query: String = "",
    var sort: Sort = Sort.ORIGINAL,
    var source: Source = Source.ALL,
) {
    enum class Sort { ORIGINAL, NAME, QUANTITY_ASCENDING, QUANTITY_DESCENDING }
    enum class Source { ALL, BASELINE, RECEIPT_PREVIEW, MANUAL }

    fun project(inventory: List<InventoryItem>): List<InventoryItem> {
        val needle = query.trim()
        val matches = inventory.withIndex().filter {
            it.value.name.contains(needle, ignoreCase = true) &&
                (source == Source.ALL || sourceOf(it.value) == source)
        }
        val ordered = when (sort) {
            Sort.ORIGINAL -> matches
            Sort.NAME -> matches.sortedWith(
                compareBy<IndexedValue<InventoryItem>> { it.value.name.lowercase(Locale.ROOT) }
                    .thenBy { it.index },
            )
            Sort.QUANTITY_ASCENDING -> matches.sortedWith(
                compareBy<IndexedValue<InventoryItem>> { it.value.quantity }.thenBy { it.index },
            )
            Sort.QUANTITY_DESCENDING -> matches.sortedWith(
                compareByDescending<IndexedValue<InventoryItem>> { it.value.quantity }.thenBy { it.index },
            )
        }
        return ordered.map { it.value }
    }

    companion object {
        fun sourceOf(item: InventoryItem): Source = when {
            item.id.startsWith(PantryUiState.MANUAL_ROW_PREFIX) -> Source.MANUAL
            item.id.startsWith("receipt-") -> Source.RECEIPT_PREVIEW
            else -> Source.BASELINE
        }
    }
}
