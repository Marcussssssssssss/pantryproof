package com.pantryproof.prototype.data

import android.content.Context
import java.io.IOException
import java.nio.file.Files
import java.nio.file.NoSuchFileException
import java.nio.file.Path
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import java.nio.channels.FileChannel
import java.nio.file.StandardOpenOption.READ
import java.time.DateTimeException
import java.util.UUID
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
        private const val LEGACY_VERSION = 1
        private const val VERSION = 2
        private val lock = Any()
        private val digestSyntax = Regex("[0-9a-f]{64}")
        private val oldLiveRow = Regex("live-receipt-([0-9a-f]{64})-.+")
        private val sidecar = Regex("saved-receipt-[0-9a-f-]{36}\\.(review|original)")
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

    internal enum class Commit { COMMITTED, REPLAYED, CONFLICT, FAILED }

    private data class Snapshot(
        val rows: List<InventoryItem> = emptyList(),
        val history: List<PurchaseRecord> = emptyList(),
        val ledger: Map<String, String> = emptyMap(),
        val legacy: Set<String> = emptySet(),
        val pendingAcknowledgements: Set<String> = emptySet(),
    )

    override fun load(): List<InventoryItem>? = synchronized(lock) {
        storageResult { readSnapshot().rows }
    }

    override fun update(change: (List<InventoryItem>) -> List<InventoryItem>?): List<InventoryItem>? =
        synchronized(lock) {
            storageResult {
                val current = readSnapshot()
                val updated = change(current.rows) ?: return@storageResult null
                if (updated != current.rows) writeSnapshot(current.copy(rows = updated))
                updated
            }
        }

    fun commit(plan: ReceiptConfirmation, evidence: ByteArray, original: ByteArray?): Commit = synchronized(lock) {
        storageResult {
            val current = readSnapshot()
            val fingerprint = plan.fingerprint()
            current.ledger[plan.identity]?.let { return@storageResult if (it == fingerprint) Commit.REPLAYED else Commit.CONFLICT }
            if (plan.legacyIdentity in current.legacy) return@storageResult Commit.CONFLICT
            require(digestSyntax.matches(plan.identity) && digestSyntax.matches(plan.legacyIdentity))
            require(plan.stock.isNotEmpty() && plan.stock.all { it.id.startsWith("$LIVE_ROW_PREFIX${plan.identity}-") &&
                it.unit != InventoryUnit.UNKNOWN && it.quantity.signum() > 0 })
            require(plan.decisions.filter { it.second }.map { "$LIVE_ROW_PREFIX${plan.identity}-${it.first}" } == plan.stock.map { it.id })
            require(plan.evidenceDigest == sha256(evidence))
            require((plan.mode == ReceiptConfirmationMode.INVENTORY_AND_RECEIPT) == (plan.history != null))
            require(!plan.keepOriginal || plan.history != null && original != null)
            val staged = mutableListOf<Path>()
            var published = false
            try {
                val history = plan.history?.let { record ->
                    require(record.confirmationId == plan.identity && record.evidenceFile == null && record.originalFile == null)
                    val evidenceFile = stage("review", evidence, staged)
                    val originalFile = if (plan.keepOriginal) stage("original", requireNotNull(original), staged) else null
                    syncDirectory()
                    record.copy(evidenceFile = evidenceFile, originalFile = originalFile)
                }
                val next = current.copy(
                    rows = current.rows + plan.stock,
                    history = current.history + listOfNotNull(history),
                    ledger = current.ledger + (plan.identity to fingerprint),
                    pendingAcknowledgements = current.pendingAcknowledgements + plan.identity,
                )
                writeSnapshot(next)
                published = true
                Commit.COMMITTED
            } finally {
                if (!published && staged.isNotEmpty()) {
                    // A replace interrupted after rename can leave the new snapshot visible.
                    // If the snapshot cannot be read, defer ownership checks to recovery.
                    storageResult { readSnapshot() }?.let { observed ->
                        val retained = referencedFiles(observed)
                        staged.filterNot { it.fileName.toString() in retained }
                            .forEach { storageResult { Files.deleteIfExists(it) } }
                    }
                }
            }
        } ?: Commit.FAILED
    }

    fun history(): List<PurchaseRecord>? = synchronized(lock) { storageResult { readSnapshot().history } }

    fun recover(): Set<String>? = synchronized(lock) {
        storageResult {
            val snapshot = readSnapshot()
            cleanDetached(snapshot)
            snapshot.pendingAcknowledgements
        }
    }

    fun acknowledge(ids: Set<String>): Boolean = synchronized(lock) {
        storageResult {
            val current = readSnapshot()
            val remaining = current.pendingAcknowledgements - ids
            if (remaining != current.pendingAcknowledgements) writeSnapshot(current.copy(pendingAcknowledgements = remaining))
            true
        } ?: false
    }

    fun deleteHistory(identity: String): Boolean = synchronized(lock) {
        storageResult {
            val current = readSnapshot()
            val next = current.copy(history = current.history.filterNot { it.confirmationId == identity })
            if (next == current) return@storageResult false
            writeSnapshot(next)
            cleanDetached(next)
            true
        } ?: false
    }

    fun originalFile(identity: String): java.io.File? = synchronized(lock) {
        storageResult { readSnapshot().history.firstOrNull { it.confirmationId == identity }?.originalFile
            ?.let(file::resolveSibling)?.toFile()?.takeIf { it.isFile } }
    }

    private fun stage(extension: String, bytes: ByteArray, staged: MutableList<Path>): String {
        require(bytes.isNotEmpty())
        val name = "saved-receipt-${UUID.randomUUID()}.$extension"
        val path = Files.createFile(file.resolveSibling(name))
        staged.add(path)
        writeDurable(path, bytes)
        return name
    }

    private fun cleanDetached(snapshot: Snapshot) {
        val referenced = referencedFiles(snapshot)
        storageResult {
            Files.newDirectoryStream(file.parent).use { paths ->
                paths.forEach { path ->
                    val name = path.fileName.toString()
                    if (sidecar.matches(name) && name !in referenced ||
                        name.startsWith("manual-inventory-") && name.endsWith(".pending")
                    ) storageResult { Files.deleteIfExists(path) }
                }
            }
        }
    }

    private fun referencedFiles(snapshot: Snapshot) =
        snapshot.history.flatMap { listOfNotNull(it.evidenceFile, it.originalFile) }.toSet()

    private fun readSnapshot(): Snapshot {
        val bytes = try {
            Files.readAllBytes(file)
        } catch (_: NoSuchFileException) {
            return Snapshot()
        }
        val input = JSONTokener(bytes.toString(Charsets.UTF_8))
        val document = input.nextValue() as? JSONObject ?: throw JSONException("Expected an object")
        require(input.nextClean() == '\u0000')
        val version = document.get("version")
        require(version == LEGACY_VERSION || version == VERSION)
        val rows = document.getJSONArray("rows")
        val inventory = List(rows.length()) { index ->
            val row = rows.getJSONObject(index)
            val id = row.get("id") as? String ?: throw JSONException("Expected an item ID")
            val unit = if (version == LEGACY_VERSION) InventoryUnit.UNKNOWN else
                InventoryUnit.fromCode(row.get("unit") as? String ?: throw JSONException("Expected a unit"))
                    ?: throw JSONException("Unknown stock unit")
            val quantity = if (version == LEGACY_VERSION) {
                val whole = row.get("quantity") as? Int ?: throw JSONException("Expected a whole quantity")
                whole.toBigDecimal()
            } else {
                val text = row.get("quantity") as? String ?: throw JSONException("Expected a decimal string")
                unit.parse(text)?.takeIf { it.toPlainString() == text }
                    ?: throw JSONException("Invalid stock quantity")
            }
            InventoryItem(
                id = id,
                name = row.get("name") as? String ?: throw JSONException("Expected an item name"),
                quantity = quantity,
                state = rowState(id) ?: throw JSONException("Unrecognized item ID"),
                unit = unit,
            )
        }.also(::validate)
        if (version == LEGACY_VERSION) {
            return Snapshot(rows = inventory, legacy = inventory.mapNotNull { oldLiveRow.matchEntire(it.id)?.groupValues?.get(1) }.toSet())
        }
        val ledger = document.getJSONObject("ledger").let { values -> values.keys().asSequence().associateWith(values::getString) }
        val history = document.getJSONArray("history").objects().map(PurchaseRecord::read)
        val legacy = document.getJSONArray("legacy").strings().toSet()
        val pending = document.getJSONArray("pendingAcknowledgements").strings().toSet()
        return Snapshot(inventory, history, ledger, legacy, pending).also(::validateSnapshot)
    }

    private fun writeSnapshot(snapshot: Snapshot) {
        validateSnapshot(snapshot)
        val encodedRows = JSONArray()
        snapshot.rows.forEach { row ->
            encodedRows.put(JSONObject().put("id", row.id).put("name", row.name)
                .put("quantity", row.quantity.toPlainString()).put("unit", row.unit.code))
        }
        val bytes = JSONObject().put("version", VERSION).put("rows", encodedRows)
            .put("history", JSONArray(snapshot.history.map(PurchaseRecord::json)))
            .put("ledger", JSONObject(snapshot.ledger))
            .put("legacy", JSONArray(snapshot.legacy.toList()))
            .put("pendingAcknowledgements", JSONArray(snapshot.pendingAcknowledgements.toList()))
            .toString().toByteArray(Charsets.UTF_8)

        // Sync a sibling file before publishing it. A failed write or move leaves the old snapshot in place.
        val pending = Files.createTempFile(file.parent, "manual-inventory-", ".pending")
        try {
            writeDurable(pending, bytes)
            replace(pending, file)
            // A successful rename is already visible. Directory sync strengthens crash durability.
            storageResult { syncDirectory() }
        } finally {
            // After a successful move this path is already gone.
            storageResult { Files.deleteIfExists(pending) }
        }
    }

    private fun writeDurable(path: Path, bytes: ByteArray) = path.toFile().outputStream().use { stream ->
        stream.write(bytes)
        stream.fd.sync()
    }

    private fun syncDirectory() = FileChannel.open(file.parent, READ).use { it.force(true) }

    private fun validateSnapshot(snapshot: Snapshot) {
        validate(snapshot.rows)
        require(snapshot.ledger.all { (id, hash) -> digestSyntax.matches(id) && digestSyntax.matches(hash) })
        require(snapshot.legacy.all(digestSyntax::matches) && snapshot.pendingAcknowledgements.all(snapshot.ledger::containsKey))
        val receipts = hashSetOf<String>()
        val files = hashSetOf<String>()
        snapshot.history.forEach { record ->
            require(receipts.add(record.confirmationId) && record.confirmationId in snapshot.ledger)
            require(record.store.isNotBlank() && record.date.year in 1..9999 && validMoney(record.total))
            require(record.rows.isNotEmpty() && record.rows.any(PurchasedRow::included) &&
                record.rows.map(PurchasedRow::id).distinct().size == record.rows.size)
            record.rows.forEach { row ->
                require(row.id.isNotBlank() && row.description.isNotBlank() && row.quantity.signum() > 0 &&
                    row.quantity.scale() in 0..3 && validMoney(row.lineTotal))
                require((row.unitPrice == null) == !row.unitPriceAbsence.isNullOrBlank() &&
                    (row.unitPrice == null || validMoney(row.unitPrice)))
                require(!row.included || row.inventoryUnit?.let { it != InventoryUnit.UNKNOWN && it.represents(row.quantity) } == true)
            }
            require(record.evidenceFile?.let { sidecar.matches(it) && it.endsWith(".review") && files.add(it) } == true)
            require(record.originalFile?.let { sidecar.matches(it) && it.endsWith(".original") && files.add(it) } != false)
        }
    }

    private fun validMoney(value: java.math.BigDecimal) = value.signum() >= 0 && value.scale() == 2

    private fun JSONArray.strings(): List<String> = List(length()) { get(it) as String }

    private fun validate(rows: List<InventoryItem>) {
        val ids = mutableSetOf<String>()
        for (row in rows) {
            require(ids.add(row.id))
            require(row.name.isNotBlank() && row.unit.stores(row.quantity))
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
    } catch (_: DateTimeException) {
        null
    } catch (_: ClassCastException) {
        null
    } catch (_: SecurityException) {
        null
    }
}
