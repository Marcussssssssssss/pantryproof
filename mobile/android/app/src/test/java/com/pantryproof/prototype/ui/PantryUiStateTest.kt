package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.MockReceiptPresentationSource
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.PresentedFieldStatus
import com.pantryproof.prototype.data.ReceiptPresentationSource
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PantryUiStateTest {
    @Test
    fun confirmationBuildsTemporaryPreviewWithoutPersistenceDependency() {
        val state = PantryUiState(MockReceiptPresentationSource())

        assertTrue(state.confirmForInventoryPreview())

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
        assertEquals("Edited synthetic store", state.receipt?.storeName)
    }

    @Test
    fun restoringSessionStateRetainsReceiptInventoryAndConfirmation() {
        val source = MockReceiptPresentationSource()
        val state = PantryUiState(source)
        val restoredReceipt = source.syntheticReceipt().copy(storeName = "Restored temporary store")
        val confirmedState = PantryUiState(source)
        confirmedState.applyReceipt(restoredReceipt)
        confirmedState.adjustInventory(confirmedState.inventory.first().id, 6)
        assertTrue(confirmedState.confirmForInventoryPreview())
        val adjustedReceiptRowId = confirmedState.inventory.first {
            it.id.startsWith("receipt-")
        }.id
        confirmedState.adjustInventory(adjustedReceiptRowId, 2)

        state.restore(restoredReceipt, confirmedState.inventory, restoredDemoConfirmed = true)

        assertEquals("Restored temporary store", state.receipt?.storeName)
        assertEquals(7, state.inventory.first().quantity)
        assertEquals(3, state.inventory.count { it.id.startsWith("receipt-") })
        assertEquals(4, state.inventory.first { it.id == adjustedReceiptRowId }.quantity)
        assertTrue(state.demoConfirmed)
    }

    @Test
    fun nonResultRestorationDropsPreExistingReceiptPreviewRows() {
        val source = MockReceiptPresentationSource()
        val nonResults = listOf(
            ReceiptPresentationUiResult.ProcessingUnavailable(
                failureCode = "PROCESSOR_NOT_AVAILABLE",
                retryable = false,
            ),
            ReceiptPresentationUiResult.ProcessingFailed(
                stage = com.pantryproof.prototype.contract.v1.PresentationFailureStage.OCR,
                failureCode = "OCR_ENGINE_FAILURE",
                retryable = true,
            ),
            ReceiptPresentationUiResult.InsufficientEvidence(
                reasons = listOf("Synthetic source evidence was insufficient."),
            ),
        )
        val restoredInventory = listOf(
            InventoryItem("stock-test", "Synthetic stock", 7, "In pantry"),
            InventoryItem("receipt-stale", "Stale receipt item", 2, "Temporary receipt preview"),
        )

        nonResults.forEach { result ->
            val state = PantryUiState(FixedPresentationSource(result))
            state.restore(
                restoredReceipt = source.syntheticReceipt(),
                restoredInventory = restoredInventory,
                restoredDemoConfirmed = true,
            )

            assertEquals(null, state.receipt)
            assertFalse(state.demoConfirmed)
            assertEquals(7, state.inventory.single().quantity)
            assertTrue(state.inventory.none { it.id.startsWith("receipt-") })
        }
    }

    @Test
    fun rejectedRestorationDropsPreExistingReceiptPreviewRows() {
        val rejected = com.pantryproof.prototype.data.M3eReceiptPresentationAdapter().decodeAndMap(
            "{".toByteArray(),
            com.pantryproof.prototype.contract.v1.PresentationConsumerContext(
                "request-test",
                "image-test",
                com.pantryproof.prototype.contract.v1.PresentationConsumerMode.FIXTURE,
            ),
        )
        val state = PantryUiState(FixedPresentationSource(rejected))

        state.restore(
            restoredReceipt = MockReceiptPresentationSource().syntheticReceipt(),
            restoredInventory = listOf(
                InventoryItem("stock-test", "Synthetic stock", 4, "In pantry"),
                InventoryItem("receipt-stale", "Stale receipt item", 1, "Temporary receipt preview"),
            ),
            restoredDemoConfirmed = true,
        )

        assertEquals(null, state.receipt)
        assertFalse(state.demoConfirmed)
        assertEquals(4, state.inventory.single().quantity)
        assertTrue(state.inventory.none { it.id.startsWith("receipt-") })
    }

    @Test
    fun incompleteAvailableRestorationWithoutEligibleReceiptDropsPreviewRows() {
        val available = MockReceiptPresentationSource().syntheticPresentation()
            as ReceiptPresentationUiResult.Available
        val incomplete = available.copy(
            receipt = available.receipt.copy(
                storeName = available.receipt.storeName.copy(
                    status = PresentedFieldStatus.MISSING,
                    value = null,
                    absenceReason = "STORE_NAME_NOT_OBSERVED",
                ),
            ),
        )
        val state = PantryUiState(FixedPresentationSource(incomplete))

        state.restore(
            restoredReceipt = null,
            restoredInventory = listOf(
                InventoryItem("stock-test", "Synthetic stock", 5, "In pantry"),
                InventoryItem("receipt-stale", "Stale receipt item", 1, "Temporary receipt preview"),
            ),
            restoredDemoConfirmed = true,
        )

        assertEquals(null, state.receipt)
        assertFalse(state.demoConfirmed)
        assertEquals(5, state.inventory.single().quantity)
        assertTrue(state.inventory.none { it.id.startsWith("receipt-") })
    }

    @Test
    fun availableRestorationDropsReceiptRowsThatDoNotMatchRestoredReceipt() {
        val source = MockReceiptPresentationSource()
        val state = PantryUiState(source)

        state.restore(
            restoredReceipt = source.syntheticReceipt(),
            restoredInventory = listOf(
                InventoryItem("stock-rice", "Jasmine Rice 5kg", 8, "In pantry"),
                InventoryItem("receipt-unrelated", "Unrelated preview", 1, "Temporary receipt preview"),
            ),
            restoredDemoConfirmed = true,
        )

        assertEquals(source.syntheticReceipt(), state.receipt)
        assertFalse(state.demoConfirmed)
        assertEquals(8, state.inventory.single().quantity)
        assertTrue(state.inventory.none { it.id.startsWith("receipt-") })
    }

    @Test
    fun nonResultPresentationCannotPromoteReceiptRows() {
        val state = PantryUiState(
            FixedPresentationSource(
                ReceiptPresentationUiResult.ProcessingUnavailable(
                    failureCode = "PROCESSOR_NOT_AVAILABLE",
                    retryable = false,
                ),
            ),
        )

        assertFalse(state.confirmForInventoryPreview())
        assertFalse(state.demoConfirmed)
        assertTrue(state.inventory.none { it.id.startsWith("receipt-") })
        assertEquals(null, state.receipt)
    }

    @Test
    fun rejectedPresentationCannotPromoteReceiptRows() {
        val result = com.pantryproof.prototype.data.M3eReceiptPresentationAdapter().decodeAndMap(
            "{".toByteArray(),
            com.pantryproof.prototype.contract.v1.PresentationConsumerContext(
                "request-test",
                "image-test",
                com.pantryproof.prototype.contract.v1.PresentationConsumerMode.FIXTURE,
            ),
        )
        val state = PantryUiState(FixedPresentationSource(result))

        assertFalse(state.confirmForInventoryPreview())
        assertFalse(state.demoConfirmed)
        assertTrue(state.inventory.none { it.id.startsWith("receipt-") })
    }

    @Test
    fun incompleteUnresolvedAndDecimalPresentationsCannotPromoteReceiptRows() {
        val available = MockReceiptPresentationSource().syntheticPresentation()
            as ReceiptPresentationUiResult.Available
        val blockedResults = listOf(
            available.copy(
                receipt = available.receipt.copy(
                    storeName = available.receipt.storeName.copy(
                        status = PresentedFieldStatus.MISSING,
                        value = null,
                        absenceReason = "STORE_NAME_NOT_OBSERVED",
                    ),
                ),
            ),
            available.copy(
                receipt = available.receipt.copy(
                    purchaseDate = available.receipt.purchaseDate.copy(
                        status = PresentedFieldStatus.UNRESOLVED,
                        value = null,
                        absenceReason = "AMBIGUOUS_DATE_FORMAT",
                    ),
                ),
            ),
            available.copy(
                receipt = available.receipt.copy(
                    items = available.receipt.items.mapIndexed { index, item ->
                        if (index == 0) {
                            item.copy(quantity = item.quantity.copy(value = "0.750"))
                        } else {
                            item
                        }
                    },
                ),
            ),
        )

        blockedResults.forEach { result ->
            val state = PantryUiState(FixedPresentationSource(result))
            assertFalse(state.confirmForInventoryPreview())
            assertEquals(null, state.receipt)
            assertTrue(state.inventory.none { it.id.startsWith("receipt-") })
        }
    }

    @Test
    fun failedAndInsufficientPresentationsCannotPromoteReceiptRows() {
        val blockedResults = listOf(
            ReceiptPresentationUiResult.ProcessingFailed(
                stage = com.pantryproof.prototype.contract.v1.PresentationFailureStage.OCR,
                failureCode = "OCR_ENGINE_FAILURE",
                retryable = true,
            ),
            ReceiptPresentationUiResult.InsufficientEvidence(
                reasons = listOf("Synthetic source evidence was insufficient."),
            ),
        )

        blockedResults.forEach { result ->
            val state = PantryUiState(FixedPresentationSource(result))
            assertFalse(state.confirmForInventoryPreview())
            assertEquals(null, state.receipt)
            assertTrue(state.inventory.none { it.id.startsWith("receipt-") })
        }
    }

    private class FixedPresentationSource(
        private val result: ReceiptPresentationUiResult,
    ) : ReceiptPresentationSource {
        override fun syntheticPresentation(): ReceiptPresentationUiResult = result

        override fun syntheticInventory(): List<InventoryItem> =
            listOf(InventoryItem("stock-test", "Synthetic stock", 1, "In pantry"))
    }
}
