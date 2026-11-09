package com.pantryproof.prototype.contract.v1

import com.fasterxml.jackson.core.JsonFactory
import com.fasterxml.jackson.core.JsonParseException
import com.fasterxml.jackson.core.JsonParser
import com.fasterxml.jackson.core.JsonToken
import com.fasterxml.jackson.core.StreamReadFeature
import java.io.IOException
import java.math.BigDecimal
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets

object ReceiptPresentationV1Decoder {
    private val jsonFactory: JsonFactory =
        JsonFactory.builder()
            .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
            .build()

    fun decode(rawJson: ByteArray): ReceiptPresentationResult<ReceiptPresentationV1> =
        try {
            val text = decodeUtf8(rawJson)
            jsonFactory.createParser(text).use { parser ->
                val firstToken = parser.nextToken()
                    ?: rejectPresentation(
                        ReceiptPresentationIssueCodes.INVALID_JSON,
                        "$",
                        "JSON input is empty",
                    )
                if (firstToken != JsonToken.START_OBJECT) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.INVALID_JSON,
                        "$",
                        "JSON root must be an object",
                    )
                }
                val envelope = decodeEnvelopeValue(readValue(parser, "$"))
                if (parser.nextToken() != null) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.INVALID_JSON,
                        "$",
                        "trailing content after the presentation envelope",
                    )
                }
                ReceiptPresentationResult.Accepted(envelope)
            }
        } catch (violation: ReceiptPresentationViolation) {
            ReceiptPresentationResult.Rejected(violation.issue)
        } catch (error: JsonParseException) {
            ReceiptPresentationResult.Rejected(parserIssue(error))
        } catch (error: IOException) {
            ReceiptPresentationResult.Rejected(
                ReceiptPresentationIssue(
                    ReceiptPresentationIssueCodes.INVALID_JSON,
                    "$",
                    "JSON parser failure: ${error.message ?: error.javaClass.simpleName}",
                ),
            )
        }

    /**
     * Decodes one envelope object from a parser currently positioned at its
     * START_OBJECT token. This is intentionally internal so the fixture test
     * harness can preserve duplicate keys in the nested envelope without
     * making the test-only wrapper part of the production contract.
     */
    internal fun decodeCurrentEnvelope(
        parser: JsonParser,
    ): ReceiptPresentationResult<ReceiptPresentationV1> =
        try {
            if (parser.currentToken != JsonToken.START_OBJECT) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.INVALID_JSON,
                    "$",
                    "presentation envelope must start with an object",
                )
            }
            ReceiptPresentationResult.Accepted(decodeEnvelopeValue(readValue(parser, "$")))
        } catch (violation: ReceiptPresentationViolation) {
            ReceiptPresentationResult.Rejected(violation.issue)
        } catch (error: JsonParseException) {
            ReceiptPresentationResult.Rejected(parserIssue(error))
        } catch (error: IOException) {
            ReceiptPresentationResult.Rejected(
                ReceiptPresentationIssue(
                    ReceiptPresentationIssueCodes.INVALID_JSON,
                    "$",
                    "JSON parser failure: ${error.message ?: error.javaClass.simpleName}",
                ),
            )
        }

    private fun decodeUtf8(rawJson: ByteArray): String {
        if (
            rawJson.size >= 3 &&
            rawJson[0] == 0xEF.toByte() &&
            rawJson[1] == 0xBB.toByte() &&
            rawJson[2] == 0xBF.toByte()
        ) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_JSON,
                "$",
                "UTF-8 BOM is forbidden",
            )
        }
        return try {
            StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(rawJson))
                .toString()
        } catch (error: Exception) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_JSON,
                "$",
                "input is not strict UTF-8: ${error.message ?: error.javaClass.simpleName}",
            )
        }
    }

    private fun readValue(parser: JsonParser, path: String): JsonValue =
        when (parser.currentToken) {
            JsonToken.START_OBJECT -> readObject(parser, path)
            JsonToken.START_ARRAY -> readArray(parser, path)
            JsonToken.VALUE_STRING -> JsonString(requireUnicodeScalar(parser.text, path))
            JsonToken.VALUE_NUMBER_INT,
            JsonToken.VALUE_NUMBER_FLOAT,
            -> {
                val rawNumber = parser.text
                val decimal = try {
                    BigDecimal(rawNumber)
                } catch (error: NumberFormatException) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.INVALID_JSON,
                        path,
                        "invalid JSON number",
                    )
                }
                JsonNumber(decimal)
            }
            JsonToken.VALUE_TRUE -> JsonBoolean(true)
            JsonToken.VALUE_FALSE -> JsonBoolean(false)
            JsonToken.VALUE_NULL -> JsonNull
            else -> rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_JSON,
                path,
                "unexpected JSON token ${parser.currentToken}",
            )
        }

    private fun readObject(parser: JsonParser, path: String): JsonObject {
        val members = linkedMapOf<String, JsonValue>()
        while (true) {
            val token = parser.nextToken()
                ?: rejectPresentation(
                    ReceiptPresentationIssueCodes.INVALID_JSON,
                    path,
                    "unterminated JSON object",
                )
            if (token == JsonToken.END_OBJECT) {
                return JsonObject(members)
            }
            if (token != JsonToken.FIELD_NAME) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.INVALID_JSON,
                    path,
                    "expected an object member name",
                )
            }
            val name = requireUnicodeScalar(parser.currentName(), path)
            if (members.containsKey(name)) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.DUPLICATE_JSON_KEY,
                    path,
                    "duplicate object member '$name'",
                )
            }
            val valueToken = parser.nextToken()
                ?: rejectPresentation(
                    ReceiptPresentationIssueCodes.INVALID_JSON,
                    "$path.$name",
                    "missing object member value",
                )
            if (valueToken == JsonToken.FIELD_NAME || valueToken == JsonToken.END_OBJECT) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.INVALID_JSON,
                    "$path.$name",
                    "missing object member value",
                )
            }
            members[name] = readValue(parser, "$path.$name")
        }
    }

    private fun readArray(parser: JsonParser, path: String): JsonArray {
        val values = mutableListOf<JsonValue>()
        while (true) {
            val token = parser.nextToken()
                ?: rejectPresentation(
                    ReceiptPresentationIssueCodes.INVALID_JSON,
                    path,
                    "unterminated JSON array",
                )
            if (token == JsonToken.END_ARRAY) {
                return JsonArray(values.toList())
            }
            values += readValue(parser, "$path[${values.size}]")
        }
    }

    private fun decodeEnvelopeValue(value: JsonValue): ReceiptPresentationV1 {
        val rootObject = value.asObject("$")
        for (member in listOf("schemaName", "schemaVersion", "sourceContractVersion")) {
            if (!rootObject.members.containsKey(member)) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.MISSING_MEMBER,
                    "$",
                    "missing member '$member'",
                )
            }
        }
        val schemaName = rootObject.required("schemaName").asString("$.schemaName")
        val schemaVersion = rootObject.required("schemaVersion").asString("$.schemaVersion")
        val sourceContractVersion =
            rootObject.required("sourceContractVersion").asString("$.sourceContractVersion")
        if (schemaName != "receipt-presentation" || schemaVersion != "1") {
            rejectPresentation(
                ReceiptPresentationIssueCodes.UNSUPPORTED_SCHEMA_VERSION,
                "$.schemaVersion",
                "unsupported receipt-presentation schema identity/version",
            )
        }
        if (sourceContractVersion != "0") {
            rejectPresentation(
                ReceiptPresentationIssueCodes.UNSUPPORTED_CONTRACT_VERSION,
                "$.sourceContractVersion",
                "unsupported source contract version",
            )
        }
        rootObject.requireExactMembers("$", TOP_MEMBERS)

        return ReceiptPresentationV1(
            schemaName = schemaName,
            schemaVersion = schemaVersion,
            sourceContractVersion = sourceContractVersion,
            requestId = rootObject.required("requestId").asString("$.requestId"),
            imageId = rootObject.required("imageId").asString("$.imageId"),
            source = decodeSource(rootObject.required("source"), "$.source"),
            outcome = decodeOutcome(rootObject.required("outcome"), "$.outcome"),
            sourceEvidence = rootObject.required("sourceEvidence").nullableObject {
                decodeEvidence(it, "$.sourceEvidence")
            },
            sourceGate = rootObject.required("sourceGate").nullableObject {
                decodeGate(it, "$.sourceGate")
            },
            automaticExtraction = rootObject.required("automaticExtraction").nullableObject {
                decodeExtraction(it, "$.automaticExtraction")
            },
            receipt = rootObject.required("receipt").nullableObject {
                decodeReceipt(it, "$.receipt")
            },
        )
    }

    private fun decodeSource(value: JsonValue, path: String): PresentationSource {
        val source = value.asObject(path).withExactMembers(path, SOURCE_MEMBERS)
        return PresentationSource(
            type = source.required("type").asEnum(path("$path", "type")),
            provenance = decodeProvenance(source.required("provenance"), "$path.provenance"),
        )
    }

    private fun decodeProvenance(value: JsonValue, path: String): PresentationProvenance {
        val provenance = value.asObject(path).withExactMembers(path, PROVENANCE_MEMBERS)
        return PresentationProvenance(
            sourceSystem = provenance.required("sourceSystem").asString("$path.sourceSystem"),
            sourceReference =
                provenance.required("sourceReference").asString("$path.sourceReference"),
            contentSha256 =
                provenance.required("contentSha256").asNullableString("$path.contentSha256"),
        )
    }

    private fun decodeOutcome(value: JsonValue, path: String): PresentationOutcome {
        val outcome = value.asObject(path).withExactMembers(path, OUTCOME_MEMBERS)
        return PresentationOutcome(
            status = outcome.required("status").asEnum("$path.status"),
            failure = outcome.required("failure").nullableObject {
                decodeFailure(it, "$path.failure")
            },
        )
    }

    private fun decodeFailure(value: JsonValue, path: String): PresentationFailure {
        val failure = value.asObject(path).withExactMembers(path, FAILURE_MEMBERS)
        return PresentationFailure(
            stage = failure.required("stage").asEnum("$path.stage"),
            code = failure.required("code").asString("$path.code"),
            retryable = failure.required("retryable").asBoolean("$path.retryable"),
        )
    }

    private fun decodeEvidence(value: JsonValue, path: String): PresentationSourceEvidence {
        val evidence = value.asObject(path).withExactMembers(path, EVIDENCE_MEMBERS)
        return PresentationSourceEvidence(
            sourceProcessingStatus =
                evidence.required("sourceProcessingStatus")
                    .asEnum("$path.sourceProcessingStatus"),
            tokenIds = evidence.required("tokenIds").asStringList("$path.tokenIds"),
        )
    }

    private fun decodeGate(value: JsonValue, path: String): PresentationSourceGate {
        val gate = value.asObject(path).withExactMembers(path, GATE_MEMBERS)
        return PresentationSourceGate(
            gateResultId = gate.required("gateResultId").asString("$path.gateResultId"),
            decision = gate.required("decision").asEnum("$path.decision"),
            reasons = gate.required("reasons").asStringList("$path.reasons"),
        )
    }

    private fun decodeExtraction(
        value: JsonValue,
        path: String,
    ): PresentationAutomaticExtraction {
        val extraction = value.asObject(path).withExactMembers(path, EXTRACTION_MEMBERS)
        return PresentationAutomaticExtraction(
            stage = extraction.required("stage").asEnum("$path.stage"),
            extractionStatus =
                extraction.required("extractionStatus").asEnum("$path.extractionStatus"),
            producer = decodeProducer(extraction.required("producer"), "$path.producer"),
        )
    }

    private fun decodeProducer(value: JsonValue, path: String): PresentationProducer {
        val producer = value.asObject(path)
        if (!producer.members.containsKey("producerVersion")) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.PRODUCER_METADATA,
                path,
                "producerVersion is required",
            )
        }
        producer.requireExactMembers(path, PRODUCER_MEMBERS)
        return PresentationProducer(
            producerId = producer.required("producerId").asString("$path.producerId"),
            producerVersion =
                producer.required("producerVersion").asString("$path.producerVersion"),
        )
    }

    private fun decodeReceipt(value: JsonValue, path: String): PresentationReceipt {
        val receipt = value.asObject(path)
        if (!receipt.members.containsKey("currencyCode")) {
            rejectPresentation(
                ReceiptPresentationIssueCodes.CURRENCY_METADATA,
                path,
                "available receipt requires currencyCode",
            )
        }
        receipt.requireExactMembers(path, RECEIPT_MEMBERS)
        return PresentationReceipt(
            receiptId = receipt.required("receiptId").asString("$path.receiptId"),
            currencyCode = receipt.required("currencyCode").asString("$path.currencyCode"),
            receiptFields =
                receipt.required("receiptFields").asArray("$path.receiptFields").values
                    .mapIndexed { index, field ->
                        decodeField(field, "$path.receiptFields[$index]")
                    },
            itemRows =
                receipt.required("itemRows").asArray("$path.itemRows").values
                    .mapIndexed { index, row -> decodeRow(row, "$path.itemRows[$index]") },
        )
    }

    private fun decodeRow(value: JsonValue, path: String): PresentationItemRow {
        val row = value.asObject(path).withExactMembers(path, ROW_MEMBERS)
        return PresentationItemRow(
            rowId = row.required("rowId").asString("$path.rowId"),
            fields =
                row.required("fields").asArray("$path.fields").values
                    .mapIndexed { index, field -> decodeField(field, "$path.fields[$index]") },
        )
    }

    private fun decodeField(value: JsonValue, path: String): PresentationField {
        val field = value.asObject(path).withExactMembers(path, FIELD_MEMBERS)
        return PresentationField(
            fieldId = field.required("fieldId").asString("$path.fieldId"),
            role = field.required("role").asEnum("$path.role", ReceiptPresentationIssueCodes.UNKNOWN_ROLE),
            status = field.required("status").asEnum("$path.status"),
            originalAutomaticValue =
                field.required("originalAutomaticValue")
                    .asNullableString("$path.originalAutomaticValue"),
            presentationValue =
                field.required("presentationValue").asNullableString("$path.presentationValue"),
            absenceReason =
                field.required("absenceReason").asNullableString("$path.absenceReason"),
            sourceTokenIds =
                field.required("sourceTokenIds").asStringList("$path.sourceTokenIds"),
            nativeConfidence =
                field.required("nativeConfidence").asNullableNumber("$path.nativeConfidence"),
        )
    }

    private fun parserIssue(error: JsonParseException): ReceiptPresentationIssue {
        val message = error.originalMessage ?: error.message ?: "malformed JSON"
        val duplicate = message.contains("duplicate field", ignoreCase = true)
        return ReceiptPresentationIssue(
            if (duplicate) {
                ReceiptPresentationIssueCodes.DUPLICATE_JSON_KEY
            } else {
                ReceiptPresentationIssueCodes.INVALID_JSON
            },
            "$",
            message,
        )
    }

    private fun requireUnicodeScalar(value: String, path: String): String {
        var index = 0
        while (index < value.length) {
            val character = value[index]
            if (character.isHighSurrogate()) {
                if (index + 1 >= value.length || !value[index + 1].isLowSurrogate()) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.INVALID_JSON,
                        path,
                        "unpaired high surrogate",
                    )
                }
                index += 2
                continue
            }
            if (character.isLowSurrogate()) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.INVALID_JSON,
                    path,
                    "unpaired low surrogate",
                )
            }
            index += 1
        }
        return value
    }

    private fun path(parent: String, member: String): String = "$parent.$member"

    private sealed interface JsonValue

    private data class JsonObject(val members: Map<String, JsonValue>) : JsonValue {
        fun required(name: String): JsonValue =
            members[name]
                ?: rejectPresentation(
                    ReceiptPresentationIssueCodes.MISSING_MEMBER,
                    "$",
                    "missing member '$name'",
                )

        fun requireExactMembers(path: String, expected: List<String>) {
            for (member in expected) {
                if (!members.containsKey(member)) {
                    rejectPresentation(
                        ReceiptPresentationIssueCodes.MISSING_MEMBER,
                        path,
                        "missing member '$member'",
                    )
                }
            }
            val unknown = (members.keys - expected.toSet()).sorted().firstOrNull()
            if (unknown != null) {
                rejectPresentation(
                    ReceiptPresentationIssueCodes.UNKNOWN_MEMBER,
                    path,
                    "unknown member '$unknown'",
                )
            }
        }

        fun withExactMembers(path: String, expected: List<String>): JsonObject {
            requireExactMembers(path, expected)
            return this
        }
    }

    private data class JsonArray(val values: List<JsonValue>) : JsonValue

    private data class JsonString(val value: String) : JsonValue

    private data class JsonNumber(val value: BigDecimal) : JsonValue

    private data class JsonBoolean(val value: Boolean) : JsonValue

    private data object JsonNull : JsonValue

    private fun JsonValue.asObject(path: String): JsonObject =
        this as? JsonObject
            ?: rejectPresentation(ReceiptPresentationIssueCodes.INVALID_JSON, path, "expected object")

    private fun JsonValue.asArray(path: String): JsonArray =
        this as? JsonArray
            ?: rejectPresentation(ReceiptPresentationIssueCodes.INVALID_JSON, path, "expected array")

    private fun JsonValue.asString(path: String): String =
        (this as? JsonString)?.value
            ?: rejectPresentation(ReceiptPresentationIssueCodes.INVALID_JSON, path, "expected string")

    private fun JsonValue.asNullableString(path: String): String? =
        when (this) {
            JsonNull -> null
            is JsonString -> value
            else -> rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_JSON,
                path,
                "expected string or null",
            )
        }

    private fun JsonValue.asNullableNumber(path: String): BigDecimal? =
        when (this) {
            JsonNull -> null
            is JsonNumber -> value
            else -> rejectPresentation(
                ReceiptPresentationIssueCodes.INVALID_CONFIDENCE,
                path,
                "confidence must be a JSON number or null",
            )
        }

    private fun JsonValue.asBoolean(path: String): Boolean =
        (this as? JsonBoolean)?.value
            ?: rejectPresentation(ReceiptPresentationIssueCodes.INVALID_JSON, path, "expected boolean")

    private fun JsonValue.asStringList(path: String): List<String> =
        asArray(path).values.mapIndexed { index, value -> value.asString("$path[$index]") }

    private inline fun <T> JsonValue.nullableObject(block: (JsonValue) -> T): T? =
        if (this === JsonNull) null else block(this)

    private inline fun <reified T : Enum<T>> JsonValue.asEnum(
        path: String,
        code: String = ReceiptPresentationIssueCodes.UNKNOWN_ENUM,
    ): T {
        val raw = asString(path)
        return enumValues<T>().firstOrNull { it.name == raw }
            ?: rejectPresentation(code, path, "unknown enum value '$raw'")
    }

    private val TOP_MEMBERS =
        listOf(
            "schemaName",
            "schemaVersion",
            "sourceContractVersion",
            "requestId",
            "imageId",
            "source",
            "outcome",
            "sourceEvidence",
            "sourceGate",
            "automaticExtraction",
            "receipt",
        )
    private val SOURCE_MEMBERS = listOf("type", "provenance")
    private val PROVENANCE_MEMBERS = listOf("sourceSystem", "sourceReference", "contentSha256")
    private val OUTCOME_MEMBERS = listOf("status", "failure")
    private val FAILURE_MEMBERS = listOf("stage", "code", "retryable")
    private val EVIDENCE_MEMBERS = listOf("sourceProcessingStatus", "tokenIds")
    private val GATE_MEMBERS = listOf("gateResultId", "decision", "reasons")
    private val EXTRACTION_MEMBERS = listOf("stage", "extractionStatus", "producer")
    private val PRODUCER_MEMBERS = listOf("producerId", "producerVersion")
    private val RECEIPT_MEMBERS = listOf("receiptId", "currencyCode", "receiptFields", "itemRows")
    private val ROW_MEMBERS = listOf("rowId", "fields")
    private val FIELD_MEMBERS =
        listOf(
            "fieldId",
            "role",
            "status",
            "originalAutomaticValue",
            "presentationValue",
            "absenceReason",
            "sourceTokenIds",
            "nativeConfidence",
        )
}
