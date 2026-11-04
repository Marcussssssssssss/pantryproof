package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.MockReceiptPresentationSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PantryUiStateTest {
    @Test
    fun confirmationBuildsTemporaryPreviewWithoutPersistenceDependency() {
        val state = PantryUiState(MockReceiptPresentationSource())

        state.confirmForInventoryPreview()

        assertTrue(state.demoConfirmed)
        assertTrue(state.inventory.any { it.state == "Temporary receipt preview" })
    }

    @Test
    fun quantityAdjustmentNeverDropsBelowZero() {
        val state = PantryUiState(MockReceiptPresentationSource())
        val first = state.inventory.first()

        state.adjustInventory(first.id, -100)

        assertEquals(0, state.inventory.first().quantity)
    }

    @Test
    fun quantityAdjustmentNeverExceedsTemporaryMaximum() {
        val state = PantryUiState(MockReceiptPresentationSource())
        val first = state.inventory.first()

        state.adjustInventory(first.id, 1000)

        assertEquals(PantryUiState.MAX_INVENTORY_QUANTITY, state.inventory.first().quantity)
    }

    @Test
    fun confirmationIsIdempotentAndDoesNotDuplicateReceiptRows() {
        val state = PantryUiState(MockReceiptPresentationSource())
        val baselineId = state.inventory.first().id
        state.adjustInventory(baselineId, -1)

        state.confirmForInventoryPreview()
        val firstSize = state.inventory.size
        state.confirmForInventoryPreview()

        assertEquals(firstSize, state.inventory.size)
        assertEquals(3, state.inventory.count { it.id.startsWith("receipt-") })
        assertEquals(0, state.inventory.first { it.id == baselineId }.quantity)
    }

    @Test
    fun applyingEditsClearsStaleConfirmationAndReceiptPreviewRows() {
        val source = MockReceiptPresentationSource()
        val state = PantryUiState(source)
        state.confirmForInventoryPreview()

        state.applyReceipt(source.syntheticReceipt().copy(storeName = "Edited synthetic store"))

        assertFalse(state.demoConfirmed)
        assertTrue(state.inventory.none { it.id.startsWith("receipt-") })
        assertEquals("Edited synthetic store", state.receipt.storeName)
    }

    @Test
    fun restoringSessionStateRetainsReceiptInventoryAndConfirmation() {
        val source = MockReceiptPresentationSource()
        val state = PantryUiState(source)
        val restoredReceipt = source.syntheticReceipt().copy(storeName = "Restored temporary store")
        val restoredInventory = source.syntheticInventory().mapIndexed { index, item ->
            if (index == 0) item.copy(quantity = 7) else item
        }

        state.restore(restoredReceipt, restoredInventory, restoredDemoConfirmed = true)

        assertEquals("Restored temporary store", state.receipt.storeName)
        assertEquals(7, state.inventory.first().quantity)
        assertTrue(state.demoConfirmed)
    }
}
