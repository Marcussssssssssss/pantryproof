package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryCategory
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryMetadata
import com.pantryproof.prototype.data.InventoryUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SageInventoryGroupsTest {
    private val fruit = InventoryCategory.VEGETABLES_FRUITS
    private val dry = InventoryCategory.DRY_FOOD

    @Test fun groupsPreserveExactProjectedOrderAndCountsAcrossSources() {
        val rows = listOf(row("live-receipt-one", fruit), row("manual-receipt-two", fruit), row("stock-base", dry))
        val groups = requireNotNull(sageCategoryGroups(rows))
        assertEquals(rows, groups.values.flatten())
        assertEquals(mapOf(fruit to 2, dry to 1), groups.mapValues { it.value.size })
    }

    @Test fun repeatedCategoryRequiresFlatListWithoutChangingAnySort() {
        val rows = listOf(
            row("manual-receipt-a", fruit, "0.750").copy(name = "Market apples"),
            row("manual-inventory-b", dry, "2.5").copy(name = "Market beans"),
            row("manual-receipt-c", fruit, "10.0").copy(name = "Market carrots"),
        )
        InventoryBrowseProjection.Sort.entries.forEach { sort ->
            val projected = InventoryBrowseProjection(sort = sort).project(rows)
            assertEquals(if (sort == InventoryBrowseProjection.Sort.QUANTITY_DESCENDING) rows.reversed() else rows, projected)
            assertNull(sageCategoryGroups(projected))
        }
        val manual = InventoryBrowseProjection(query = "market", source = InventoryBrowseProjection.Source.MANUAL).project(rows)
        assertEquals(listOf(rows.first(), rows.last()), sageCategoryGroups(manual)?.get(fruit))
    }

    private fun row(id: String, category: InventoryCategory, quantity: String = "1") =
        InventoryItem(id, id, quantity.toBigDecimal(), "", InventoryUnit.KILOGRAM, InventoryMetadata(category))
}
