package com.pantryproof.prototype.image

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Rect
import android.graphics.RectF
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.hypot

// Programmatically constructed with an image. Native buttons provide an alternative to gestures.
@SuppressLint("ViewConstructor", "ClickableViewAccessibility")
internal class ZoomReceiptView(
    context: Context,
    private val bitmap: Bitmap,
    crop: ReceiptCrop,
) : View(context) {
    private val source = Rect(
        floor(crop.left * bitmap.width).toInt().coerceIn(0, bitmap.width - 1),
        floor(crop.top * bitmap.height).toInt().coerceIn(0, bitmap.height - 1),
        ceil(crop.right * bitmap.width).toInt().coerceIn(1, bitmap.width),
        ceil(crop.bottom * bitmap.height).toInt().coerceIn(1, bitmap.height),
    )
    private val destination = RectF()
    private val paint = Paint(Paint.FILTER_BITMAP_FLAG)
    private val zoom = ReceiptZoom()
    private var lastX = 0f
    private var lastY = 0f
    private val scaling = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScaleBegin(detector: ScaleGestureDetector): Boolean {
            parent?.requestDisallowInterceptTouchEvent(true)
            return true
        }

        override fun onScale(detector: ScaleGestureDetector): Boolean {
            zoom.zoomBy(detector.scaleFactor, detector.focusX, detector.focusY)
            update()
            return true
        }
    }).apply { isQuickScaleEnabled = false }

    val zoomScale: Float get() = zoom.scale
    var onZoomChanged: (Float) -> Unit = {}

    fun changeZoom(factor: Float) {
        zoom.zoomBy(factor)
        update()
    }

    fun resetZoom() {
        zoom.reset()
        update()
    }

    private fun update() {
        invalidate()
        onZoomChanged(zoom.scale)
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        zoom.layout(w, h, source.width(), source.height())
    }

    override fun onDraw(canvas: Canvas) {
        val cx = width / 2f + zoom.offsetX
        val cy = height / 2f + zoom.offsetY
        val hw = zoom.fitWidth * zoom.scale / 2f
        val hh = zoom.fitHeight * zoom.scale / 2f
        destination.set(cx - hw, cy - hh, cx + hw, cy + hh)
        canvas.drawBitmap(bitmap, source, destination, paint)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked == MotionEvent.ACTION_POINTER_DOWN) {
            parent?.requestDisallowInterceptTouchEvent(true)
        }
        scaling.onTouchEvent(event)
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (zoom.scale > 1f) parent?.requestDisallowInterceptTouchEvent(true)
                lastX = event.x
                lastY = event.y
            }
            MotionEvent.ACTION_MOVE -> {
                if (!scaling.isInProgress && event.pointerCount == 1 && zoom.scale > 1f) {
                    zoom.panBy(event.x - lastX, event.y - lastY)
                    invalidate()
                }
                lastX = event.x
                lastY = event.y
            }
            MotionEvent.ACTION_POINTER_UP -> {
                val remaining = if (event.actionIndex == 0) 1 else 0
                lastX = event.getX(remaining)
                lastY = event.getY(remaining)
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL ->
                parent?.requestDisallowInterceptTouchEvent(false)
        }
        return true
    }
}

// Programmatically constructed with an image. Four labeled sliders provide an alternative to gestures.
@SuppressLint("ViewConstructor", "ClickableViewAccessibility")
internal class ReceiptCropView(
    context: Context,
    private val bitmap: Bitmap,
    initial: ReceiptCrop,
) : View(context) {
    private enum class Drag { MOVE, TOP_LEFT, TOP_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT }

    private val image = RectF()
    private val selection = RectF()
    private val shade = Path()
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val density = resources.displayMetrics.density
    private var drag: Drag? = null
    private var lastX = 0f
    private var lastY = 0f
    var crop: ReceiptCrop = initial
        private set
    var onCropChanged: (ReceiptCrop) -> Unit = {}

    fun setCrop(bounds: ReceiptCrop) {
        if (crop == bounds) return
        crop = bounds
        updateSelection()
        invalidate()
        onCropChanged(crop)
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        val inset = 12f * density
        val fit = minOf(
            (w - 2f * inset).coerceAtLeast(0f) / bitmap.width,
            (h - 2f * inset).coerceAtLeast(0f) / bitmap.height,
        )
        val halfWidth = bitmap.width * fit / 2f
        val halfHeight = bitmap.height * fit / 2f
        image.set(w / 2f - halfWidth, h / 2f - halfHeight, w / 2f + halfWidth, h / 2f + halfHeight)
        updateSelection()
    }

    private fun updateSelection() {
        selection.set(
            image.left + crop.left * image.width(), image.top + crop.top * image.height(),
            image.left + crop.right * image.width(), image.top + crop.bottom * image.height(),
        )
    }

    override fun onDraw(canvas: Canvas) {
        paint.style = Paint.Style.FILL
        paint.color = Color.WHITE
        canvas.drawBitmap(bitmap, null, image, paint)
        shade.reset()
        shade.fillType = Path.FillType.EVEN_ODD
        shade.addRect(image, Path.Direction.CW)
        shade.addRect(selection, Path.Direction.CW)
        paint.color = 0xA6000000.toInt()
        canvas.drawPath(shade, paint)
        paint.color = Color.WHITE
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = 2f * density
        canvas.drawRect(selection, paint)
        paint.style = Paint.Style.FILL
        for ((x, y) in listOf(
            selection.left to selection.top, selection.right to selection.top,
            selection.left to selection.bottom, selection.right to selection.bottom,
        )) {
            paint.color = Color.WHITE
            canvas.drawCircle(x, y, 6f * density, paint)
            paint.color = 0xFF176B52.toInt()
            canvas.drawCircle(x, y, 4f * density, paint)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (image.isEmpty) return false
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                val corners = listOf(
                    Drag.TOP_LEFT to hypot(event.x - selection.left, event.y - selection.top),
                    Drag.TOP_RIGHT to hypot(event.x - selection.right, event.y - selection.top),
                    Drag.BOTTOM_LEFT to hypot(event.x - selection.left, event.y - selection.bottom),
                    Drag.BOTTOM_RIGHT to hypot(event.x - selection.right, event.y - selection.bottom),
                )
                val inside = selection.contains(event.x, event.y)
                // Reserve the center for moving even when all four handle targets overlap.
                val insideMoveArea = inside &&
                    abs(event.x - selection.centerX()) <= selection.width() / 4f &&
                    abs(event.y - selection.centerY()) <= selection.height() / 4f
                drag = if (insideMoveArea) Drag.MOVE else {
                    corners.minByOrNull { it.second }?.takeIf { it.second <= 24f * density }?.first
                        ?: Drag.MOVE.takeIf { inside }
                }
                if (drag == null) return false
                lastX = event.x
                lastY = event.y
                parent?.requestDisallowInterceptTouchEvent(true)
            }
            MotionEvent.ACTION_MOVE -> {
                val dx = (event.x - lastX) / image.width()
                val dy = (event.y - lastY) / image.height()
                val updated = when (drag) {
                    Drag.MOVE -> crop.move(dx, dy)
                    Drag.TOP_LEFT -> crop.adjust(CropEdge.LEFT, crop.left + dx).adjust(CropEdge.TOP, crop.top + dy)
                    Drag.TOP_RIGHT -> crop.adjust(CropEdge.RIGHT, crop.right + dx).adjust(CropEdge.TOP, crop.top + dy)
                    Drag.BOTTOM_LEFT -> crop.adjust(CropEdge.LEFT, crop.left + dx).adjust(CropEdge.BOTTOM, crop.bottom + dy)
                    Drag.BOTTOM_RIGHT -> crop.adjust(CropEdge.RIGHT, crop.right + dx).adjust(CropEdge.BOTTOM, crop.bottom + dy)
                    null -> crop
                }
                setCrop(updated)
                lastX = event.x
                lastY = event.y
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                drag = null
                parent?.requestDisallowInterceptTouchEvent(false)
            }
        }
        return true
    }
}
