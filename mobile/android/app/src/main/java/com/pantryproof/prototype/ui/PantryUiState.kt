package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.ManualInventoryPersistence
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.data.Receipt
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.data.ReceiptPresentationSource

class PantryUiState internal constructor(
    private val source: ReceiptPresentationSource,
    private val manualInventory: ManualInventoryPersistence?,
) {
    constructor(source: ReceiptPresentationSource) : this(source, null)

    companion object {
        const val MIN_INVENTORY_QUANTITY = ManualInventoryStore.MIN_QUANTITY
        const val MAX_INVENTORY_QUANTITY = ManualInventoryStore.MAX_QUANTITY
        const val MANUAL_ROW_PREFIX = ManualInventoryStore.ROW_PREFIX
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
        val manualRows = inventory.filter { it.id.startsWith(MANUAL_ROW_PREFIX) }
        inventory = (existingStock + receiptPreview + manualRows).toMutableList()
        demoConfirmed = true
        return true
    }

    fun confirmManualReceipt(draft: EditableReceipt): Boolean {
        val confirmed = ReceiptValidator.validateManual(draft).receipt ?: return false
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

    fun adjustInventory(id: String, delta: Int): Boolean {
        val index = inventory.indexOfFirst { it.id == id }
        if (index < 0) return false
        if (manualInventory != null && id.startsWith(MANUAL_ROW_PREFIX)) {
            return updateManualInventory { committed ->
                if (committed.none { it.id == id }) null
                else committed.map { row -> if (row.id == id) adjustQuantity(row, delta) else row }
            }
        }
        inventory[index] = adjustQuantity(inventory[index], delta)
        return true
    }

    private fun adjustQuantity(row: InventoryItem, delta: Int): InventoryItem =
        row.copy(
            quantity = (row.quantity.toLong() + delta.toLong()).coerceIn(
                MIN_INVENTORY_QUANTITY.toLong(),
                MAX_INVENTORY_QUANTITY.toLong(),
            ).toInt(),
        )

    private fun updateManualInventory(change: (List<InventoryItem>) -> List<InventoryItem>?): Boolean {
        val committed = checkNotNull(manualInventory).update(change) ?: return false
        inventory.removeAll { it.id.startsWith(MANUAL_ROW_PREFIX) }
        inventory.addAll(committed)
        manualInventoryLoadFailed = false
        return true
    }

    fun restore(
        restoredReceipt: Receipt?,
        restoredInventory: List<InventoryItem>,
        restoredDemoConfirmed: Boolean,
    ) {
        val sessionInventory = if (manualInventory == null) restoredInventory else
            restoredInventory.filterNot { it.id.startsWith(MANUAL_ROW_PREFIX) }
        // Reject an invalid saved inventory as a whole; never normalize admitted stock.
        if (sessionInventory.any { it.quantity !in MIN_INVENTORY_QUANTITY..MAX_INVENTORY_QUANTITY }) return
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
        val committedManualRows = if (manualInventory == null) emptyList()
        else inventory.filter { it.id.startsWith(MANUAL_ROW_PREFIX) }
        inventory = sessionInventory
            .filterNot { item ->
                item.id.startsWith("receipt-") && !demoConfirmed
            }
            .toMutableList()
        inventory.addAll(committedManualRows)
    }

    private fun inventoryCompatibleReceipt(result: ReceiptPresentationUiResult): Receipt? =
        (result as? ReceiptPresentationUiResult.Available)
            ?.receipt
            ?.toInventoryCompatibleReceiptOrNull()
}
