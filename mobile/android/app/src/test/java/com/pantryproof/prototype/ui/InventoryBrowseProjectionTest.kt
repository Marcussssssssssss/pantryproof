package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryUnit
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.data.MockReceiptPresentationSource
import org.junit.Assert.*
import org.junit.Test

class InventoryBrowseProjectionTest {
    private val items = listOf(
        InventoryItem("stock-z", "Zulu rice", 4, "In pantry"),
        InventoryItem("stock-a", "apple", 1, "In fridge"),
        InventoryItem("receipt-one", "Rice preview", 7, "Temporary receipt preview"),
        InventoryItem("manual-receipt-one", "Manual rice", 2, "Manually entered receipt"),
        InventoryItem("stock-duplicate", "APPLE", 2, "In pantry"),
    )
    private fun ids(p: InventoryBrowseProjection) = p.project(items).map { it.id }

    @Test fun emptyQueryDefaultsToOriginalOrder() {
        assertEquals(items, InventoryBrowseProjection().project(items))
    }
    @Test fun searchIsCaseInsensitiveSubstringWithTrimmedWhitespace() {
        assertEquals(listOf("stock-z", "receipt-one", "manual-receipt-one"), ids(InventoryBrowseProjection(query = "  rIcE \t")))
    }
    @Test fun whitespaceOnlySearchShowsEverything() {
        assertEquals(items, InventoryBrowseProjection(query = " \t ").project(items))
    }
    @Test fun noMatchProducesEmptyProjectionWithoutRemovingStock() {
        assertTrue(InventoryBrowseProjection(query = "no fictional match").project(items).isEmpty())
        assertEquals(5, items.size)
    }
    @Test fun searchNeverRewritesProductNamesOrRawQuery() {
        val p = InventoryBrowseProjection(query = "  RICE  ")
        assertEquals("Zulu rice", p.project(items).first().name)
        assertEquals("  RICE  ", p.query)
    }
    @Test fun alphabeticalSortIsCaseInsensitiveAndKeepsOriginalPositionForTies() {
        val p = InventoryBrowseProjection(sort = InventoryBrowseProjection.Sort.NAME)
        assertEquals(listOf("stock-a", "stock-duplicate", "manual-receipt-one", "receipt-one", "stock-z"), ids(p))
    }
    @Test fun duplicateNamesPreserveDistinctOriginalIdsAndObjects() {
        val duplicates = listOf(items[1], items[1].copy(id = "stock-other"))
        val result = InventoryBrowseProjection(sort = InventoryBrowseProjection.Sort.NAME).project(duplicates)
        assertEquals(listOf("stock-a", "stock-other"), result.map { it.id })
        assertSame(duplicates[0], result[0]); assertSame(duplicates[1], result[1])
    }
    @Test fun decimalQuantitySortComparesNumericValuesAndKeepsTiesInSourceOrder() {
        val row = items.first()
        val unit = InventoryUnit.KILOGRAM
        val a = row.copy(id = "a", quantity = "10".toBigDecimal(), unit = unit)
        val b = row.copy(id = "b", quantity = "2.50".toBigDecimal(), unit = unit)
        val c = row.copy(id = "c", quantity = "2.500".toBigDecimal(), unit = unit)
        val projection = InventoryBrowseProjection(sort = InventoryBrowseProjection.Sort.QUANTITY_ASCENDING)
        assertEquals(listOf(b, c, a), projection.project(listOf(a, b, c)))
        projection.sort = InventoryBrowseProjection.Sort.QUANTITY_DESCENDING
        assertEquals(listOf(a, b, c), projection.project(listOf(a, b, c)))
    }

    @Test fun quantityAscendingKeepsOriginalPositionForTies() {
        assertEquals(listOf("stock-a", "manual-receipt-one", "stock-duplicate", "stock-z", "receipt-one"), ids(InventoryBrowseProjection(sort = InventoryBrowseProjection.Sort.QUANTITY_ASCENDING)))
    }
    @Test fun quantityDescendingKeepsOriginalPositionForTies() {
        assertEquals(listOf("receipt-one", "stock-z", "manual-receipt-one", "stock-duplicate", "stock-a"), ids(InventoryBrowseProjection(sort = InventoryBrowseProjection.Sort.QUANTITY_DESCENDING)))
    }
    @Test fun originalOrderCanBeRestoredAfterOtherSorts() {
        val p = InventoryBrowseProjection(sort = InventoryBrowseProjection.Sort.NAME)
        p.project(items); p.sort = InventoryBrowseProjection.Sort.ORIGINAL
        assertEquals(items, p.project(items))
    }
    @Test fun baselineFilterUsesRemainingIdsRatherThanStateText() {
        val p = InventoryBrowseProjection(source = InventoryBrowseProjection.Source.BASELINE)
        assertEquals(listOf("stock-z", "stock-a", "stock-duplicate"), ids(p))
        assertEquals(InventoryBrowseProjection.Source.BASELINE, InventoryBrowseProjection.sourceOf(items[0].copy(state = "Temporary receipt preview")))
    }
    @Test fun receiptPreviewFilterUsesExistingReceiptPrefix() {
        assertEquals(listOf("receipt-one"), ids(InventoryBrowseProjection(source = InventoryBrowseProjection.Source.RECEIPT_PREVIEW)))
    }
    @Test fun manualFilterUsesPantryManualPrefix() {
        assertEquals(listOf("manual-receipt-one"), ids(InventoryBrowseProjection(source = InventoryBrowseProjection.Source.MANUAL)))
        assertEquals(PantryUiState.MANUAL_ROW_PREFIX, "manual-receipt-")
    }
    @Test fun allSourceFilterIncludesAllThreeExistingGroups() {
        assertEquals(items, InventoryBrowseProjection(source = InventoryBrowseProjection.Source.ALL).project(items))
    }
    @Test fun standaloneFilterKeepsReceiptRowsSeparateAndSortsSameNameItemsByQuantity() {
        val directRows = listOf(1, 9).map { quantity ->
            InventoryItem("manual-inventory-$quantity", "Manual rice", quantity, ManualInventoryStore.STANDALONE_ROW_STATE)
        }
        val mixed = items + directRows
        val projection = InventoryBrowseProjection(
            " RICE ", InventoryBrowseProjection.Sort.QUANTITY_DESCENDING, InventoryBrowseProjection.Source.STANDALONE,
        )
        assertEquals(directRows.reversed(), projection.project(mixed))
        projection.source = InventoryBrowseProjection.Source.MANUAL
        assertEquals(listOf("manual-receipt-one"), projection.project(mixed).map { it.id })
        projection.query = ""
        projection.sort = InventoryBrowseProjection.Sort.ORIGINAL
        projection.source = InventoryBrowseProjection.Source.ALL
        assertEquals(mixed, projection.project(mixed))
    }
    @Test fun searchSortAndSourceFilterCombine() {
        val p = InventoryBrowseProjection(" apple ", InventoryBrowseProjection.Sort.QUANTITY_DESCENDING, InventoryBrowseProjection.Source.BASELINE)
        assertEquals(listOf("stock-duplicate", "stock-a"), ids(p))
    }
    @Test fun emptyInventoryRemainsEmptyForEveryControlCombination() {
        for (sort in InventoryBrowseProjection.Sort.values()) for (source in InventoryBrowseProjection.Source.values()) {
            assertTrue(InventoryBrowseProjection("anything", sort, source).project(emptyList()).isEmpty())
        }
    }
    @Test fun projectionsNeverMutateOriginalOrderOrItems() {
        val order = items.toList()
        for (sort in InventoryBrowseProjection.Sort.values()) for (source in InventoryBrowseProjection.Source.values()) {
            val p = InventoryBrowseProjection(sort = sort, source = source)
            p.project(items).forEach { item -> assertSame(order.first { it.id == item.id }, item) }
            assertEquals(order, items)
        }
    }
    @Test fun quantitiesAreNotNormalizedOrChangedByProjection() {
        val values = listOf(items[0].copy(quantity = 0.toBigDecimal()), items[1].copy(quantity = 99.toBigDecimal()))
        assertEquals(listOf(99.toBigDecimal(), 0.toBigDecimal()), InventoryBrowseProjection(sort = InventoryBrowseProjection.Sort.QUANTITY_DESCENDING).project(values).map { it.quantity })
        assertEquals(listOf(0.toBigDecimal(), 99.toBigDecimal()), values.map { it.quantity })
    }
    @Test fun projectionDoesNotConfirmOrChangePantryReceiptOrStock() {
        val state = PantryUiState(MockReceiptPresentationSource())
        val receipt = state.receipt; val presentation = state.presentationResult
        val inventory = state.inventory.toList(); val confirmation = state.demoConfirmed
        InventoryBrowseProjection("rice", InventoryBrowseProjection.Sort.NAME, InventoryBrowseProjection.Source.BASELINE).project(state.inventory)
        assertSame(receipt, state.receipt); assertSame(presentation, state.presentationResult)
        assertEquals(inventory, state.inventory); assertEquals(confirmation, state.demoConfirmed)
    }
    @Test fun quantitySortReprojectsUpdatedValuesWithoutChangingIdBinding() {
        val state = PantryUiState(MockReceiptPresentationSource()); val p = InventoryBrowseProjection(sort = InventoryBrowseProjection.Sort.QUANTITY_DESCENDING)
        val before = p.project(state.inventory)
        assertEquals("stock-eggs", before.first().id)
        state.adjustInventory("stock-rice", 5)
        assertEquals("stock-rice", p.project(state.inventory).first().id)
        assertEquals(1.toBigDecimal(), before.first { it.id == "stock-rice" }.quantity)
        assertEquals(6.toBigDecimal(), state.inventory.first { it.id == "stock-rice" }.quantity)
    }
}
