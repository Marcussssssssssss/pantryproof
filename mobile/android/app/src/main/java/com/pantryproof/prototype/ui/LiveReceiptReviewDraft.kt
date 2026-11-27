package com.pantryproof.prototype.ui

import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.PresentationSourceType
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.LiveReceiptEvidence
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.data.PresentedField
import com.pantryproof.prototype.data.PresentedReceiptItem
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle
import com.pantryproof.prototype.data.ReceiptProcessingRequest
import java.security.MessageDigest
import java.time.LocalDate

/** In-memory corrections overlay the original validated evidence for this submission. */
internal class LiveReceiptReviewDraft private constructor(
    val request: ReceiptProcessingRequest,
    val evidence: LiveReceiptEvidence,
    available: ReceiptPresentationUiResult.Available,
) {
    class Field(val original: PresentedField) {
        val initialValue = original.value.orEmpty()
        var value = initialValue
    }

    class Item(original: PresentedReceiptItem) {
        val rowId = original.rowId
        val description = Field(original.description)
        val quantity = Field(original.quantity)
        val unitPrice = Field(original.unitPrice)
        val lineTotal = Field(original.lineTotal)
        var selected = true
    }

    enum class Problem { INACTIVE, PURCHASE_DATE, NO_ITEMS, DESCRIPTION, QUANTITY }

    sealed interface Selection {
        data class Invalid(val problem: Problem, val itemNumber: Int? = null) : Selection
        data class Ready(val receiptIdPrefix: String, val rows: List<InventoryItem>, val purchaseDate: LocalDate) : Selection
    }

    val storeName = Field(available.receipt.storeName)
    val purchaseDate = Field(available.receipt.purchaseDate)
    val receiptTotal = Field(available.receipt.receiptTotal)
    val currencyCode = available.receipt.currencyCode
    val items = available.receipt.items.map(::Item)
    private var active = true

    // The prefix identifies one confirmed response even if a later draft selects a different subset.
    private val receiptIdPrefix = ManualInventoryStore.LIVE_ROW_PREFIX +
        digest(evidence.envelope.requestId + "\u0000" + evidence.envelope.imageId) + "-"

    fun discard() {
        active = false
    }

    fun selection(today: LocalDate = LocalDate.now()): Selection {
        if (!active) return Selection.Invalid(Problem.INACTIVE)
        val finalDate = ReceiptValidator.parsePurchaseDate(purchaseDate.value)
        if (ReceiptValidator.purchaseDateProblem(finalDate, today) != null) {
            return Selection.Invalid(Problem.PURCHASE_DATE)
        }
        val rows = mutableListOf<InventoryItem>()
        items.forEachIndexed { index, item ->
            if (!item.selected) return@forEachIndexed
            val name = item.description.value.trim()
            if (name.isEmpty()) return Selection.Invalid(Problem.DESCRIPTION, index + 1)
            val input = item.quantity.value.trim()
            val quantity = input.takeIf { value -> value.all { it in '0'..'9' } }?.toIntOrNull()
            if (quantity == null || quantity !in 1..ManualInventoryStore.MAX_QUANTITY) {
                return Selection.Invalid(Problem.QUANTITY, index + 1)
            }
            rows.add(InventoryItem(receiptIdPrefix + item.rowId, name, quantity, ManualInventoryStore.LIVE_ROW_STATE))
        }
        if (rows.isEmpty()) return Selection.Invalid(Problem.NO_ITEMS)
        return Selection.Ready(receiptIdPrefix, rows.toList(), requireNotNull(finalDate))
    }

    companion object {
        fun from(finished: ReceiptProcessingLifecycle.State.Finished): LiveReceiptReviewDraft? {
            val request = finished.request
            val context = request.context
            if (context.mode != PresentationConsumerMode.LIVE) return null
            val outcome = finished.outcome as? ReceiptProcessingLifecycle.Outcome.Presentation ?: return null
            val available = outcome.result as? ReceiptPresentationUiResult.Available ?: return null
            val evidence = available.liveEvidence ?: return null
            val envelope = evidence.envelope
            if (envelope.source.type != PresentationSourceType.LOCAL_IMAGE ||
                envelope.requestId != context.expectedRequestId ||
                envelope.imageId != context.expectedImageId ||
                envelope.imageId != request.selection.imageId
            ) return null
            return LiveReceiptReviewDraft(request, evidence, available)
        }

        private fun digest(value: String): String =
            MessageDigest.getInstance("SHA-256").digest(value.encodeToByteArray())
                .joinToString("") { "%02x".format(it) }
    }
}
