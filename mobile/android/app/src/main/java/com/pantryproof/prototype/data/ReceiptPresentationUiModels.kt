package com.pantryproof.prototype.data

import com.pantryproof.prototype.contract.v1.PresentationFailureStage
import com.pantryproof.prototype.contract.v1.ReceiptPresentationIssue
import java.math.BigDecimal
import java.time.LocalDate

enum class PresentedFieldStatus {
    EXTRACTED,
    MISSING,
    UNRESOLVED,
}

data class PresentedField(
    val id: String,
    val status: PresentedFieldStatus,
    val originalAutomaticValue: String?,
    val value: String?,
    val absenceReason: String?,
)

data class PresentedReceiptItem(
    val rowId: String,
    val description: PresentedField,
    val quantity: PresentedField,
    val unitPrice: PresentedField,
    val lineTotal: PresentedField,
)

data class PresentedReceipt(
    val receiptId: String,
    val currencyCode: String,
    val storeName: PresentedField,
    val purchaseDate: PresentedField,
    val receiptTotal: PresentedField,
    val items: List<PresentedReceiptItem>,
) {
    /**
     * Converts only values that the legacy session inventory can represent
     * exactly. Missing required fields, unresolved fields, and decimal receipt
     * quantities deliberately return null instead of being defaulted or rounded.
     */
    fun toInventoryCompatibleReceiptOrNull(): Receipt? = runCatching {
        val store = storeName.extractedValueOrNull() ?: return null
        val date = purchaseDate.extractedValueOrNull()?.let(LocalDate::parse) ?: return null
        val total = receiptTotal.extractedValueOrNull()?.let(::BigDecimal) ?: return null
        val mappedItems = items.map { item ->
            val description = item.description.extractedValueOrNull() ?: return null
            val quantity = item.quantity.extractedValueOrNull()?.toIntOrNull()
                ?.takeIf { it > 0 } ?: return null
            val unitPrice = when (item.unitPrice.status) {
                PresentedFieldStatus.EXTRACTED ->
                    item.unitPrice.value?.let(::BigDecimal) ?: return null
                PresentedFieldStatus.MISSING -> null
                PresentedFieldStatus.UNRESOLVED -> return null
            }
            val lineTotal = item.lineTotal.extractedValueOrNull()?.let(::BigDecimal) ?: return null
            ReceiptItem(item.rowId, description, quantity, unitPrice, lineTotal)
        }
        Receipt(store, date, mappedItems, total)
    }.getOrNull()

    private fun PresentedField.extractedValueOrNull(): String? =
        value?.takeIf { status == PresentedFieldStatus.EXTRACTED }
}

sealed interface ReceiptPresentationUiResult {
    val canReview: Boolean get() = this is Available

    data class Available(val receipt: PresentedReceipt) : ReceiptPresentationUiResult

    data class ProcessingUnavailable(
        val failureCode: String,
        val retryable: Boolean,
    ) : ReceiptPresentationUiResult

    data class ProcessingFailed(
        val stage: PresentationFailureStage,
        val failureCode: String,
        val retryable: Boolean,
    ) : ReceiptPresentationUiResult

    data class InsufficientEvidence(
        val reasons: List<String>,
    ) : ReceiptPresentationUiResult

    data class Rejected(
        val issue: ReceiptPresentationIssue,
    ) : ReceiptPresentationUiResult
}
