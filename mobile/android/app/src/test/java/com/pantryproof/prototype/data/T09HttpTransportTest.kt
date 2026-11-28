package com.pantryproof.prototype.data

import com.pantryproof.prototype.contract.review.loadReviewFixture
import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.ReceiptPresentationIssueCodes
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.InputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketAddress
import java.net.SocketException
import java.net.SocketTimeoutException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong
import java.util.zip.CRC32
import java.util.zip.DeflaterOutputStream
import org.junit.Assert.*
import org.junit.Test

class T09HttpTransportTest {
    private val testToken = "a".repeat(64)

    @Test fun approvedOriginAndCredentialAreExplicitAndProcessLocal() {
        T09ProcessingConfig.clear()
        try {
            assertFalse(T09ProcessingConfig.isConfigured())
            assertTrue(T09ProcessingConfig.isCapable("com.pantryproof.prototype.t09live"))
            assertFalse(T09ProcessingConfig.isCapable("com.pantryproof.prototype"))
            assertFalse(T09ProcessingConfig.isCapable("com.pantryproof.prototype.s04fake"))
            assertThrows(IllegalArgumentException::class.java) { T09ProcessingConfig.configure("https", "10.0.2.2", 8765, "fake") }
            assertThrows(IllegalArgumentException::class.java) { T09ProcessingConfig.configure("http", "127.0.0.1", 8765, "fake") }
            assertThrows(IllegalArgumentException::class.java) { T09ProcessingConfig.configure("http", "10.0.2.2", 8766, "fake") }
            assertThrows(IllegalArgumentException::class.java) { T09ProcessingConfig.configure("http", "10.0.2.2", 8765, "fake\r\nInjected") }
            assertThrows(IllegalArgumentException::class.java) { T09ProcessingConfig.configure("http", "10.0.2.2", 8765, "") }
            T09ProcessingConfig.configure("http", "10.0.2.2", 8765, testToken)
            val configured = checkNotNull(T09ProcessingConfig.take())
            assertEquals(testToken, configured.credential())
            assertNull(T09ProcessingConfig.take())
            configured.clear()
            assertNull(configured.credential())
        } finally {
            T09ProcessingConfig.clear()
        }
    }

    @Test fun sendsExactRequestAndPreservesResponseBytesForLiveValidation() {
        val body = liveFixture()
        val socket = FakeSocket(ByteArrayInputStream(response(body)))
        val session = session()
        T09HttpTransport(session, { 0 }, ::png, openSocket = { socket }).use { transport ->
            val payload = (submit(transport) as ReceiptProcessingDelivery.ReviewEnvelope).body.takeBytes()
            assertArrayEquals(body, payload)
            assertEquals("10.0.2.2", (socket.destination as InetSocketAddress).address.hostAddress)
            assertEquals(8765, (socket.destination as InetSocketAddress).port)
            assertEquals(5000, socket.connectTimeout)
            assertEquals(125_000, socket.firstReadTimeout)
            val image = png()
            val exact = (
                "POST /v1/receipts/process HTTP/1.1\r\nHost: 10.0.2.2:8765\r\n" +
                    "Content-Type: image/png\r\nContent-Length: ${image.size}\r\nConnection: close\r\n" +
                    "X-Request-Id: ${SyntheticReceiptPresentationPayload.REQUEST_ID}\r\n" +
                    "X-Image-Id: ${SyntheticReceiptPresentationPayload.IMAGE_ID}\r\n" +
                    "X-Response-Schema: receipt-review-v1\r\n" +
                    "Authorization: Bearer $testToken\r\n\r\n"
                ).toByteArray(Charsets.US_ASCII) + image
            assertArrayEquals(exact, socket.upload.toByteArray())
            assertTrue(M3eReceiptPresentationAdapter().decodeAndMap(payload, request().context) is ReceiptPresentationUiResult.Available)
            assertTrue(socket.isClosed)
        }
        assertEquals(testToken, session.credential())
        session.clear()
    }

    @Test fun strictValidationRejectsMismatchFixtureAndMalformedUtf8() {
        val body = liveFixture()
        val cases = listOf(
            body.decodeToString().replace(SyntheticReceiptPresentationPayload.REQUEST_ID, "wrong-request").encodeToByteArray()
                to ReceiptPresentationIssueCodes.REQUEST_ID_MISMATCH,
            body.decodeToString().replace(SyntheticReceiptPresentationPayload.IMAGE_ID, "wrong-image").encodeToByteArray()
                to ReceiptPresentationIssueCodes.IMAGE_ID_MISMATCH,
            SyntheticReceiptPresentationPayload.bytes() to ReceiptPresentationIssueCodes.SOURCE_MODE_MISMATCH,
            byteArrayOf(0xC3.toByte(), 0x28) to ReceiptPresentationIssueCodes.INVALID_JSON,
        )
        for ((responseBody, expected) in cases) {
            val socket = FakeSocket(ByteArrayInputStream(response(responseBody)))
            T09HttpTransport(session(), { 0 }, ::png, openSocket = { socket }).use { transport ->
                val bytes = (submit(transport) as ReceiptProcessingDelivery.ReviewEnvelope).body.takeBytes()
                val rejected = M3eReceiptPresentationAdapter().decodeAndMap(bytes, request().context)
                    as ReceiptPresentationUiResult.Rejected
                assertEquals(expected, rejected.issue.code)
            }
        }
    }

    @Test fun liveLifecycleInstallsOnlyNegotiatedBoundReviewAndCanRetryBusyExplicitly() {
        val fixture = loadReviewFixture("fixtures/13-exact-weighted-quantity.json")
        val ids = fixture.context.presentation
        val live = fixture.body.decodeToString().replace("\"SYNTHETIC_FIXTURE\"", "\"LOCAL_IMAGE\"")
        val good = live.encodeToByteArray()
        val bare = liveFixture()
        val refusals = listOf(429, 503).map { "HTTP/1.1 $it Refused\r\nContent-Length: 0\r\n\r\n".encodeToByteArray() }
        val replies = ArrayDeque(refusals + listOf(response(bare), response(good)))
        val work = LinkedBlockingQueue<() -> Unit>()
        T09HttpTransport(session(), { 0 }, { png(480, 640) },
            openSocket = { FakeSocket(ByteArrayInputStream(replies.removeFirst())) }).use { transport ->
            val flow = ReceiptProcessingLifecycle(transport, { work.add(it) }, { work.add(it) }, { _, _ -> },
                { 0L }, T09HttpTransport.TOTAL_MS, { ids.expectedImageId }, { ids.expectedRequestId })
            fun attempt(): ReceiptProcessingLifecycle.Outcome {
                flow.selectInput()
                flow.submit(PresentationConsumerMode.LIVE)
                while (flow.state !is ReceiptProcessingLifecycle.State.Finished) {
                    checkNotNull(work.poll(4, TimeUnit.SECONDS)).invoke()
                }
                return (flow.state as ReceiptProcessingLifecycle.State.Finished).outcome
            }
            assertEquals(ReceiptProcessingLifecycle.Outcome.HttpRefusal(429), attempt())
            assertEquals(3, replies.size)
            assertEquals(ReceiptProcessingLifecycle.Outcome.HttpRefusal(503), attempt())
            val rejected = (attempt() as ReceiptProcessingLifecycle.Outcome.Presentation).result as ReceiptPresentationUiResult.Rejected
            assertEquals(ReceiptPresentationIssueCodes.UNSUPPORTED_SCHEMA_VERSION, rejected.issue.code)
            val accepted = (attempt() as ReceiptProcessingLifecycle.Outcome.Presentation).result as ReceiptPresentationUiResult.Available
            assertEquals(7, accepted.liveEvidence?.wrapper?.review?.fields?.size)
            assertTrue(replies.isEmpty())
        }
    }

    @Test fun responseRejectsIncorrectLengthDuplicateFramingAndWrongContentType() {
        val correct = response(byteArrayOf(123, 125))
        val cases = listOf(
            correct + byteArrayOf(32),
            correct.copyOf(correct.size - 1),
            correct.decodeToString().replace("Content-Length: 2", "Content-Length: 2\r\ncontent-length: 2").encodeToByteArray(),
            correct.decodeToString().replace("application/json", "text/plain").encodeToByteArray(),
        )
        for (wire in cases) {
            T09HttpTransport(session(), { 0 }, ::png, openSocket = {
                FakeSocket(ByteArrayInputStream(wire))
            }).use { assertSame(ReceiptProcessingDelivery.ProtocolFailure, submit(it)) }
        }
    }

    @Test fun non200AndSocketFailureNeverRetryOrProduceReceipt() {
        for (status in listOf(302, 400, 401, 406, 413, 415, 422, 429, 500, 503, 504)) {
            val response = "HTTP/1.1 $status Error\r\nContent-Length: 0\r\n\r\n".encodeToByteArray()
            val calls = AtomicInteger()
            T09HttpTransport(session(), { 0 }, ::png, openSocket = {
                calls.incrementAndGet()
                FakeSocket(ByteArrayInputStream(response))
             }).use {
                val expected = if (status == 302) ReceiptProcessingDelivery.ProtocolFailure
                    else ReceiptProcessingDelivery.HttpRefusal(status)
                assertEquals(expected, submit(it))
            }
            assertEquals(1, calls.get())
        }
        val calls = AtomicInteger()
        T09HttpTransport(session(), { 0 }, ::png, openSocket = {
            calls.incrementAndGet()
            throw SocketException()
        }).use { assertSame(ReceiptProcessingDelivery.ExecutionFailure, submit(it)) }
        assertEquals(1, calls.get())
    }

    @Test fun fixtureWrongSelectionAndOutOfBoundsPngNeverOpenSocket() {
        val calls = AtomicInteger()
        val badPngs = listOf(png(width = 1601), png(height = 1601), png().copyOf(T09HttpTransport.MAX_PNG_BYTES + 1))
        for (image in badPngs) {
            T09HttpTransport(session(), { 0 }, { image }, openSocket = {
                calls.incrementAndGet()
                error("Unexpected socket")
            }).use {
                assertSame(ReceiptProcessingDelivery.ImageLimit, submit(it))
                assertSame(ReceiptProcessingDelivery.ExecutionFailure, submit(it, request(mode = PresentationConsumerMode.FIXTURE)))
                val wrongId = request().let { req -> req.copy(context = req.context.copy(expectedImageId = "another-image")) }
                assertSame(ReceiptProcessingDelivery.ExecutionFailure, submit(it, wrongId))
            }
        }
        assertEquals(0, calls.get())
    }

    @Test fun responseCapCoversFixedLengthCloseDelimitedAndChunkedBodies() {
        val max = T09HttpTransport.MAX_RESPONSE_BYTES
        val oversized = listOf(
            "HTTP/1.1 200 OK\r\nContent-Length: ${max + 1}\r\n\r\n".encodeToByteArray(),
            "HTTP/1.0 200 OK\r\n\r\n".encodeToByteArray() + ByteArray(max + 1),
            "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n${(max + 1).toString(16)}\r\n".encodeToByteArray(),
        )
        for (wire in oversized) {
            val socket = FakeSocket(ByteArrayInputStream(wire))
            T09HttpTransport(session(), { 0 }, ::png, openSocket = { socket }).use {
                assertSame(ReceiptProcessingDelivery.ProtocolFailure, submit(it))
            }
        }
        val boundary = FakeSocket(ByteArrayInputStream(response(ByteArray(max))))
        T09HttpTransport(session(), { 0 }, ::png, openSocket = { boundary }).use {
            assertEquals(max, (submit(it) as ReceiptProcessingDelivery.ReviewEnvelope).body.takeBytes().size)
        }
        val chunks = FakeSocket(ByteArrayInputStream(
            "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n".encodeToByteArray(),
        ))
        T09HttpTransport(session(), { 0 }, ::png, openSocket = { chunks }).use {
            assertSame(ReceiptProcessingDelivery.ProtocolFailure, submit(it))
        }
    }

    @Test fun firstByteTimeoutIsCappedAndPreparationUsesStartDeadline() {
        val read = object : InputStream() {
            override fun read(): Int = throw SocketTimeoutException()
        }
        val socket = FakeSocket(read)
        T09HttpTransport(session(), { 0 }, ::png, openSocket = { socket }).use {
            assertSame(ReceiptProcessingDelivery.TimedOut, submit(it, request(deadline = 4500)))
            assertEquals(4500, socket.connectTimeout)
            assertEquals(4500, socket.firstReadTimeout)
            assertTrue(socket.isClosed)
        }
        val time = AtomicLong()
        val calls = AtomicInteger()
        T09HttpTransport(session(), time::get, { time.set(125_000); png() }, openSocket = {
            calls.incrementAndGet()
            error("Expired preparation must not reach a socket")
        }).use {
            assertSame(ReceiptProcessingDelivery.TimedOut, submit(it))
            assertEquals(0, calls.get())
        }
    }

    @Test fun continuousBodyChunksCannotExtendOverallDeadline() {
        val time = AtomicLong()
        val status = responseHeaders(8)
        val slowly = object : InputStream() {
            var servedHeader = false
            override fun read(): Int = error("Expected buffered read")
            override fun read(b: ByteArray, off: Int, len: Int): Int {
                if (!servedHeader) {
                    servedHeader = true
                    status.copyInto(b, off)
                    return status.size
                }
                time.addAndGet(40_000)
                b[off] = 42
                return 1
            }
        }
        val socket = FakeSocket(slowly)
        T09HttpTransport(session(), time::get, ::png, openSocket = { socket }).use {
            assertSame(ReceiptProcessingDelivery.TimedOut, submit(it))
            assertTrue(socket.isClosed)
        }
    }

    @Test fun blockedReadClosesOnCancelAndSecondActiveSubmissionIsRejected() {
        val socket = blockingSocket()
        val result = LinkedBlockingQueue<ReceiptProcessingDelivery>()
        T09HttpTransport(session(), { 0 }, ::png, openSocket = { socket.first }).use { transport ->
            val cancellation = transport.submit(request()) { result.add(it) }
            assertTrue(socket.second.await(3, TimeUnit.SECONDS))
            assertSame(ReceiptProcessingDelivery.ExecutionFailure, submit(transport))
            cancellation.cancel()
            assertTrue(socket.first.closeSignal.await(3, TimeUnit.SECONDS))
            assertNull(result.poll(100, TimeUnit.MILLISECONDS))
        }
    }

    @Test fun overallWatchdogClosesBlockedIoAndDeliversTimeout() {
        val socket = blockingSocket()
        val result = LinkedBlockingQueue<ReceiptProcessingDelivery>()
        val clock = { System.nanoTime() / 1_000_000 }
        T09HttpTransport(session(), clock, ::png, openSocket = { socket.first }).use { transport ->
            transport.submit(request(deadline = clock() + 1_000)) { result.add(it) }
            assertTrue(socket.second.await(3, TimeUnit.SECONDS))
            assertSame(ReceiptProcessingDelivery.TimedOut, result.poll(4, TimeUnit.SECONDS))
            assertTrue(socket.first.isClosed)
        }
    }

    private fun blockingSocket(): Pair<FakeSocket, CountDownLatch> {
        val reading = CountDownLatch(1)
        val closed = CountDownLatch(1)
        val blocked = object : InputStream() {
            override fun read(): Int {
                reading.countDown()
                while (closed.count != 0L) {
                    try { closed.await() } catch (_: InterruptedException) { /* Simulate blocking network I/O. */ }
                }
                throw SocketException()
            }
        }
        return FakeSocket(blocked, closed) to reading
    }

    private fun request(
        deadline: Long = 125_000,
        mode: PresentationConsumerMode = PresentationConsumerMode.LIVE,
    ): ReceiptProcessingRequest {
        val image = SyntheticReceiptPresentationPayload.IMAGE_ID
        return ReceiptProcessingRequest(
            ReceiptProcessingRequest.Selection(ReceiptProcessingRequest.Owner(), image),
            ReceiptProcessingRequest.Submission(),
            PresentationConsumerContext(SyntheticReceiptPresentationPayload.REQUEST_ID, image, mode),
            deadline,
        )
    }

    private fun submit(
        transport: T09HttpTransport,
        request: ReceiptProcessingRequest = request(),
    ): ReceiptProcessingDelivery {
        val result = LinkedBlockingQueue<ReceiptProcessingDelivery>()
        transport.submit(request) { result.add(it) }
        return checkNotNull(result.poll(4, TimeUnit.SECONDS))
    }

    private fun png(width: Int = 1, height: Int = 1): ByteArray {
        val output = ByteArrayOutputStream()
        val png = DataOutputStream(output)
        png.write(byteArrayOf(-119, 80, 78, 71, 13, 10, 26, 10))
        fun chunk(name: String, data: ByteArray) {
            val type = name.encodeToByteArray()
            png.writeInt(data.size)
            png.write(type)
            png.write(data)
            png.writeInt(CRC32().apply { update(type); update(data) }.value.toInt())
        }
        val ihdr = java.nio.ByteBuffer.allocate(13).putInt(width).putInt(height)
            .put(8.toByte()).put(2.toByte()).array()
        val compressed = ByteArrayOutputStream()
        val scanline = ByteArray(1 + width * 3)
        DeflaterOutputStream(compressed).use { deflater -> repeat(height) { deflater.write(scanline) } }
        chunk("IHDR", ihdr)
        chunk("IDAT", compressed.toByteArray())
        chunk("IEND", byteArrayOf())
        return output.toByteArray()
    }

    private fun liveFixture() = SyntheticReceiptPresentationPayload.bytes().decodeToString()
        .replace("SYNTHETIC_FIXTURE", "LOCAL_IMAGE").encodeToByteArray()

    private fun response(body: ByteArray) = responseHeaders(body.size) + body

    private fun responseHeaders(size: Int) =
        ("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n" +
            "Connection: close\r\nContent-Length: $size\r\n\r\n").encodeToByteArray()

    private fun session() = T09ProcessingConfig.Session("http", "10.0.2.2", 8765, testToken)

    private class FakeSocket(
        private val input: InputStream,
        val closeSignal: CountDownLatch = CountDownLatch(1),
    ) : Socket() {
        var destination: SocketAddress? = null
        var connectTimeout = 0
        var firstReadTimeout = 0
        val upload = ByteArrayOutputStream()
        override fun connect(endpoint: SocketAddress, timeout: Int) {
            destination = endpoint
            connectTimeout = timeout
        }
        override fun getInputStream(): InputStream = input
        override fun getOutputStream(): ByteArrayOutputStream = upload
        override fun setSoTimeout(timeout: Int) {
            if (firstReadTimeout == 0) firstReadTimeout = timeout
        }
        override fun close() { closeSignal.countDown() }
        override fun isClosed(): Boolean = closeSignal.count == 0L
    }
}
