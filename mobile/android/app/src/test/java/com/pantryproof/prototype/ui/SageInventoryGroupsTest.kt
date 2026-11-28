package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryCategory
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryMetadata
import com.pantryproof.prototype.data.InventoryUnit
import org.junit.Assert.assertEquals
import org.junit.Test

class SageInventoryGroupsTest {
    private val fruit = InventoryCategory.VEGETABLES_FRUITS
    private val dry = InventoryCategory.DRY_FOOD

    @Test fun groupsPreserveExactProjectedOrderAndCountsAcrossSources() {
        val rows = listOf(row("live-receipt-one", fruit), row("manual-receipt-two", fruit), row("stock-base", dry))
        val groups = sageCategoryGroups(rows, rows)
        assertEquals(rows, groups.values.flatten())
        assertEquals(mapOf(fruit to 2, dry to 1), groups.mapValues { it.value.size })
    }

    @Test fun interleavedCategoriesKeepTheirOrderAndSortWithinEachGroup() {
        val rows = listOf(
            row("manual-receipt-a", fruit, "10.0").copy(name = "Market pears"),
            row("manual-inventory-b", dry, "2.5").copy(name = "Market beans"),
            row("manual-receipt-c", fruit, "0.750").copy(name = "Market apples"),
            row("live-receipt-d", fruit, "0.75").copy(name = "market APPLES"),
        )
        val (pears, beans, apples, scannedApples) = rows
        val expectations = mapOf(
            InventoryBrowseProjection.Sort.ORIGINAL to listOf(pears, apples, scannedApples),
            InventoryBrowseProjection.Sort.NAME to listOf(apples, scannedApples, pears),
            InventoryBrowseProjection.Sort.QUANTITY_ASCENDING to listOf(apples, scannedApples, pears),
            InventoryBrowseProjection.Sort.QUANTITY_DESCENDING to listOf(pears, apples, scannedApples),
        )
        expectations.forEach { (sort, expected) ->
            val groups = sageCategoryGroups(rows, InventoryBrowseProjection(sort = sort).project(rows))
            assertEquals(listOf(fruit, dry), groups.keys.toList())
            assertEquals(listOf(expected, listOf(beans)), groups.values.toList())
        }
        val manual = InventoryBrowseProjection(query = "market", source = InventoryBrowseProjection.Source.MANUAL)
        assertEquals(mapOf(fruit to listOf(pears, apples)), sageCategoryGroups(rows, manual.project(rows)))
    }

    @Test fun appendedRecordsAndFilteredResultsKeepStableHeaderOrder() {
        val misc = InventoryCategory.UNCATEGORIZED
        val rows = listOf(row("stock-base", misc), row("manual-inventory-b", dry), row("receipt-c", fruit))
        val appended = rows + row("manual-inventory-d", dry) + row("manual-inventory-e", misc)
        val projection = InventoryBrowseProjection(query = "inventory", sort = InventoryBrowseProjection.Sort.NAME)
        val groups = sageCategoryGroups(appended, projection.project(appended))
        assertEquals(listOf(misc, dry), groups.keys.toList())
        assertEquals(listOf(appended.last(), appended[1], appended[3]), groups.values.flatten())
    }

    private fun row(id: String, category: InventoryCategory, quantity: String = "1") =
        InventoryItem(id, id, quantity.toBigDecimal(), "", InventoryUnit.KILOGRAM, InventoryMetadata(category))
}
