package com.pantryproof.prototype.data

import com.pantryproof.prototype.contract.review.ReceiptReviewV1Decoder
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import java.io.BufferedInputStream
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.Socket
import java.net.SocketTimeoutException
import java.util.Locale
import java.util.concurrent.FutureTask
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit

/** One direct development HTTP connection per explicit Start. No redirects or replay. */
internal class T09HttpTransport(
    private val session: T09ProcessingConfig.Session,
    private val nowMillis: () -> Long,
    private val preparePng: () -> ByteArray,
    private val onPhase: (ReceiptProcessingRequest, Phase) -> Unit = { _, _ -> },
    private val openSocket: () -> Socket = { Socket(Proxy.NO_PROXY) },
) : ReceiptProcessingTransport, AutoCloseable {
    enum class Phase { PREPARING, UPLOADING, WAITING_FOR_RESULT }

    private class Attempt(
        val request: ReceiptProcessingRequest,
        val deadline: Long,
        val deliver: (ReceiptProcessingDelivery) -> Unit,
    ) {
        var socket: Socket? = null
        var timer: ScheduledFuture<*>? = null
        var task: FutureTask<Unit>? = null
    }

    private val lock = Any()
    private val io = ThreadPoolExecutor(1, 1, 0, TimeUnit.SECONDS, LinkedBlockingQueue())
    private val timers = ScheduledThreadPoolExecutor(1).apply { removeOnCancelPolicy = true }
    private var active: Attempt? = null
    private var closed = false

    override fun submit(
        request: ReceiptProcessingRequest,
        deliver: (ReceiptProcessingDelivery) -> Unit,
    ): ReceiptProcessingTransport.Cancellation {
        val deadline = request.deadlineElapsedMillis
        if (deadline == null || request.context.mode != PresentationConsumerMode.LIVE ||
            !idSyntax.matches(request.context.expectedRequestId) || !idSyntax.matches(request.context.expectedImageId) ||
            request.context.expectedImageId != request.selection.imageId
        ) {
            deliver(ReceiptProcessingDelivery.ExecutionFailure)
            return ReceiptProcessingTransport.Cancellation {}
        }
        val attempt = Attempt(request, deadline, deliver)
        val rejection = synchronized(lock) {
            when {
                closed || active != null || session.credential() == null -> ReceiptProcessingDelivery.ExecutionFailure
                deadline <= nowMillis() -> ReceiptProcessingDelivery.TimedOut
                else -> {
                    active = attempt
                    attempt.task = FutureTask<Unit> { run(attempt) }.also { io.execute(it) }
                    scheduleDeadline(attempt)
                    null
                }
            }
        }
        if (rejection != null) deliver(rejection)
        return ReceiptProcessingTransport.Cancellation { retire(attempt, interrupt = true) }
    }

    /** Caller holds lock. This independent timer closes blocked network I/O. */
    private fun scheduleDeadline(attempt: Attempt) {
        attempt.timer = timers.schedule({
            val expired = synchronized(lock) {
                if (active !== attempt) return@synchronized false
                if (nowMillis() < attempt.deadline) {
                    scheduleDeadline(attempt)
                    false
                } else true
            }
            if (expired && retire(attempt, interrupt = true)) attempt.deliver(ReceiptProcessingDelivery.TimedOut)
        }, (attempt.deadline - nowMillis()).coerceAtLeast(0), TimeUnit.MILLISECONDS)
    }

    private fun run(attempt: Attempt) {
        val outcome = try {
            exchange(attempt)
        } catch (_: SocketTimeoutException) {
            ReceiptProcessingDelivery.TimedOut
        } catch (_: ProtocolException) {
            ReceiptProcessingDelivery.ProtocolFailure
        } catch (_: Exception) {
            ReceiptProcessingDelivery.ExecutionFailure
        }
        if (retire(attempt, interrupt = false)) {
            attempt.deliver(if (nowMillis() >= attempt.deadline) ReceiptProcessingDelivery.TimedOut else outcome)
        }
    }

    private fun exchange(attempt: Attempt): ReceiptProcessingDelivery {
        requireCurrent(attempt)
        onPhase(attempt.request, Phase.PREPARING)
        val prepared = try { preparePng() } catch (_: RuntimeException) { return ReceiptProcessingDelivery.ImageLimit }
        val dimensions: Pair<Int, Int>
        val snapshot = try {
            requireCurrent(attempt)
            dimensions = pngDimensions(prepared) ?: return ReceiptProcessingDelivery.ImageLimit
            ReceiptSubmissionBinding.Snapshot(attempt.request.selection, prepared, MAX_PNG_BYTES)
        } finally {
            prepared.fill(0)
        }
        val png = try {
            snapshot.bind(attempt.request).copyBytes()
        } finally {
            snapshot.release()
        }
        try {
            requireCurrent(attempt)
            val token = checkNotNull(session.credential())
            val headers = buildString {
                append("POST /v1/receipts/process HTTP/1.1\r\n")
                append("Host: ${session.host}:${session.port}\r\n")
                append("Content-Type: image/png\r\nContent-Length: ${png.size}\r\n")
                append("Connection: close\r\n")
                append("X-Request-Id: ${attempt.request.context.expectedRequestId}\r\n")
                append("X-Image-Id: ${attempt.request.context.expectedImageId}\r\n")
                append("X-Response-Schema: ${ReceiptReviewV1Decoder.RESPONSE_SCHEMA}\r\n")
                append("Authorization: Bearer $token\r\n\r\n")
            }.toByteArray(Charsets.US_ASCII)
            try {
                onPhase(attempt.request, Phase.UPLOADING)
                openSocket().use { socket ->
                    synchronized(lock) {
                        check(active === attempt)
                        attempt.socket = socket
                    }
                    requireCurrent(attempt)
                    val address = InetAddress.getByAddress(byteArrayOf(10, 0, 2, 2))
                    socket.connect(InetSocketAddress(address, session.port), remaining(attempt.deadline, CONNECT_MS))
                    requireCurrent(attempt)
                    socket.getOutputStream().apply {
                        write(headers)
                        requireCurrent(attempt)
                        write(png)
                        flush()
                    }
                    requireCurrent(attempt)
                    onPhase(attempt.request, Phase.WAITING_FOR_RESULT)
                    return ResponseReader(socket, attempt.deadline).read(dimensions)
                }
            } finally {
                headers.fill(0)
            }
        } finally {
            png.fill(0)
        }
    }

    private inner class ResponseReader(private val socket: Socket, private val deadline: Long) {
        private val input = BufferedInputStream(socket.getInputStream())
        private var metadataRemaining = 8192

        fun read(dimensions: Pair<Int, Int>): ReceiptProcessingDelivery {
            val code = statusLine.matchEntire(line())?.groupValues?.get(1)?.toInt()
            protocol(code == 200 || code in refusalStatuses)
            val headers = linkedMapOf<String, String>()
            while (true) {
                val field = line()
                if (field.isEmpty()) break
                val colon = field.indexOf(':')
                protocol(colon > 0 && headerName.matches(field.substring(0, colon)) && headers.size < 32)
                val key = field.substring(0, colon).lowercase(Locale.ROOT)
                protocol(headers.put(key, field.substring(colon + 1).trim()) == null)
            }
            protocol("transfer-encoding" !in headers && "content-encoding" !in headers)
            val lengthText = headers["content-length"].orEmpty()
            protocol(lengthText.isNotEmpty() && lengthText.all { it in '0'..'9' })
            val length = lengthText.toIntOrNull() ?: throw ProtocolException()
            if (code != 200) {
                protocol(length == 0 && readByte() == -1)
                return ReceiptProcessingDelivery.HttpRefusal(checkNotNull(code))
            }
            protocol(length in 1..MAX_RESPONSE_BYTES)
            protocol(headers["content-type"].equals("application/json", ignoreCase = true))
            protocol(headers["cache-control"].equals("no-store", ignoreCase = true))
            protocol(headers["connection"].equals("close", ignoreCase = true))
            val body = ByteArray(length)
            try {
                var position = 0
                while (position < length) {
                    socket.soTimeout = remaining(deadline)
                    val count = input.read(body, position, length - position)
                    remaining(deadline)
                    protocol(count > 0)
                    position += count
                }
                protocol(readByte() == -1)
                return ReceiptProcessingDelivery.ReviewEnvelope(body, dimensions.first, dimensions.second)
            } finally {
                body.fill(0)
            }
        }

        private fun line(): String {
            val text = StringBuilder()
            var byte = readByte()
            while (byte != '\r'.code) {
                protocol(byte in 32..126 || byte == '\t'.code)
                protocol(text.length < 2048 && --metadataRemaining >= 0)
                text.append(byte.toChar())
                byte = readByte()
            }
            metadataRemaining -= 2
            protocol(metadataRemaining >= 0 && readByte() == '\n'.code)
            return text.toString()
        }

        private fun readByte(): Int {
            socket.soTimeout = remaining(deadline)
            return input.read().also { remaining(deadline) }
        }

    }

    private class ProtocolException : RuntimeException()

    private fun protocol(valid: Boolean) {
        if (!valid) throw ProtocolException()
    }

    private fun requireCurrent(attempt: Attempt) {
        synchronized(lock) { check(active === attempt) }
        remaining(attempt.deadline)
    }

    private fun remaining(deadline: Long, limit: Int = Int.MAX_VALUE): Int {
        val remaining = deadline - nowMillis()
        if (remaining <= 0) throw SocketTimeoutException()
        return minOf(remaining, limit.toLong()).toInt()
    }

    private fun retire(attempt: Attempt, interrupt: Boolean): Boolean {
        synchronized(lock) {
            if (active !== attempt) return false
            active = null
            attempt.timer?.cancel(false)
            if (interrupt) attempt.task?.let {
                it.cancel(true)
                io.remove(it)
            }
        }
        runCatching { attempt.socket?.close() }
        return true
    }

    override fun close() {
        val attempt = synchronized(lock) {
            if (closed) return
            closed = true
            active
        }
        attempt?.let { retire(it, interrupt = true) }
        timers.shutdownNow()
        io.shutdownNow()
    }

    companion object {
        const val TOTAL_MS = 125_000L
        const val CONNECT_MS = 5_000
        const val MAX_PNG_BYTES = 4_194_304
        const val MAX_RESPONSE_BYTES = ReceiptReviewV1Decoder.MAX_BYTES
        private val refusalStatuses = setOf(400, 401, 406, 413, 415, 422, 429, 500, 503, 504)
        private val headerName = Regex("[A-Za-z0-9-]+")
        private val pngSignature = byteArrayOf(-119, 80, 78, 71, 13, 10, 26, 10)
        private val idSyntax = Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
        private val statusLine = Regex("HTTP/1\\.[01] ([0-9]{3})(?: .*)?")

        internal fun pngDimensions(png: ByteArray): Pair<Int, Int>? {
            if (png.size !in 33..MAX_PNG_BYTES || !pngSignature.indices.all { png[it] == pngSignature[it] }) return null
            fun word(at: Int): Int = (0..3).fold(0) { value, index -> (value shl 8) or (png[at + index].toInt() and 255) }
            val width = word(16)
            val height = word(20)
            if (word(8) != 13 || word(12) != 0x49484452 || width !in 1..1600 || height !in 1..1600) return null
            return width to height
        }
    }
}
