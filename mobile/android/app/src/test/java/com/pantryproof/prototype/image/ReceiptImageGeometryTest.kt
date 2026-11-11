package com.pantryproof.prototype.image

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class ReceiptImageGeometryTest {
    @Test
    fun cropRestoreRejectsInvalidOrInvertedCoordinates() {
        for (bounds in listOf(
            floatArrayOf(),
            floatArrayOf(Float.NaN, 0f, 1f, 1f),
            floatArrayOf(-0.1f, 0f, 1f, 1f),
            floatArrayOf(0.8f, 0f, 0.2f, 1f),
            floatArrayOf(0f, 0f, 0.02f, 1f),
        )) {
            assertNull(ReceiptCrop.from(bounds))
        }
        assertEquals(ReceiptCrop.FULL, ReceiptCrop.from(ReceiptCrop.FULL.values()))
    }

    @Test
    fun cropEdgesAndMovementStayInsideImage() {
        val initial = requireNotNull(ReceiptCrop.from(floatArrayOf(0.2f, 0.3f, 0.8f, 0.7f)))
        val moved = initial.move(2f, -2f)
        assertEquals(1f, moved.right, 0.0001f)
        assertEquals(0f, moved.top, 0.0001f)
        assertEquals(initial.right - initial.left, moved.right - moved.left, 0.0001f)
        val resized = moved.adjust(CropEdge.LEFT, 5f).adjust(CropEdge.BOTTOM, -5f)
        assertEquals(0.08f, resized.right - resized.left, 0.0001f)
        assertEquals(0.08f, resized.bottom - resized.top, 0.0001f)
        assertNotNull(ReceiptCrop.from(resized.values()))
    }

    @Test
    fun zoomFitsBoundsPanAndResets() {
        val zoom = ReceiptZoom()
        zoom.layout(300, 300, 120, 240)
        assertEquals(150f, zoom.fitWidth, 0.0001f)
        assertEquals(300f, zoom.fitHeight, 0.0001f)
        zoom.zoomBy(10f, 75f, 75f)
        assertEquals(ReceiptZoom.MAX_SCALE, zoom.scale, 0.0001f)
        zoom.panBy(3000f, -3000f)
        assertEquals(150f, zoom.offsetX, 0.0001f)
        assertEquals(-450f, zoom.offsetY, 0.0001f)
        zoom.zoomBy(0.5f)
        assertEquals(2f, zoom.scale, 0.0001f)
        assertEquals(0f, zoom.offsetX, 0.0001f)
        zoom.zoomBy(0.01f)
        assertEquals(1f, zoom.scale, 0.0001f)
        zoom.zoomBy(3f)
        zoom.panBy(30f, 40f)
        zoom.reset()
        assertEquals(1f, zoom.scale, 0.0001f)
        assertEquals(0f, zoom.offsetX, 0.0001f)
        assertEquals(0f, zoom.offsetY, 0.0001f)
    }
}
