package com.pantryproof.prototype.image

import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import android.net.Uri
import android.os.Looper
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.OutputStream
import java.io.InputStream
import java.io.SequenceInputStream
import kotlin.math.ceil
import kotlin.math.floor

/** Bounded sampled PNG, cropped in Preview's orientation-corrected coordinate space.
 * No disk output or EXIF metadata is retained. This is not a full-resolution snapshot.
 */
internal class SelectedImageSnapshotEncoder(private val resolver: ContentResolver) {
    class ImageInputException : RuntimeException("Selected image cannot be prepared within the local limits.")

    fun encode(uri: Uri, crop: ReceiptCrop): ByteArray {
        val source = readOriginal(uri)
        return try { encodeBytes(source, crop) } finally { source.fill(0) }
    }

    fun readOriginal(uri: Uri): ByteArray {
        checkWorker()
        return try {
            resolver.openInputStream(uri)?.use { input ->
                val output = ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    if (output.size().toLong() + count > MAX_SOURCE_BYTES) throw ImageInputException()
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            } ?: throw ImageInputException()
        } catch (_: Exception) {
            throw ImageInputException()
        } catch (_: OutOfMemoryError) {
            throw ImageInputException()
        }
    }

    /** Also used by device tests with generated fictional pixels. Caller owns source until return. */
    fun encodeBytes(source: ByteArray, crop: ReceiptCrop): ByteArray {
        checkWorker()
        val owned = mutableListOf<Bitmap>()
        try {
            if (source.isEmpty() || source.size > MAX_SOURCE_BYTES) throw ImageInputException()
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(source, 0, source.size, bounds)
            if (bounds.outWidth !in 1..MAX_SOURCE_DIMENSION || bounds.outHeight !in 1..MAX_SOURCE_DIMENSION ||
                bounds.outWidth.toLong() * bounds.outHeight > MAX_SOURCE_PIXELS ||
                bounds.outMimeType !in setOf("image/jpeg", "image/png", "image/webp")
            ) throw ImageInputException()
            rejectUnsupportedExif(source, bounds.outMimeType)
            var sample = 1
            while ((bounds.outWidth + sample - 1) / sample > MAX_DECODED_DIMENSION ||
                (bounds.outHeight + sample - 1) / sample > MAX_DECODED_DIMENSION
            ) sample *= 2
            val options = BitmapFactory.Options().apply {
                inSampleSize = sample
                inPreferredConfig = Bitmap.Config.ARGB_8888
            }
            val decoded = BitmapFactory.decodeByteArray(source, 0, source.size, options)
                ?: throw ImageInputException()
            owned.add(decoded)
            if (decoded.width > MAX_DECODED_DIMENSION || decoded.height > MAX_DECODED_DIMENSION ||
                decoded.allocationByteCount > MAX_SINGLE_BITMAP_BYTES
            ) throw ImageInputException()
            val orientation = ByteArrayInputStream(source).use { readOrientation(it) }
            val matrix = Matrix().apply {
                when (orientation) {
                    ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> setScale(-1f, 1f)
                    ExifInterface.ORIENTATION_ROTATE_180 -> setRotate(180f)
                    ExifInterface.ORIENTATION_FLIP_VERTICAL -> setScale(1f, -1f)
                    ExifInterface.ORIENTATION_TRANSPOSE -> { setRotate(90f); postScale(-1f, 1f) }
                    ExifInterface.ORIENTATION_ROTATE_90 -> setRotate(90f)
                    ExifInterface.ORIENTATION_TRANSVERSE -> { setRotate(-90f); postScale(-1f, 1f) }
                    ExifInterface.ORIENTATION_ROTATE_270 -> setRotate(-90f)
                }
            }
            val oriented = if (matrix.isIdentity) decoded else
                Bitmap.createBitmap(decoded, 0, 0, decoded.width, decoded.height, matrix, true)
                    .also { owned.add(it) }
            val left = floor(crop.left * oriented.width).toInt().coerceIn(0, oriented.width - 1)
            val top = floor(crop.top * oriented.height).toInt().coerceIn(0, oriented.height - 1)
            val right = ceil(crop.right * oriented.width).toInt().coerceIn(left + 1, oriented.width)
            val bottom = ceil(crop.bottom * oriented.height).toInt().coerceIn(top + 1, oriented.height)
            val cropped = Bitmap.createBitmap(oriented, left, top, right - left, bottom - top)
            if (cropped !== oriented) owned.add(cropped)
            val output = ByteArrayOutputStream()
            val limited = object : OutputStream() {
                override fun write(value: Int) {
                    if (output.size() >= MAX_RETAINED_BYTES) throw ImageInputException()
                    output.write(value)
                }
                override fun write(bytes: ByteArray, offset: Int, count: Int) {
                    if (output.size().toLong() + count > MAX_RETAINED_BYTES) throw ImageInputException()
                    output.write(bytes, offset, count)
                }
            }
            if (!cropped.compress(Bitmap.CompressFormat.PNG, 100, limited) || output.size() == 0) {
                throw ImageInputException()
            }
            return output.toByteArray()
        } catch (_: Exception) {
            throw ImageInputException()
        } catch (_: OutOfMemoryError) {
            throw ImageInputException()
        } finally {
            owned.distinct().forEach { if (!it.isRecycled) it.recycle() }
        }
    }

    private fun checkWorker() { check(Looper.myLooper() !== Looper.getMainLooper()) }

    /** API 26 cannot orient PNG/WebP EXIF. Reject that combination instead of ignoring it. */
    private fun rejectUnsupportedExif(bytes: ByteArray, mime: String) {
        if (mime == "image/jpeg") return
        val png = mime == "image/png"
        var offset = if (png) 8 else 12
        while (offset + (if (png) 12 else 8) <= bytes.size) {
            val typeOffset = offset + (if (png) 4 else 0)
            val type = String(bytes, typeOffset, 4, Charsets.US_ASCII)
            if (type == (if (png) "eXIf" else "EXIF")) throw ImageInputException()
            val sizeOffset = offset + (if (png) 0 else 4)
            var length = 0L
            for (index in 0..3) {
                val byte = bytes[sizeOffset + index].toInt() and 255
                length = length or (byte.toLong() shl (8 * (if (png) 3 - index else index)))
            }
            val end = offset.toLong() + length + (if (png) 12L else 8L + (length % 2))
            if (end > bytes.size || end <= offset) throw ImageInputException()
            offset = end.toInt()
            if (png && type == "IEND") break
        }
    }

    companion object {
        /** API 26's format probe requires a single full 5000-byte read, even for a tiny JPEG.
         * Supply a filled prefix to the metadata reader only. Original image bytes are untouched.
         * Preview and snapshot encoding deliberately share this orientation interpretation.
         */
        fun readOrientation(input: InputStream): Int = runCatching {
            val prefix = ByteArray(5000)
            var used = 0
            while (used < prefix.size) {
                val count = input.read(prefix, used, prefix.size - used)
                if (count < 0) break
                if (count == 0) {
                    val value = input.read()
                    if (value < 0) break
                    prefix[used++] = value.toByte()
                } else used += count
            }
            val head = ByteArrayInputStream(prefix)
            val metadata = object : SequenceInputStream(head, input) {
                override fun available(): Int =
                    (head.available().toLong() + input.available().coerceAtLeast(0))
                        .coerceAtMost(Int.MAX_VALUE.toLong()).toInt()
            }
            metadata.use {
                ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
            }
        }.getOrDefault(ExifInterface.ORIENTATION_NORMAL)

        const val MAX_SOURCE_BYTES = 16 * 1024 * 1024
        const val MAX_SOURCE_DIMENSION = 16_384
        const val MAX_SOURCE_PIXELS = 64_000_000L
        const val MAX_DECODED_DIMENSION = 1600
        const val MAX_SINGLE_BITMAP_BYTES = MAX_DECODED_DIMENSION * MAX_DECODED_DIMENSION * 4
        const val MAX_BITMAP_BYTES = MAX_SINGLE_BITMAP_BYTES * 3
        const val MAX_RETAINED_BYTES = 4 * 1024 * 1024
    }
}
