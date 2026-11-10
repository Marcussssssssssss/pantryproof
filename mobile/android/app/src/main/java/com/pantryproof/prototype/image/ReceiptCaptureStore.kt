package com.pantryproof.prototype.image

import android.content.Context
import android.net.Uri
import androidx.core.content.FileProvider
import java.io.File

/** Owns only temporary camera outputs inside the application's cache directory. */
class ReceiptCaptureStore(private val context: Context) {
    data class Target(
        val uri: Uri,
        val fileName: String,
    )

    private val captureDirectory = File(context.cacheDir, DIRECTORY_NAME)

    fun createTarget(): Target {
        check(captureDirectory.exists() || captureDirectory.mkdirs()) {
            "Unable to create the receipt camera cache directory."
        }
        val file = File.createTempFile(FILE_PREFIX, FILE_SUFFIX, captureDirectory)
        return try {
            Target(
                uri = FileProvider.getUriForFile(
                    context,
                    "${context.packageName}.fileprovider",
                    file,
                ),
                fileName = file.name,
            )
        } catch (error: RuntimeException) {
            file.delete()
            throw error
        }
    }

    fun uriFor(fileName: String?): Uri? {
        val file = ownedFile(fileName) ?: return null
        if (!file.isFile) return null
        return runCatching {
            FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                file,
            )
        }.getOrNull()
    }

    fun delete(fileName: String?) {
        ownedFile(fileName)?.takeIf(File::isFile)?.delete()
    }

    fun cleanupOrphans(retainedFileNames: Set<String>) {
        val retained = retainedFileNames.filter(::isSafeFileName).toSet()
        captureDirectory.listFiles().orEmpty().forEach { file ->
            if (file.isFile && file.name !in retained) file.delete()
        }
    }

    private fun ownedFile(fileName: String?): File? {
        if (fileName == null || !isSafeFileName(fileName)) return null
        val candidate = File(captureDirectory, fileName)
        return candidate.takeIf {
            runCatching { it.canonicalFile.parentFile == captureDirectory.canonicalFile }
                .getOrDefault(false)
        }
    }

    private fun isSafeFileName(fileName: String): Boolean =
        File(fileName).name == fileName &&
            fileName.startsWith(FILE_PREFIX) &&
            fileName.endsWith(FILE_SUFFIX)

    private companion object {
        const val DIRECTORY_NAME = "receipt_camera"
        const val FILE_PREFIX = "receipt-"
        const val FILE_SUFFIX = ".jpg"
    }
}
