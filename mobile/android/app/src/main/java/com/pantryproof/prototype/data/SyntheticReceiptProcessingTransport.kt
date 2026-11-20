package com.pantryproof.prototype.data

import com.fasterxml.jackson.core.JsonFactory
import com.fasterxml.jackson.core.JsonGenerator
import java.io.ByteArrayOutputStream
import java.util.concurrent.atomic.AtomicBoolean

/** Fictional V1 responses for the isolated processing page. No image input is consumed. */
internal class SyntheticReceiptProcessingTransport(
    private val scenario: () -> Scenario,
    private val dispatchResponse: (() -> Unit) -> Unit,
) : ReceiptProcessingTransport {
    enum class Scenario {
        AVAILABLE, EXTRACTION_FAILED, UNAVAILABLE, PROCESSING_FAILED, INSUFFICIENT,
        INVALID_JSON, WRONG_REQUEST, WRONG_IMAGE, NO_ENVELOPE, EXECUTION_FAILURE, NO_RESPONSE,
    }

    override fun submit(
        request: ReceiptProcessingRequest,
        deliver: (ReceiptProcessingDelivery) -> Unit,
    ): ReceiptProcessingTransport.Cancellation {
        val selected = scenario()
        val cancelled = AtomicBoolean(false)
        if (selected != Scenario.NO_RESPONSE) {
            dispatchResponse {
                if (!cancelled.get()) deliver(response(request, selected))
            }
        }
        return ReceiptProcessingTransport.Cancellation { cancelled.set(true) }
    }

    private fun response(request: ReceiptProcessingRequest, selected: Scenario): ReceiptProcessingDelivery =
        when (selected) {
            Scenario.NO_ENVELOPE -> ReceiptProcessingDelivery.NoEnvelope
            Scenario.EXECUTION_FAILURE -> ReceiptProcessingDelivery.ExecutionFailure
            Scenario.INVALID_JSON -> ReceiptProcessingDelivery.Envelope("{".toByteArray())
            else -> ReceiptProcessingDelivery.Envelope(envelope(request, selected))
        }

    private fun envelope(request: ReceiptProcessingRequest, selected: Scenario): ByteArray {
        val output = ByteArrayOutputStream()
        JsonFactory().createGenerator(output).use { json ->
            json.writeStartObject()
            json.writeStringField("schemaName", "receipt-presentation")
            json.writeStringField("schemaVersion", "1")
            json.writeStringField("sourceContractVersion", "0")
            json.writeStringField("requestId", request.context.expectedRequestId +
                if (selected == Scenario.WRONG_REQUEST) ".mismatch" else "")
            json.writeStringField("imageId", request.context.expectedImageId +
                if (selected == Scenario.WRONG_IMAGE) ".mismatch" else "")
            json.writeObjectFieldStart("source")
            json.writeStringField("type", "SYNTHETIC_FIXTURE")
            json.writeObjectFieldStart("provenance")
            json.writeStringField("sourceSystem", "ANDROID_SYNTHETIC_PROCESSING")
            json.writeStringField("sourceReference", "synthetic-processing-001")
            json.writeNullField("contentSha256")
            json.writeEndObject()
            json.writeEndObject()
            json.writeObjectFieldStart("outcome")
            when (selected) {
                Scenario.UNAVAILABLE -> {
                    json.writeStringField("status", "PROCESSING_UNAVAILABLE")
                    failure(json, "AVAILABILITY", "PROCESSOR_NOT_AVAILABLE", false)
                }
                Scenario.PROCESSING_FAILED -> {
                    json.writeStringField("status", "PROCESSING_FAILED")
                    failure(json, "OCR", "OCR_ENGINE_FAILURE", true)
                }
                Scenario.INSUFFICIENT -> {
                    json.writeStringField("status", "SOURCE_EVIDENCE_INSUFFICIENT")
                    json.writeNullField("failure")
                }
                else -> {
                    json.writeStringField("status", "RESULT_AVAILABLE")
                    json.writeNullField("failure")
                }
            }
            json.writeEndObject()
            evidence(json, selected)
            if (selected in setOf(Scenario.UNAVAILABLE, Scenario.PROCESSING_FAILED, Scenario.INSUFFICIENT)) {
                json.writeNullField("automaticExtraction")
                json.writeNullField("receipt")
            } else {
                json.writeObjectFieldStart("automaticExtraction")
                json.writeStringField("stage", "PRE_REVIEW_AUTOMATIC")
                json.writeStringField("extractionStatus", if (selected == Scenario.EXTRACTION_FAILED) "FAILED" else "PARTIAL")
                json.writeObjectFieldStart("producer")
                json.writeStringField("producerId", "android-synthetic-processing")
                json.writeStringField("producerVersion", "1.0")
                json.writeEndObject()
                json.writeEndObject()
                receipt(json, selected == Scenario.EXTRACTION_FAILED)
            }
            json.writeEndObject()
        }
        return output.toByteArray()
    }

    private fun failure(json: JsonGenerator, stage: String, code: String, retryable: Boolean) {
        json.writeObjectFieldStart("failure")
        json.writeStringField("stage", stage)
        json.writeStringField("code", code)
        json.writeBooleanField("retryable", retryable)
        json.writeEndObject()
    }

    private fun evidence(json: JsonGenerator, selected: Scenario) {
        if (selected == Scenario.UNAVAILABLE) {
            json.writeNullField("sourceEvidence")
        } else {
            json.writeObjectFieldStart("sourceEvidence")
            json.writeStringField("sourceProcessingStatus", if (selected == Scenario.PROCESSING_FAILED) "OCR_FAILED" else "OCR_PARTIAL")
            json.writeArrayFieldStart("tokenIds")
            if (selected != Scenario.PROCESSING_FAILED) json.writeString("synthetic-observation")
            json.writeEndArray()
            json.writeEndObject()
        }
        if (selected == Scenario.UNAVAILABLE || selected == Scenario.PROCESSING_FAILED) {
            json.writeNullField("sourceGate")
        } else {
            json.writeObjectFieldStart("sourceGate")
            json.writeStringField("gateResultId", "synthetic-processing-gate")
            json.writeStringField("decision", if (selected == Scenario.INSUFFICIENT) "INSUFFICIENT" else "SUFFICIENT")
            json.writeArrayFieldStart("reasons")
            if (selected == Scenario.INSUFFICIENT) json.writeString("Synthetic source structure was unavailable.")
            json.writeEndArray()
            json.writeEndObject()
        }
    }

    private fun receipt(json: JsonGenerator, failed: Boolean) {
        json.writeObjectFieldStart("receipt")
        json.writeStringField("receiptId", "synthetic-processing-receipt")
        json.writeStringField("currencyCode", "MYR")
        json.writeArrayFieldStart("receiptFields")
        field(json, "store", "STORE_NAME", if (failed) null else "Synthetic Processing Market", "STORE_NAME_NOT_OBSERVED")
        field(json, "date", "PURCHASE_DATE", null, "AMBIGUOUS_DATE_FORMAT", unresolved = true)
        field(json, "total", "RECEIPT_TOTAL", if (failed) null else "14.50", "RECEIPT_TOTAL_NOT_OBSERVED")
        json.writeEndArray()
        json.writeArrayFieldStart("itemRows")
        if (!failed) {
            row(json, "weighted", "Synthetic apples", "0.750", "6.00", "4.50")
            row(json, "second", "Synthetic rice", "2", null, "10.00")
        }
        json.writeEndArray()
        json.writeEndObject()
    }

    private fun row(json: JsonGenerator, id: String, description: String, quantity: String, unit: String?, total: String) {
        json.writeStartObject()
        json.writeStringField("rowId", id)
        json.writeArrayFieldStart("fields")
        field(json, "$id-description", "ITEM_DESCRIPTION", description, "DESCRIPTION_NOT_OBSERVED")
        field(json, "$id-quantity", "QUANTITY", quantity, "QUANTITY_NOT_OBSERVED")
        field(json, "$id-unit", "UNIT_PRICE", unit, "NO_EXPLICIT_UNIT_PRICE_OBSERVED")
        field(json, "$id-total", "LINE_TOTAL", total, "TOTAL_NOT_OBSERVED")
        json.writeEndArray()
        json.writeEndObject()
    }

    private fun field(json: JsonGenerator, id: String, role: String, value: String?, reason: String, unresolved: Boolean = false) {
        json.writeStartObject()
        json.writeStringField("fieldId", id)
        json.writeStringField("role", role)
        json.writeStringField("status", if (value != null) "EXTRACTED" else if (unresolved) "UNRESOLVED" else "MISSING")
        json.writeStringField("originalAutomaticValue", value)
        json.writeStringField("presentationValue", value)
        json.writeStringField("absenceReason", if (value == null) reason else null)
        json.writeArrayFieldStart("sourceTokenIds")
        if (value != null || unresolved) json.writeString("synthetic-observation")
        json.writeEndArray()
        json.writeNullField("nativeConfidence")
        json.writeEndObject()
    }
}
