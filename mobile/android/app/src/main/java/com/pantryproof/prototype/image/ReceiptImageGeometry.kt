package com.pantryproof.prototype.image

internal enum class CropEdge { LEFT, TOP, RIGHT, BOTTOM }

/** Bounds in the orientation-corrected image, independent of decode or viewport size. */
@ConsistentCopyVisibility
internal data class ReceiptCrop private constructor(
    val left: Float,
    val top: Float,
    val right: Float,
    val bottom: Float,
) {
    fun values() = floatArrayOf(left, top, right, bottom)

    fun move(dx: Float, dy: Float): ReceiptCrop {
        val x = dx.coerceIn(-left, 1f - right)
        val y = dy.coerceIn(-top, 1f - bottom)
        return ReceiptCrop(left + x, top + y, right + x, bottom + y)
    }

    fun adjust(edge: CropEdge, position: Float): ReceiptCrop = when (edge) {
        CropEdge.LEFT -> copy(left = position.coerceIn(0f, (right - MIN_SPAN).coerceAtLeast(0f)))
        CropEdge.TOP -> copy(top = position.coerceIn(0f, (bottom - MIN_SPAN).coerceAtLeast(0f)))
        CropEdge.RIGHT -> copy(right = position.coerceIn((left + MIN_SPAN).coerceAtMost(1f), 1f))
        CropEdge.BOTTOM -> copy(bottom = position.coerceIn((top + MIN_SPAN).coerceAtMost(1f), 1f))
    }

    companion object {
        private const val MIN_SPAN = 0.08f
        val FULL = ReceiptCrop(0f, 0f, 1f, 1f)

        fun from(values: FloatArray?): ReceiptCrop? {
            if (values == null || values.size != 4 || values.any { it !in 0f..1f }) return null
            val (left, top, right, bottom) = values
            val minimum = MIN_SPAN - 0.00001f
            if (right - left < minimum || bottom - top < minimum) return null
            return ReceiptCrop(left, top, right, bottom)
        }
    }
}

/** Zoom and pan in viewport pixels, always retaining access to the image. */
internal class ReceiptZoom {
    var scale = 1f
        private set
    var offsetX = 0f
        private set
    var offsetY = 0f
        private set
    var fitWidth = 0f
        private set
    var fitHeight = 0f
        private set
    private var viewportWidth = 0f
    private var viewportHeight = 0f

    fun layout(width: Int, height: Int, imageWidth: Int, imageHeight: Int) {
        viewportWidth = width.toFloat()
        viewportHeight = height.toFloat()
        val fit = minOf(viewportWidth / imageWidth, viewportHeight / imageHeight)
        fitWidth = imageWidth * fit
        fitHeight = imageHeight * fit
        clampPan()
    }

    fun zoomBy(factor: Float, x: Float = viewportWidth / 2f, y: Float = viewportHeight / 2f) {
        val next = (scale * factor).coerceIn(1f, MAX_SCALE)
        val ratio = next / scale
        val relativeX = x - viewportWidth / 2f
        val relativeY = y - viewportHeight / 2f
        offsetX = relativeX + (offsetX - relativeX) * ratio
        offsetY = relativeY + (offsetY - relativeY) * ratio
        scale = next
        clampPan()
    }

    fun panBy(dx: Float, dy: Float) {
        offsetX += dx
        offsetY += dy
        clampPan()
    }

    fun reset() {
        scale = 1f
        offsetX = 0f
        offsetY = 0f
    }

    private fun clampPan() {
        val x = ((fitWidth * scale - viewportWidth) / 2f).coerceAtLeast(0f)
        val y = ((fitHeight * scale - viewportHeight) / 2f).coerceAtLeast(0f)
        offsetX = offsetX.coerceIn(-x, x)
        offsetY = offsetY.coerceIn(-y, y)
    }

    companion object {
        const val MAX_SCALE = 4f
    }
}
