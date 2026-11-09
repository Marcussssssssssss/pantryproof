package com.pantryproof.prototype.contract.v1

import com.fasterxml.jackson.core.JsonFactory
import com.fasterxml.jackson.core.JsonParser
import com.fasterxml.jackson.core.JsonToken
import com.fasterxml.jackson.core.StreamReadFeature
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
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

            val wrapper = parseWrapperMetadata(rawFixture)
            assertEquals("manifest/wrapper expectation mismatch for ${entry.path}", entry.expectedResult, wrapper.expectedResult)

            val decoded = decodeNestedEnvelope(rawFixture)
            val actual =
                when (decoded) {
                    is ReceiptPresentationResult.Rejected -> decoded.issue.code
                    is ReceiptPresentationResult.Accepted -> {
                        val envelope = decoded.value
                        val context = wrapper.context?.toProductionContext()
                            ?: PresentationConsumerContext(
                                envelope.requestId,
                                envelope.imageId,
                                PresentationConsumerMode.FIXTURE,
                            )
                        when (val validated = ReceiptPresentationV1Validator.validate(envelope, context)) {
                            is ReceiptPresentationResult.Accepted -> "ACCEPT"
                            is ReceiptPresentationResult.Rejected -> validated.issue.code
                        }
                    }
                }
            assertEquals("conformance mismatch for ${entry.path}", entry.expectedResult, actual)
            executed += 1
            if (actual == "ACCEPT") accepted += 1 else rejected += 1
        }

        assertTrue("zero canonical fixtures executed", executed > 0)
        assertEquals(32, executed)
        assertEquals(17, accepted)
        assertEquals(15, rejected)
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

    private fun decodeNestedEnvelope(raw: ByteArray): ReceiptPresentationResult<ReceiptPresentationV1> {
        strictFactory.createParser(strictUtf8(raw)).use { parser ->
            expect(parser.nextToken(), JsonToken.START_OBJECT, "fixture wrapper root")
            while (parser.nextToken() != JsonToken.END_OBJECT) {
                expect(parser.currentToken, JsonToken.FIELD_NAME, "fixture wrapper member")
                val name = parser.currentName()
                val token = parser.nextToken()
                if (name == "envelope") {
                    expect(token, JsonToken.START_OBJECT, "fixture envelope")
                    return ReceiptPresentationV1Decoder.decodeCurrentEnvelope(parser)
                }
                parser.skipChildren()
            }
        }
        fail("fixture wrapper omitted envelope")
        throw AssertionError("unreachable")
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
