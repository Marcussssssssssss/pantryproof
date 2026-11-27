package com.pantryproof.prototype.data

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
            T09ProcessingConfig.configure("http", "10.0.2.2", 8765, "test-token")
            val configured = checkNotNull(T09ProcessingConfig.take())
            assertEquals("test-token", configured.credential())
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
            val payload = (submit(transport) as ReceiptProcessingDelivery.Envelope).takeBytes()
            assertArrayEquals(body, payload)
            assertEquals("10.0.2.2", (socket.destination as InetSocketAddress).address.hostAddress)
            assertEquals(8765, (socket.destination as InetSocketAddress).port)
            assertEquals(5000, socket.connectTimeout)
            assertEquals(120_000, socket.firstReadTimeout)
            val image = png()
            val exact = (
                "POST /v1/receipts/process HTTP/1.1\r\nHost: 10.0.2.2:8765\r\n" +
                    "Content-Type: image/png\r\nContent-Length: ${image.size}\r\nConnection: close\r\n" +
                    "X-Request-Id: ${SyntheticReceiptPresentationPayload.REQUEST_ID}\r\n" +
                    "X-Image-Id: ${SyntheticReceiptPresentationPayload.IMAGE_ID}\r\n" +
                    "Authorization: Bearer test-token\r\n\r\n"
                ).toByteArray(Charsets.US_ASCII) + image
            assertArrayEquals(exact, socket.upload.toByteArray())
            assertTrue(M3eReceiptPresentationAdapter().decodeAndMap(payload, request().context) is ReceiptPresentationUiResult.Available)
            assertTrue(socket.isClosed)
        }
        assertNull(session.credential())
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
                val bytes = (submit(transport) as ReceiptProcessingDelivery.Envelope).takeBytes()
                val rejected = M3eReceiptPresentationAdapter().decodeAndMap(bytes, request().context)
                    as ReceiptPresentationUiResult.Rejected
                assertEquals(expected, rejected.issue.code)
            }
        }
    }

    @Test fun non200AndSocketFailureNeverRetryOrProduceReceipt() {
        for (status in listOf(302, 400, 401, 413, 415, 422, 429, 500, 503, 504)) {
            val response = "HTTP/1.1 $status Error\r\nContent-Length: 0\r\n\r\n".encodeToByteArray()
            val calls = AtomicInteger()
            T09HttpTransport(session(), { 0 }, ::png, openSocket = {
                calls.incrementAndGet()
                FakeSocket(ByteArrayInputStream(response))
            }).use { assertSame(ReceiptProcessingDelivery.ExecutionFailure, submit(it)) }
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
                assertSame(ReceiptProcessingDelivery.ExecutionFailure, submit(it))
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
                assertSame(ReceiptProcessingDelivery.ExecutionFailure, submit(it))
            }
        }
        val boundary = FakeSocket(ByteArrayInputStream(response(ByteArray(max))))
        T09HttpTransport(session(), { 0 }, ::png, openSocket = { boundary }).use {
            assertEquals(max, (submit(it) as ReceiptProcessingDelivery.Envelope).takeBytes().size)
        }
        val chunks = FakeSocket(ByteArrayInputStream(
            "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n".encodeToByteArray(),
        ))
        T09HttpTransport(session(), { 0 }, ::png, openSocket = { chunks }).use {
            assertArrayEquals("{}".encodeToByteArray(), (submit(it) as ReceiptProcessingDelivery.Envelope).takeBytes())
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
        T09HttpTransport(session(), time::get, { time.set(130_000); png() }, openSocket = {
            calls.incrementAndGet()
            error("Expired preparation must not reach a socket")
        }).use {
            assertSame(ReceiptProcessingDelivery.TimedOut, submit(it))
            assertEquals(0, calls.get())
        }
    }

    @Test fun continuousBodyChunksCannotExtendOverallDeadline() {
        val time = AtomicLong()
        val status = "HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\n".encodeToByteArray()
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
        deadline: Long = 130_000,
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
        DeflaterOutputStream(compressed).use { it.write(byteArrayOf(0, 0, 0, 0)) }
        chunk("IHDR", ihdr)
        chunk("IDAT", compressed.toByteArray())
        chunk("IEND", byteArrayOf())
        return output.toByteArray()
    }

    private fun liveFixture() = SyntheticReceiptPresentationPayload.bytes().decodeToString()
        .replace("SYNTHETIC_FIXTURE", "LOCAL_IMAGE").encodeToByteArray()

    private fun response(body: ByteArray) =
        "HTTP/1.1 200 OK\r\nContent-Length: ${body.size}\r\n\r\n".encodeToByteArray() + body

    private fun session() = T09ProcessingConfig.Session("http", "10.0.2.2", 8765, "test-token")

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
