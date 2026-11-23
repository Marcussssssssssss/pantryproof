package com.pantryproof.prototype.data

import android.security.NetworkSecurityPolicy
import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.PresentationSourceType
import com.pantryproof.prototype.contract.v1.ReceiptPresentationResult
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder
import java.io.IOException
import java.io.InputStream
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.Socket
import java.security.MessageDigest
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.TimeUnit

/**
 * One generated-image attempt per independently configured S04 run.
 *
 * The test owner supplies the exact eligible Start's origin and a thread-safe current-attempt
 * check. Both the origin and [elapsedMillis] must use the lifecycle's monotonic clock. This
 * transport has no fallback origin. The lifecycle still owns serialized terminal UI admission.
 */
internal class S04FakeHttpTransport(
    port: String,
    token: String,
    private val selection: ReceiptProcessingRequest.Selection,
    private val context: PresentationConsumerContext,
    preparedBytes: ByteArray,
    generatedImage: GeneratedImage,
    private val responsePin: ResponsePin,
    private val elapsedMillis: () -> Long,
    private val lifecycleStartMillis: (ReceiptProcessingRequest) -> Long?,
    private val isCurrentAttempt: (ReceiptProcessingRequest) -> Boolean,
) : ReceiptProcessingTransport, AutoCloseable {
    enum class GeneratedImage(val sha256: String) {
        G1("865DA7F5BA12869F3A1C31E1A8A5B6C4A9E211D5A634DE79F7840F0DFDE81B24"),
        G2("586D92088E58AE38BA60CF100BA9AFF9DA9C1CE7CFE7F87FB9763212CC64EC64"),
    }

    sealed interface ResponsePin {
        val length: Int
        val sha256: String
    }

    enum class Fixture(override val length: Int, override val sha256: String) : ResponsePin {
        F01(6093, "2FB388F98FAECA3398CE1243C6EF6583541B789BFE11528A997462EA09D983A3"),
        F05(4125, "A4AF8C33C8BBCA448A657AFB9658A90129A05BC9E2741A0CF9F3538E41FB4C84"),
        F06(742, "70F72BD67E1B8AE50034D184BD56D36AC2BFF0C3E8C7342F14595A328DB83699"),
        F07(780, "AEEFC4DF16EA7B96C26329F506AB9E5BC1FD14AC49AB8927089DDAA16BB61C3D"),
        F09(4144, "8A65A424446BAC32CEA11458A83519047E4E5D4C7FA0D2DFFF310BCAECBFA97C"),
        F15(2235, "991FB09D62EFCCA3877503481682E0FEEF8A6AC648B22C8CA5A2DC1A1FB44951"),
        F16(946, "3DCAFACCF3548370DB38A62CDF2E35AF030695C0B8BE7C65372D5E626F829C28"),
    }

    /** Exact negative-vector bytes pinned by the test owner out of band before Start. */
    class MalformedV1(override val length: Int, override val sha256: String) : ResponsePin {
        init {
            require(length in 1..MAX_RESPONSE_BYTES && SHA256.matches(sha256))
        }
    }

    private class Attempt(val request: ReceiptProcessingRequest, val deadline: Long) {
        var socket: Socket? = null
        var phase: Phase? = null
        var phaseExpired = false
    }

    private class Phase(val deadline: Long) {
        var timeout: ScheduledFuture<*>? = null
    }

    private val portNumber = canonicalPort(port)
    private val host = "$DESTINATION:$portNumber"
    private var runToken: String? = token
    private val snapshot: ReceiptSubmissionBinding.Snapshot

    init {
        require(TOKEN.matches(token))
        require(context.mode == PresentationConsumerMode.FIXTURE)
        require(ID.matches(context.expectedRequestId) && ID.matches(context.expectedImageId))
        require(context.expectedImageId == selection.imageId)
        require(preparedBytes.size == GENERATED_PNG_BYTES)
        snapshot = ReceiptSubmissionBinding.Snapshot(selection, preparedBytes, GENERATED_PNG_BYTES)
        require(matchesDigest(snapshot.copyBytes(), generatedImage.sha256))
    }

    private val lock = Any()
    private val worker = Executors.newSingleThreadExecutor()
    private val watchdog = ScheduledThreadPoolExecutor(1).apply {
        removeOnCancelPolicy = true
    }
    private var closed = false
    private var active: Attempt? = null

    override fun submit(
        request: ReceiptProcessingRequest,
        deliver: (ReceiptProcessingDelivery) -> Unit,
    ): ReceiptProcessingTransport.Cancellation {
        val start = if (request.selection === selection && request.context == context && current(request)) {
            lifecycleStartMillis(request)
        } else {
            null
        }
        val now = elapsedMillis()
        if (start == null || start < 0L || start > now || start > Long.MAX_VALUE - TOTAL_MS) {
            deliver(ReceiptProcessingDelivery.ExecutionFailure)
            return ReceiptProcessingTransport.Cancellation {}
        }
        val attempt = Attempt(request, start + TOTAL_MS)
        if (now >= attempt.deadline) return ReceiptProcessingTransport.Cancellation {}
        val queued = synchronized(lock) {
            if (closed || active != null) {
                false
            } else {
                active = attempt
                worker.execute { exchange(attempt, deliver) }
                true
            }
        }
        if (!queued) {
            deliver(ReceiptProcessingDelivery.ExecutionFailure)
            return ReceiptProcessingTransport.Cancellation {}
        }
        return ReceiptProcessingTransport.Cancellation { retire(attempt) }
    }

    override fun close() {
        retire()
    }

    private fun exchange(attempt: Attempt, deliver: (ReceiptProcessingDelivery) -> Unit) {
        val delivery = try {
            performExchange(attempt)
        } catch (_: IOException) {
            ReceiptProcessingDelivery.ExecutionFailure
        } catch (_: RuntimeException) {
            ReceiptProcessingDelivery.ExecutionFailure
        }
        // Cancellation can win before this claim. The lifecycle also guards a callback that
        // was already claimed before invalidation and takes TIMEOUT at its UI cutoff.
        if (retire(attempt) && current(attempt.request) && elapsedMillis() < attempt.deadline) {
            deliver(delivery)
        }
    }

    private fun performExchange(attempt: Attempt): ReceiptProcessingDelivery {
        check(current(attempt.request))
        check(NetworkSecurityPolicy.getInstance().isCleartextTrafficPermitted(DESTINATION))
        val bytes = snapshot.bind(attempt.request).copyBytes()
        val token = synchronized(lock) {
            check(active === attempt)
            checkNotNull(runToken)
        }
        val headers = requestHeaders(bytes.size, token)
        val hostAddress = InetAddress.getByAddress(byteArrayOf(10, 0, 2, 2))
        val body = try {
            Socket(Proxy.NO_PROXY).use { socket ->
                synchronized(lock) {
                    check(active === attempt)
                    attempt.socket = socket
                }
                check(current(attempt.request))
                beginPhase(attempt, CONNECT_MS)
                socket.connect(InetSocketAddress(hostAddress, portNumber), remainingInPhase(attempt))

                check(current(attempt.request))
                beginPhase(attempt, UPLOAD_MS)
                val output = socket.getOutputStream()
                remainingInPhase(attempt)
                output.write(headers)
                check(current(attempt.request))
                remainingInPhase(attempt)
                output.write(bytes)
                remainingInPhase(attempt)
                output.flush()

                beginPhase(attempt, RESPONSE_MS)
                val response = receive(socket, attempt)
                endPhase(attempt)
                response
            }
        } finally {
            headers.fill(0)
            bytes.fill(0)
        }
        if (body == null) return ReceiptProcessingDelivery.ExecutionFailure
        return try {
            check(current(attempt.request) && elapsedMillis() < attempt.deadline)
            fixtureDelivery(body)
        } finally {
            body.fill(0)
        }
    }

    private fun requestHeaders(size: Int, token: String): ByteArray {
        check(size in 1..MAX_REQUEST_BYTES)
        return buildString {
            append("POST /s04/v1/fixture-presentation HTTP/1.1\r\n")
            append("Host: $host\r\n")
            append("Content-Length: $size\r\n")
            append("Content-Type: image/png\r\n")
            append("Connection: close\r\n")
            append("X-PantryProof-Test-Version: 1\r\n")
            append("X-PantryProof-Test-Profile: FIXTURE\r\n")
            append("X-PantryProof-Request-Id: ").append(context.expectedRequestId).append("\r\n")
            append("X-PantryProof-Image-Id: ").append(context.expectedImageId).append("\r\n")
            append("Authorization: Bearer $token\r\n\r\n")
        }.toByteArray(Charsets.US_ASCII)
    }

    private fun receive(socket: Socket, attempt: Attempt): ByteArray? {
        val input = socket.getInputStream()
        fun nextByte(): Int {
            socket.soTimeout = remainingInPhase(attempt)
            val byte = input.read()
            check(byte >= 0)
            return byte
        }

        val statusLine = readLine(MAX_LINE_BYTES, ::nextByte)
        val success = statusLine == "HTTP/1.1 200 OK"
        check(success || statusLine in REFUSALS)
        val allowed = if (success) SUCCESS_HEADERS else REFUSAL_HEADERS
        val headers = readHeaders(allowed, ::nextByte)
        check(headers["connection"] == "close")
        val length = contentLength(headers.getValue("content-length"))
        if (!success) {
            check(length == 0 && input.available() == 0)
            return null
        }

        check(length == responsePin.length && length in 1..MAX_RESPONSE_BYTES)
        check(headers["content-type"] == "application/json")
        check(headers["x-pantryproof-test-version"] == "1")
        check(headers["x-pantryproof-test-profile"] == "FIXTURE")
        check(headers["x-pantryproof-request-id"] == context.expectedRequestId)
        check(headers["x-pantryproof-image-id"] == context.expectedImageId)
        val body = ByteArray(length)
        readBody(input, body) { socket.soTimeout = remainingInPhase(attempt) }
        // Only surplus already observable at the boundary is detectable without waiting.
        check(input.available() == 0)
        return body
    }

    private fun fixtureDelivery(body: ByteArray): ReceiptProcessingDelivery {
        check(matchesDigest(body, responsePin.sha256))
        when (val decoded = ReceiptPresentationV1Decoder.decode(body)) {
            is ReceiptPresentationResult.Accepted -> {
                check(responsePin is Fixture)
                check(decoded.value.source.type == PresentationSourceType.SYNTHETIC_FIXTURE)
                check(decoded.value.requestId == context.expectedRequestId)
                check(decoded.value.imageId == context.expectedImageId)
            }
            is ReceiptPresentationResult.Rejected -> check(responsePin is MalformedV1)
        }
        // The original bytes go through the existing strict validator and M3E path.
        return ReceiptProcessingDelivery.Envelope(body)
    }

    private fun beginPhase(attempt: Attempt, limit: Long) = synchronized(lock) {
        val now = elapsedMillis()
        check(active === attempt && !attempt.phaseExpired && now < attempt.deadline)
        attempt.phase?.let {
            check(now < it.deadline)
            it.timeout?.cancel(false)
        }
        val duration = minOf(limit, attempt.deadline - now)
        val phase = Phase(now + duration)
        attempt.phase = phase
        scheduleWatchdog(attempt, phase, duration)
    }

    // Called with the lock held. A superseded watchdog may never close a socket for a new phase.
    private fun scheduleWatchdog(attempt: Attempt, phase: Phase, delay: Long) {
        phase.timeout = watchdog.schedule(Runnable {
            val socket = synchronized(lock) {
                if (active !== attempt || attempt.phase !== phase) return@Runnable
                val remaining = phase.deadline - elapsedMillis()
                if (remaining > 0L) {
                    scheduleWatchdog(attempt, phase, remaining)
                    return@Runnable
                }
                attempt.phaseExpired = true
                attempt.socket
            }
            closeSocket(socket)
        }, delay, TimeUnit.MILLISECONDS)
    }

    private fun remainingInPhase(attempt: Attempt): Int = synchronized(lock) {
        check(active === attempt && !attempt.phaseExpired)
        val remaining = checkNotNull(attempt.phase).deadline - elapsedMillis()
        check(remaining in 1L..TOTAL_MS)
        remaining.toInt()
    }

    private fun endPhase(attempt: Attempt) = synchronized(lock) {
        remainingInPhase(attempt)
        attempt.phase?.timeout?.cancel(false)
        attempt.phase = null
    }

    private fun retire(expected: Attempt? = null): Boolean {
        val closingSocket = synchronized(lock) {
            if (closed || (expected != null && active !== expected)) return false
            closed = true
            runToken = null
            val attempt = active
            active = null
            attempt?.phase?.timeout?.cancel(false)
            attempt?.socket
        }
        closeSocket(closingSocket)
        snapshot.release()
        watchdog.shutdownNow()
        worker.shutdown()
        return true
    }

    private fun current(request: ReceiptProcessingRequest): Boolean =
        try {
            isCurrentAttempt(request)
        } catch (_: RuntimeException) {
            false
        }

    private companion object {
        const val DESTINATION = "10.0.2.2"
        const val MAX_REQUEST_BYTES = 32_768
        const val MAX_RESPONSE_BYTES = 16_384
        const val MAX_LINE_BYTES = 512
        const val MAX_HEADER_BYTES = 4_096
        const val MAX_FIELDS = 24
        const val GENERATED_PNG_BYTES = 1_352
        const val CONNECT_MS = 1_000L
        const val UPLOAD_MS = 1_500L
        const val RESPONSE_MS = 3_000L
        const val TOTAL_MS = 6_000L

        val ID = Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
        val TOKEN = Regex("[0-9a-f]{64}")
        val SHA256 = Regex("[0-9A-F]{64}")
        val REFUSAL_HEADERS = setOf("content-length", "connection")
        val SUCCESS_HEADERS = REFUSAL_HEADERS + setOf(
            "content-type",
            "x-pantryproof-test-version",
            "x-pantryproof-test-profile",
            "x-pantryproof-request-id",
            "x-pantryproof-image-id",
        )
        val REFUSALS = setOf(
            "HTTP/1.1 400 Bad Request",
            "HTTP/1.1 403 Forbidden",
            "HTTP/1.1 409 Conflict",
            "HTTP/1.1 413 Content Too Large",
            "HTTP/1.1 413 Payload Too Large",
            "HTTP/1.1 413 Request Entity Too Large",
            "HTTP/1.1 415 Unsupported Media Type",
            "HTTP/1.1 500 Internal Server Error",
            "HTTP/1.1 503 Service Unavailable",
        )

        fun canonicalPort(text: String): Int {
            require(Regex("[1-9][0-9]{0,4}").matches(text))
            return text.toInt().also { require(it in 1..65_535) }
        }

        fun contentLength(text: String): Int {
            val limit = MAX_RESPONSE_BYTES.toString()
            check(text.length <= limit.length)
            check(Regex("0|[1-9][0-9]*").matches(text))
            check(text.length < limit.length || text <= limit)
            return text.toInt()
        }

        fun readHeaders(allowed: Set<String>, nextByte: () -> Int): Map<String, String> {
            val headers = mutableMapOf<String, String>()
            var remaining = MAX_HEADER_BYTES
            while (true) {
                val line = readLine(minOf(remaining, MAX_LINE_BYTES), nextByte)
                remaining -= line.length + 2
                if (line.isEmpty()) break
                check(headers.size < MAX_FIELDS)
                val colon = line.indexOf(':')
                check(colon > 0 && colon + 2 < line.length && line[colon + 1] == ' ')
                val name = line.substring(0, colon).lowercase(Locale.ROOT)
                val value = line.substring(colon + 2)
                check(value.first() != ' ' && value.last() != ' ')
                check(name in allowed && name !in headers)
                headers[name] = value
            }
            check(headers.keys == allowed)
            return headers
        }

        fun readLine(limit: Int, nextByte: () -> Int): String {
            val line = StringBuilder()
            while (line.length + 2 <= limit) {
                val byte = nextByte()
                if (byte == 13) {
                    check(nextByte() == 10)
                    return line.toString()
                }
                check(byte in 32..126)
                line.append(byte.toChar())
            }
            error("Invalid HTTP line")
        }

        fun readBody(input: InputStream, body: ByteArray, beforeRead: () -> Unit) {
            var count = 0
            while (count < body.size) {
                beforeRead()
                val read = input.read(body, count, body.size - count)
                check(read > 0)
                count += read
            }
        }

        fun matchesDigest(bytes: ByteArray, expected: String): Boolean {
            val actual = MessageDigest.getInstance("SHA-256").digest(bytes)
            return actual.joinToString("") { "%02X".format(Locale.ROOT, it.toInt() and 0xff) } == expected
        }

        fun closeSocket(socket: Socket?) {
            try {
                socket?.close()
            } catch (_: IOException) {
                // Closing is best effort. Local authority has already been revoked.
            }
        }
    }
}
