package com.pantryproof.prototype.data

import android.content.Context
import java.io.IOException
import java.nio.file.Files
import java.nio.file.NoSuchFileException
import java.nio.file.Path
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import org.json.JSONTokener

internal interface ManualInventoryPersistence {
    /** An empty list means no stock has been saved. Null means the snapshot could not be read. */
    fun load(): List<InventoryItem>?

    /** Transform the latest committed rows. Null rejects the change or reports a storage failure. */
    fun update(change: (List<InventoryItem>) -> List<InventoryItem>?): List<InventoryItem>?
}

internal class ManualInventoryStore(
    private val file: Path,
    private val replace: (Path, Path) -> Unit = { pending, target ->
        Files.move(pending, target, ATOMIC_MOVE, REPLACE_EXISTING)
    },
) : ManualInventoryPersistence {
    constructor(context: Context) : this(context.filesDir.toPath().resolve(FILE_NAME))

    companion object {
        private const val FILE_NAME = "manual-inventory.json"
        private const val VERSION = 1
        private val lock = Any()
        const val ROW_PREFIX = "manual-receipt-"
        const val ROW_STATE = "Manually entered receipt"
        const val LIVE_ROW_PREFIX = "live-receipt-"
        const val LIVE_ROW_STATE = "Confirmed receipt scan"
        const val STANDALONE_ROW_PREFIX = "manual-inventory-"
        const val STANDALONE_ROW_STATE = "Added directly to inventory"
        const val MIN_QUANTITY = 0
        const val MAX_QUANTITY = 99

        fun isDurableRowId(id: String): Boolean = rowState(id) != null

        private fun rowState(id: String): String? = when {
            id.startsWith(ROW_PREFIX) && id.removePrefix(ROW_PREFIX).isNotBlank() -> ROW_STATE
            id.startsWith(LIVE_ROW_PREFIX) && id.removePrefix(LIVE_ROW_PREFIX).isNotBlank() -> LIVE_ROW_STATE
            id.startsWith(STANDALONE_ROW_PREFIX) && id.removePrefix(STANDALONE_ROW_PREFIX).isNotBlank() ->
                STANDALONE_ROW_STATE
            else -> null
        }
    }

    override fun load(): List<InventoryItem>? = synchronized(lock) {
        storageResult { readSnapshot() }
    }

    override fun update(change: (List<InventoryItem>) -> List<InventoryItem>?): List<InventoryItem>? =
        synchronized(lock) {
            storageResult {
                val current = readSnapshot()
                val updated = change(current) ?: return@storageResult null
                if (updated != current) writeSnapshot(updated)
                updated
            }
        }

    private fun readSnapshot(): List<InventoryItem> {
        val bytes = try {
            Files.readAllBytes(file)
        } catch (_: NoSuchFileException) {
            return emptyList()
        }
        val input = JSONTokener(bytes.toString(Charsets.UTF_8))
        val document = input.nextValue() as? JSONObject ?: throw JSONException("Expected an object")
        require(input.nextClean() == '\u0000')
        require(document.get("version") == VERSION)
        val rows = document.getJSONArray("rows")
        return List(rows.length()) { index ->
            val row = rows.getJSONObject(index)
            val id = row.get("id") as? String ?: throw JSONException("Expected an item ID")
            InventoryItem(
                id = id,
                name = row.get("name") as? String ?: throw JSONException("Expected an item name"),
                quantity = row.get("quantity") as? Int ?: throw JSONException("Expected a whole quantity"),
                state = rowState(id) ?: throw JSONException("Unrecognized item ID"),
            )
        }.also(::validate)
    }

    private fun writeSnapshot(rows: List<InventoryItem>) {
        validate(rows)
        val encodedRows = JSONArray()
        rows.forEach { row ->
            encodedRows.put(JSONObject().put("id", row.id).put("name", row.name).put("quantity", row.quantity))
        }
        val bytes = JSONObject().put("version", VERSION).put("rows", encodedRows)
            .toString().toByteArray(Charsets.UTF_8)

        // Sync a sibling file before publishing it. A failed write or move leaves the old snapshot in place.
        val pending = Files.createTempFile(file.parent, "manual-inventory-", ".pending")
        try {
            pending.toFile().outputStream().use { stream ->
                stream.write(bytes)
                stream.fd.sync()
            }
            replace(pending, file)
        } finally {
            // After a successful move this path is already gone.
            storageResult { Files.deleteIfExists(pending) }
        }
    }

    private fun validate(rows: List<InventoryItem>) {
        val ids = mutableSetOf<String>()
        for (row in rows) {
            require(ids.add(row.id))
            require(row.name.isNotBlank() && row.quantity in MIN_QUANTITY..MAX_QUANTITY)
            require(row.state == rowState(row.id))
        }
    }

    private inline fun <T> storageResult(block: () -> T): T? = try {
        block()
    } catch (_: IOException) {
        null
    } catch (_: JSONException) {
        null
    } catch (_: IllegalArgumentException) {
        null
    } catch (_: SecurityException) {
        null
    }
}
