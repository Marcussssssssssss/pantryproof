package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryItem
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SageInventoryGroupsTest {
    @Test fun groupsPreserveExactProjectedOrder() {
        val rows = listOf(
            row("live-receipt-one"), row("live-receipt-two"),
            row("stock-base"), row("receipt-preview"), row("manual-inventory-one"),
            row("manual-receipt-last"),
        )
        val groups = requireNotNull(sageSourceGroups(rows))
        assertEquals(rows, groups.values.flatten())
        assertEquals(rows.map(InventoryBrowseProjection::sourceOf).distinct(), groups.keys.toList())
    }

    @Test fun repeatedSourceAfterAnInterruptionRequiresAFlatList() {
        assertNull(sageSourceGroups(listOf(
            row("manual-receipt-first"), row("manual-inventory-one"), row("manual-receipt-last"),
        )))
    }

    private fun row(id: String) = InventoryItem(id, id, 1, "")
}
