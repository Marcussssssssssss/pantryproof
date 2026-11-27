package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.ManualInventoryPersistence
import com.pantryproof.prototype.data.MockReceiptPresentationSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class ManualReceiptTest {
    private fun draft(id: String = "oats") = EditableReceipt(
        "Fictional Kedai", "2026-11-10",
        mutableListOf(EditableReceiptItem(id, "Oats", "2", "", "8.20")),
        "8.20",
    )

    private fun draftWithRows(count: Int) = draft().apply {
        val sample = items.single()
        items.clear()
        repeat(count) { index -> items.add(sample.copy(id = "oats-$index")) }
        receiptTotal = (java.math.BigDecimal("8.20") * count.toBigDecimal()).toPlainString()
    }

    @Test
    fun manualPurchaseDateUsesTheCurrentLocalDayAtValidationAndAtWrite() {
        var today = LocalDate.of(2026, 2, 28)
        val originalDay = today
        val store = TestManualInventoryPersistence(emptyList())
        val state = PantryUiState(MockReceiptPresentationSource(), store, today = { today })
        val before = state.inventory.toList()
        val receipt = draft()
        for (date in listOf(today.toString(), "2024-02-29", "1899-12-31")) {
            receipt.purchaseDate = date
            assertTrue(ReceiptValidator.validateManual(receipt, today).isValid)
        }
        for (date in listOf("2026-02-29", "2026-13-01", "2026-01-00", "2026-02")) {
            receipt.purchaseDate = date
            assertFalse(ReceiptValidator.validateManual(receipt, today).isValid)
        }
        for (date in listOf(today.plusDays(1), today.plusYears(1))) {
            receipt.purchaseDate = date.toString()
            assertTrue("Synthetic validation keeps its scoped behavior", ReceiptValidator.validate(receipt).isValid)
            assertEquals(ReceiptValidator.FUTURE_PURCHASE_DATE_ERROR,
                ReceiptValidator.validateManual(receipt, today).errors["purchaseDate"])
            assertFalse(state.confirmManualReceipt(receipt))
        }
        assertEquals(before, state.inventory)
        assertTrue(store.committed.isEmpty())

        receipt.purchaseDate = originalDay.plusDays(1).toString()
        today = originalDay.plusDays(1)
        val reviewed = requireNotNull(ReceiptValidator.validateManual(receipt, today).receipt)
        assertEquals(today, reviewed.purchaseDate)
        assertEquals("2026-03-01", receipt.purchaseDate)
        today = originalDay
        assertFalse(state.confirmManualReceipt(receipt))
        assertTrue(store.committed.isEmpty())
        today = originalDay.plusDays(1)
        assertTrue(state.confirmManualReceipt(receipt))
        assertFalse(state.confirmManualReceipt(receipt))
        assertEquals(receipt.items.size, store.committed.size)
    }

    @Test
    fun acceptsOptionalUnitPriceAndPreservesExactMoney() {
        val receipt = requireNotNull(ReceiptValidator.validateManual(draft()).receipt)
        assertNull(receipt.items.single().unitPrice)
        assertEquals("8.20", receipt.items.single().lineTotal.toPlainString())
        assertEquals("8.20", receipt.receiptTotal.toPlainString())
        assertEquals(ManualArithmeticWarnings(emptyList(), false), ReceiptValidator.manualArithmeticWarnings(receipt))
    }

    @Test
    fun exactComparisonsIgnoreScaleAndFlagACentInEitherDirection() {
        val draft = draft()
        val item = draft.items.single()
        item.unitPrice = "4"
        item.lineTotal = "8.00"
        draft.receiptTotal = "8.0"
        assertEquals(ManualArithmeticWarnings(emptyList(), false), warningsFor(draft))

        item.unitPrice = ""
        for (total in listOf("7.99", "8.01")) {
            draft.receiptTotal = total
            assertEquals(ManualArithmeticWarnings(emptyList(), true), warningsFor(draft))
        }
    }

    @Test
    fun oneCentRowDifferenceWarnsWithoutBlockingConfirmation() {
        val draft = draft().apply {
            items.single().unitPrice = "4.00"
            items.single().lineTotal = "8.01"
            receiptTotal = "8.01"
        }
        val original = draft.deepCopy()
        val validation = ReceiptValidator.validateManual(draft)
        assertTrue(validation.isValid)
        val receipt = requireNotNull(validation.receipt)

        assertEquals(ManualArithmeticWarnings(listOf(1), false), ReceiptValidator.manualArithmeticWarnings(receipt))
        assertEquals(2, receipt.items.single().quantity)
        assertEquals("4.00", receipt.items.single().unitPrice?.toPlainString())
        assertEquals("8.01", receipt.items.single().lineTotal.toPlainString())
        assertEquals("8.01", receipt.receiptTotal.toPlainString())
        assertTrue(PantryUiState(MockReceiptPresentationSource()).confirmManualReceipt(draft))
        assertEquals(original, draft)
    }

    @Test
    fun promotionAndReceiptAdjustmentWarnWithoutChangingEnteredValuesOrAddingRows() {
        val draft = draftWithRows(3)
        draft.items[0].unitPrice = "4.11" // 2 × 4.11 differs from the entered 8.20.
        draft.items[1].unitPrice = "4.10"
        draft.items[2].unitPrice = "4.25"
        draft.receiptTotal = "24.50"
        val original = draft.deepCopy()
        assertEquals(ManualArithmeticWarnings(listOf(1, 3), true), warningsFor(draft))
        assertEquals(original, draft)
        val state = PantryUiState(MockReceiptPresentationSource())
        val originalInventory = state.inventory.toList()
        assertTrue(state.confirmManualReceipt(draft))
        assertEquals(listOf("Oats", "Oats", "Oats"), state.inventory.drop(originalInventory.size).map { it.name })
        val confirmedInventory = state.inventory.toList()
        assertFalse(state.confirmManualReceipt(draft))
        assertEquals(confirmedInventory, state.inventory)
        assertEquals(original, draft)
    }

    @Test
    fun editedDraftDoesNotChangeTheReviewedSnapshot() {
        val draft = draft().apply { items.single().unitPrice = "4.20" }
        val reviewed = draft.deepCopy()
        assertEquals(ManualArithmeticWarnings(listOf(1), false), warningsFor(reviewed))
        draft.items.single().unitPrice = "4.10"
        assertFalse(draft == reviewed)
        assertEquals(ManualArithmeticWarnings(listOf(1), false), warningsFor(reviewed))
        assertEquals(ManualArithmeticWarnings(emptyList(), false), warningsFor(draft))
    }

    @Test
    fun duplicateCandidateRowIdsDoNotPartiallyInsertInventory() {
        val state = PantryUiState(MockReceiptPresentationSource())
        val draft = draftWithRows(3)
        draft.items[2] = draft.items[2].copy(id = draft.items[1].id)
        val before = state.inventory.toList()
        assertTrue(ReceiptValidator.validateManual(draft).isValid)
        assertFalse(state.confirmManualReceipt(draft))
        assertEquals(before, state.inventory)
    }

    private fun warningsFor(draft: EditableReceipt): ManualArithmeticWarnings =
        ReceiptValidator.manualArithmeticWarnings(requireNotNull(ReceiptValidator.validateManual(draft).receipt))

    @Test
    fun rejectsEmptyRowsFractionalOrOutOfBoundsQuantityAndInvalidFields() {
        val state = PantryUiState(MockReceiptPresentationSource())
        val originalInventory = state.inventory.toList()
        val cases = listOf(
            "items" to draft().apply { items.clear() },
            "storeName" to draft().apply { storeName = "" },
            "purchaseDate" to draft().apply { purchaseDate = "2026-02-30" },
            "item.0.description" to draft().apply { items.single().description = "" },
            "item.0.quantity" to draft().apply { items.single().quantity = "1.5" },
            "item.0.quantity" to draft().apply { items.single().quantity = "100" },
            "item.0.unitPrice" to draft().apply { items.single().unitPrice = "1e2" },
            "item.0.lineTotal" to draft().apply { items.single().lineTotal = "1.234" },
            "receiptTotal" to draft().apply { receiptTotal = "" },
        )
        cases.forEach { (field, invalidDraft) ->
            assertTrue(field in ReceiptValidator.validateManual(invalidDraft).errors)
            assertFalse(state.confirmManualReceipt(invalidDraft))
        }
        assertEquals(originalInventory, state.inventory)
    }

    @Test
    fun acceptsAndConfirmsEverySupportedRowCount() {
        for (count in 1..30) {
            val state = PantryUiState(MockReceiptPresentationSource())
            val receipt = draftWithRows(count)
            assertTrue("Expected $count valid rows", ReceiptValidator.validateManual(receipt).isValid)
            assertTrue("Expected $count confirmed rows", state.confirmManualReceipt(receipt))
            assertEquals(count, state.inventory.count { it.id.startsWith(PantryUiState.MANUAL_ROW_PREFIX) })
        }
    }

    @Test
    fun rejects31OtherwiseValidRowsWithoutChangingInventory() {
        val state = PantryUiState(MockReceiptPresentationSource())
        assertTrue(state.confirmManualReceipt(draft()))
        val originalInventory = state.inventory.toList()
        val oversized = draftWithRows(31)

        assertTrue(ReceiptValidator.validate(oversized).isValid)
        val result = ReceiptValidator.validateManual(oversized)
        assertNull(result.receipt)
        assertEquals(setOf("items"), result.errors.keys)
        assertFalse(state.confirmManualReceipt(oversized))
        assertEquals(originalInventory, state.inventory)
    }

    @Test
    fun distinctConfirmationsAccumulateAndSurviveDemoChangesAndRestore() {
        val source = MockReceiptPresentationSource()
        val state = PantryUiState(source)
        val initialReceipt = state.receipt
        val first = draft()
        assertTrue(state.confirmManualReceipt(first))
        assertFalse(state.confirmManualReceipt(first))
        assertTrue(state.confirmManualReceipt(draft("tea")))
        assertEquals(initialReceipt, state.receipt)
        assertFalse(state.demoConfirmed)

        assertTrue(state.confirmForInventoryPreview())
        state.revertReceipt()
        val restored = PantryUiState(source)
        restored.restore(state.receipt, state.inventory, state.demoConfirmed)
        assertEquals(
            listOf(2, 2),
            restored.inventory.filter { it.id.startsWith(PantryUiState.MANUAL_ROW_PREFIX) }
                .map { it.quantity },
        )
    }

    @Test
    fun failedCommitKeepsDraftAndInventoryForRetryAndOnlyManualRowsAreSaved() {
        val store = TestManualInventoryPersistence()
        val state = PantryUiState(MockReceiptPresentationSource(), store)
        val draft = draftWithRows(2)
        val beforeReview = draft.deepCopy()
        state.adjustInventory("stock-rice", 1)
        assertTrue(state.confirmForInventoryPreview())
        val inventoryBefore = state.inventory.toList()
        assertEquals(emptyList<InventoryItem>(), store.committed)

        store.failWrite = true
        assertFalse(state.confirmManualReceipt(draft))
        assertEquals(beforeReview, draft)
        assertEquals(inventoryBefore, state.inventory)
        assertEquals(emptyList<InventoryItem>(), store.committed)

        store.failWrite = false
        assertTrue(state.confirmManualReceipt(draft))
        assertEquals(inventoryBefore + store.committed, state.inventory)
        assertEquals(listOf("manual-receipt-oats-0", "manual-receipt-oats-1"), store.committed.map { it.id })
        assertEquals(listOf("Oats", "Oats"), store.committed.map { it.name })
        assertFalse(state.confirmManualReceipt(draft))
        assertEquals(2, store.committed.size)

        val fresh = PantryUiState(MockReceiptPresentationSource(), store)
        assertEquals(MockReceiptPresentationSource().syntheticInventory() + store.committed, fresh.inventory)
        assertFalse(fresh.demoConfirmed)
    }

    @Test
    fun confirmationChecksCommittedIdsEvenWhenAnotherActivityWasOpenedEarlier() {
        val store = TestManualInventoryPersistence()
        val first = PantryUiState(MockReceiptPresentationSource(), store)
        val earlier = PantryUiState(MockReceiptPresentationSource(), store)
        assertTrue(first.confirmManualReceipt(draft()))

        assertFalse(earlier.confirmManualReceipt(draft()))
        assertTrue(earlier.confirmManualReceipt(draft("tea")))
        assertEquals(listOf("manual-receipt-oats", "manual-receipt-tea"), store.committed.map { it.id })
    }
}

internal class TestManualInventoryPersistence(
    var committed: List<InventoryItem> = emptyList(),
) : ManualInventoryPersistence {
    var failRead = false
    var failWrite = false

    override fun load(): List<InventoryItem>? = if (failRead) null else committed.toList()

    override fun update(change: (List<InventoryItem>) -> List<InventoryItem>?): List<InventoryItem>? {
        val current = load() ?: return null
        val updated = change(current) ?: return null
        if (failWrite && updated != current) return null
        committed = updated.toList()
        return committed
    }
}
