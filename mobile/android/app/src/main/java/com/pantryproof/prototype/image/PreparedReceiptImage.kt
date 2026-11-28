package com.pantryproof.prototype.image

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri

/** Owns the acquisition bytes and the exact independently prepared submission for one preview. */
internal class PreparedReceiptImage {
    private var retired = false
    private var original: ByteArray? = null
    private var submitted: ByteArray? = null
    @Volatile var bitmap: Bitmap? = null
        private set

    fun prepare(encoder: SelectedImageSnapshotEncoder, uri: Uri, crop: ReceiptCrop): Boolean {
        val acquisition = encoder.readOriginal(uri)
        var png: ByteArray? = null
        var adopted = false
        try {
            png = encoder.encodeBytes(acquisition, crop)
            val preview = BitmapFactory.decodeByteArray(png, 0, png.size) ?: return false
            return synchronized(this) {
                if (retired) {
                    preview.recycle()
                    return@synchronized false
                }
                original = acquisition
                submitted = png
                bitmap = preview
                adopted = true
                true
            }
        } finally {
            if (!adopted) {
                acquisition.fill(0)
                png?.fill(0)
            }
        }
    }

    @Synchronized fun uploadBytes(): ByteArray = checkNotNull(submitted).copyOf()
    @Synchronized fun originalBytes(): ByteArray? = original?.copyOf()

    @Synchronized fun release() {
        retired = true
        original?.fill(0)
        submitted?.fill(0)
        original = null
        submitted = null
        bitmap = null
    }
}
