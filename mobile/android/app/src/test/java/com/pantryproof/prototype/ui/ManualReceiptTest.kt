package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.MockReceiptPresentationSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

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
    fun acceptsOptionalUnitPriceAndPreservesExactMoney() {
        val receipt = requireNotNull(ReceiptValidator.validateManual(draft()).receipt)
        assertNull(receipt.items.single().unitPrice)
        assertEquals("8.20", receipt.items.single().lineTotal.toPlainString())
        assertEquals("8.20", receipt.receiptTotal.toPlainString())
    }

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
}
