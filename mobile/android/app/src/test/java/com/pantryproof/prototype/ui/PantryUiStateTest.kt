package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.MockReceiptPresentationSource
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.data.PresentedFieldStatus
import com.pantryproof.prototype.data.ReceiptPresentationSource
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.ui.PantryUiState.InventoryChange
import java.util.UUID
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

    @Test
    fun reviewedBoundaryAdmissionControlsAndRestorationKeepExactQuantities() {
        for (quantity in listOf(98, 99)) {
            val source = MockReceiptPresentationSource()
            val state = PantryUiState(source)
            val draft = EditableReceipt.from(source.syntheticReceipt()).apply {
                items[0].quantity = quantity.toString()
            }
            val reviewed = requireNotNull(ReceiptValidator.validate(draft).receipt)
            state.applyReceipt(reviewed)
            assertTrue(state.confirmForInventoryPreview())
            val rowId = "receipt-${reviewed.items[0].id}"
            assertEquals(quantity, state.inventory.single { it.id == rowId }.quantity)
            state.adjustInventory(rowId, 1)
            assertEquals(99, state.inventory.single { it.id == rowId }.quantity)
            state.adjustInventory(rowId, 1)
            assertEquals(99, state.inventory.single { it.id == rowId }.quantity)
            state.adjustInventory(rowId, -1)
            assertEquals(98, state.inventory.single { it.id == rowId }.quantity)
            assertEquals(quantity, state.receipt!!.items[0].quantity)
            val restored = PantryUiState(source)
            restored.restore(state.receipt, state.inventory, state.demoConfirmed)
            assertEquals(state.inventory, restored.inventory)
            assertEquals(state.receipt, restored.receipt)
            assertTrue(restored.demoConfirmed)
        }
    }

    @Test
    fun invalidDirectReceiptAdmissionIsAtomicAndNeverClampsQuantities() {
        for (quantity in listOf(100, Int.MAX_VALUE, 0, -1, Int.MIN_VALUE)) {
            val source = MockReceiptPresentationSource()
            val state = PantryUiState(source)
            val original = source.syntheticReceipt()
            // Put the invalid row last to prove a valid prefix cannot be partly admitted.
            val invalid = original.copy(items = original.items.mapIndexed { index, item ->
                if (index == original.items.lastIndex) item.copy(quantity = quantity) else item.copy(quantity = 98)
            })
            state.applyReceipt(invalid)
            val inventory = state.inventory
            val rows = inventory.toList()
            assertFalse("Direct quantity $quantity must not be admitted", state.confirmForInventoryPreview())
            org.junit.Assert.assertSame(inventory, state.inventory)
            assertEquals(rows, state.inventory)
            rows.zip(state.inventory).forEach { (before, after) -> org.junit.Assert.assertSame(before, after) }
            org.junit.Assert.assertSame(invalid, state.receipt)
            assertFalse(state.demoConfirmed)
            assertEquals(quantity, state.receipt!!.items.last().quantity)
        }
    }

    @Test
    fun extremeAdjustmentDeltasSaturateWithoutIntegerOverflow() {
        val state = PantryUiState(MockReceiptPresentationSource())
        val id = state.inventory.first().id
        state.adjustInventory(id, 98)
        assertEquals(99, state.inventory.single { it.id == id }.quantity)
        state.adjustInventory(id, Int.MAX_VALUE)
        assertEquals(99, state.inventory.single { it.id == id }.quantity)
        state.adjustInventory(id, Int.MIN_VALUE)
        assertEquals(0, state.inventory.single { it.id == id }.quantity)
        state.adjustInventory(id, Int.MAX_VALUE)
        assertEquals(99, state.inventory.single { it.id == id }.quantity)
        state.adjustInventory(id, -1)
        assertEquals(98, state.inventory.single { it.id == id }.quantity)
    }

    @Test
    fun outOfRangeSavedInventoryIsRejectedWithoutChangingTheCurrentSession() {
        for (quantity in listOf(-1, 100, Int.MIN_VALUE, Int.MAX_VALUE)) {
            val source = MockReceiptPresentationSource()
            val state = PantryUiState(source)
            assertTrue(state.confirmForInventoryPreview())
            val inventory = state.inventory
            val originalRows = inventory.toList()
            val receipt = state.receipt
            val invalid = originalRows.mapIndexed { index, item ->
                if (index == 0) item.copy(quantity = quantity) else item
            }
            state.restore(source.syntheticReceipt(), invalid, restoredDemoConfirmed = true)
            org.junit.Assert.assertSame(inventory, state.inventory)
            assertEquals(originalRows, state.inventory)
            org.junit.Assert.assertSame(receipt, state.receipt)
            assertTrue(state.demoConfirmed)
        }
    }
    @Test
    fun savedReceipt100WithStock99CannotRestoreConfirmedPreviewRows() {
        val savedReceipt = savedReceiptWithQuantity(100)
        val savedStock = savedPreviewStock(99)
        val firstRowId = "receipt-${savedReceipt.items.first().id}"
        assertEquals(3, savedStock.count { it.id.startsWith("receipt-") })
        assertEquals(99, savedStock.single { it.id == firstRowId }.quantity)
        val restored = PantryUiState(MockReceiptPresentationSource())

        restored.restore(savedReceipt, savedStock, restoredDemoConfirmed = true)

        assertFalse(restored.demoConfirmed)
        assertEquals(savedStock.filterNot { it.id.startsWith("receipt-") }, restored.inventory)
        org.junit.Assert.assertSame(savedReceipt, restored.receipt)
        assertEquals(100, restored.receipt!!.items.first().quantity)
        assertFalse(restored.confirmForInventoryPreview())
        assertFalse(restored.demoConfirmed)
        assertTrue(restored.inventory.none { it.id.startsWith("receipt-") })
    }

    @Test
    fun eligibleSavedReceiptsKeepConfirmationAndIndependentlyAdjustedStock() {
        for (quantity in listOf(1, 98, 99)) {
            for (stockQuantity in listOf(0, 50, 99)) {
                val savedReceipt = savedReceiptWithQuantity(quantity)
                val savedStock = savedPreviewStock(stockQuantity)
                val restored = PantryUiState(MockReceiptPresentationSource())

                restored.restore(savedReceipt, savedStock, restoredDemoConfirmed = true)

                assertTrue("Receipt $quantity / stock $stockQuantity remains eligible", restored.demoConfirmed)
                org.junit.Assert.assertSame(savedReceipt, restored.receipt)
                assertEquals(savedStock, restored.inventory)
                savedStock.zip(restored.inventory).forEach { (before, after) ->
                    org.junit.Assert.assertSame(before, after)
                }
                assertEquals(quantity, restored.receipt!!.items.first().quantity)
                assertEquals(3, restored.inventory.count { it.id.startsWith("receipt-") })
            }
        }
    }

    @Test
    fun ineligibleSavedReceiptQuantitiesNeverGainConfirmationFromValidStockOrSavedFlag() {
        for (quantity in listOf(0, -1, 100, Int.MIN_VALUE, Int.MAX_VALUE)) {
            for (stockQuantity in listOf(0, 99)) {
                for (savedFlag in listOf(false, true)) {
                    val savedReceipt = savedReceiptWithQuantity(quantity)
                    val savedStock = savedPreviewStock(stockQuantity)
                    val restored = PantryUiState(MockReceiptPresentationSource())

                    restored.restore(savedReceipt, savedStock, savedFlag)

                    assertFalse("Receipt $quantity / stock $stockQuantity / flag $savedFlag", restored.demoConfirmed)
                    org.junit.Assert.assertSame(savedReceipt, restored.receipt)
                    assertEquals(quantity, restored.receipt!!.items.first().quantity)
                    val retained = savedStock.filterNot { it.id.startsWith("receipt-") }
                    assertEquals(retained, restored.inventory)
                    retained.zip(restored.inventory).forEach { (before, after) ->
                        org.junit.Assert.assertSame(before, after)
                    }
                    assertFalse(restored.confirmForInventoryPreview())
                    assertFalse(restored.demoConfirmed)
                }
            }
        }
    }

    @Test
    fun falseSavedConfirmationKeepsEligibleReceiptUnconfirmedUntilExplicitConfirmation() {
        for (quantity in listOf(1, 99)) {
            val savedReceipt = savedReceiptWithQuantity(quantity)
            val savedStock = savedPreviewStock(99)
            val restored = PantryUiState(MockReceiptPresentationSource())

            restored.restore(savedReceipt, savedStock, restoredDemoConfirmed = false)

            assertFalse(restored.demoConfirmed)
            org.junit.Assert.assertSame(savedReceipt, restored.receipt)
            assertEquals(savedStock.filterNot { it.id.startsWith("receipt-") }, restored.inventory)
            assertTrue(restored.confirmForInventoryPreview())
            assertEquals(quantity, restored.inventory.single {
                it.id == "receipt-${savedReceipt.items.first().id}"
            }.quantity)
            assertTrue(restored.inventory.any { it.id == "manual-receipt-saved-manual" })
        }
    }

    @Test
    fun repeatedRestorationCannotReinstateIneligibleConfirmationAfterAValidSession() {
        val invalidReceipt = savedReceiptWithQuantity(100)
        val validReceipt = savedReceiptWithQuantity(99)
        val savedStock = savedPreviewStock(99)
        val restored = PantryUiState(MockReceiptPresentationSource())
        assertTrue(restored.confirmForInventoryPreview())

        repeat(3) {
            restored.restore(invalidReceipt, savedStock, restoredDemoConfirmed = true)
            assertFalse(restored.demoConfirmed)
            assertTrue(restored.inventory.none { it.id.startsWith("receipt-") })
            restored.restore(validReceipt, savedStock, restoredDemoConfirmed = true)
            assertTrue(restored.demoConfirmed)
            assertEquals(savedStock, restored.inventory)
            restored.restore(invalidReceipt, savedStock, restoredDemoConfirmed = true)
            assertFalse(restored.demoConfirmed)
            assertEquals(savedStock.filterNot { it.id.startsWith("receipt-") }, restored.inventory)
        }
    }

    @Test
    fun invalidStockStillRejectsTheEntireSnapshotRegardlessOfSavedReceiptEligibility() {
        for (quantity in listOf(1, 99, 100)) {
            for (stockQuantity in listOf(-1, 100, Int.MIN_VALUE, Int.MAX_VALUE)) {
                val invalidStock = savedPreviewStock(99).mapIndexed { index, item ->
                    if (index == 0) item.copy(quantity = stockQuantity) else item
                }
                val restored = PantryUiState(MockReceiptPresentationSource())
                assertTrue(restored.confirmForInventoryPreview())
                val originalInventory = restored.inventory
                val originalRows = originalInventory.toList()
                val originalReceipt = restored.receipt

                restored.restore(savedReceiptWithQuantity(quantity), invalidStock, restoredDemoConfirmed = true)

                org.junit.Assert.assertSame(originalInventory, restored.inventory)
                org.junit.Assert.assertSame(originalReceipt, restored.receipt)
                assertEquals(originalRows, restored.inventory)
                assertTrue(restored.demoConfirmed)
            }
        }
    }

    @Test
    fun manualQuantityOnlyChangesAfterCommitAndUsesLatestStoredValue() {
        val row = InventoryItem("manual-receipt-pasta", "Pasta", 2, "Manually entered receipt")
        val store = TestManualInventoryPersistence(listOf(row))
        val source = MockReceiptPresentationSource()
        val state = PantryUiState(source, store)
        val anotherActivity = PantryUiState(source, store)
        val original = state.inventory.toList()

        store.failWrite = true
        assertFalse(state.adjustInventory(row.id, -1))
        assertEquals(original, state.inventory)
        assertEquals(listOf(row), store.committed)

        store.failWrite = false
        assertTrue(anotherActivity.adjustInventory(row.id, 1))
        assertTrue(state.adjustInventory(row.id, -1))
        assertEquals(listOf(row), store.committed)
        assertEquals(original, state.inventory)
        assertTrue(state.adjustInventory(row.id, -2))
        assertEquals(row.copy(quantity = 0), PantryUiState(source, store).inventory.last())
    }

    @Test
    fun savedActivityRowsCannotReplaceOrReintroduceManualStock() {
        val source = MockReceiptPresentationSource()
        val row = InventoryItem("manual-receipt-pasta", "Pasta", 8, "Manually entered receipt")
        val store = TestManualInventoryPersistence(listOf(row))
        val state = PantryUiState(source, store)
        val sessionRows = source.syntheticInventory().map { it.copy(quantity = 5) }
        val staleRows = listOf(row.copy(quantity = 2), row.copy(id = "manual-receipt-old", quantity = 100))

        state.restore(source.syntheticReceipt(), sessionRows + staleRows, restoredDemoConfirmed = false)

        assertEquals(sessionRows + row, state.inventory)
        assertEquals(listOf(row), store.committed)
    }

    @Test
    fun unreadableLocalStockIsNotReplacedBySavedActivityRows() {
        val source = MockReceiptPresentationSource()
        val row = InventoryItem("manual-receipt-pasta", "Pasta", 8, "Manually entered receipt")
        val store = TestManualInventoryPersistence(listOf(row)).apply { failRead = true }
        val state = PantryUiState(source, store)

        state.restore(source.syntheticReceipt(), source.syntheticInventory() + row, restoredDemoConfirmed = false)

        assertTrue(state.manualInventoryLoadFailed)
        assertEquals(source.syntheticInventory(), state.inventory)
        assertEquals(listOf(row), store.committed)
    }

    @Test
    fun standaloneAddAndEditValidateFieldsAndKeepSameNameRowsDistinct() {
        val store = TestManualInventoryPersistence()
        val state = PantryUiState(MockReceiptPresentationSource(), store)
        val firstId = UUID(0, 1)
        val secondId = UUID(0, 2)
        assertEquals(InventoryChange.INVALID_NAME, state.addInventoryItem(" \t ", "1") { firstId })
        for (quantity in listOf("", " ", "-1", "1.5", "100", "2147483648", "rice")) {
            assertEquals(InventoryChange.INVALID_QUANTITY, state.addInventoryItem("Rice", quantity) { firstId })
        }
        assertTrue(store.committed.isEmpty())

        assertEquals(InventoryChange.SAVED, state.addInventoryItem(" Rice ", " 0 ") { firstId })
        assertEquals(InventoryChange.SAVED, state.addInventoryItem("Rice", "99") { secondId })
        val rows = store.committed
        assertEquals(listOf("manual-inventory-$firstId", "manual-inventory-$secondId"), rows.map { it.id })
        assertEquals(listOf("Rice", "Rice"), rows.map { it.name })
        assertEquals(listOf(0, 99), rows.map { it.quantity })

        assertEquals(InventoryChange.NOT_SAVED, state.addInventoryItem("Duplicate ID", "1") { firstId })
        assertEquals(InventoryChange.INVALID_NAME, state.editInventoryItem(rows[0].id, "", "9"))
        assertEquals(InventoryChange.INVALID_QUANTITY, state.editInventoryItem(rows[0].id, "Rice", "100"))
        assertEquals(rows, store.committed)
        assertEquals(InventoryChange.SAVED, state.editInventoryItem(rows[0].id, " Brown rice ", "99"))
        assertEquals(listOf(rows[0].copy(name = "Brown rice", quantity = 99), rows[1]), store.committed)
    }

    @Test
    fun failedStandaloneChangesDoNotPublishAndCanBeRetried() {
        val receiptRow = InventoryItem("manual-receipt-pasta", "Pasta", 3, ManualInventoryStore.ROW_STATE)
        val store = TestManualInventoryPersistence(listOf(receiptRow))
        val source = MockReceiptPresentationSource()
        val state = PantryUiState(source, store)
        val inventoryBefore = state.inventory.toList()
        val id = UUID(0, 1)
        store.failWrite = true

        assertEquals(InventoryChange.NOT_SAVED, state.addInventoryItem("Rice", "1") { id })
        assertEquals(InventoryChange.NOT_SAVED, state.editInventoryItem(receiptRow.id, "New pasta", "7"))
        assertFalse(state.deleteInventoryItem(receiptRow.id))
        assertEquals(inventoryBefore, state.inventory)
        assertEquals(listOf(receiptRow), store.committed)

        store.failWrite = false
        assertEquals(InventoryChange.SAVED, state.addInventoryItem("Rice", "1") { id })
        assertEquals(InventoryChange.SAVED, state.editInventoryItem(receiptRow.id, "New pasta", "7"))
        assertTrue(state.adjustInventory("manual-inventory-$id", 1))
        assertEquals(
            listOf(
                receiptRow.copy(name = "New pasta", quantity = 7),
                InventoryItem("manual-inventory-$id", "Rice", 2, ManualInventoryStore.STANDALONE_ROW_STATE),
            ),
            store.committed,
        )
        assertEquals(state.inventory, PantryUiState(source, store).inventory)
    }

    @Test
    fun committedDeletionIsAuthoritativeOverStaleEditsAndActivityState() {
        val source = MockReceiptPresentationSource()
        val store = TestManualInventoryPersistence()
        val state = PantryUiState(source, store)
        assertEquals(InventoryChange.SAVED, state.addInventoryItem("Oats", "2"))
        val deleted = state.inventory.last()
        val stale = PantryUiState(source, store)
        val savedRows = stale.inventory.toList()

        assertTrue(state.deleteInventoryItem(deleted.id))
        assertFalse(state.deleteInventoryItem(deleted.id))
        assertEquals(InventoryChange.NOT_SAVED, stale.editInventoryItem(deleted.id, "Oat flakes", "3"))
        assertFalse(stale.adjustInventory(deleted.id, 1))
        val reopened = PantryUiState(source, store)
        reopened.restore(source.syntheticReceipt(), savedRows, restoredDemoConfirmed = false)
        assertEquals(source.syntheticInventory(), reopened.inventory)
        assertTrue(store.committed.isEmpty())
    }

    @Test
    fun fixturePreviewAndBaselineStayOutsideDurableManagement() {
        val source = MockReceiptPresentationSource()
        val store = TestManualInventoryPersistence()
        val state = PantryUiState(source, store)
        assertEquals(InventoryChange.SAVED, state.addInventoryItem("Oats", "2"))
        val draft = EditableReceipt(
            "Synthetic market", "2026-11-23",
            mutableListOf(EditableReceiptItem("beans", "Beans", "1", "", "2.00")),
            "2.00",
        )
        assertTrue(state.confirmManualReceipt(draft))
        val saved = store.committed
        assertEquals(listOf("Oats", "Beans"), saved.map { it.name })
        assertTrue(state.confirmForInventoryPreview())
        val previewId = state.inventory.first { it.id.startsWith("receipt-") }.id
        val baselineId = source.syntheticInventory().first().id
        for (id in listOf(previewId, baselineId)) {
            assertEquals(InventoryChange.NOT_SAVED, state.editInventoryItem(id, "Changed", "8"))
            assertFalse(state.deleteInventoryItem(id))
            assertTrue(state.adjustInventory(id, 1))
        }
        state.revertReceipt()
        assertEquals(saved, store.committed)
        assertEquals(source.syntheticInventory() + saved, PantryUiState(source, store).inventory)
    }

    private fun savedReceiptWithQuantity(quantity: Int) =
        MockReceiptPresentationSource().syntheticReceipt().let { original ->
            original.copy(items = original.items.mapIndexed { index, item ->
                if (index == 0) item.copy(quantity = quantity) else item
            })
        }

    private fun savedPreviewStock(firstStockQuantity: Int): List<InventoryItem> {
        val donor = PantryUiState(MockReceiptPresentationSource())
        assertTrue(donor.confirmForInventoryPreview())
        val item = donor.receipt!!.items.first()
        donor.adjustInventory("receipt-${item.id}", firstStockQuantity - item.quantity)
        assertTrue(donor.confirmManualReceipt(EditableReceipt(
            "Synthetic saved manual", "2026-10-31",
            mutableListOf(EditableReceiptItem("saved-manual", "Preserved manual stock", "4", "", "4.00")),
            "4.00",
        )))
        return donor.inventory.toList()
    }
    private class FixedPresentationSource(
        private val result: ReceiptPresentationUiResult,
    ) : ReceiptPresentationSource {
        override fun syntheticPresentation(): ReceiptPresentationUiResult = result

        override fun syntheticInventory(): List<InventoryItem> =
            listOf(InventoryItem("stock-test", "Synthetic stock", 1, "In pantry"))
    }
}
