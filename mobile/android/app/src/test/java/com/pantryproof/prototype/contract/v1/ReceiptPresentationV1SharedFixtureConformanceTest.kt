package com.pantryproof.prototype.contract.v1

import com.fasterxml.jackson.core.JsonFactory
import com.fasterxml.jackson.core.JsonGenerator
import com.fasterxml.jackson.core.JsonParser
import com.fasterxml.jackson.core.JsonToken
import com.fasterxml.jackson.core.StreamReadFeature
import java.io.ByteArrayOutputStream
import java.lang.reflect.Modifier
import java.math.BigDecimal
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.nio.file.StandardOpenOption
import java.security.MessageDigest
import java.util.stream.Collectors
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class ReceiptPresentationV1SharedFixtureConformanceTest {
    @Test
    fun canonicalSharedFixturesMatchManifestHashesAndExpectedOutcomes() {
        dtoFields.forEach { (type, names) ->
            assertEquals("DTO inventory for ${type.simpleName}", names.toSet(), declaredFields(type).keys)
            assertEquals(names.size, names.toSet().size)
        }
        enumTokens.forEach { (type, tokens) ->
            val constants = requireNotNull(type.enumConstants)
            assertEquals("enum inventory for ${type.simpleName}", tokens.toSet(), constants.map { it.name }.toSet())
        }
        val rows = mutableListOf<Map<String, Any?>>()
        val fixtureRoot = locateFixtureRoot()
        val manifestPath = fixtureRoot.resolve("manifest.json")
        val manifestBytes = Files.readAllBytes(manifestPath)
        assertEquals(MANIFEST_SHA256, sha256(manifestBytes))
        val manifest = parseManifest(manifestBytes)

        assertEquals("receipt-presentation-v1-conformance-fixtures", manifest.schemaName)
        assertEquals("1", manifest.schemaVersion)
        assertEquals(32, manifest.fixtureCount)
        assertEquals(17, manifest.acceptCount)
        assertEquals(15, manifest.rejectCount)
        assertEquals(manifest.fixtureCount, manifest.entries.size)

        val manifestPaths = manifest.entries.map { it.path }
        assertEquals("manifest contains duplicate fixture paths", manifestPaths.size, manifestPaths.toSet().size)
        manifestPaths.forEach { path ->
            assertTrue("unsafe or unexpected fixture path $path", FIXTURE_PATH_REGEX.matches(path))
            val resolved = fixtureRoot.resolve(path).normalize()
            assertTrue("fixture escaped its canonical directory: $path", resolved.startsWith(fixtureRoot.resolve("fixtures")))
        }

        val diskPaths = Files.walk(fixtureRoot.resolve("fixtures")).use { paths ->
            paths
                .filter { Files.isRegularFile(it) && it.fileName.toString().endsWith(".json") }
                .map { fixtureRoot.relativize(it).toString().replace('\\', '/') }
                .collect(Collectors.toSet())
        }
        assertEquals(manifestPaths.toSet(), diskPaths)

        var executed = 0
        var accepted = 0
        var rejected = 0
        manifest.entries.forEach { entry ->
            val fixturePath = fixtureRoot.resolve(entry.path)
            val rawFixture = Files.readAllBytes(fixturePath)
            assertEquals("byte length mismatch for ${entry.path}", entry.byteLength, rawFixture.size)
            assertEquals("SHA-256 mismatch for ${entry.path}", entry.sha256, sha256(rawFixture))

            val span = envelopeSpan(rawFixture)
            val rawEnvelope = rawFixture.copyOfRange(span.first, span.second)
            val wrapper = parseWrapperMetadata(rawFixture.copyOfRange(0, span.first) +
                "{}".toByteArray() + rawFixture.copyOfRange(span.second, rawFixture.size))
            assertEquals("manifest/wrapper expectation mismatch for ${entry.path}", entry.expectedResult, wrapper.expectedResult)

            val id = entry.path.substringAfterLast('/').substringBefore('-')
            val context = if (id == "38") {
                assertEquals(188 to 947, span)
                assertEquals(ENVELOPE_38_SHA, sha256(rawEnvelope))
                evidenceDir()?.let { Files.write(it.resolve("fixture-38-kotlin.bin"), rawEnvelope, StandardOpenOption.CREATE_NEW) }
                PresentationConsumerContext("request-duplicate-json-key-001",
                    "image-duplicate-json-key-001", PresentationConsumerMode.FIXTURE)
            } else wrapper.context?.toProductionContext() ?: fixtureContext(readObject(rawEnvelope))
            val result = ReceiptPresentationV1Validator.decodeAndValidate(rawEnvelope, context)
            val actual = when (result) {
                is ReceiptPresentationResult.Accepted -> "ACCEPT"
                is ReceiptPresentationResult.Rejected -> {
                    requiredPaths[id]?.let { assertEquals("${entry.path} diagnostic path", it, result.issue.path) }
                    result.issue.code
                }
            }
            rows += mapOf(
                "fixtureId" to entry.path, "fixtureSha256" to entry.sha256,
                "fixtureGitBlob" to digest("SHA-1", "blob ${rawFixture.size}\u0000".toByteArray() + rawFixture),
                "envelopeSha256" to sha256(rawEnvelope),
                "context" to mapOf("expectedRequestId" to context.expectedRequestId,
                    "expectedImageId" to context.expectedImageId, "mode" to context.mode.name),
            ) + resultRecord(result)
            assertEquals("conformance mismatch for ${entry.path}", entry.expectedResult, actual)
            executed += 1
            if (actual == "ACCEPT") accepted += 1 else rejected += 1
        }

        assertTrue("zero canonical fixtures executed", executed > 0)
        assertEquals(32, executed)
        assertEquals(17, accepted)
        assertEquals(15, rejected)
        evidenceDir()?.let { directory ->
            val jsonl = rows.joinToString(separator = "\n", postfix = "\n") { String(jsonBytes(it), StandardCharsets.UTF_8) }
            Files.write(directory.resolve("kotlin.jsonl"), jsonl.toByteArray(StandardCharsets.UTF_8), StandardOpenOption.CREATE_NEW)
        }
    }

    private fun locateFixtureRoot(): Path {
        var current: Path? = Paths.get(System.getProperty("user.dir")).toAbsolutePath().normalize()
        while (current != null) {
            val candidate = current.resolve("tests/fixtures/receipt_presentation_v1/v1")
            if (Files.isRegularFile(candidate.resolve("manifest.json"))) {
                return candidate
            }
            current = current.parent
        }
        fail("could not locate tests/fixtures/receipt_presentation_v1/v1 from ${System.getProperty("user.dir")}")
        throw AssertionError("unreachable")
    }

    private fun parseManifest(raw: ByteArray): FixtureManifest {
        strictFactory.createParser(strictUtf8(raw)).use { parser ->
            expect(parser.nextToken(), JsonToken.START_OBJECT, "manifest root")
            val seen = linkedSetOf<String>()
            var schemaName: String? = null
            var schemaVersion: String? = null
            var fixtureCount: Int? = null
            var acceptCount: Int? = null
            var rejectCount: Int? = null
            var entries: List<FixtureEntry>? = null
            while (parser.nextToken() != JsonToken.END_OBJECT) {
                expect(parser.currentToken, JsonToken.FIELD_NAME, "manifest member")
                val name = parser.currentName()
                assertTrue("duplicate manifest member $name", seen.add(name))
                val valueToken = parser.nextToken()
                when (name) {
                    "schemaName" -> schemaName = readString(parser, valueToken, "manifest.schemaName")
                    "schemaVersion" -> schemaVersion = readString(parser, valueToken, "manifest.schemaVersion")
                    "fixtureCount" -> fixtureCount = readInt(parser, valueToken, "manifest.fixtureCount")
                    "acceptCount" -> acceptCount = readInt(parser, valueToken, "manifest.acceptCount")
                    "rejectCount" -> rejectCount = readInt(parser, valueToken, "manifest.rejectCount")
                    "fixtures" -> entries = parseManifestEntries(parser, valueToken)
                    else -> fail("unknown manifest member $name")
                }
            }
            assertEquals(MANIFEST_MEMBERS, seen)
            assertEquals(null, parser.nextToken())
            return FixtureManifest(
                assertNotNullValue(schemaName, "manifest.schemaName"),
                assertNotNullValue(schemaVersion, "manifest.schemaVersion"),
                assertNotNullValue(fixtureCount, "manifest.fixtureCount"),
                assertNotNullValue(acceptCount, "manifest.acceptCount"),
                assertNotNullValue(rejectCount, "manifest.rejectCount"),
                assertNotNullValue(entries, "manifest.fixtures"),
            )
        }
    }

    private fun parseManifestEntries(parser: JsonParser, token: JsonToken?): List<FixtureEntry> {
        expect(token, JsonToken.START_ARRAY, "manifest.fixtures")
        val entries = mutableListOf<FixtureEntry>()
        while (parser.nextToken() != JsonToken.END_ARRAY) {
            expect(parser.currentToken, JsonToken.START_OBJECT, "manifest fixture entry")
            entries += parseManifestEntry(parser)
        }
        return entries
    }

    private fun parseManifestEntry(parser: JsonParser): FixtureEntry {
        val seen = linkedSetOf<String>()
        var path: String? = null
        var expectedResult: String? = null
        var decisionIds: List<String>? = null
        var hash: String? = null
        var byteLength: Int? = null
        var sourceClassification: String? = null
        while (parser.nextToken() != JsonToken.END_OBJECT) {
            expect(parser.currentToken, JsonToken.FIELD_NAME, "manifest fixture member")
            val name = parser.currentName()
            assertTrue("duplicate manifest fixture member $name", seen.add(name))
            val valueToken = parser.nextToken()
            when (name) {
                "path" -> path = readString(parser, valueToken, "manifest fixture path")
                "expectedResult" -> expectedResult = readString(parser, valueToken, "manifest expected result")
                "decisionIds" -> decisionIds = readStringArray(parser, valueToken, "manifest decision IDs")
                "sha256" -> hash = readString(parser, valueToken, "manifest fixture hash")
                "byteLength" -> byteLength = readInt(parser, valueToken, "manifest fixture length")
                "sourceClassification" -> sourceClassification = readString(parser, valueToken, "manifest source classification")
                else -> fail("unknown manifest fixture member $name")
            }
        }
        assertEquals(ENTRY_MEMBERS, seen)
        val ids = assertNotNullValue(decisionIds, "manifest decision IDs")
        assertTrue("manifest decision IDs must not be empty", ids.isNotEmpty())
        assertEquals("duplicate decision IDs", ids.size, ids.toSet().size)
        ids.forEach { assertTrue("blank decision ID", it.isNotBlank()) }
        val expected = assertNotNullValue(expectedResult, "manifest expected result")
        assertTrue("invalid expected result $expected", EXPECTED_RESULT_REGEX.matches(expected))
        val digest = assertNotNullValue(hash, "manifest fixture hash")
        assertTrue("invalid fixture SHA-256 $digest", SHA256_REGEX.matches(digest))
        val classification = assertNotNullValue(sourceClassification, "manifest source classification")
        assertTrue("blank source classification", classification.isNotBlank())
        return FixtureEntry(
            assertNotNullValue(path, "manifest fixture path"),
            expected,
            ids,
            digest,
            assertNotNullValue(byteLength, "manifest fixture length"),
            classification,
        )
    }

    /**
     * Validates the test-only wrapper in a separate pass. Duplicate detection
     * inside `envelope` is deliberately left to the production decoder in the
     * second pass, so fixture 38 cannot be normalized away by the harness.
     */
    private fun parseWrapperMetadata(raw: ByteArray): FixtureWrapper {
        wrapperFactory.createParser(strictUtf8(raw)).use { parser ->
            expect(parser.nextToken(), JsonToken.START_OBJECT, "fixture wrapper root")
            val seen = linkedSetOf<String>()
            var fixtureStatus: String? = null
            var scenario: String? = null
            var expectedResult: String? = null
            var context: FixtureConsumerContext? = null
            var consumerContextSeen = false
            var envelopeSeen = false
            while (parser.nextToken() != JsonToken.END_OBJECT) {
                expect(parser.currentToken, JsonToken.FIELD_NAME, "fixture wrapper member")
                val name = parser.currentName()
                assertTrue("duplicate fixture wrapper member $name", seen.add(name))
                val token = parser.nextToken()
                when (name) {
                    "fixtureStatus" -> fixtureStatus = readString(parser, token, "fixtureStatus")
                    "scenario" -> scenario = readString(parser, token, "scenario")
                    "expectedResult" -> expectedResult = readString(parser, token, "expectedResult")
                    "consumerContext" -> {
                        consumerContextSeen = true
                        context = if (token == JsonToken.VALUE_NULL) null else parseConsumerContext(parser, token)
                    }
                    "envelope" -> {
                        expect(token, JsonToken.START_OBJECT, "fixture envelope")
                        envelopeSeen = true
                        parser.skipChildren()
                    }
                    else -> fail("unknown fixture wrapper member $name")
                }
            }
            assertTrue("fixture wrapper contains trailing JSON", parser.nextToken() == null)
            assertTrue("fixture wrapper omitted envelope", envelopeSeen)
            assertTrue("fixture wrapper omitted fixtureStatus", seen.contains("fixtureStatus"))
            assertTrue("fixture wrapper omitted scenario", seen.contains("scenario"))
            assertTrue("fixture wrapper omitted expectedResult", seen.contains("expectedResult"))
            assertTrue("fixture wrapper contains unknown required-member shape", seen == REQUIRED_WRAPPER_MEMBERS || seen == ALL_WRAPPER_MEMBERS)
            assertEquals(FIXTURE_STATUS, fixtureStatus)
            assertTrue("blank fixture scenario", assertNotNullValue(scenario, "fixture scenario").isNotBlank())
            val expected = assertNotNullValue(expectedResult, "fixture expected result")
            assertTrue("invalid fixture expected result", EXPECTED_RESULT_REGEX.matches(expected))
            if (!consumerContextSeen) {
                context = null
            }
            return FixtureWrapper(expected, context)
        }
    }

    private fun parseConsumerContext(parser: JsonParser, token: JsonToken?): FixtureConsumerContext {
        expect(token, JsonToken.START_OBJECT, "consumerContext")
        val seen = linkedSetOf<String>()
        var requestId: String? = null
        var imageId: String? = null
        var mode: String? = null
        while (parser.nextToken() != JsonToken.END_OBJECT) {
            expect(parser.currentToken, JsonToken.FIELD_NAME, "consumerContext member")
            val name = parser.currentName()
            assertTrue("duplicate consumerContext member $name", seen.add(name))
            val valueToken = parser.nextToken()
            when (name) {
                "expectedRequestId" -> requestId = readString(parser, valueToken, "consumerContext.expectedRequestId")
                "expectedImageId" -> imageId = readString(parser, valueToken, "consumerContext.expectedImageId")
                "mode" -> mode = readString(parser, valueToken, "consumerContext.mode")
                else -> fail("unknown consumerContext member $name")
            }
        }
        assertEquals(CONTEXT_MEMBERS, seen)
        return FixtureConsumerContext(
            assertNotNullValue(requestId, "consumerContext.expectedRequestId"),
            assertNotNullValue(imageId, "consumerContext.expectedImageId"),
            assertNotNullValue(mode, "consumerContext.mode"),
        )
    }


    private val dtoFields = mapOf(
        ReceiptPresentationV1::class.java to "schemaName schemaVersion sourceContractVersion requestId imageId source outcome sourceEvidence sourceGate automaticExtraction receipt".split(' '),
        PresentationSource::class.java to "type provenance".split(' '),
        PresentationProvenance::class.java to "sourceSystem sourceReference contentSha256".split(' '),
        PresentationOutcome::class.java to "status failure".split(' '),
        PresentationFailure::class.java to "stage code retryable".split(' '),
        PresentationSourceEvidence::class.java to "sourceProcessingStatus tokenIds".split(' '),
        PresentationSourceGate::class.java to "gateResultId decision reasons".split(' '),
        PresentationAutomaticExtraction::class.java to "stage extractionStatus producer".split(' '),
        PresentationProducer::class.java to "producerId producerVersion".split(' '),
        PresentationReceipt::class.java to "receiptId currencyCode receiptFields itemRows".split(' '),
        PresentationItemRow::class.java to "rowId fields".split(' '),
        PresentationField::class.java to "fieldId role status originalAutomaticValue presentationValue absenceReason sourceTokenIds nativeConfidence".split(' '),
    )
    private val enumTokens = mapOf<Class<out Enum<*>>, List<String>>(
        PresentationSourceType::class.java to "LOCAL_IMAGE SYNTHETIC_FIXTURE".split(' '),
        PresentationOutcomeStatus::class.java to "RESULT_AVAILABLE PROCESSING_UNAVAILABLE PROCESSING_FAILED SOURCE_EVIDENCE_INSUFFICIENT".split(' '),
        PresentationFailureStage::class.java to "AVAILABILITY OCR SOURCE_GATE EXTRACTION PRESENTATION_ADAPTER".split(' '),
        SourceProcessingStatus::class.java to "RECEIVED OCR_COMPLETED OCR_PARTIAL OCR_FAILED".split(' '),
        SourceGateDecision::class.java to "SUFFICIENT INSUFFICIENT".split(' '),
        AutomaticExtractionStage::class.java to "PRE_REVIEW_AUTOMATIC".split(' '),
        AutomaticExtractionStatus::class.java to "EXTRACTED PARTIAL FAILED".split(' '),
        ReceiptFieldRole::class.java to "STORE_NAME PURCHASE_DATE ITEM_DESCRIPTION QUANTITY UNIT_PRICE LINE_TOTAL RECEIPT_TOTAL".split(' '),
        ReceiptFieldStatus::class.java to "EXTRACTED MISSING UNRESOLVED".split(' '),
    )
    private val requiredPaths = mapOf(
        "08" to "$.schemaVersion",
        "33" to "$.receipt.receiptFields[1].presentationValue",
        "38" to "$",
        "44" to "$.requestId",
        "45" to "$.imageId",
        "57" to "$.receipt.itemRows[0].fields[0].sourceTokenIds[0]",
    )

    private fun declaredFields(type: Class<*>) =
        type.declaredFields.filterNot { Modifier.isStatic(it.modifiers) || it.isSynthetic }.associateBy { it.name }

    private fun dtoRecord(value: Any?): Any? = when (value) {
        null, is String, is Boolean -> value
        is Enum<*> -> value.name
        is List<*> -> value.map(::dtoRecord)
        is BigDecimal -> {
            val digits = value.unscaledValue().toString()
            if (value.signum() == 0) mapOf("coefficient" to "0", "exponent" to "0")
            else {
                val coefficient = digits.trimEnd('0')
                mapOf("coefficient" to coefficient,
                    "exponent" to (-value.scale().toLong() + digits.length - coefficient.length).toString())
            }
        }
        else -> {
            val properties = declaredFields(value.javaClass)
            dtoFields.getValue(value.javaClass).associateWith { name ->
                val property = properties.getValue(name)
                property.isAccessible = true
                dtoRecord(property.get(value))
            }
        }
    }

    private fun resultRecord(result: ReceiptPresentationResult<ReceiptPresentationV1>): Map<String, Any?> = when (result) {
        is ReceiptPresentationResult.Accepted -> mapOf("verdict" to "ACCEPT", "record" to dtoRecord(result.value))
        is ReceiptPresentationResult.Rejected -> mapOf("verdict" to "REJECT", "diagnostic" to mapOf(
            "code" to result.issue.code, "path" to result.issue.path, "detail" to result.issue.detail,
        ))
    }

    private fun evidenceDir(): Path? =
        System.getenv("PANTRYPROOF_M3E_PARITY_EVIDENCE_DIR")?.takeIf(String::isNotBlank)?.let(Paths::get)

    private fun digest(algorithm: String, raw: ByteArray): String =
        MessageDigest.getInstance(algorithm).digest(raw).joinToString("") { "%02x".format(it) }

    private fun envelopeSpan(raw: ByteArray): Pair<Int, Int> {
        require(raw.size <= 1_048_576) { "fixture size exceeds 1 MiB" }
        strictUtf8(raw)
        wrapperFactory.createParser(raw).use { parser ->
            expect(parser.nextToken(), JsonToken.START_OBJECT, "fixture root")
            var depth = 1
            var pendingEnvelope = false
            var start = -1
            var end = -1
            while (true) {
                val token = parser.nextToken() ?: break
                require(depth > 0) { "trailing fixture content" }
                if (pendingEnvelope) {
                    require(token == JsonToken.START_OBJECT && start == -1) { "duplicate or non-object envelope" }
                    start = parser.currentTokenLocation().byteOffset.toInt()
                    pendingEnvelope = false
                }
                when (token) {
                    JsonToken.FIELD_NAME -> if (depth == 1 && parser.currentName() == "envelope") pendingEnvelope = true
                    JsonToken.START_OBJECT, JsonToken.START_ARRAY -> {
                        depth++
                        require(depth <= 64) { "fixture depth exceeds 64" }
                    }
                    JsonToken.END_OBJECT, JsonToken.END_ARRAY -> {
                        depth--
                        if (depth == 1 && start >= 0 && end == -1) {
                            end = parser.currentTokenLocation().byteOffset.toInt() + 1
                        }
                    }
                    else -> Unit
                }
            }
            require(depth == 0 && start >= 0 && end > start && !pendingEnvelope) { "incomplete fixture envelope" }
            return start to end
        }
    }

    private fun readValue(parser: JsonParser): Any? = when (parser.currentToken()) {
        JsonToken.START_OBJECT -> linkedMapOf<String, Any?>().apply {
            while (parser.nextToken() != JsonToken.END_OBJECT) {
                expect(parser.currentToken(), JsonToken.FIELD_NAME, "object member")
                val key = parser.currentName()
                parser.nextToken()
                put(key, readValue(parser))
            }
        }
        JsonToken.START_ARRAY -> buildList {
            while (parser.nextToken() != JsonToken.END_ARRAY) add(readValue(parser))
        }
        JsonToken.VALUE_STRING -> parser.text
        JsonToken.VALUE_TRUE -> true
        JsonToken.VALUE_FALSE -> false
        JsonToken.VALUE_NULL -> null
        JsonToken.VALUE_NUMBER_INT, JsonToken.VALUE_NUMBER_FLOAT -> parser.decimalValue
        else -> error("Unexpected fixture token ${parser.currentToken()}")
    }

    @Suppress("UNCHECKED_CAST")
    private fun readObject(raw: ByteArray): MutableMap<String, Any?> =
        strictFactory.createParser(raw).use { parser ->
            expect(parser.nextToken(), JsonToken.START_OBJECT, "fixture envelope")
            val result = readValue(parser) as MutableMap<String, Any?>
            assertEquals(null, parser.nextToken())
            result
        }

    private fun fixtureContext(envelope: Map<String, Any?>) = PresentationConsumerContext(
        envelope.getValue("requestId") as String, envelope.getValue("imageId") as String, PresentationConsumerMode.FIXTURE,
    )

    private fun jsonBytes(value: Any?): ByteArray {
        val buffer = ByteArrayOutputStream()
        wrapperFactory.createGenerator(buffer).use { writeValue(it, value) }
        return buffer.toByteArray()
    }

    private fun writeValue(generator: JsonGenerator, value: Any?) {
        when (value) {
            null -> generator.writeNull()
            is String -> generator.writeString(value)
            is Boolean -> generator.writeBoolean(value)
            is BigDecimal -> generator.writeNumber(value)
            is Map<*, *> -> {
                generator.writeStartObject()
                value.forEach { (key, item) ->
                    generator.writeFieldName(key as String)
                    writeValue(generator, item)
                }
                generator.writeEndObject()
            }
            is List<*> -> {
                generator.writeStartArray()
                value.forEach { writeValue(generator, it) }
                generator.writeEndArray()
            }
            else -> error("Unexpected evidence value ${value.javaClass}")
        }
    }

    @Suppress("UNCHECKED_CAST")
    private fun dateField(envelope: Map<String, Any?>, index: Int): MutableMap<String, Any?> =
        ((envelope.getValue("receipt") as Map<*, *>)["receiptFields"] as List<*>)[index] as MutableMap<String, Any?>

    @Test
    fun nativeConfidenceRecordIsExact() {
        for ((token, coefficient, exponent) in listOf(
            Triple("0.750", "75", "-2"), Triple("75e-2", "75", "-2"),
            Triple("-0.00", "0", "0"), Triple("0E+4", "0", "0"),
            Triple("0.75000000000000000001", "75000000000000000001", "-20"),
        )) {
            assertEquals(token, mapOf("coefficient" to coefficient, "exponent" to exponent), dtoRecord(BigDecimal(token)))
        }
        assertEquals(null, dtoRecord(null))
    }

    @Test
    @Suppress("UNCHECKED_CAST")
    fun dateDomainAndRawPrecedence() {
        fun load(name: String): MutableMap<String, Any?> {
            val bytes = Files.readAllBytes(locateFixtureRoot().resolve("fixtures/$name"))
            val (start, end) = envelopeSpan(bytes)
            return readObject(bytes.copyOfRange(start, end))
        }
        fun reject(label: String, envelope: Map<String, Any?>, code: String, path: String,
                   raw: ByteArray = jsonBytes(envelope)) {
            val actual = ReceiptPresentationV1Validator.decodeAndValidate(raw, fixtureContext(envelope))
            assertTrue(label, actual is ReceiptPresentationResult.Rejected)
            val issue = (actual as ReceiptPresentationResult.Rejected).issue
            assertEquals(label, code, issue.code)
            assertEquals(label, path, issue.path)
        }
        val datePath = "$.receipt.receiptFields[1]"
        val validDates = listOf("0001-01-01", "9999-12-31", "0004-02-29", "1582-10-10", "2000-02-29")
        val invalidDates = listOf("0000-01-01", "0000-02-29", "0001-02-29", "1900-02-29",
            "2100-02-29", "2026-02-30", "10000-01-01", "2026-2-03")
        val env = load("01-complete-extracted-receipt.json")
        val date = dateField(env, 1)
        for (value in validDates + invalidDates) {
            date["originalAutomaticValue"] = value
            date["presentationValue"] = value
            if (value in invalidDates) {
                reject(value, env, "REJECT_INVALID_DATE", "$datePath.presentationValue")
            } else {
                val actual = ReceiptPresentationV1Validator.decodeAndValidate(jsonBytes(env), fixtureContext(env))
                assertTrue(value, actual is ReceiptPresentationResult.Accepted)
                val field = (actual as ReceiptPresentationResult.Accepted).value.receipt!!.receiptFields[1]
                assertEquals(value, field.originalAutomaticValue)
                assertEquals(value, field.presentationValue)
            }
        }
        date["originalAutomaticValue"] = "0001-01-01"
        date["presentationValue"] = "0000-02-29"
        reject("date relationship first", env, "REJECT_VALUE_RELATIONSHIP", datePath)
        val badVersion = load("01-complete-extracted-receipt.json")
        badVersion["schemaVersion"] = "999"
        reject("duplicate before version", badVersion, "REJECT_DUPLICATE_JSON_KEY", "$",
            "{\"schemaVersion\":\"1\",".toByteArray() + jsonBytes(badVersion).drop(1).toByteArray())

        val unsafe = "Reference evidence A12"
        val gated = load("16-source-evidence-insufficient.json")
        val gate = gated.getValue("sourceGate") as MutableMap<String, Any?>
        gate["reasons"] = listOf(unsafe, unsafe)
        reject("duplicate unsafe reasons", gated, "REJECT_GATE_STATE", "$.sourceGate.reasons[1]")
        gate["reasons"] = listOf(unsafe)
        reject("unsafe gate control", gated, "REJECT_UNSAFE_PROVENANCE", "$.sourceGate.reasons[0]")
        for ((name, index) in listOf("03-missing-required-store-name.json" to 0, "04-unresolved-purchase-date.json" to 1)) {
            val receipt = load(name)
            val field = dateField(receipt, index)
            val path = "$.receipt.receiptFields[$index]"
            field["absenceReason"] = unsafe
            reject(name, receipt, "REJECT_UNSAFE_PROVENANCE", "$path.absenceReason")
            field["originalAutomaticValue"] = "unexpected"
            reject(name, receipt, "REJECT_CONTRADICTORY_FIELD_STATE", path)
        }
    }


    private fun strictUtf8(raw: ByteArray): String {
        assertFalse(
            "UTF-8 BOM is forbidden",
            raw.size >= 3 &&
                raw[0] == 0xEF.toByte() &&
                raw[1] == 0xBB.toByte() &&
                raw[2] == 0xBF.toByte(),
        )
        return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(raw))
            .toString()
    }

    private fun readString(parser: JsonParser, token: JsonToken?, label: String): String {
        expect(token, JsonToken.VALUE_STRING, label)
        return parser.text
    }

    private fun readInt(parser: JsonParser, token: JsonToken?, label: String): Int {
        expect(token, JsonToken.VALUE_NUMBER_INT, label)
        return parser.intValue
    }

    private fun readStringArray(parser: JsonParser, token: JsonToken?, label: String): List<String> {
        expect(token, JsonToken.START_ARRAY, label)
        val values = mutableListOf<String>()
        while (parser.nextToken() != JsonToken.END_ARRAY) {
            values += readString(parser, parser.currentToken, "$label[${values.size}]")
        }
        return values
    }

    private fun expect(actual: JsonToken?, expected: JsonToken, label: String) {
        if (actual != expected) {
            fail("$label expected $expected but found $actual")
        }
    }

    private fun sha256(raw: ByteArray): String =
        MessageDigest.getInstance("SHA-256")
            .digest(raw)
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }

    private fun <T : Any> assertNotNullValue(value: T?, label: String): T {
        assertNotNull("$label is required", value)
        return value!!
    }

    private data class FixtureManifest(
        val schemaName: String,
        val schemaVersion: String,
        val fixtureCount: Int,
        val acceptCount: Int,
        val rejectCount: Int,
        val entries: List<FixtureEntry>,
    )

    private data class FixtureEntry(
        val path: String,
        val expectedResult: String,
        val decisionIds: List<String>,
        val sha256: String,
        val byteLength: Int,
        val sourceClassification: String,
    )

    private data class FixtureWrapper(
        val expectedResult: String,
        val context: FixtureConsumerContext?,
    )

    private data class FixtureConsumerContext(
        val expectedRequestId: String,
        val expectedImageId: String,
        val mode: String,
    ) {
        fun toProductionContext(): PresentationConsumerContext {
            val parsedMode = PresentationConsumerMode.entries.firstOrNull { it.name == mode }
                ?: throw AssertionError("unknown fixture consumer mode $mode")
            return PresentationConsumerContext(expectedRequestId, expectedImageId, parsedMode)
        }
    }

    private companion object {
        const val MANIFEST_SHA256 = "4b1bcd3445d82852c7f4c3beb5f0e07f39853497e92713b81a063dcdf5350ee9"
        const val ENVELOPE_38_SHA = "afbfa334ff2b9ec1b5a00bc6e9fed85b5074cc7413af966ef249189768a0614a"
        const val FIXTURE_STATUS = "DRAFT_NOT_APPROVED — SYNTHETIC_ONLY"

        val strictFactory: JsonFactory =
            JsonFactory.builder()
                .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
                .build()
        val wrapperFactory = JsonFactory()

        val MANIFEST_MEMBERS =
            linkedSetOf("schemaName", "schemaVersion", "fixtureCount", "acceptCount", "rejectCount", "fixtures")
        val ENTRY_MEMBERS =
            linkedSetOf("path", "expectedResult", "decisionIds", "sha256", "byteLength", "sourceClassification")
        val REQUIRED_WRAPPER_MEMBERS = linkedSetOf("fixtureStatus", "scenario", "expectedResult", "envelope")
        val ALL_WRAPPER_MEMBERS = linkedSetOf("fixtureStatus", "scenario", "expectedResult", "consumerContext", "envelope")
        val CONTEXT_MEMBERS = linkedSetOf("expectedRequestId", "expectedImageId", "mode")

        val FIXTURE_PATH_REGEX = Regex("^fixtures/[A-Za-z0-9][A-Za-z0-9._-]*\\.json$")
        val EXPECTED_RESULT_REGEX = Regex("^(?:ACCEPT|REJECT_[A-Z0-9_]+)$")
        val SHA256_REGEX = Regex("^[0-9a-f]{64}$")
    }
}
