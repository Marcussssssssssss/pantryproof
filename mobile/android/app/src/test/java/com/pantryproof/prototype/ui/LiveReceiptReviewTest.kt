package com.pantryproof.prototype.ui

import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.PresentationSourceType
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryUnit
import com.pantryproof.prototype.data.M3eReceiptPresentationAdapter
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.data.MockReceiptPresentationSource
import com.pantryproof.prototype.data.PresentedFieldStatus
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle
import com.pantryproof.prototype.data.ReceiptProcessingRequest
import com.pantryproof.prototype.data.SyntheticReceiptPresentationPayload
import com.pantryproof.prototype.ui.PantryUiState.LiveConfirmation
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class LiveReceiptReviewTest {
    private val source = MockReceiptPresentationSource()
    private val originalStock = InventoryItem(
        "${ManualInventoryStore.ROW_PREFIX}existing", "Oats", 3, ManualInventoryStore.ROW_STATE,
    )

    @Test
    fun futureOrEditedPurchaseDateCannotUseAnEarlierLiveConfirmation() {
        val draft = draft()
        val sourceDate = LocalDate.of(2026, 10, 31)
        var today = sourceDate.minusDays(1)
        val store = TestManualInventoryPersistence(listOf(originalStock))
        val state = PantryUiState(source, store, today = { today })
        val before = state.inventory.toList()
        val original = draft.purchaseDate.original
        val invalidDate = LiveReceiptReviewDraft.Selection.Invalid(LiveReceiptReviewDraft.Problem.PURCHASE_DATE)
        assertEquals(invalidDate, draft.selection(today))
        assertEquals(sourceDate.toString(), draft.purchaseDate.value)

        today = sourceDate
        val reviewed = draft.selection(today) as LiveReceiptReviewDraft.Selection.Ready
        today = sourceDate.minusDays(1)
        assertEquals(LiveConfirmation.INVALID_DATE, state.confirmLiveReceipt(draft, reviewed))
        draft.purchaseDate.value = ""
        assertEquals(invalidDate, draft.selection(today))
        draft.purchaseDate.value = today.toString()
        val corrected = draft.selection(today) as LiveReceiptReviewDraft.Selection.Ready
        assertEquals(LiveConfirmation.INVALID, state.confirmLiveReceipt(draft, reviewed))
        assertEquals(listOf(originalStock), store.committed)
        assertEquals(before, state.inventory)
        assertEquals(original, draft.purchaseDate.original)
        assertEquals(sourceDate.toString(), original.value)
        assertEquals(LiveConfirmation.SAVED, state.confirmLiveReceipt(draft, corrected))
        assertEquals(LiveConfirmation.INVALID, state.confirmLiveReceipt(draft, corrected))
    }

    @Test
    fun validatedLiveResultKeepsOriginalValuesAndBinding() {
        val finished = finished()
        val draft = requireNotNull(LiveReceiptReviewDraft.from(finished))
        val envelope = draft.evidence.envelope
        assertSame(finished.request, draft.request)
        assertEquals(finished.request.context.expectedRequestId, envelope.requestId)
        assertEquals(finished.request.context.expectedImageId, envelope.imageId)
        assertEquals(PresentationSourceType.LOCAL_IMAGE, envelope.source.type)
        assertEquals("m3f-demo-001", envelope.source.provenance.sourceReference)
        assertEquals("Demo Grocery Store (Synthetic)", draft.storeName.value)
        assertEquals("2026-10-31", draft.purchaseDate.value)
        assertEquals("RM 23.00", draft.receiptTotal.original.originalAutomaticValue)
        assertEquals("23.00", draft.receiptTotal.value)
        assertEquals("demo-milk", draft.items.first().rowId)
        assertEquals(PresentedFieldStatus.MISSING, draft.items.last().unitPrice.original.status)
        assertEquals("", draft.items.last().unitPrice.value)
    }

    @Test
    fun fixtureAndMismatchedOrRejectedResultsCannotStartReview() {
        assertNull(LiveReceiptReviewDraft.from(finished(live = false)))
        val finished = finished()
        val request = finished.request
        val wrongRequest = request.copy(context = request.context.copy(expectedRequestId = "different-request"))
        assertNull(LiveReceiptReviewDraft.from(finished.copy(request = wrongRequest)))
        val wrongSelection = request.copy(selection = ReceiptProcessingRequest.Selection(request.selection.owner, "different-image"))
        assertNull(LiveReceiptReviewDraft.from(finished.copy(request = wrongSelection)))
        val rejected = M3eReceiptPresentationAdapter().decodeAndMap(
            SyntheticReceiptPresentationPayload.bytes(), request.context,
        )
        assertTrue(rejected is ReceiptPresentationUiResult.Rejected)
        assertNull(LiveReceiptReviewDraft.from(finished.copy(outcome = ReceiptProcessingLifecycle.Outcome.Presentation(rejected))))
    }

    @Test
    fun everyFieldCanBeCorrectedWithoutChangingEvidenceOrStock() {
        val store = TestManualInventoryPersistence(listOf(originalStock))
        val state = PantryUiState(source, store)
        val before = state.inventory.toList()
        val draft = draft()
        val item = draft.items.first()
        val fields = listOf(
            draft.storeName, draft.purchaseDate, draft.receiptTotal,
            item.description, item.quantity, item.unitPrice, item.lineTotal,
        )
        val extracted = fields.map { it.original.value }
        val corrections = listOf("Example Market", "2026-11-01", "17.00", "Fresh Milk", "3", "4.00", "12.00")
        fields.zip(corrections).forEach { (field, value) -> field.value = value }
        assertEquals(corrections, fields.map { it.value })
        assertEquals(extracted, fields.map { it.original.value })
        assertEquals(before, state.inventory)
        assertEquals(listOf(originalStock), store.committed)
    }

    @Test
    fun unresolvedDateStartsBlankAndCorrectionKeepsItsOriginalStatus() {
        val draft = requireNotNull(LiveReceiptReviewDraft.from(finished(unresolvedDate = true)))
        val date = draft.purchaseDate
        assertEquals("", date.value)
        assertEquals(PresentedFieldStatus.UNRESOLVED, date.original.status)
        assertEquals("AMBIGUOUS_DATE_FORMAT", date.original.absenceReason)
        date.value = "2026-11-01"
        assertEquals("2026-11-01", date.value)
        assertNull(date.original.value)
        assertEquals(3, ready(draft).rows.size)
    }

    @Test
    fun decimalQuantityNeedsACompatibleExplicitUnitOrExclusion() {
        val draft = requireNotNull(LiveReceiptReviewDraft.from(finished(decimal = true)))
        val item = draft.items.first()
        assertEquals("0.750", item.quantity.value)
        assertEquals(
            LiveReceiptReviewDraft.Selection.Invalid(LiveReceiptReviewDraft.Problem.QUANTITY, 1),
            draft.selection(),
        )
        item.selected = false
        assertEquals(2, ready(draft).rows.size)
        item.selected = true
        item.inventoryUnit = InventoryUnit.EACH
        assertEquals(LiveReceiptReviewDraft.Selection.Invalid(LiveReceiptReviewDraft.Problem.QUANTITY, 1), draft.selection())
        item.inventoryUnit = InventoryUnit.KILOGRAM
        val selection = ready(draft)
        val row = selection.rows.first()
        assertEquals("0.750".toBigDecimal(), row.quantity)
        assertEquals(InventoryUnit.KILOGRAM, row.unit)
        val store = TestManualInventoryPersistence()
        val state = PantryUiState(source, store)
        item.inventoryUnit = InventoryUnit.GRAM
        assertEquals(LiveConfirmation.INVALID, state.confirmLiveReceipt(draft, selection))
        assertTrue(store.committed.isEmpty())
        item.inventoryUnit = InventoryUnit.KILOGRAM
        assertEquals(LiveConfirmation.SAVED, state.confirmLiveReceipt(draft, selection))
        assertEquals(row, PantryUiState(source, store).inventory.single { it.id == row.id })
        assertEquals("0.750", item.quantity.original.value)
    }

    @Test
    fun rejectsInvalidSelectedFieldsAndAnEmptySelection() {
        val draft = draft()
        val item = draft.items.first()
        for (invalid in listOf("", "0", "-2", "+2", "2.0", "100", "two")) {
            item.quantity.value = invalid
            assertEquals(
                LiveReceiptReviewDraft.Selection.Invalid(LiveReceiptReviewDraft.Problem.QUANTITY, 1),
                draft.selection(),
            )
        }
        item.quantity.value = "99"
        item.description.value = " "
        assertEquals(
            LiveReceiptReviewDraft.Selection.Invalid(LiveReceiptReviewDraft.Problem.DESCRIPTION, 1),
            draft.selection(),
        )
        draft.items.forEach { it.selected = false }
        assertEquals(LiveReceiptReviewDraft.Selection.Invalid(LiveReceiptReviewDraft.Problem.NO_ITEMS), draft.selection())
    }

    @Test
    fun discardAndChangedSelectionInvalidateAnEarlierConfirmation() {
        val store = TestManualInventoryPersistence()
        val state = PantryUiState(source, store)
        val draft = draft()
        val selection = ready(draft)
        draft.items.first().quantity.value = "3"
        assertEquals(LiveConfirmation.INVALID, state.confirmLiveReceipt(draft, selection))
        val revised = ready(draft)
        draft.discard()
        assertEquals(LiveConfirmation.INVALID, state.confirmLiveReceipt(draft, revised))
        assertEquals(source.syntheticInventory(), state.inventory)
        assertTrue(store.committed.isEmpty())
    }

    @Test
    fun confirmationCommitsOnlySelectedRowsAndReloadPreservesBothSources() {
        val store = TestManualInventoryPersistence(listOf(originalStock))
        val state = PantryUiState(source, store)
        val draft = draft()
        draft.items.first().description.value = "Corrected product"
        draft.items.first().quantity.value = "3"
        draft.items[1].description.value = "Corrected product"
        draft.items.last().selected = false
        val selection = ready(draft)
        assertEquals(LiveConfirmation.SAVED, state.confirmLiveReceipt(draft, selection))
        assertEquals(LiveConfirmation.INVALID, state.confirmLiveReceipt(draft, selection))
        assertEquals(listOf(originalStock) + selection.rows, store.committed)
        assertEquals(2, selection.rows.map(InventoryItem::id).distinct().size)
        assertEquals(listOf("Corrected product", "Corrected product"), selection.rows.map(InventoryItem::name))
        assertTrue(state.confirmForInventoryPreview())
        assertTrue(state.inventory.containsAll(store.committed))
        val liveRow = selection.rows.first()
        assertTrue(state.adjustInventory(liveRow.id, 1))
        val reopened = PantryUiState(source, store)
        reopened.restore(null, source.syntheticInventory() + liveRow, false)
        assertEquals(source.syntheticInventory() + store.committed, reopened.inventory)
        assertEquals(4.toBigDecimal(), reopened.inventory.single { it.id == liveRow.id }.quantity)
        val liveStock = InventoryBrowseProjection(source = InventoryBrowseProjection.Source.LIVE).project(reopened.inventory)
        assertEquals(selection.rows.map(InventoryItem::id), liveStock.map(InventoryItem::id))
    }

    @Test
    fun failedAtomicAdmissionKeepsExistingStockAndEditsForRetry() {
        val store = TestManualInventoryPersistence(listOf(originalStock))
        val state = PantryUiState(source, store)
        val before = state.inventory.toList()
        val draft = draft()
        draft.items.first().description.value = "Corrected"
        val selection = ready(draft)
        store.failWrite = true
        assertEquals(LiveConfirmation.SAVE_FAILED, state.confirmLiveReceipt(draft, selection))
        assertEquals(before, state.inventory)
        assertEquals(listOf(originalStock), store.committed)
        assertEquals("Corrected", draft.items.first().description.value)
        assertEquals(selection, ready(draft))
        store.failWrite = false
        assertEquals(LiveConfirmation.SAVED, state.confirmLiveReceipt(draft, selection))
        assertEquals(listOf(originalStock) + selection.rows, store.committed)
    }

    @Test
    fun committedRequestCannotBeReadmittedFromAnotherDraftEvenWithDifferentSelectedRows() {
        val store = TestManualInventoryPersistence()
        val firstState = PantryUiState(source, store)
        val staleState = PantryUiState(source, store)
        val first = draft()
        first.items.drop(1).forEach { it.selected = false }
        val second = draft()
        second.items.first().selected = false
        assertEquals(LiveConfirmation.SAVED, firstState.confirmLiveReceipt(first, ready(first)))
        assertEquals(LiveConfirmation.ALREADY_SAVED, staleState.confirmLiveReceipt(second, ready(second)))
        assertEquals(1, store.committed.size)
        assertFalse(staleState.inventory.any { it.id.startsWith(ManualInventoryStore.LIVE_ROW_PREFIX) })
    }

    @Test
    fun mixedInventoryPersistsAndLiveRowsKeepConfirmationProtection() {
        val store = TestManualInventoryPersistence(listOf(originalStock))
        val state = PantryUiState(source, store)
        assertEquals(PantryUiState.InventoryChange.SAVED, state.addInventoryItem("Oat flour", "99"))
        val standalone = store.committed.single { it.id.startsWith(ManualInventoryStore.STANDALONE_ROW_PREFIX) }
        val firstReview = draft().apply { items.drop(1).forEach { it.selected = false } }
        val selection = ready(firstReview)

        store.failWrite = true
        assertEquals(LiveConfirmation.SAVE_FAILED, state.confirmLiveReceipt(firstReview, selection))
        assertEquals(listOf(originalStock, standalone), store.committed)
        assertEquals(source.syntheticInventory() + store.committed, state.inventory)
        store.failWrite = false
        assertEquals(LiveConfirmation.SAVED, state.confirmLiveReceipt(firstReview, selection))

        val liveRow = selection.rows.single()
        val reopened = PantryUiState(source, store)
        assertEquals(listOf(originalStock, standalone, liveRow), store.committed)
        assertEquals(source.syntheticInventory() + store.committed, reopened.inventory)
        assertEquals(PantryUiState.InventoryChange.NOT_SAVED, reopened.editInventoryItem(liveRow.id, "Other", "0"))
        assertFalse(reopened.deleteInventoryItem(liveRow.id))
        assertEquals(listOf(originalStock, standalone, liveRow), store.committed)
        val duplicate = draft()
        assertEquals(LiveConfirmation.ALREADY_SAVED, reopened.confirmLiveReceipt(duplicate, ready(duplicate)))

        val filter = InventoryBrowseProjection(source = InventoryBrowseProjection.Source.LIVE)
        assertEquals(listOf(liveRow), filter.project(reopened.inventory))
        filter.source = InventoryBrowseProjection.Source.MANUAL
        assertEquals(listOf(originalStock), filter.project(reopened.inventory))
        filter.source = InventoryBrowseProjection.Source.STANDALONE
        assertEquals(listOf(standalone), filter.project(reopened.inventory))
        assertTrue(reopened.adjustInventory(standalone.id, 1))
        assertEquals(99.toBigDecimal(), store.committed.single { it.id == standalone.id }.quantity)
        assertEquals(PantryUiState.InventoryChange.SAVED, reopened.editInventoryItem(standalone.id, "Flour", "0"))
        assertTrue(reopened.deleteInventoryItem(standalone.id))
        assertEquals(listOf(originalStock, liveRow), store.committed)
    }

    @Test
    fun standaloneAddWithoutStorageReturnsRecoverableFailure() {
        val state = PantryUiState(source)
        assertEquals(PantryUiState.InventoryChange.NOT_SAVED, state.addInventoryItem("Oats", "2"))
        assertEquals(source.syntheticInventory(), state.inventory)
    }

    private fun draft() = requireNotNull(LiveReceiptReviewDraft.from(finished()))

    private fun ready(draft: LiveReceiptReviewDraft): LiveReceiptReviewDraft.Selection.Ready =
        draft.selection() as LiveReceiptReviewDraft.Selection.Ready

    private fun finished(
        live: Boolean = true,
        decimal: Boolean = false,
        unresolvedDate: Boolean = false,
    ): ReceiptProcessingLifecycle.State.Finished {
        val context = SyntheticReceiptPresentationPayload.context.let {
            if (live) it.copy(mode = PresentationConsumerMode.LIVE) else it
        }
        var json = SyntheticReceiptPresentationPayload.bytes().decodeToString()
        if (live) json = json.replace("SYNTHETIC_FIXTURE", "LOCAL_IMAGE")
        if (decimal) json = json.replace(
            "\"originalAutomaticValue\": \"2\", \"presentationValue\": \"2\"",
            "\"originalAutomaticValue\": \"0.750\", \"presentationValue\": \"0.750\"",
        )
        if (unresolvedDate) json = json
            .replace(
                """"role": "PURCHASE_DATE", "status": "EXTRACTED"""",
                """"role": "PURCHASE_DATE", "status": "UNRESOLVED"""",
            )
            .replace(
                """"originalAutomaticValue": "2026-10-31", "presentationValue": "2026-10-31"""",
                """"originalAutomaticValue": null, "presentationValue": null""",
            )
            .replace(
                """"absenceReason": null, "sourceTokenIds": ["token-date"], "nativeConfidence": 0.99""",
                """"absenceReason": "AMBIGUOUS_DATE_FORMAT", "sourceTokenIds": ["token-date"], "nativeConfidence": null""",
            )
        val result = M3eReceiptPresentationAdapter().decodeAndMap(json.encodeToByteArray(), context)
        assertTrue(result.toString(), result is ReceiptPresentationUiResult.Available)
        val request = ReceiptProcessingRequest(
            ReceiptProcessingRequest.Selection(ReceiptProcessingRequest.Owner(), context.expectedImageId),
            ReceiptProcessingRequest.Submission(),
            context,
        )
        return ReceiptProcessingLifecycle.State.Finished(request, ReceiptProcessingLifecycle.Outcome.Presentation(result))
    }
}
