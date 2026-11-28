package com.pantryproof.prototype.contract.review

import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.PresentationOutcomeStatus
import com.pantryproof.prototype.contract.v1.ReceiptPresentationIssueCodes as V1
import com.pantryproof.prototype.contract.v1.ReceiptPresentationResult
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Validator
import com.pantryproof.prototype.contract.v1.ReceiptPresentationViolation
import com.pantryproof.prototype.contract.v1.capturePresentationResult

internal object ReceiptReviewV1Decoder {
    const val MAX_BYTES = 2_097_152
    const val RESPONSE_SCHEMA = "receipt-review-v1"

    fun decode(bytes: ByteArray, context: ReviewContext): ReceiptPresentationResult<ReceiptReviewV1> =
        capturePresentationResult {
            if (bytes.size > MAX_BYTES) {
                com.pantryproof.prototype.contract.v1.rejectPresentation(V1.RESPONSE_TOO_LARGE, "$", "review exceeds byte limit")
            }
            val root = ReviewJson(ReceiptPresentationV1Decoder.strictObject(bytes).value(), "$")
            val name = root["schemaName"].string()
            val version = root["schemaVersion"].string()
            root["schemaVersion"].require(name == "receipt-review" && version == "1", V1.UNSUPPORTED_SCHEMA_VERSION)
            root.obj("schemaName", "schemaVersion", "presentation", "review")
            val span = root["presentation"].objectNode()
            val length = span.byteEnd - span.byteStart
            root["presentation"].require(length <= ReceiptPresentationV1Decoder.MAX_BYTES, V1.RESPONSE_TOO_LARGE)
            val embedded = bytes.copyOfRange(span.byteStart, span.byteEnd)
            val presentation = ReceiptPresentationV1Validator.decodeAndValidate(embedded, context.presentation)
                .value("$.presentation")
            val extension = root["review"].nullable { readExtension(it, presentation, context) }
            root["review"].require(
                (extension == null) == (presentation.outcome.status == PresentationOutcomeStatus.PROCESSING_UNAVAILABLE),
                REVIEW_STATE,
            )
            ReceiptReviewV1(presentation, extension, bytes)
        }

    private fun readExtension(j: ReviewJson, presentation: ReceiptPresentationV1, context: ReviewContext): ReviewExtension {
        j.obj("methodId", "methodVersion", "methodReadiness", "receiptDisposition", "failure", "region", "ocrEvidence", "fields", "pantryMappings")
        j["methodId"].enum("PROPOSED_RECEIPT_V1")
        val methodVersion = j["methodVersion"].textOrNull()
        val readiness = j["methodReadiness"].enum<ReviewReadiness>()
        val disposition = j["receiptDisposition"].enum<ReceiptDisposition>()
        val failure = j["failure"].nullable {
            it.obj("stage", "code")["stage"].enum("PRE_RESOLUTION")
            it["code"].reason()
        }
        val region = j["region"].nullable(ReviewJson::nonblank)
        val ocr = j["ocrEvidence"].nullable { readReviewOcr(it, context, presentation.sourceEvidence?.tokenIds.orEmpty()) }
        val fields = j["fields"].array()
        val pantry = j["pantryMappings"].array()
        val receipt = presentation.receipt
        val expected = receipt?.let { value ->
            value.receiptFields.map { null to it } + value.itemRows.flatMap { row -> row.fields.map { row.rowId to it } }
        }.orEmpty()
        j["ocrEvidence"].require(ocr != null || presentation.sourceEvidence?.tokenIds.isNullOrEmpty(), REVIEW_REFERENCE)
        j["fields"].require(fields.size == expected.size, REVIEW_REFERENCE, "fields must follow presentation order")
        val evidence = ReviewEvidenceReader(ocr?.tokens.orEmpty())
        val fieldReader = ReviewFieldReader(evidence, readiness)
        val mapped = fields.mapIndexed { i, field -> fieldReader.read(field, expected[i].first, expected[i].second) }
            .immutableReviewList()
        val rows = receipt?.itemRows.orEmpty()
        j["pantryMappings"].require(pantry.size == rows.size, REVIEW_REFERENCE)
        val mappings = pantry.mapIndexed { i, value -> readPantryMapping(value, rows[i]) }.immutableReviewList()

        when (presentation.outcome.status) {
            PresentationOutcomeStatus.RESULT_AVAILABLE -> {
                val producer = presentation.automaticExtraction?.producer
                j["methodVersion"].require(methodVersion == "proposed-receipt-research-v1" &&
                    producer?.producerVersion == methodVersion, REVIEW_STATE)
                val required = when (producer?.producerId) {
                    "PROPOSED_RECEIPT_V1" -> ReviewReadiness.POLICY_APPLIED
                    "PROPOSED_UNVERIFIED_REVIEW_V1" -> ReviewReadiness.NOT_READY
                    else -> j["methodReadiness"].fail(REVIEW_STATE, "unsupported presentation producer")
                }
                j["methodReadiness"].require(readiness == required, REVIEW_STATE)
                val expectedDisposition = when {
                    readiness == ReviewReadiness.NOT_READY -> ReceiptDisposition.UNVERIFIED_DRAFT
                    mapped.any { it.disposition == FieldDisposition.REVIEW_REQUIRED } -> ReceiptDisposition.REVIEW_REQUIRED
                    else -> ReceiptDisposition.AUTO_RESOLVED
                }
                j["receiptDisposition"].require(disposition == expectedDisposition, REVIEW_STATE)
                j["failure"].require(failure == null, REVIEW_STATE)
            }
            PresentationOutcomeStatus.PROCESSING_FAILED -> {
                val underlying = presentation.outcome.failure?.code
                val refinement = underlying == "PRESENTATION_PROJECTION_FAILURE" &&
                    failure in setOf("PROPOSED_METHOD_FAILURE", "PROPOSED_CONFIGURATION_INVALID")
                j["failure"].require(failure != null, REVIEW_STATE)
                j["failure"]["code"].require(failure == underlying || refinement, REVIEW_STATE)
                val required = if (failure == "PROPOSED_CONFIGURATION_INVALID") ReviewReadiness.NOT_VALID
                    else ReviewReadiness.NOT_EVALUATED
                j["methodReadiness"].require(readiness == required, REVIEW_STATE)
                j["receiptDisposition"].require(disposition == ReceiptDisposition.FAILED, REVIEW_STATE)
                j["methodVersion"].require(methodVersion == null, REVIEW_STATE)
            }
            PresentationOutcomeStatus.SOURCE_EVIDENCE_INSUFFICIENT -> {
                j["methodReadiness"].require(readiness == ReviewReadiness.NOT_EVALUATED, REVIEW_STATE)
                j["receiptDisposition"].require(disposition == ReceiptDisposition.FALLBACK_NO_UPDATE, REVIEW_STATE)
                j["methodVersion"].require(methodVersion == null, REVIEW_STATE)
                j["failure"].require(failure == null, REVIEW_STATE)
            }
            PresentationOutcomeStatus.PROCESSING_UNAVAILABLE -> j.fail(REVIEW_STATE, "unavailable has no review extension")
        }
        return ReviewExtension(readiness, disposition, failure, region, ocr, mapped, mappings)
    }

    private fun <T> ReceiptPresentationResult<T>.value(prefix: String = ""): T = when (this) {
        is ReceiptPresentationResult.Accepted -> value
        is ReceiptPresentationResult.Rejected -> {
            val path = if (prefix.isEmpty() || issue.path.startsWith("\$context")) issue.path else prefix + issue.path.drop(1)
            throw ReceiptPresentationViolation(issue.copy(path = path))
        }
    }
}

private fun readReviewOcr(j: ReviewJson, context: ReviewContext, expectedIds: List<String>): ReviewOcr {
    val frame = j.obj("coordinateFrame", "tokens")["coordinateFrame"]
        .obj("origin", "unit", "imageWidth", "imageHeight")
    frame["origin"].enum("TOP_LEFT")
    frame["unit"].enum("SUBMITTED_IMAGE_PIXELS")
    val width = frame["imageWidth"].integer().also { frame["imageWidth"].require(it in 1..1600) }
    val height = frame["imageHeight"].integer().also { frame["imageHeight"].require(it in 1..1600) }
    val supplied = context.imageWidth != null || context.imageHeight != null || context.presentation.mode == PresentationConsumerMode.LIVE
    if (supplied) {
        frame["imageWidth"].require(context.imageWidth == width, REVIEW_REFERENCE)
        frame["imageHeight"].require(context.imageHeight == height, REVIEW_REFERENCE)
    }
    val values = j["tokens"].array()
    j["tokens"].require(values.size <= 128)
    j["tokens"].require(values.size == expectedIds.size, REVIEW_REFERENCE)
    var characters = 0
    var bytes = 0
    var vertices = 0
    val tokens = values.mapIndexed { i, token ->
        token.obj("tokenId", "originalText", "polygon", "rawConfidence")
        val id = token["tokenId"].alias()
        token["tokenId"].require(id == expectedIds[i], REVIEW_REFERENCE)
        val literal = token["originalText"].string()
        val count = literal.codePointCount(0, literal.length)
        val encoded = literal.toByteArray(Charsets.UTF_8).size
        characters += count
        bytes += encoded
        token["originalText"].require(count in 1..256 && encoded <= 1024 && characters <= 16384 && bytes <= 49152)
        val points = token["polygon"].array()
        vertices += points.size
        token["polygon"].require(points.size in 3..8 && vertices <= 1024)
        val geometry = points.map { entry ->
            val point = entry.array()
            entry.require(point.size == 2)
            val x = point[0].finite().also { point[0].require(it >= java.math.BigDecimal.ZERO && it <= width.toBigDecimal()) }
            val y = point[1].finite().also { point[1].require(it >= java.math.BigDecimal.ZERO && it <= height.toBigDecimal()) }
            ReviewPoint(x, y)
        }
        token["polygon"].require(geometry.any { it.x.compareTo(geometry.first().x) != 0 } &&
            geometry.any { it.y.compareTo(geometry.first().y) != 0 })
        ReviewToken(id, literal, geometry.immutableReviewList(), token["rawConfidence"].nullable(ReviewJson::finite))
    }
    return ReviewOcr(width, height, tokens.immutableReviewList())
}
