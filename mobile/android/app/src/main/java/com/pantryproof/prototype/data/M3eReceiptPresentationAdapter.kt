package com.pantryproof.prototype.data

import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationOutcomeStatus
import com.pantryproof.prototype.contract.v1.PresentationField
import com.pantryproof.prototype.contract.v1.ReceiptFieldRole
import com.pantryproof.prototype.contract.v1.ReceiptFieldStatus
import com.pantryproof.prototype.contract.v1.ReceiptPresentationResult
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Validator

class M3eReceiptPresentationAdapter {
    fun decodeAndMap(
        payload: ByteArray,
        context: PresentationConsumerContext,
    ): ReceiptPresentationUiResult =
        when (val result = ReceiptPresentationV1Validator.decodeAndValidate(payload, context)) {
            is ReceiptPresentationResult.Rejected -> ReceiptPresentationUiResult.Rejected(result.issue)
            is ReceiptPresentationResult.Accepted -> mapAccepted(result.value)
        }

    private fun mapAccepted(envelope: ReceiptPresentationV1): ReceiptPresentationUiResult =
        when (envelope.outcome.status) {
            PresentationOutcomeStatus.RESULT_AVAILABLE ->
                ReceiptPresentationUiResult.Available(mapReceipt(requireNotNull(envelope.receipt)))
            PresentationOutcomeStatus.PROCESSING_UNAVAILABLE -> {
                val failure = requireNotNull(envelope.outcome.failure)
                ReceiptPresentationUiResult.ProcessingUnavailable(failure.code, failure.retryable)
            }
            PresentationOutcomeStatus.PROCESSING_FAILED -> {
                val failure = requireNotNull(envelope.outcome.failure)
                ReceiptPresentationUiResult.ProcessingFailed(
                    failure.stage,
                    failure.code,
                    failure.retryable,
                )
            }
            PresentationOutcomeStatus.SOURCE_EVIDENCE_INSUFFICIENT ->
                ReceiptPresentationUiResult.InsufficientEvidence(
                    requireNotNull(envelope.sourceGate).reasons,
                )
        }

    private fun mapReceipt(
        receipt: com.pantryproof.prototype.contract.v1.PresentationReceipt,
    ): PresentedReceipt {
        val receiptFields = receipt.receiptFields.associateBy(PresentationField::role)
        return PresentedReceipt(
            receiptId = receipt.receiptId,
            currencyCode = receipt.currencyCode,
            storeName = mapField(requireNotNull(receiptFields[ReceiptFieldRole.STORE_NAME])),
            purchaseDate = mapField(requireNotNull(receiptFields[ReceiptFieldRole.PURCHASE_DATE])),
            receiptTotal = mapField(requireNotNull(receiptFields[ReceiptFieldRole.RECEIPT_TOTAL])),
            items = receipt.itemRows.map { row ->
                val fields = row.fields.associateBy(PresentationField::role)
                PresentedReceiptItem(
                    rowId = row.rowId,
                    description = mapField(requireNotNull(fields[ReceiptFieldRole.ITEM_DESCRIPTION])),
                    quantity = mapField(requireNotNull(fields[ReceiptFieldRole.QUANTITY])),
                    unitPrice = mapField(requireNotNull(fields[ReceiptFieldRole.UNIT_PRICE])),
                    lineTotal = mapField(requireNotNull(fields[ReceiptFieldRole.LINE_TOTAL])),
                )
            },
        )
    }

    private fun mapField(field: PresentationField): PresentedField =
        PresentedField(
            id = field.fieldId,
            status = when (field.status) {
                ReceiptFieldStatus.EXTRACTED -> PresentedFieldStatus.EXTRACTED
                ReceiptFieldStatus.MISSING -> PresentedFieldStatus.MISSING
                ReceiptFieldStatus.UNRESOLVED -> PresentedFieldStatus.UNRESOLVED
            },
            originalAutomaticValue = field.originalAutomaticValue,
            value = field.presentationValue,
            absenceReason = field.absenceReason,
        )
}
