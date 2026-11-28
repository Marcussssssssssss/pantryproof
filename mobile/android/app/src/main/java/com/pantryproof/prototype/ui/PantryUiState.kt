package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryUnit
import com.pantryproof.prototype.data.ManualInventoryPersistence
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.data.Receipt
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.data.ReceiptPresentationSource
import com.pantryproof.prototype.data.ReceiptConfirmation
import com.pantryproof.prototype.data.PurchaseRecord
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.PresentationSourceType
import java.math.BigDecimal
import java.time.LocalDate
import java.util.UUID

class PantryUiState internal constructor(
    private val source: ReceiptPresentationSource,
    private val manualInventory: ManualInventoryPersistence?,
    private val today: () -> LocalDate = LocalDate::now,
) {
    constructor(source: ReceiptPresentationSource) : this(source, null)

    enum class InventoryChange { SAVED, INVALID_NAME, INVALID_QUANTITY, NOT_SAVED }

    companion object {
        const val MIN_INVENTORY_QUANTITY = ManualInventoryStore.MIN_QUANTITY
        const val MAX_INVENTORY_QUANTITY = ManualInventoryStore.MAX_QUANTITY
        const val MANUAL_ROW_PREFIX = ManualInventoryStore.ROW_PREFIX
        internal val maximumStock = MAX_INVENTORY_QUANTITY.toBigDecimal()
    }

    var presentationResult: ReceiptPresentationUiResult = source.syntheticPresentation()
        private set

    var receipt: Receipt? = inventoryCompatibleReceipt(presentationResult)
        private set

    var inventory: MutableList<InventoryItem> = source.syntheticInventory().toMutableList()
        private set

    var demoConfirmed: Boolean = false
        private set

    var manualInventoryLoadFailed: Boolean = false
        private set

    init {
        if (manualInventory != null) {
            val committed = manualInventory.load()
            manualInventoryLoadFailed = committed == null
            if (committed != null) inventory.addAll(committed)
        }
    }

    fun applyReceipt(updated: Receipt) {
        if (presentationResult !is ReceiptPresentationUiResult.Available) return
        receipt = updated
        demoConfirmed = false
        inventory.removeAll { it.id.startsWith("receipt-") }
    }

    fun revertReceipt() {
        presentationResult = source.syntheticPresentation()
        receipt = inventoryCompatibleReceipt(presentationResult)
        demoConfirmed = false
        inventory.removeAll { it.id.startsWith("receipt-") }
    }

    fun confirmForInventoryPreview(): Boolean {
        val confirmedReceipt = receipt ?: return false
        if (presentationResult !is ReceiptPresentationUiResult.Available) return false
        if (confirmedReceipt.items.any { it.quantity !in 1..MAX_INVENTORY_QUANTITY }) return false
        val adjustedStockById = inventory
            .filterNot { it.id.startsWith("receipt-") }
            .associateBy(InventoryItem::id)
        val existingStock = source.syntheticInventory().map { baseline ->
            adjustedStockById[baseline.id]?.let { adjusted ->
                baseline.copy(quantity = adjusted.quantity)
            } ?: baseline
        }
        val receiptPreview = confirmedReceipt.items.map { item ->
            InventoryItem(
                id = "receipt-${item.id}",
                name = item.description,
                quantity = item.quantity,
                state = "Temporary receipt preview",
            )
        }
        val durableRows = inventory.filter { ManualInventoryStore.isDurableRowId(it.id) }
        inventory = (existingStock + receiptPreview + durableRows).toMutableList()
        demoConfirmed = true
        return true
    }

    internal fun currentLocalDate(): LocalDate = today()

    private val receiptStore: ManualInventoryStore? get() = manualInventory as? ManualInventoryStore

    internal fun receiptHistory(): List<PurchaseRecord>? = receiptStore?.history()
    internal fun deleteReceipt(identity: String): Boolean = receiptStore?.deleteHistory(identity) == true
    internal fun originalReceipt(identity: String) = receiptStore?.originalFile(identity)
    internal fun recoverConfirmations(): Set<String>? = receiptStore?.recover()
    internal fun acknowledgeConfirmations(ids: Set<String>) = receiptStore?.acknowledge(ids) == true

    internal fun commitReview(
        draft: LiveReceiptReviewDraft,
        plan: ReceiptConfirmation,
        original: ByteArray?,
    ): ManualInventoryStore.Commit {
        val store = receiptStore ?: return ManualInventoryStore.Commit.FAILED
        val wrapper = draft.wrapper ?: return ManualInventoryStore.Commit.FAILED
        if (draft.request.context.mode != PresentationConsumerMode.LIVE ||
            wrapper.presentation.source.type != PresentationSourceType.LOCAL_IMAGE) return ManualInventoryStore.Commit.FAILED
        val current = draft.confirmation(plan.mode, today(), plan.incompleteAcknowledged) as? LiveReceiptReviewDraft.ConfirmationCheck.Ready
            ?: return ManualInventoryStore.Commit.CONFLICT
        if (current.confirmation != plan || current.needsIncompleteAcknowledgement && !plan.incompleteAcknowledged) {
            return ManualInventoryStore.Commit.CONFLICT
        }
        val evidence = wrapper.evidenceBytes()
        return try { store.commit(plan, evidence, original) } finally { evidence.fill(0) }
    }

    internal fun refreshDurableInventory() {
        receiptStore?.load()?.let(::applyCommittedInventory)
    }

    fun confirmManualReceipt(draft: EditableReceipt): Boolean {
        val confirmed = ReceiptValidator.validateManual(draft, today()).receipt ?: return false
        val rows = confirmed.items.map { item ->
            InventoryItem(
                id = "$MANUAL_ROW_PREFIX${item.id}",
                name = item.description,
                quantity = item.quantity,
                state = ManualInventoryStore.ROW_STATE,
            )
        }
        val rowIds = rows.map(InventoryItem::id).toSet()
        if (rowIds.size != rows.size || inventory.any { it.id in rowIds }) return false
        if (manualInventory == null) {
            inventory.addAll(rows)
            return true
        }
        return updateManualInventory { committed ->
            if (committed.any { it.id in rowIds }) null else committed + rows
        }
    }

    internal enum class LiveConfirmation { SAVED, INVALID, INVALID_DATE, ALREADY_SAVED, SAVE_FAILED }

    internal fun confirmLiveReceipt(
        draft: LiveReceiptReviewDraft,
        reviewed: LiveReceiptReviewDraft.Selection.Ready,
    ): LiveConfirmation {
        val current = draft.selection(today())
        if (current is LiveReceiptReviewDraft.Selection.Invalid &&
            current.problem == LiveReceiptReviewDraft.Problem.PURCHASE_DATE
        ) return LiveConfirmation.INVALID_DATE
        if (current != reviewed) return LiveConfirmation.INVALID
        if (manualInventory == null) return LiveConfirmation.SAVE_FAILED
        var alreadySaved = false
        val saved = updateManualInventory { committed ->
            alreadySaved = committed.any { it.id.startsWith(reviewed.receiptIdPrefix) }
            if (alreadySaved) null else committed + reviewed.rows
        }
        if (alreadySaved) return LiveConfirmation.ALREADY_SAVED
        if (!saved) return LiveConfirmation.SAVE_FAILED
        draft.discard()
        return LiveConfirmation.SAVED
    }

    internal fun addInventoryItem(
        name: String,
        quantity: String,
        unit: InventoryUnit = InventoryUnit.UNKNOWN,
        newId: () -> UUID = UUID::randomUUID,
    ): InventoryChange = saveInventoryItem(name, quantity, unit) { trimmedName, parsedQuantity ->
        val id = "${ManualInventoryStore.STANDALONE_ROW_PREFIX}${newId()}"
        updateManualInventory { committed ->
            if (committed.any { it.id == id }) null
            else committed + InventoryItem(id, trimmedName, parsedQuantity, ManualInventoryStore.STANDALONE_ROW_STATE, unit)
        }
    }

    internal fun editInventoryItem(
        id: String,
        name: String,
        quantity: String,
        unit: InventoryUnit? = null,
    ): InventoryChange {
        val current = inventory.firstOrNull { it.id == id } ?: return InventoryChange.NOT_SAVED
        val updatedUnit = unit ?: current.unit
        if (current.unit != InventoryUnit.UNKNOWN && current.unit != updatedUnit) return InventoryChange.NOT_SAVED
        return saveInventoryItem(name, quantity, updatedUnit) { trimmedName, parsedQuantity ->
            updateExistingInventoryItem(id, expectedUnit = current.unit) {
                it.copy(name = trimmedName, quantity = parsedQuantity, unit = updatedUnit)
            }
        }
    }

    internal fun deleteInventoryItem(id: String): Boolean = updateExistingInventoryItem(id) { null }

    private inline fun saveInventoryItem(
        name: String,
        quantity: String,
        unit: InventoryUnit,
        save: (String, BigDecimal) -> Boolean,
    ): InventoryChange {
        val trimmedName = name.trim()
        if (trimmedName.isBlank()) return InventoryChange.INVALID_NAME
        val parsedQuantity = unit.parse(quantity)
        if (parsedQuantity == null || !unit.stores(parsedQuantity)) {
            return InventoryChange.INVALID_QUANTITY
        }
        return if (save(trimmedName, parsedQuantity)) InventoryChange.SAVED else InventoryChange.NOT_SAVED
    }

    private fun updateExistingInventoryItem(
        id: String,
        expectedUnit: InventoryUnit? = null,
        change: (InventoryItem) -> InventoryItem?,
    ): Boolean {
        if (!ManualInventoryStore.isDurableRowId(id) || id.startsWith(ManualInventoryStore.LIVE_ROW_PREFIX)) {
            return false
        }
        return updateManualInventory { committed ->
            val index = committed.indexOfFirst { it.id == id }
            if (index < 0) return@updateManualInventory null
            val current = committed[index]
            if (expectedUnit != null && current.unit != expectedUnit) return@updateManualInventory null
            val updated = change(current)
            committed.toMutableList().apply {
                if (updated == null) removeAt(index) else set(index, updated)
            }
        }
    }

    fun adjustInventory(id: String, delta: Int): Boolean {
        val index = inventory.indexOfFirst { it.id == id }
        if (index < 0) return false
        if (manualInventory != null && ManualInventoryStore.isDurableRowId(id)) {
            return updateManualInventory { committed ->
                val committedIndex = committed.indexOfFirst { it.id == id }
                if (committedIndex < 0) return@updateManualInventory null
                val updated = adjustQuantity(committed[committedIndex], delta) ?: return@updateManualInventory null
                committed.toMutableList().apply { set(committedIndex, updated) }
            }
        }
        inventory[index] = adjustQuantity(inventory[index], delta) ?: return false
        return true
    }

    private fun adjustQuantity(row: InventoryItem, delta: Int): InventoryItem? {
        val next = row.quantity + row.unit.step.multiply(delta.toBigDecimal())
        val quantity = if (row.unit == InventoryUnit.UNKNOWN) next.coerceIn(BigDecimal.ZERO, maximumStock)
            else next.takeIf(row.unit::stores) ?: return null
        return row.copy(quantity = quantity)
    }

    private fun updateManualInventory(change: (List<InventoryItem>) -> List<InventoryItem>?): Boolean {
        val committed = manualInventory?.update(change) ?: return false
        applyCommittedInventory(committed)
        return true
    }

    private fun applyCommittedInventory(committed: List<InventoryItem>) {
        inventory.removeAll { ManualInventoryStore.isDurableRowId(it.id) }
        inventory.addAll(committed)
        manualInventoryLoadFailed = false
    }

    fun restore(
        restoredReceipt: Receipt?,
        restoredInventory: List<InventoryItem>,
        restoredDemoConfirmed: Boolean,
    ) {
        val sessionInventory = if (manualInventory == null) restoredInventory else
            restoredInventory.filterNot { ManualInventoryStore.isDurableRowId(it.id) }
        // Reject an invalid saved inventory as a whole; never normalize admitted stock.
        if (sessionInventory.any { !it.unit.stores(it.quantity) }) return
        receipt = if (presentationResult is ReceiptPresentationUiResult.Available) {
            restoredReceipt
        } else {
            null
        }
        val expectedReceiptRowIds = receipt
            ?.items
            ?.map { item -> "receipt-${item.id}" }
            .orEmpty()
        val restoredReceiptRowIds = sessionInventory
            .filter { item -> item.id.startsWith("receipt-") }
            .map(InventoryItem::id)
        val receiptRowsMatch = expectedReceiptRowIds.isNotEmpty() &&
            expectedReceiptRowIds.distinct().size == expectedReceiptRowIds.size &&
            restoredReceiptRowIds.size == expectedReceiptRowIds.size &&
            restoredReceiptRowIds.toSet() == expectedReceiptRowIds.toSet()
        val receiptQuantitiesEligible =
            receipt?.items?.all { it.quantity in 1..MAX_INVENTORY_QUANTITY } == true
        demoConfirmed = restoredDemoConfirmed && receiptQuantitiesEligible && receiptRowsMatch
        val committedRows = if (manualInventory == null) emptyList()
        else inventory.filter { ManualInventoryStore.isDurableRowId(it.id) }
        inventory = sessionInventory
            .filterNot { item ->
                item.id.startsWith("receipt-") && !demoConfirmed
            }
            .toMutableList()
        inventory.addAll(committedRows)
    }

    private fun inventoryCompatibleReceipt(result: ReceiptPresentationUiResult): Receipt? =
        (result as? ReceiptPresentationUiResult.Available)
            ?.receipt
            ?.toInventoryCompatibleReceiptOrNull()
}
