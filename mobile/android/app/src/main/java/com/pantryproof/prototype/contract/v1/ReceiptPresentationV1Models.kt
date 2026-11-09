package com.pantryproof.prototype.contract.v1

import java.math.BigDecimal
import java.util.Collections

enum class PresentationSourceType {
    LOCAL_IMAGE,
    SYNTHETIC_FIXTURE,
}

enum class PresentationOutcomeStatus {
    RESULT_AVAILABLE,
    PROCESSING_UNAVAILABLE,
    PROCESSING_FAILED,
    SOURCE_EVIDENCE_INSUFFICIENT,
}

enum class PresentationFailureStage {
    AVAILABILITY,
    OCR,
    SOURCE_GATE,
    EXTRACTION,
    PRESENTATION_ADAPTER,
}

enum class SourceProcessingStatus {
    RECEIVED,
    OCR_COMPLETED,
    OCR_PARTIAL,
    OCR_FAILED,
}

enum class SourceGateDecision {
    SUFFICIENT,
    INSUFFICIENT,
}

enum class AutomaticExtractionStage {
    PRE_REVIEW_AUTOMATIC,
}

enum class AutomaticExtractionStatus {
    EXTRACTED,
    PARTIAL,
    FAILED,
}

enum class ReceiptFieldRole {
    STORE_NAME,
    PURCHASE_DATE,
    ITEM_DESCRIPTION,
    QUANTITY,
    UNIT_PRICE,
    LINE_TOTAL,
    RECEIPT_TOTAL,
}

enum class ReceiptFieldStatus {
    EXTRACTED,
    MISSING,
    UNRESOLVED,
}

enum class PresentationConsumerMode {
    FIXTURE,
    LIVE,
}

data class PresentationProvenance(
    val sourceSystem: String,
    val sourceReference: String,
    val contentSha256: String?,
)

data class PresentationSource(
    val type: PresentationSourceType,
    val provenance: PresentationProvenance,
)

data class PresentationFailure(
    val stage: PresentationFailureStage,
    val code: String,
    val retryable: Boolean,
)

data class PresentationOutcome(
    val status: PresentationOutcomeStatus,
    val failure: PresentationFailure?,
)

class PresentationSourceEvidence(
    val sourceProcessingStatus: SourceProcessingStatus,
    tokenIds: List<String>,
) {
    val tokenIds: List<String> = immutableListCopy(tokenIds)
}

class PresentationSourceGate(
    val gateResultId: String,
    val decision: SourceGateDecision,
    reasons: List<String>,
) {
    val reasons: List<String> = immutableListCopy(reasons)
}

data class PresentationProducer(
    val producerId: String,
    val producerVersion: String,
)

data class PresentationAutomaticExtraction(
    val stage: AutomaticExtractionStage,
    val extractionStatus: AutomaticExtractionStatus,
    val producer: PresentationProducer,
)

class PresentationField(
    val fieldId: String,
    val role: ReceiptFieldRole,
    val status: ReceiptFieldStatus,
    val originalAutomaticValue: String?,
    val presentationValue: String?,
    val absenceReason: String?,
    sourceTokenIds: List<String>,
    val nativeConfidence: BigDecimal?,
) {
    val sourceTokenIds: List<String> = immutableListCopy(sourceTokenIds)
}

class PresentationItemRow(
    val rowId: String,
    fields: List<PresentationField>,
) {
    val fields: List<PresentationField> = immutableListCopy(fields)
}

class PresentationReceipt(
    val receiptId: String,
    val currencyCode: String,
    receiptFields: List<PresentationField>,
    itemRows: List<PresentationItemRow>,
) {
    val receiptFields: List<PresentationField> = immutableListCopy(receiptFields)
    val itemRows: List<PresentationItemRow> = immutableListCopy(itemRows)
}

data class ReceiptPresentationV1(
    val schemaName: String,
    val schemaVersion: String,
    val sourceContractVersion: String,
    val requestId: String,
    val imageId: String,
    val source: PresentationSource,
    val outcome: PresentationOutcome,
    val sourceEvidence: PresentationSourceEvidence?,
    val sourceGate: PresentationSourceGate?,
    val automaticExtraction: PresentationAutomaticExtraction?,
    val receipt: PresentationReceipt?,
)

data class PresentationConsumerContext(
    val expectedRequestId: String,
    val expectedImageId: String,
    val mode: PresentationConsumerMode,
)

data class ReceiptPresentationIssue(
    val code: String,
    val path: String,
    val detail: String,
)

sealed interface ReceiptPresentationResult<out T> {
    data class Accepted<T>(val value: T) : ReceiptPresentationResult<T>

    data class Rejected(val issue: ReceiptPresentationIssue) : ReceiptPresentationResult<Nothing>
}

object ReceiptPresentationIssueCodes {
    const val INVALID_JSON = "REJECT_INVALID_JSON"
    const val DUPLICATE_JSON_KEY = "REJECT_DUPLICATE_JSON_KEY"
    const val MISSING_MEMBER = "REJECT_MISSING_MEMBER"
    const val UNKNOWN_MEMBER = "REJECT_UNKNOWN_MEMBER"
    const val UNSUPPORTED_SCHEMA_VERSION = "REJECT_UNSUPPORTED_SCHEMA_VERSION"
    const val UNSUPPORTED_CONTRACT_VERSION = "REJECT_UNSUPPORTED_CONTRACT_VERSION"
    const val UNKNOWN_ENUM = "REJECT_UNKNOWN_ENUM"
    const val INVALID_ID = "REJECT_INVALID_ID"
    const val UNSAFE_PROVENANCE = "REJECT_UNSAFE_PROVENANCE"
    const val INVALID_DIGEST = "REJECT_INVALID_DIGEST"
    const val SOURCE_MODE_MISMATCH = "REJECT_SOURCE_MODE_MISMATCH"
    const val REQUEST_ID_MISMATCH = "REJECT_REQUEST_ID_MISMATCH"
    const val IMAGE_ID_MISMATCH = "REJECT_IMAGE_ID_MISMATCH"
    const val DUPLICATE_TOKEN_ID = "REJECT_DUPLICATE_TOKEN_ID"
    const val GATE_STATE = "REJECT_GATE_STATE"
    const val PRODUCER_METADATA = "REJECT_PRODUCER_METADATA"
    const val INVALID_CONFIDENCE = "REJECT_INVALID_CONFIDENCE"
    const val INVALID_MONEY = "REJECT_INVALID_MONEY"
    const val CURRENCY_MISMATCH = "REJECT_CURRENCY_MISMATCH"
    const val VALUE_RELATIONSHIP = "REJECT_VALUE_RELATIONSHIP"
    const val INVALID_DATE = "REJECT_INVALID_DATE"
    const val INVALID_QUANTITY = "REJECT_INVALID_QUANTITY"
    const val DUPLICATE_FIELD_ID = "REJECT_DUPLICATE_FIELD_ID"
    const val UNKNOWN_ROLE = "REJECT_UNKNOWN_ROLE"
    const val DUPLICATE_TOKEN_REFERENCE = "REJECT_DUPLICATE_TOKEN_REFERENCE"
    const val UNKNOWN_TOKEN_REFERENCE = "REJECT_UNKNOWN_TOKEN_REFERENCE"
    const val CONTRADICTORY_FIELD_STATE = "REJECT_CONTRADICTORY_FIELD_STATE"
    const val TOKEN_INTEGRITY = "REJECT_TOKEN_INTEGRITY"
    const val ROLE_SET = "REJECT_ROLE_SET"
    const val ROLE_ORDER = "REJECT_ROLE_ORDER"
    const val CURRENCY_METADATA = "REJECT_CURRENCY_METADATA"
    const val DUPLICATE_ROW_ID = "REJECT_DUPLICATE_ROW_ID"
    const val OUTCOME_STATE_MISMATCH = "REJECT_OUTCOME_STATE_MISMATCH"
    const val OUTCOME_STAGE_MISMATCH = "REJECT_OUTCOME_STAGE_MISMATCH"
    const val GATE_OUTCOME_MISMATCH = "REJECT_GATE_OUTCOME_MISMATCH"
    const val EVIDENCE_STAGE_MISMATCH = "REJECT_EVIDENCE_STAGE_MISMATCH"
}

internal class ReceiptPresentationViolation(
    val issue: ReceiptPresentationIssue,
) : RuntimeException("${issue.code} at ${issue.path}: ${issue.detail}")

internal fun rejectPresentation(code: String, path: String, detail: String): Nothing {
    throw ReceiptPresentationViolation(ReceiptPresentationIssue(code, path, detail))
}

internal inline fun <T> capturePresentationResult(
    block: () -> T,
): ReceiptPresentationResult<T> =
    try {
        ReceiptPresentationResult.Accepted(block())
    } catch (violation: ReceiptPresentationViolation) {
        ReceiptPresentationResult.Rejected(violation.issue)
    }

private fun <T> immutableListCopy(values: List<T>): List<T> =
    Collections.unmodifiableList(ArrayList(values))
