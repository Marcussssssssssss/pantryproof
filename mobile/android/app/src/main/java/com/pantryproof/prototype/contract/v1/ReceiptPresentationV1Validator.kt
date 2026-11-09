package com.pantryproof.prototype.contract.v1

import java.math.BigDecimal
import java.time.LocalDate
import java.time.format.DateTimeParseException

object ReceiptPresentationV1Validator {
    fun decodeAndValidate(
        rawJson: ByteArray,
        context: PresentationConsumerContext,
    ): ReceiptPresentationResult<ReceiptPresentationV1> =
        when (val decoded = ReceiptPresentationV1Decoder.decode(rawJson)) {
            is ReceiptPresentationResult.Accepted -> validate(decoded.value, context)
            is ReceiptPresentationResult.Rejected -> decoded
        }

    fun validate(
        envelope: ReceiptPresentationV1,
        context: PresentationConsumerContext,
    ): ReceiptPresentationResult<ReceiptPresentationV1> =
        capturePresentationResult {
            validateEnvelope(envelope, context)
            envelope
        }

    private fun validateEnvelope(
        envelope: ReceiptPresentationV1,
        context: PresentationConsumerContext,
    ) {
        val expectedRequestId = validateProtocolId(
            context.expectedRequestId,
            "\$context.expectedRequestId",
        )
        val expectedImageId = validateProtocolId(
            context.expectedImageId,
            "\$context.expectedImageId",
        )

        if (envelope.schemaName != "receipt-presentation" || envelope.schemaVersion != "1") {
            rejectPresentation(
                ReceiptPresentationIssueCodes.UNSUPPORTED_SCHEMA_VERSION,
                "$.schemaVersion",
                "unsupported receipt-presentation schema identity/version",
            )
        }
        if (envelope.sourceContractVersion != "0") {
            rejectPresentation(
                ReceiptPresentationIssueCodes.UNSUPPORTED_CONTRACT_VERSION,
                "$.sourceContractVersion",
                "unsupported source contract version",
            )
        }

        val requestId = validateProtocolId(envelope.requestId, "$.requestId")
        val imageId = validateProtocolId(envelope.imageId, "$.imageId")
        if (requestId != expectedRequestId) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.REQUEST_ID_MISMATCH,
                "$.requestId",
                "envelope request identity does not match caller context",
            )
        }
        if (imageId != expectedImageId) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.IMAGE_ID_MISMATCH,
                "$.imageId",
                "envelope image identity does not match caller context",
            )
        }

        validateSource(envelope.source, context.mode)
        validateFailure(envelope.outcome.failure)
        val knownTokens = validateEvidence(envelope.sourceEvidence)
        validateGate(envelope.sourceGate)
        validateExtraction(envelope.automaticExtraction)
        validateReceipt(envelope.receipt, knownTokens)
        validateOutcomeMatrix(envelope)
    }

    private fun validateSource(source: PresentationSource, mode: PresentationConsumerMode) {
        if (source.type == PresentationSourceType.SYNTHETIC_FIXTURE && mode != PresentationConsumerMode.FIXTURE) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.SOURCE_MODE_MISMATCH,
                "$.source.type",
                "synthetic fixture source is forbidden outside FIXTURE mode",
            )
        }
        validateProtocolId(source.provenance.sourceSystem, "$.source.provenance.sourceSystem")
        validateProtocolId(
            source.provenance.sourceReference,
            "$.source.provenance.sourceReference",
            ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
        )
        val digest = source.provenance.contentSha256
        if (digest != null && !DIGEST_REGEX.matches(digest)) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_DIGEST,
                "$.source.provenance.contentSha256",
                "digest must be 64 lowercase hexadecimal characters",
            )
        }
    }

    private fun validateFailure(failure: PresentationFailure?) {
        if (failure != null && !FAILURE_CODE_REGEX.matches(failure.code)) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.UNKNOWN_ENUM,
                "$.outcome.failure.code",
                "invalid failure code token",
            )
        }
    }

    private fun validateEvidence(evidence: PresentationSourceEvidence?): Set<String> {
        if (evidence == null) {
            return emptySet()
        }
        val seen = linkedSetOf<String>()
        evidence.tokenIds.forEachIndexed { index, rawTokenId ->
            val tokenId = validateProtocolId(rawTokenId, "$.sourceEvidence.tokenIds[$index]")
            if (!seen.add(tokenId)) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.DUPLICATE_TOKEN_ID,
                    "$.sourceEvidence.tokenIds[$index]",
                    "duplicate token registry identity",
                )
            }
        }
        return seen
    }

    private fun validateGate(gate: PresentationSourceGate?) {
        if (gate == null) {
            return
        }
        validateProtocolId(gate.gateResultId, "$.sourceGate.gateResultId")
        val seenReasons = linkedSetOf<String>()
        gate.reasons.forEachIndexed { index, reason ->
            requireNonblank(
                reason,
                "$.sourceGate.reasons[$index]",
                ReceiptPresentationIssueCodes.GATE_STATE,
            )
            if (!seenReasons.add(reason)) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.GATE_STATE,
                    "$.sourceGate.reasons[$index]",
                    "duplicate gate reason",
                )
            }
        }
        if (gate.decision == SourceGateDecision.INSUFFICIENT && gate.reasons.isEmpty()) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.GATE_STATE,
                "$.sourceGate.reasons",
                "an insufficient gate requires at least one recorded reason",
            )
        }
        gate.reasons.forEachIndexed { index, reason ->
            requirePrivacySafeReason(reason, "$.sourceGate.reasons[$index]")
        }
    }

    private fun validateExtraction(extraction: PresentationAutomaticExtraction?) {
        if (extraction == null) {
            return
        }
        validateProtocolId(
            extraction.producer.producerId,
            "$.automaticExtraction.producer.producerId",
        )
        requireNonblank(
            extraction.producer.producerVersion,
            "$.automaticExtraction.producer.producerVersion",
            ReceiptPresentationIssueCodes.PRODUCER_METADATA,
        )
    }

    private fun validateReceipt(receipt: PresentationReceipt?, knownTokens: Set<String>) {
        if (receipt == null) {
            return
        }
        validateProtocolId(receipt.receiptId, "$.receipt.receiptId")
        if (receipt.currencyCode != "MYR") {
            rejectPresentation(
                ReceiptPresentationIssueCodes.CURRENCY_METADATA,
                "$.receipt.currencyCode",
                "V1 available receipts require exact currency code MYR",
            )
        }

        val fieldIds = linkedSetOf<String>()
        validateFieldGroup(
            receipt.receiptFields,
            RECEIPT_ROLE_ORDER,
            "$.receipt.receiptFields",
            knownTokens,
            fieldIds,
        )

        val rowIds = linkedSetOf<String>()
        receipt.itemRows.forEachIndexed { index, row ->
            val rowPath = "$.receipt.itemRows[$index]"
            val rowId = validateProtocolId(row.rowId, "$rowPath.rowId")
            if (!rowIds.add(rowId)) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.DUPLICATE_ROW_ID,
                    "$rowPath.rowId",
                    "duplicate row identity",
                )
            }
            validateFieldGroup(
                row.fields,
                ITEM_ROLE_ORDER,
                "$rowPath.fields",
                knownTokens,
                fieldIds,
            )
            if (row.fields.none { it.status == ReceiptFieldStatus.EXTRACTED }) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.TOKEN_INTEGRITY,
                    "$rowPath.fields",
                    "item row requires at least one OCR-backed extracted field",
                )
            }
        }
    }

    private fun validateFieldGroup(
        fields: List<PresentationField>,
        expectedRoles: List<ReceiptFieldRole>,
        path: String,
        knownTokens: Set<String>,
        fieldIds: MutableSet<String>,
    ) {
        fields.forEachIndexed { index, field ->
            validateField(field, "$path[$index]", knownTokens, fieldIds)
        }
        val actualRoles = fields.map { it.role }
        if (actualRoles.size != expectedRoles.size || actualRoles.toSet() != expectedRoles.toSet()) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.ROLE_SET,
                path,
                "field role set is incomplete or duplicated",
            )
        }
        if (actualRoles != expectedRoles) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.ROLE_ORDER,
                path,
                "field roles are not in normative order",
            )
        }
    }

    private fun validateField(
        field: PresentationField,
        path: String,
        knownTokens: Set<String>,
        fieldIds: MutableSet<String>,
    ) {
        val fieldId = validateProtocolId(field.fieldId, "$path.fieldId")
        if (!fieldIds.add(fieldId)) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.DUPLICATE_FIELD_ID,
                "$path.fieldId",
                "duplicate field identity",
            )
        }
        validateConfidence(field.nativeConfidence, "$path.nativeConfidence")

        val seenTokenReferences = linkedSetOf<String>()
        field.sourceTokenIds.forEachIndexed { index, rawTokenId ->
            val tokenPath = "$path.sourceTokenIds[$index]"
            val tokenId = validateProtocolId(rawTokenId, tokenPath)
            if (!seenTokenReferences.add(tokenId)) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.DUPLICATE_TOKEN_REFERENCE,
                    tokenPath,
                    "duplicate token reference",
                )
            }
            if (tokenId !in knownTokens) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.UNKNOWN_TOKEN_REFERENCE,
                    tokenPath,
                    "token reference is absent from source evidence",
                )
            }
        }

        when (field.status) {
            ReceiptFieldStatus.EXTRACTED -> validateExtractedField(field, path)
            ReceiptFieldStatus.MISSING,
            ReceiptFieldStatus.UNRESOLVED,
            -> validateAbsentField(field, path)
        }
    }

    private fun validateExtractedField(field: PresentationField, path: String) {
        val original = field.originalAutomaticValue
            ?: rejectPresentation(
                ReceiptPresentationIssueCodes.CONTRADICTORY_FIELD_STATE,
                path,
                "extracted field requires both values",
            )
        val presentation = field.presentationValue
            ?: rejectPresentation(
                ReceiptPresentationIssueCodes.CONTRADICTORY_FIELD_STATE,
                path,
                "extracted field requires both values",
            )
        requireNonblank(
            original,
            "$path.originalAutomaticValue",
            ReceiptPresentationIssueCodes.CONTRADICTORY_FIELD_STATE,
        )
        requireNonblank(
            presentation,
            "$path.presentationValue",
            ReceiptPresentationIssueCodes.CONTRADICTORY_FIELD_STATE,
        )
        if (field.absenceReason != null) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.CONTRADICTORY_FIELD_STATE,
                "$path.absenceReason",
                "extracted field must not carry an absence reason",
            )
        }
        if (field.sourceTokenIds.isEmpty()) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.TOKEN_INTEGRITY,
                "$path.sourceTokenIds",
                "extracted field requires at least one token reference",
            )
        }

        when (field.role) {
            ReceiptFieldRole.STORE_NAME,
            ReceiptFieldRole.ITEM_DESCRIPTION,
            -> if (original != presentation) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.VALUE_RELATIONSHIP,
                    path,
                    "text original and presentation values must be identical",
                )
            }
            ReceiptFieldRole.PURCHASE_DATE -> validateDate(original, presentation, path)
            ReceiptFieldRole.QUANTITY -> validateQuantity(original, presentation, path)
            ReceiptFieldRole.UNIT_PRICE,
            ReceiptFieldRole.LINE_TOTAL,
            ReceiptFieldRole.RECEIPT_TOTAL,
            -> validateMoney(original, presentation, path)
        }
    }

    private fun validateAbsentField(field: PresentationField, path: String) {
        if (field.originalAutomaticValue != null || field.presentationValue != null) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.CONTRADICTORY_FIELD_STATE,
                path,
                "missing or unresolved field values must be null",
            )
        }
        if (field.nativeConfidence != null) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.CONTRADICTORY_FIELD_STATE,
                "$path.nativeConfidence",
                "missing or unresolved field confidence must be null",
            )
        }
        val reason = field.absenceReason
            ?: rejectPresentation(
                ReceiptPresentationIssueCodes.CONTRADICTORY_FIELD_STATE,
                "$path.absenceReason",
                "missing or unresolved field requires an absence reason",
            )
        requireNonblank(
            reason,
            "$path.absenceReason",
            ReceiptPresentationIssueCodes.CONTRADICTORY_FIELD_STATE,
        )
        requirePrivacySafeReason(reason, "$path.absenceReason")
    }

    private fun validateConfidence(value: BigDecimal?, path: String) {
        if (value != null && !value.toDouble().isFinite()) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_CONFIDENCE,
                path,
                "confidence is not finite binary64",
            )
        }
    }

    private fun validateMoney(original: String, presentation: String, path: String) {
        if (!MONEY_REGEX.matches(presentation)) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_MONEY,
                "$path.presentationValue",
                "money must be a non-negative canonical decimal with scale two",
            )
        }
        presentation.toBigDecimalOrNull()
            ?: rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_MONEY,
                "$path.presentationValue",
                "invalid decimal money value",
            )
        if (original.startsWith('$')) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.CURRENCY_MISMATCH,
                "$path.originalAutomaticValue",
                "dollar-prefixed source value is not established as MYR",
            )
        }
        val originalMatch = ORIGINAL_MONEY_REGEX.matchEntire(original)
            ?: rejectPresentation(
                ReceiptPresentationIssueCodes.VALUE_RELATIONSHIP,
                "$path.originalAutomaticValue",
                "original money is outside the approved lexical grammar",
            )
        val normalized =
            originalMatch.groups["integer"]!!.value.replace(",", "") +
                "." +
                originalMatch.groups["fraction"]!!.value
        if (normalized != presentation) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.VALUE_RELATIONSHIP,
                path,
                "money presentation differs beyond approved lexical normalization",
            )
        }
    }

    private fun validateDate(original: String, presentation: String, path: String) {
        if (original != presentation) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.VALUE_RELATIONSHIP,
                path,
                "date original and presentation values must be identical",
            )
        }
        if (!DATE_REGEX.matches(presentation)) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_DATE,
                "$path.presentationValue",
                "invalid canonical ISO date",
            )
        }
        try {
            LocalDate.parse(presentation)
        } catch (error: DateTimeParseException) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_DATE,
                "$path.presentationValue",
                "date is not Gregorian-valid",
            )
        }
    }

    private fun validateQuantity(original: String, presentation: String, path: String) {
        if (original != presentation) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.VALUE_RELATIONSHIP,
                path,
                "quantity original and presentation values must be identical",
            )
        }
        if (!QUANTITY_REGEX.matches(presentation)) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_QUANTITY,
                "$path.presentationValue",
                "quantity is outside canonical scale-zero-to-three grammar",
            )
        }
        val numeric = presentation.toBigDecimalOrNull()
            ?: rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_QUANTITY,
                "$path.presentationValue",
                "invalid decimal quantity",
            )
        if (numeric <= BigDecimal.ZERO) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_QUANTITY,
                "$path.presentationValue",
                "quantity must be greater than zero",
            )
        }
    }

    private fun validateOutcomeMatrix(envelope: ReceiptPresentationV1) {
        val outcome = envelope.outcome
        val failure = outcome.failure
        val evidence = envelope.sourceEvidence
        val gate = envelope.sourceGate
        val extraction = envelope.automaticExtraction
        val receipt = envelope.receipt

        when (outcome.status) {
            PresentationOutcomeStatus.RESULT_AVAILABLE -> {
                if (failure != null) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.OUTCOME_STATE_MISMATCH,
                        "$.outcome.failure",
                        "available result must not carry a technical failure",
                    )
                }
                if (evidence == null) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.OUTCOME_STATE_MISMATCH,
                        "$.sourceEvidence",
                        "available result requires genuine source evidence",
                    )
                }
                if (gate == null || gate.decision != SourceGateDecision.SUFFICIENT) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.GATE_OUTCOME_MISMATCH,
                        "$.sourceGate",
                        "available result requires a recorded sufficient gate",
                    )
                }
                if (extraction == null || receipt == null) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.OUTCOME_STATE_MISMATCH,
                        if (extraction == null) "$.automaticExtraction" else "$.receipt",
                        "available result requires extraction metadata and receipt",
                    )
                }
            }

            PresentationOutcomeStatus.SOURCE_EVIDENCE_INSUFFICIENT -> {
                if (failure != null || extraction != null || receipt != null) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.OUTCOME_STATE_MISMATCH,
                        "$.outcome",
                        "insufficient-evidence result must have null failure, extraction, and receipt",
                    )
                }
                if (evidence == null) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.OUTCOME_STATE_MISMATCH,
                        "$.sourceEvidence",
                        "insufficient-evidence result requires genuine source evidence",
                    )
                }
                if (gate == null || gate.decision != SourceGateDecision.INSUFFICIENT) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.GATE_OUTCOME_MISMATCH,
                        "$.sourceGate",
                        "insufficient-evidence result requires a recorded insufficient gate",
                    )
                }
            }

            PresentationOutcomeStatus.PROCESSING_UNAVAILABLE -> {
                if (failure == null) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.OUTCOME_STATE_MISMATCH,
                        "$.outcome.failure",
                        "unavailable outcome requires a failure diagnostic",
                    )
                }
                if (failure.stage != PresentationFailureStage.AVAILABILITY) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.OUTCOME_STAGE_MISMATCH,
                        "$.outcome.failure.stage",
                        "unavailable outcome requires AVAILABILITY stage",
                    )
                }
                if (evidence != null || gate != null || extraction != null || receipt != null) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.OUTCOME_STATE_MISMATCH,
                        "$",
                        "unavailable outcome requires null evidence, gate, extraction, and receipt",
                    )
                }
            }

            PresentationOutcomeStatus.PROCESSING_FAILED ->
                validateTechnicalFailure(failure, evidence, gate, extraction, receipt)
        }
    }

    private fun validateTechnicalFailure(
        failure: PresentationFailure?,
        evidence: PresentationSourceEvidence?,
        gate: PresentationSourceGate?,
        extraction: PresentationAutomaticExtraction?,
        receipt: PresentationReceipt?,
    ) {
        if (failure == null) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.OUTCOME_STATE_MISMATCH,
                "$.outcome.failure",
                "technical failure requires a failure diagnostic",
            )
        }
        if (failure.stage == PresentationFailureStage.AVAILABILITY) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.OUTCOME_STAGE_MISMATCH,
                "$.outcome.failure.stage",
                "PROCESSING_FAILED cannot use AVAILABILITY stage",
            )
        }
        if (extraction != null || receipt != null) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.OUTCOME_STATE_MISMATCH,
                "$",
                "technical failure requires null extraction and receipt",
            )
        }
        if (failure.stage == PresentationFailureStage.OCR) {
            if (gate != null) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.GATE_OUTCOME_MISMATCH,
                    "$.sourceGate",
                    "OCR-stage failure cannot carry a gate",
                )
            }
            if (evidence != null && evidence.sourceProcessingStatus != SourceProcessingStatus.OCR_FAILED) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.EVIDENCE_STAGE_MISMATCH,
                    "$.sourceEvidence.sourceProcessingStatus",
                    "OCR-stage failure permits null or OCR_FAILED evidence only",
                )
            }
            return
        }

        if (
            evidence == null ||
            evidence.sourceProcessingStatus !in
                setOf(SourceProcessingStatus.OCR_COMPLETED, SourceProcessingStatus.OCR_PARTIAL)
        ) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.EVIDENCE_STAGE_MISMATCH,
                "$.sourceEvidence",
                "downstream technical failure requires completed or partial OCR evidence",
            )
        }
        if (failure.stage == PresentationFailureStage.SOURCE_GATE) {
            if (gate != null) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.GATE_OUTCOME_MISMATCH,
                    "$.sourceGate",
                    "source-gate failure means no durable gate result exists",
                )
            }
            return
        }
        if (gate == null || gate.decision != SourceGateDecision.SUFFICIENT) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.GATE_OUTCOME_MISMATCH,
                "$.sourceGate",
                "extraction/adapter failure requires a recorded sufficient gate",
            )
        }
    }

    private fun validateProtocolId(
        value: String,
        path: String,
        code: String = ReceiptPresentationIssueCodes.INVALID_ID,
    ): String {
        if (!PROTOCOL_ID_REGEX.matches(value) || PRIVATE_ID_MARKER_REGEX.containsMatchIn(value)) {
            rejectPresentation(code, path, "invalid or privacy-unsafe opaque protocol identifier")
        }
        return value
    }

    private fun requireNonblank(value: String, path: String, code: String): String {
        if (value.none { it != '\t' && it != '\n' && it != '\r' && it != ' ' }) {
            rejectPresentation(code, path, "expected nonblank string")
        }
        return value
    }

    private fun requirePrivacySafeReason(value: String, path: String) {
        if (containsUnsafePrivacyReason(value)) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
                path,
                "reason contains a prohibited URI, path, or protected data identifier",
            )
        }
    }

    private fun containsUnsafePrivacyReason(value: String): Boolean {
        if (URI_PATH_REASON_PATTERNS.any { it.containsMatchIn(value) } || containsInvisiblePrivacyCodePoint(value)) {
            return true
        }

        val detectionView = buildPrivacyDetectionView(value)
        if (URI_PATH_REASON_PATTERNS.any { it.containsMatchIn(detectionView) } ||
            containsMixedScriptStructuredLabel(detectionView)
        ) {
            return true
        }

        return PROTECTED_MARKER_REGEX.findAll(detectionView).any { marker ->
            containsUnsafeProtectedMarkerTail(detectionView.substring(marker.range.last + 1))
        }
    }

    private fun containsInvisiblePrivacyCodePoint(value: String): Boolean {
        var index = 0
        while (index < value.length) {
            val codePoint = Character.codePointAt(value, index)
            if (codePoint == 0x00AD ||
                codePoint == 0x034F ||
                codePoint == 0x061C ||
                codePoint == 0x180E ||
                codePoint in 0x200B..0x200F ||
                codePoint in 0x202A..0x202E ||
                codePoint in 0x2060..0x206F ||
                codePoint == 0xFEFF
            ) {
                return true
            }
            index += Character.charCount(codePoint)
        }
        return false
    }

    private fun buildPrivacyDetectionView(value: String): String {
        val normalized = StringBuilder(value.length)
        var previousWasSpace = false
        var index = 0
        while (index < value.length) {
            var codePoint = Character.codePointAt(value, index)
            index += Character.charCount(codePoint)
            if (codePoint in 0xFF01..0xFF5E) {
                codePoint -= 0xFEE0
            }
            if (isPrivacyWhitespace(codePoint)) {
                if (!previousWasSpace) {
                    normalized.append(' ')
                    previousWasSpace = true
                }
                continue
            }
            if (codePoint in 'A'.code..'Z'.code) {
                codePoint += 'a'.code - 'A'.code
            }
            normalized.appendCodePoint(codePoint)
            previousWasSpace = false
        }
        return normalized.toString()
    }

    private fun isPrivacyWhitespace(codePoint: Int): Boolean =
        codePoint in 0x0009..0x000D ||
            codePoint == 0x0020 ||
            codePoint == 0x0085 ||
            codePoint == 0x00A0 ||
            codePoint == 0x1680 ||
            codePoint in 0x2000..0x200A ||
            codePoint in 0x2028..0x2029 ||
            codePoint == 0x202F ||
            codePoint == 0x205F ||
            codePoint == 0x3000

    private fun containsUnsafeProtectedMarkerTail(postMarkerSpan: String): Boolean {
        var index = 0
        while (index < postMarkerSpan.length && postMarkerSpan[index] == ' ') {
            index++
        }
        if (index < postMarkerSpan.length && postMarkerSpan[index] in IMMEDIATE_MARKER_PUNCTUATION) {
            return true
        }
        if (index < postMarkerSpan.length && postMarkerSpan[index].isAsciiDigit()) {
            return true
        }
        if (index > 0 && startsWithIdentifierQualifier(postMarkerSpan, index)) {
            return true
        }

        val atom = StringBuilder()
        var completeAtomCount = 0
        var hasWrapper = false
        var spanIndex = 0
        while (spanIndex < postMarkerSpan.length) {
            val codePoint = Character.codePointAt(postMarkerSpan, spanIndex)
            spanIndex += Character.charCount(codePoint)
            if (codePoint == 0x0020 || codePoint in PRIVACY_DELIMITERS) {
                if (atom.isNotEmpty()) {
                    completeAtomCount++
                    if (isUnsafeProtectedAtom(atom.toString())) {
                        return true
                    }
                    atom.setLength(0)
                }
                if (codePoint in PRIVACY_WRAPPERS) {
                    hasWrapper = true
                }
            } else {
                atom.appendCodePoint(codePoint)
            }
        }
        if (atom.isNotEmpty()) {
            completeAtomCount++
            if (isUnsafeProtectedAtom(atom.toString())) {
                return true
            }
        }
        if ((hasWrapper && completeAtomCount == 0) || hasUnbalancedPrivacyWrappers(postMarkerSpan)) {
            return true
        }
        return false
    }

    private fun startsWithIdentifierQualifier(value: String, start: Int): Boolean {
        for (qualifier in IDENTIFIER_QUALIFIERS) {
            if (value.regionMatches(start, qualifier, 0, qualifier.length) &&
                (start + qualifier.length == value.length || !value[start + qualifier.length].isAsciiAlphaNumeric())
            ) {
                return true
            }
        }
        return false
    }

    private fun isUnsafeProtectedAtom(atom: String): Boolean {
        var index = 0
        var idRunContainsDigit = false
        while (index < atom.length) {
            val codePoint = Character.codePointAt(atom, index)
            index += Character.charCount(codePoint)
            if (codePoint > 0x7F) {
                return true
            }
            val character = codePoint.toChar()
            if (character.isIdentifierCoreCharacter()) {
                if (character.isAsciiDigit()) {
                    idRunContainsDigit = true
                }
                continue
            }
            if (idRunContainsDigit) {
                return true
            }
            idRunContainsDigit = false
            if (codePoint in 0x21..0x7E && codePoint !in PRIVACY_DELIMITERS) {
                return true
            }
        }
        return idRunContainsDigit
    }

    private fun hasUnbalancedPrivacyWrappers(value: String): Boolean {
        val expectedClosings = mutableListOf<Int>()
        var index = 0
        while (index < value.length) {
            val codePoint = Character.codePointAt(value, index)
            index += Character.charCount(codePoint)
            val expectedClosing = ASYMMETRIC_WRAPPER_OPENINGS[codePoint]
            if (expectedClosing != null) {
                expectedClosings.add(expectedClosing)
                continue
            }
            if (codePoint in SYMMETRIC_PRIVACY_QUOTES) {
                if (expectedClosings.lastOrNull() == codePoint) {
                    expectedClosings.removeAt(expectedClosings.lastIndex)
                } else {
                    expectedClosings.add(codePoint)
                }
                continue
            }
            if (codePoint in ASYMMETRIC_WRAPPER_CLOSINGS) {
                if (expectedClosings.lastOrNull() != codePoint) {
                    return true
                }
                expectedClosings.removeAt(expectedClosings.lastIndex)
            }
        }
        return expectedClosings.isNotEmpty()
    }

    private fun containsMixedScriptStructuredLabel(value: String): Boolean {
        var punctuationIndex = 0
        while (punctuationIndex < value.length) {
            val punctuation = value[punctuationIndex]
            if (punctuation !in IMMEDIATE_MARKER_PUNCTUATION) {
                punctuationIndex++
                continue
            }
            var end = punctuationIndex - 1
            while (end >= 0 && value[end] == ' ') {
                end--
            }
            var start = end
            while (start >= 0 && value[start] != ' ' && value[start] !in IMMEDIATE_MARKER_PUNCTUATION) {
                start--
            }
            var hasAsciiLetter = false
            var hasNonAscii = false
            var tokenIndex = start + 1
            while (tokenIndex <= end) {
                val codePoint = Character.codePointAt(value, tokenIndex)
                tokenIndex += Character.charCount(codePoint)
                hasAsciiLetter = hasAsciiLetter || codePoint in 'a'.code..'z'.code
                hasNonAscii = hasNonAscii || codePoint > 0x7F
            }
            if (hasAsciiLetter && hasNonAscii) {
                return true
            }
            punctuationIndex++
        }
        return false
    }

    private fun Char.isAsciiDigit(): Boolean = this in '0'..'9'

    private fun Char.isAsciiAlphaNumeric(): Boolean = this in 'a'..'z' || this in 'A'..'Z' || isAsciiDigit()

    private fun Char.isIdentifierCoreCharacter(): Boolean = isAsciiAlphaNumeric() || this == '.' || this == '_' || this == '-'

    private val PROTOCOL_ID_REGEX = Regex("^[A-Za-z0-9][A-Za-z0-9._-]*$")
    private val DIGEST_REGEX = Regex("^[0-9a-f]{64}$")
    private val FAILURE_CODE_REGEX = Regex("^[A-Z][A-Z0-9_]*$")
    private val MONEY_REGEX = Regex("^(0|[1-9][0-9]*)\\.[0-9]{2}$")
    private val ORIGINAL_MONEY_REGEX =
        Regex(
            "^(?:(?i:RM|MYR)[ ]*)?" +
                "(?<integer>(?:0|[1-9][0-9]*)|(?:[1-9][0-9]{0,2}(?:,[0-9]{3})+))" +
                "\\.(?<fraction>[0-9]{2})$",
        )
    private val QUANTITY_REGEX = Regex("^(0|[1-9][0-9]*)(?:\\.[0-9]{1,3})?$")
    private val DATE_REGEX = Regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    private val PRIVATE_ID_MARKER_REGEX =
        Regex(
            "(?:^|[._-])(?:participant|evaluation|ground[-_]?truth|annotation|held[-_]?out)(?:$|[._-])",
            RegexOption.IGNORE_CASE,
        )

    private val URI_PATH_REASON_PATTERNS =
        listOf(
            Regex("(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*:(?=\\S)"),
            Regex(
                "(?<![A-Za-z0-9])(?:[A-Za-z]:[\\\\/]|\\\\\\\\[^\\\\/\\s]+[\\\\/][^\\\\/\\s]+|//[^/\\s]+/[^/\\s]+)",
            ),
            Regex("(?<![A-Za-z0-9])/(?!/)(?=[^\\s])(?:[^/\\s]+)(?:/[^/\\s]*)*"),
            Regex(
                "(?<![A-Za-z0-9])(?:path|file)\\s*(?:=|:)\\s*[^\\s=:]*[\\\\/][^\\s]+",
                RegexOption.IGNORE_CASE,
            ),
            Regex(
                "(?<![A-Za-z0-9])(?:\\.{1,2}[\\\\/](?=[^\\s])|" +
                    "[A-Za-z0-9._-]+\\\\[A-Za-z0-9._-]+(?:\\\\[A-Za-z0-9._-]+)*|" +
                    "[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\\.[A-Za-z0-9._-]+)",
            ),
            Regex(
                "(?<![A-Za-z0-9._-])(?=[A-Za-z0-9._-]*[A-Za-z0-9])" +
                    "[A-Za-z0-9._-]+(?:/(?=[A-Za-z0-9._-]*[A-Za-z0-9])" +
                    "[A-Za-z0-9._-]+)+(?![A-Za-z0-9._-])",
            ),
        )

    private val PROTECTED_MARKER_REGEX =
        Regex(
            "(?<![A-Za-z0-9])(?:participant|reference|ref|evaluation|annotation|" +
                "ground(?:[ _-]+)truth|held(?:[ _-]+)out)(?![A-Za-z0-9])",
        )
    private val IDENTIFIER_QUALIFIERS = listOf("id", "case")
    private val IMMEDIATE_MARKER_PUNCTUATION = setOf(':', '=', '#', '.', '_', '-')
    private val PRIVACY_DELIMITERS =
        setOf(
            0x0028,
            0x0029,
            0x005B,
            0x005D,
            0x007B,
            0x007D,
            0x0022,
            0x0027,
            0x201C,
            0x201D,
            0x2018,
            0x2019,
            0x00AB,
            0x00BB,
            0x2039,
            0x203A,
            0x002C,
            0x003B,
            0x003A,
            0x0021,
            0x003F,
        )
    private val ASYMMETRIC_WRAPPER_OPENINGS =
        mapOf(
            0x0028 to 0x0029,
            0x005B to 0x005D,
            0x007B to 0x007D,
            0x201C to 0x201D,
            0x2018 to 0x2019,
            0x00AB to 0x00BB,
            0x2039 to 0x203A,
        )
    private val ASYMMETRIC_WRAPPER_CLOSINGS = ASYMMETRIC_WRAPPER_OPENINGS.values.toSet()
    private val SYMMETRIC_PRIVACY_QUOTES = setOf(0x0022, 0x0027)
    private val PRIVACY_WRAPPERS =
        ASYMMETRIC_WRAPPER_OPENINGS.keys + ASYMMETRIC_WRAPPER_CLOSINGS + SYMMETRIC_PRIVACY_QUOTES

    private val RECEIPT_ROLE_ORDER =
        listOf(
            ReceiptFieldRole.STORE_NAME,
            ReceiptFieldRole.PURCHASE_DATE,
            ReceiptFieldRole.RECEIPT_TOTAL,
        )
    private val ITEM_ROLE_ORDER =
        listOf(
            ReceiptFieldRole.ITEM_DESCRIPTION,
            ReceiptFieldRole.QUANTITY,
            ReceiptFieldRole.UNIT_PRICE,
            ReceiptFieldRole.LINE_TOTAL,
        )
}
