package com.pantryproof.prototype.contract.v1

import java.math.BigDecimal
import java.nio.charset.StandardCharsets
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class ReceiptPresentationV1ValidatorTest {
    @Test
    fun validAvailableAndUnavailableEnvelopesAreAccepted() {
        assertAccepted(validAvailableEnvelope())
        assertAccepted(validUnavailableEnvelope())
    }

    @Test
    fun correlationSourceModeAndOpaqueIdentifiersAreEnforced() {
        assertCode(
            validAvailableEnvelope(),
            ReceiptPresentationIssueCodes.REQUEST_ID_MISMATCH,
            context = PresentationConsumerContext("request-other", IMAGE_ID, PresentationConsumerMode.FIXTURE),
        )
        assertCode(
            validAvailableEnvelope(),
            ReceiptPresentationIssueCodes.IMAGE_ID_MISMATCH,
            context = PresentationConsumerContext(REQUEST_ID, "image-other", PresentationConsumerMode.FIXTURE),
        )
        assertCode(
            validAvailableEnvelope(),
            ReceiptPresentationIssueCodes.SOURCE_MODE_MISMATCH,
            context = PresentationConsumerContext(REQUEST_ID, IMAGE_ID, PresentationConsumerMode.LIVE),
        )
        assertCode(
            validAvailableEnvelope(requestId = "request/unsafe"),
            ReceiptPresentationIssueCodes.INVALID_ID,
            context = PresentationConsumerContext("request/unsafe", IMAGE_ID, PresentationConsumerMode.FIXTURE),
        )
        assertCode(
            validAvailableEnvelope(
                source =
                    PresentationSource(
                        PresentationSourceType.SYNTHETIC_FIXTURE,
                        PresentationProvenance("M3E_ANDROID_TEST", "participant-001", null),
                    ),
            ),
            ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
        )
    }

    @Test
    fun evidenceAndFieldTokenIntegrityIsEnforced() {
        assertCode(
            validAvailableEnvelope(
                evidence = PresentationSourceEvidence(SourceProcessingStatus.OCR_COMPLETED, listOf("token-store", "token-store")),
            ),
            ReceiptPresentationIssueCodes.DUPLICATE_TOKEN_ID,
        )

        val unknownTokenStore = extractedField(
            "field-store",
            ReceiptFieldRole.STORE_NAME,
            "Kedai Sintetik",
            "Kedai Sintetik",
            listOf("token-unknown"),
        )
        assertCode(
            validAvailableEnvelope(receipt = validReceipt(storeField = unknownTokenStore)),
            ReceiptPresentationIssueCodes.UNKNOWN_TOKEN_REFERENCE,
        )

        val duplicateReferenceStore = extractedField(
            "field-store",
            ReceiptFieldRole.STORE_NAME,
            "Kedai Sintetik",
            "Kedai Sintetik",
            listOf("token-store", "token-store"),
        )
        assertCode(
            validAvailableEnvelope(receipt = validReceipt(storeField = duplicateReferenceStore)),
            ReceiptPresentationIssueCodes.DUPLICATE_TOKEN_REFERENCE,
        )
    }

    @Test
    fun fieldStatesRoleOrderAndReceiptWideIdentitiesAreEnforced() {
        val contradictory = PresentationField(
            "field-store",
            ReceiptFieldRole.STORE_NAME,
            ReceiptFieldStatus.MISSING,
            "Kedai Sintetik",
            null,
            "Store name was not available.",
            emptyList(),
            null,
        )
        assertCode(
            validAvailableEnvelope(receipt = validReceipt(storeField = contradictory)),
            ReceiptPresentationIssueCodes.CONTRADICTORY_FIELD_STATE,
        )

        val receipt = validReceipt()
        val reordered = PresentationReceipt(
            receipt.receiptId,
            receipt.currencyCode,
            listOf(receipt.receiptFields[1], receipt.receiptFields[0], receipt.receiptFields[2]),
            receipt.itemRows,
        )
        assertCode(validAvailableEnvelope(receipt = reordered), ReceiptPresentationIssueCodes.ROLE_ORDER)

        val duplicateId = extractedField(
            "field-store",
            ReceiptFieldRole.ITEM_DESCRIPTION,
            "Beras Sintetik",
            "Beras Sintetik",
            listOf("token-description"),
        )
        val duplicateIdReceipt = validReceipt(
            itemFields = validItemFields().toMutableList().also { it[0] = duplicateId },
        )
        assertCode(
            validAvailableEnvelope(receipt = duplicateIdReceipt),
            ReceiptPresentationIssueCodes.DUPLICATE_FIELD_ID,
        )
    }

    @Test
    fun exactMoneyQuantityAndGregorianDateRulesAreEnforced() {
        val weighted = extractedField(
            "field-quantity",
            ReceiptFieldRole.QUANTITY,
            "1.250",
            "1.250",
            listOf("token-quantity"),
        )
        val groupedTotal = extractedField(
            "field-total",
            ReceiptFieldRole.RECEIPT_TOTAL,
            "MYR 1,234.50",
            "1234.50",
            listOf("token-total"),
        )
        assertAccepted(
            validAvailableEnvelope(
                receipt = validReceipt(totalField = groupedTotal, itemFields = validItemFields(quantity = weighted)),
            ),
        )

        val invalidMoney = extractedField(
            "field-total",
            ReceiptFieldRole.RECEIPT_TOTAL,
            "12.345",
            "12.345",
            listOf("token-total"),
        )
        assertCode(
            validAvailableEnvelope(receipt = validReceipt(totalField = invalidMoney)),
            ReceiptPresentationIssueCodes.INVALID_MONEY,
        )

        val invalidQuantity = extractedField(
            "field-quantity",
            ReceiptFieldRole.QUANTITY,
            "1.2500",
            "1.2500",
            listOf("token-quantity"),
        )
        assertCode(
            validAvailableEnvelope(receipt = validReceipt(itemFields = validItemFields(quantity = invalidQuantity))),
            ReceiptPresentationIssueCodes.INVALID_QUANTITY,
        )

        val invalidDate = extractedField(
            "field-date",
            ReceiptFieldRole.PURCHASE_DATE,
            "2026-02-30",
            "2026-02-30",
            listOf("token-date"),
        )
        assertCode(
            validAvailableEnvelope(receipt = validReceipt(dateField = invalidDate)),
            ReceiptPresentationIssueCodes.INVALID_DATE,
        )
    }

    @Test
    fun privacyGuardRejectsApprovedUriPathAndProtectedIdentifierShapes() {
        val unsafeReasons =
            listOf(
                "file:/tmp/receipt.jpg",
                "mailto:user@example.test",
                "urn:receipt:001",
                "android.resource:com.pantryproof/raw/sample",
                "OCR:failed to recognize total.",
                "Reason:missing text.",
                "Import failed at CuStOm+V1:opaque-payload during capture.",
                "C:\\receipts\\receipt.jpg",
                "\\\\server\\share\\receipt.jpg",
                "/tmp/receipt.jpg",
                "../private/receipt.jpg",
                "receipts\\receipt.jpg",
                "path=receipts/receipt.jpg",
                "path: receipts/receipt",
                "receipts/receipt",
                "private/2026/receipt",
                "Could not read receipts/receipt during capture.",
                "A/B",
                "and/or",
                "2026/11/06",
                "Participant ID 001",
                "Participant #001",
                "Participant 001",
                "participant-id-alpha",
                "reference-id-ABC",
                "held out case 7",
                "Participant: 001",
                "Reference: ABC",
                "Annotation: sampleA",
                "Evaluation: 001",
                "Participant = 001",
                "Participant ID = 001",
                "Participant: #001",
                "participant# 001",
                "held\tout: 7",
            )
        unsafeReasons.forEach { reason ->
            assertCode(
                validAvailableEnvelope(gate = sufficientGate(listOf(reason))),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )
            assertCode(
                validAvailableEnvelope(
                    receipt = validReceipt(storeField = absentStore(ReceiptFieldStatus.MISSING, reason)),
                ),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )
            assertCode(
                validAvailableEnvelope(
                    receipt = validReceipt(dateField = absentDate(ReceiptFieldStatus.UNRESOLVED, reason)),
                ),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )
        }
    }

    @Test
    fun protectedIdentifierWhitespaceAfterPunctuationMatchesPythonR6() {
        val r6FalseAcceptRegressions =
            listOf(
                "Participant :# 001",
                "Participant ID: # 001",
                "Reference: # 001",
            )
        r6FalseAcceptRegressions.forEach { reason ->
            assertCode(
                validAvailableEnvelope(gate = sufficientGate(listOf(reason))),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )
            assertCode(
                validAvailableEnvelope(
                    receipt = validReceipt(storeField = absentStore(ReceiptFieldStatus.MISSING, reason)),
                ),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )
            assertCode(
                validAvailableEnvelope(
                    receipt = validReceipt(dateField = absentDate(ReceiptFieldStatus.UNRESOLVED, reason)),
                ),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )

            val rawResult =
                ReceiptPresentationV1Validator.decodeAndValidate(
                    insufficientJson(reason),
                    PresentationConsumerContext(
                        "request-raw-001",
                        "image-raw-001",
                        PresentationConsumerMode.FIXTURE,
                    ),
                )
            assertTrue(
                "Expected raw JSON rejection for $reason but received $rawResult",
                rawResult is ReceiptPresentationResult.Rejected,
            )
            assertEquals(
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
                (rawResult as ReceiptPresentationResult.Rejected).issue.code,
            )
        }
    }

    @Test
    fun protectedIdentifierWhitespaceBeforePunctuationMatchesPythonR6() {
        val r6FalseAcceptRegressions =
            listOf(
                "Participant - 001",
                "Reference - A12",
                "Evaluation _ case 012",
                "Participant . 001",
            )
        r6FalseAcceptRegressions.forEach { reason ->
            assertCode(
                validAvailableEnvelope(gate = sufficientGate(listOf(reason))),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )
            assertCode(
                validAvailableEnvelope(
                    receipt = validReceipt(storeField = absentStore(ReceiptFieldStatus.MISSING, reason)),
                ),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )
            assertCode(
                validAvailableEnvelope(
                    receipt = validReceipt(dateField = absentDate(ReceiptFieldStatus.UNRESOLVED, reason)),
                ),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )

            val rawResult =
                ReceiptPresentationV1Validator.decodeAndValidate(
                    insufficientJson(reason),
                    PresentationConsumerContext(
                        "request-raw-001",
                        "image-raw-001",
                        PresentationConsumerMode.FIXTURE,
                    ),
                )
            assertTrue(
                "Expected raw JSON rejection for $reason but received $rawResult",
                rawResult is ReceiptPresentationResult.Rejected,
            )
            assertEquals(
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
                (rawResult as ReceiptPresentationResult.Rejected).issue.code,
            )
        }
    }

    @Test
    fun protectedIdentifierCompoundMarkersMatchPythonR6() {
        val r6FalseAcceptRegressions =
            listOf(
                "Ref#:ID 123",
                "Reference #: id 001",
                "Reference ==id 7",
                "Reference - - evidence",
            )
        r6FalseAcceptRegressions.forEach { reason ->
            assertCode(
                validAvailableEnvelope(gate = sufficientGate(listOf(reason))),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )
            assertCode(
                validAvailableEnvelope(
                    receipt = validReceipt(storeField = absentStore(ReceiptFieldStatus.MISSING, reason)),
                ),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )
            assertCode(
                validAvailableEnvelope(
                    receipt = validReceipt(dateField = absentDate(ReceiptFieldStatus.UNRESOLVED, reason)),
                ),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )

            val rawResult =
                ReceiptPresentationV1Validator.decodeAndValidate(
                    insufficientJson(reason),
                    PresentationConsumerContext(
                        "request-raw-001",
                        "image-raw-001",
                        PresentationConsumerMode.FIXTURE,
                    ),
                )
            assertTrue(
                "Expected raw JSON rejection for $reason but received $rawResult",
                rawResult is ReceiptPresentationResult.Rejected,
            )
            assertEquals(
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
                (rawResult as ReceiptPresentationResult.Rejected).issue.code,
            )
        }
    }

    @Test
    fun protectedIdentifierPunctuationWhitespaceMatrixIsFailClosed() {
        val unsafeReasons =
            listOf(
                "Participant-001",
                "Participant -001",
                "Participant- 001",
                "Participant\t-\t001",
                "Reference.A12",
                "Reference . A12",
                "Evaluation_case_012",
                "Evaluation _ CASE 012",
                "Annotation # sampleA",
                "Ref - ABC",
                "ground truth - id 7",
                "held-out _ case 7",
                "Participant ._- case#001",
            )
        unsafeReasons.forEach { reason ->
            assertCode(
                validAvailableEnvelope(gate = sufficientGate(listOf(reason))),
                ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            )
        }

        val safeReasons =
            listOf(
                "Reference evidence was unavailable.",
                "Participant evidence was unavailable.",
                "Refresh2 attempt could not read the image.",
                "Refill2 operation failed.",
                "Refactor2 parser was unavailable.",
                "Input / output processing failed.",
                "OCR: failed to recognize total.",
            )
        safeReasons.forEach { reason ->
            assertAccepted(validAvailableEnvelope(gate = sufficientGate(listOf(reason))))
        }
    }

    @Test
    fun privacyGuardPreservesNaturalLanguageAndStatePrecedence() {
        val safeReasons =
            listOf(
                "Reference evidence was unavailable.",
                "Participant evidence was unavailable.",
                "Evaluation evidence was unavailable.",
                "Annotation evidence was unavailable.",
                "Reference number was unavailable.",
                "Refresh2 attempt could not read the image.",
                "Refill2 operation failed.",
                "Refactor2 parser was unavailable.",
                "Input / output processing failed.",
                "OCR: failed to recognize total.",
            )
        safeReasons.forEach { reason ->
            assertAccepted(validAvailableEnvelope(gate = sufficientGate(listOf(reason))))
            assertAccepted(
                validAvailableEnvelope(receipt = validReceipt(storeField = absentStore(ReceiptFieldStatus.MISSING, reason))),
            )
        }

        val unsafe = "file:///tmp/receipt.jpg"
        assertCode(
            validAvailableEnvelope(gate = sufficientGate(listOf(unsafe, unsafe))),
            ReceiptPresentationIssueCodes.GATE_STATE,
        )
        assertCode(
            validAvailableEnvelope(gate = sufficientGate(listOf("   "))),
            ReceiptPresentationIssueCodes.GATE_STATE,
        )
        val extractedWithUnsafeReason = PresentationField(
            "field-store",
            ReceiptFieldRole.STORE_NAME,
            ReceiptFieldStatus.EXTRACTED,
            "Kedai Sintetik",
            "Kedai Sintetik",
            unsafe,
            listOf("token-store"),
            null,
        )
        assertCode(
            validAvailableEnvelope(receipt = validReceipt(storeField = extractedWithUnsafeReason)),
            ReceiptPresentationIssueCodes.CONTRADICTORY_FIELD_STATE,
        )
    }

    @Test
    fun s06FourOutcomeAndFailureStageMatrixIsPreserved() {
        assertAccepted(validAvailableEnvelope(evidence = evidence(SourceProcessingStatus.RECEIVED)))
        assertAccepted(
            validAvailableEnvelope(
                evidence = evidence(SourceProcessingStatus.OCR_FAILED),
                extractionStatus = AutomaticExtractionStatus.FAILED,
            ),
        )
        assertAccepted(insufficientEnvelope(SourceProcessingStatus.RECEIVED))
        assertAccepted(insufficientEnvelope(SourceProcessingStatus.OCR_FAILED))
        assertAccepted(validUnavailableEnvelope())
        assertAccepted(technicalFailureEnvelope(PresentationFailureStage.OCR, SourceProcessingStatus.OCR_FAILED, null))
        assertAccepted(technicalFailureEnvelope(PresentationFailureStage.SOURCE_GATE, SourceProcessingStatus.OCR_COMPLETED, null))
        assertAccepted(technicalFailureEnvelope(PresentationFailureStage.EXTRACTION, SourceProcessingStatus.OCR_PARTIAL, sufficientGate()))
        assertAccepted(technicalFailureEnvelope(PresentationFailureStage.PRESENTATION_ADAPTER, SourceProcessingStatus.OCR_COMPLETED, sufficientGate()))

        assertCode(
            technicalFailureEnvelope(PresentationFailureStage.OCR, SourceProcessingStatus.RECEIVED, null),
            ReceiptPresentationIssueCodes.EVIDENCE_STAGE_MISMATCH,
        )
        assertCode(
            technicalFailureEnvelope(PresentationFailureStage.EXTRACTION, SourceProcessingStatus.OCR_FAILED, sufficientGate()),
            ReceiptPresentationIssueCodes.EVIDENCE_STAGE_MISMATCH,
        )
        assertCode(
            validAvailableEnvelope(gate = insufficientGate()),
            ReceiptPresentationIssueCodes.GATE_OUTCOME_MISMATCH,
        )
    }

    @Test
    fun automaticValuesRemainUnmodifiedAndConfidenceMustFitFiniteBinary64() {
        val envelope = validAvailableEnvelope()
        val result = ReceiptPresentationV1Validator.validate(envelope, fixtureContext())
        assertTrue(result is ReceiptPresentationResult.Accepted)
        assertSame(envelope, (result as ReceiptPresentationResult.Accepted).value)
        assertEquals(
            "RM 12.30",
            result.value.receipt!!.receiptFields[2].originalAutomaticValue,
        )

        val hugeConfidence = extractedField(
            "field-store",
            ReceiptFieldRole.STORE_NAME,
            "Kedai Sintetik",
            "Kedai Sintetik",
            listOf("token-store"),
            BigDecimal("1e10000"),
        )
        assertCode(
            validAvailableEnvelope(receipt = validReceipt(storeField = hugeConfidence)),
            ReceiptPresentationIssueCodes.INVALID_CONFIDENCE,
        )
    }

    @Test
    fun rawJsonDecodeAndValidateUsesTheSamePrivacySemantics() {
        val raw = insufficientJson("Participant ID = 001")
        val result = ReceiptPresentationV1Validator.decodeAndValidate(
            raw,
            PresentationConsumerContext("request-raw-001", "image-raw-001", PresentationConsumerMode.FIXTURE),
        )
        assertTrue(result is ReceiptPresentationResult.Rejected)
        assertEquals(
            ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            (result as ReceiptPresentationResult.Rejected).issue.code,
        )
    }

    @Test
    fun candidate02ScansCompleteProtectedMarkerTailsFailClosed() {
        val unsafeReasons =
            listOf(
                "Reference evidence A12",
                "Reference evidence (A12)",
                "Reference information 123",
                "Reference version 2",
                "Reference version \u0662",
                "Reference @note",
                "Reference @A12",
                "Reference \u201Cr\u00E9sum\u00E9\u201D",
                "Reference A12\u00E9",
                "Reference P\uFF10\uFF10\uFF11",
                "Reference (note",
                "Reference note)",
                "Reference A12,",
                "Participant (P001)",
                "The participant can review 2 options.",
                "Caf\u00E9: unavailable",
            )
        unsafeReasons.forEach(::assertUnsafeReasonAcrossEntryPoints)
    }

    @Test
    fun candidate02DelimiterWrapperAndUnsupportedPunctuationMatrixIsEnforced() {
        val unsafeReasons =
            listOf(
                "Reference A12)",
                "Reference (A12)",
                "Reference ,A12",
                "Reference ((A12))",
                "Reference A12,,",
                "Reference ([A12]),",
                "Reference \"A12\"",
                "Reference 'A12'",
                "Reference \u201CA12\u201D",
                "Reference ( A12 )",
                "Reference A12),\u201D",
                "Evaluation \"E-004\"",
                "Reference A12.",
                "Reference A12_",
                "Reference A12-",
                "Reference 123",
                "Reference ()",
                "Reference ((",
                "Reference A12/path",
                "Reference A12\\path",
                "Reference A12+",
                "Reference @@A12",
                "Reference A12+B34",
                "Reference ([note)]",
                "Reference \"note",
            )
        unsafeReasons.forEach(::assertUnsafeReasonAcrossEntryPoints)
    }

    @Test
    fun candidate02AllowsBalancedDigitFreeNaturalLanguage() {
        val safeReasons =
            listOf(
                "Reference evidence was unavailable.",
                "Reference (note)",
                "Reference note,",
                "Reference information is unavailable.",
                "The reference has been removed.",
                "Reference N_A",
                "Reference ((note))",
                "Reference \"note\"",
                "Reference ABC",
                "Reference ABC-DEF",
                "Reference identifier",
                "No participant information was retained.",
                "The participant can review the result.",
                "Imej caf\u00E9 tidak tersedia.",
            )
        safeReasons.forEach(::assertSafeReasonAcrossEntryPoints)
    }

    @Test
    fun candidate02DetectionNormalizationInvisibleAndMixedLabelsAreEnforced() {
        val unsafeReasons =
            listOf(
                "\uFF32\uFF45\uFF46\uFF45\uFF52\uFF45\uFF4E\uFF43\uFF45\uFF1A \uFF21\uFF11\uFF12",
                "Reference P00\uFF11",
                "Part\u0456cipant:001",
                "Reference evidence\u200B unavailable.",
                "Reference \u041012",
                "Reference A\u0661\u0662",
                "Reference \u0661\u0662",
                "Reference caf\u00E9",
                "Reference \u8BC1\u636E",
                "Caf\u00E9: unavailable",
            )
        unsafeReasons.forEach(::assertUnsafeReasonAcrossEntryPoints)

        val approvedWhitespaceCodePoints =
            (0x0009..0x000D).toList() +
                listOf(0x0020, 0x0085, 0x00A0, 0x1680) +
                (0x2000..0x200A).toList() +
                (0x2028..0x2029).toList() +
                listOf(0x202F, 0x205F, 0x3000)
        approvedWhitespaceCodePoints.forEach { codePoint ->
            assertUnsafeReasonAcrossEntryPoints("Reference${String(Character.toChars(codePoint))}A12")
        }

        val prohibitedInvisibleCodePoints =
            listOf(0x00AD, 0x034F, 0x061C, 0x180E) +
                (0x200B..0x200F).toList() +
                (0x202A..0x202E).toList() +
                (0x2060..0x206F).toList() +
                listOf(0xFEFF)
        prohibitedInvisibleCodePoints.forEach { codePoint ->
            assertUnsafeReasonAcrossEntryPoints("Evidence${String(Character.toChars(codePoint))} unavailable.")
        }
    }

    @Test
    fun candidate02SupportsTheExactBalancedWrapperCatalogue() {
        val balancedReasons =
            listOf(
                "Reference (note)",
                "Reference [note]",
                "Reference {note}",
                "Reference \"note\"",
                "Reference 'note'",
                "Reference \u201Cnote\u201D",
                "Reference \u2018note\u2019",
                "Reference \u00ABnote\u00BB",
                "Reference \u2039note\u203A",
            )
        balancedReasons.forEach(::assertSafeReasonAcrossEntryPoints)

        val malformedReasons =
            listOf(
                "Reference (note]",
                "Reference [note}",
                "Reference {note)",
                "Reference \u201Cnote\u2019",
                "Reference \u2018note\u201D",
                "Reference \u00ABnote\u203A",
                "Reference \u2039note\u00BB",
            )
        malformedReasons.forEach(::assertUnsafeReasonAcrossEntryPoints)
    }

    @Test
    fun candidate02PreservesGateAndFieldStatePrecedence() {
        val unsafe = "Reference A12"
        assertCode(
            validAvailableEnvelope(gate = sufficientGate(listOf(unsafe, unsafe))),
            ReceiptPresentationIssueCodes.GATE_STATE,
        )
        val contradictory =
            PresentationField(
                "field-store",
                ReceiptFieldRole.STORE_NAME,
                ReceiptFieldStatus.MISSING,
                "Kedai Sintetik",
                null,
                unsafe,
                emptyList(),
                null,
            )
        assertCode(
            validAvailableEnvelope(receipt = validReceipt(storeField = contradictory)),
            ReceiptPresentationIssueCodes.CONTRADICTORY_FIELD_STATE,
        )
    }

    private fun assertAccepted(envelope: ReceiptPresentationV1) {
        val result = ReceiptPresentationV1Validator.validate(envelope, fixtureContext(envelope))
        assertTrue("Expected acceptance but received $result", result is ReceiptPresentationResult.Accepted)
    }

    private fun assertCode(
        envelope: ReceiptPresentationV1,
        expectedCode: String,
        context: PresentationConsumerContext = fixtureContext(envelope),
    ) {
        val result = ReceiptPresentationV1Validator.validate(envelope, context)
        assertTrue("Expected $expectedCode but received $result", result is ReceiptPresentationResult.Rejected)
        assertEquals(expectedCode, (result as ReceiptPresentationResult.Rejected).issue.code)
    }

    private fun assertUnsafeReasonAcrossEntryPoints(reason: String) {
        assertCode(
            validAvailableEnvelope(gate = sufficientGate(listOf(reason))),
            ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
        )
        assertCode(
            validAvailableEnvelope(receipt = validReceipt(storeField = absentStore(ReceiptFieldStatus.MISSING, reason))),
            ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
        )
        assertCode(
            validAvailableEnvelope(receipt = validReceipt(dateField = absentDate(ReceiptFieldStatus.UNRESOLVED, reason))),
            ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
        )
        val rawResult =
            ReceiptPresentationV1Validator.decodeAndValidate(
                insufficientJson(reason),
                PresentationConsumerContext("request-raw-001", "image-raw-001", PresentationConsumerMode.FIXTURE),
            )
        assertTrue("Expected raw JSON rejection for $reason but received $rawResult", rawResult is ReceiptPresentationResult.Rejected)
        assertEquals(
            ReceiptPresentationIssueCodes.UNSAFE_PROVENANCE,
            (rawResult as ReceiptPresentationResult.Rejected).issue.code,
        )
    }

    private fun assertSafeReasonAcrossEntryPoints(reason: String) {
        assertAccepted(validAvailableEnvelope(gate = sufficientGate(listOf(reason))))
        assertAccepted(
            validAvailableEnvelope(receipt = validReceipt(storeField = absentStore(ReceiptFieldStatus.MISSING, reason))),
        )
        assertAccepted(
            validAvailableEnvelope(receipt = validReceipt(dateField = absentDate(ReceiptFieldStatus.UNRESOLVED, reason))),
        )
        val rawResult =
            ReceiptPresentationV1Validator.decodeAndValidate(
                insufficientJson(reason),
                PresentationConsumerContext("request-raw-001", "image-raw-001", PresentationConsumerMode.FIXTURE),
            )
        assertTrue("Expected raw JSON acceptance for $reason but received $rawResult", rawResult is ReceiptPresentationResult.Accepted)
    }

    private fun validAvailableEnvelope(
        requestId: String = REQUEST_ID,
        source: PresentationSource = syntheticSource(),
        evidence: PresentationSourceEvidence = evidence(SourceProcessingStatus.OCR_COMPLETED),
        gate: PresentationSourceGate = sufficientGate(),
        extractionStatus: AutomaticExtractionStatus = AutomaticExtractionStatus.PARTIAL,
        receipt: PresentationReceipt = validReceipt(),
    ): ReceiptPresentationV1 =
        ReceiptPresentationV1(
            "receipt-presentation",
            "1",
            "0",
            requestId,
            IMAGE_ID,
            source,
            PresentationOutcome(PresentationOutcomeStatus.RESULT_AVAILABLE, null),
            evidence,
            gate,
            PresentationAutomaticExtraction(
                AutomaticExtractionStage.PRE_REVIEW_AUTOMATIC,
                extractionStatus,
                PresentationProducer("producer-synthetic-001", "1.0"),
            ),
            receipt,
        )

    private fun validUnavailableEnvelope(): ReceiptPresentationV1 =
        ReceiptPresentationV1(
            "receipt-presentation",
            "1",
            "0",
            REQUEST_ID,
            IMAGE_ID,
            syntheticSource(),
            PresentationOutcome(
                PresentationOutcomeStatus.PROCESSING_UNAVAILABLE,
                PresentationFailure(PresentationFailureStage.AVAILABILITY, "PROCESSOR_NOT_AVAILABLE", false),
            ),
            null,
            null,
            null,
            null,
        )

    private fun insufficientEnvelope(status: SourceProcessingStatus): ReceiptPresentationV1 =
        ReceiptPresentationV1(
            "receipt-presentation",
            "1",
            "0",
            REQUEST_ID,
            IMAGE_ID,
            syntheticSource(),
            PresentationOutcome(PresentationOutcomeStatus.SOURCE_EVIDENCE_INSUFFICIENT, null),
            evidence(status),
            insufficientGate(),
            null,
            null,
        )

    private fun technicalFailureEnvelope(
        stage: PresentationFailureStage,
        evidenceStatus: SourceProcessingStatus?,
        gate: PresentationSourceGate?,
    ): ReceiptPresentationV1 =
        ReceiptPresentationV1(
            "receipt-presentation",
            "1",
            "0",
            REQUEST_ID,
            IMAGE_ID,
            syntheticSource(),
            PresentationOutcome(
                PresentationOutcomeStatus.PROCESSING_FAILED,
                PresentationFailure(stage, "SYNTHETIC_TECHNICAL_FAILURE", false),
            ),
            evidenceStatus?.let(::evidence),
            gate,
            null,
            null,
        )

    private fun validReceipt(
        storeField: PresentationField =
            extractedField(
                "field-store",
                ReceiptFieldRole.STORE_NAME,
                "Kedai Sintetik",
                "Kedai Sintetik",
                listOf("token-store"),
            ),
        dateField: PresentationField =
            extractedField(
                "field-date",
                ReceiptFieldRole.PURCHASE_DATE,
                "2026-11-05",
                "2026-11-05",
                listOf("token-date"),
            ),
        totalField: PresentationField =
            extractedField(
                "field-total",
                ReceiptFieldRole.RECEIPT_TOTAL,
                "RM 12.30",
                "12.30",
                listOf("token-total"),
            ),
        itemFields: List<PresentationField> = validItemFields(),
    ): PresentationReceipt =
        PresentationReceipt(
            "receipt-synthetic-001",
            "MYR",
            listOf(storeField, dateField, totalField),
            listOf(PresentationItemRow("row-001", itemFields)),
        )

    private fun validItemFields(
        quantity: PresentationField =
            extractedField(
                "field-quantity",
                ReceiptFieldRole.QUANTITY,
                "1.250",
                "1.250",
                listOf("token-quantity"),
            ),
    ): List<PresentationField> =
        listOf(
            extractedField(
                "field-description",
                ReceiptFieldRole.ITEM_DESCRIPTION,
                "Beras Sintetik",
                "Beras Sintetik",
                listOf("token-description"),
            ),
            quantity,
            PresentationField(
                "field-unit-price",
                ReceiptFieldRole.UNIT_PRICE,
                ReceiptFieldStatus.MISSING,
                null,
                null,
                "Unit price was not printed separately.",
                emptyList(),
                null,
            ),
            extractedField(
                "field-line-total",
                ReceiptFieldRole.LINE_TOTAL,
                "12.30",
                "12.30",
                listOf("token-line-total"),
            ),
        )

    private fun extractedField(
        id: String,
        role: ReceiptFieldRole,
        original: String,
        presentation: String,
        tokens: List<String>,
        confidence: BigDecimal? = BigDecimal("0.90"),
    ): PresentationField =
        PresentationField(
            id,
            role,
            ReceiptFieldStatus.EXTRACTED,
            original,
            presentation,
            null,
            tokens,
            confidence,
        )

    private fun absentStore(status: ReceiptFieldStatus, reason: String): PresentationField =
        PresentationField("field-store", ReceiptFieldRole.STORE_NAME, status, null, null, reason, emptyList(), null)

    private fun absentDate(status: ReceiptFieldStatus, reason: String): PresentationField =
        PresentationField("field-date", ReceiptFieldRole.PURCHASE_DATE, status, null, null, reason, emptyList(), null)

    private fun evidence(status: SourceProcessingStatus): PresentationSourceEvidence =
        PresentationSourceEvidence(
            status,
            listOf(
                "token-store",
                "token-date",
                "token-total",
                "token-description",
                "token-quantity",
                "token-line-total",
            ),
        )

    private fun sufficientGate(reasons: List<String> = emptyList()): PresentationSourceGate =
        PresentationSourceGate("gate-001", SourceGateDecision.SUFFICIENT, reasons)

    private fun insufficientGate(): PresentationSourceGate =
        PresentationSourceGate(
            "gate-001",
            SourceGateDecision.INSUFFICIENT,
            listOf("Synthetic source evidence was insufficient."),
        )

    private fun syntheticSource(): PresentationSource =
        PresentationSource(
            PresentationSourceType.SYNTHETIC_FIXTURE,
            PresentationProvenance("M3E_ANDROID_TEST", "source-synthetic-001", null),
        )

    private fun fixtureContext(envelope: ReceiptPresentationV1 = validAvailableEnvelope()): PresentationConsumerContext =
        PresentationConsumerContext(envelope.requestId, envelope.imageId, PresentationConsumerMode.FIXTURE)

    private fun insufficientJson(reason: String): ByteArray =
        """
        {
          "schemaName": "receipt-presentation",
          "schemaVersion": "1",
          "sourceContractVersion": "0",
          "requestId": "request-raw-001",
          "imageId": "image-raw-001",
          "source": {
            "type": "SYNTHETIC_FIXTURE",
            "provenance": {
              "sourceSystem": "M3E_ANDROID_TEST",
              "sourceReference": "source-raw-001",
              "contentSha256": null
            }
          },
          "outcome": {"status": "SOURCE_EVIDENCE_INSUFFICIENT", "failure": null},
          "sourceEvidence": {"sourceProcessingStatus": "RECEIVED", "tokenIds": []},
          "sourceGate": {"gateResultId": "gate-raw-001", "decision": "INSUFFICIENT", "reasons": ["${jsonString(reason)}"]},
          "automaticExtraction": null,
          "receipt": null
        }
        """.trimIndent().toByteArray(StandardCharsets.UTF_8)

    private fun jsonString(value: String): String =
        buildString {
            value.forEach { character ->
                when (character) {
                    '\\' -> append("\\\\")
                    '"' -> append("\\\"")
                    '\b' -> append("\\b")
                    '\u000C' -> append("\\f")
                    '\n' -> append("\\n")
                    '\r' -> append("\\r")
                    '\t' -> append("\\t")
                    else -> {
                        if (character.code < 0x20) {
                            append("\\u")
                            append(character.code.toString(16).padStart(4, '0'))
                        } else {
                            append(character)
                        }
                    }
                }
            }
        }

    private companion object {
        const val REQUEST_ID = "request-synthetic-001"
        const val IMAGE_ID = "image-synthetic-001"
    }
}
