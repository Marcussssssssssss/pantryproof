package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.Receipt
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.data.ReceiptPresentationSource

class PantryUiState(private val source: ReceiptPresentationSource) {
    companion object {
        const val MIN_INVENTORY_QUANTITY = 0
        const val MAX_INVENTORY_QUANTITY = 99
        const val MANUAL_ROW_PREFIX = "manual-receipt-"
    }

    var presentationResult: ReceiptPresentationUiResult = source.syntheticPresentation()
        private set

    var receipt: Receipt? = inventoryCompatibleReceipt(presentationResult)
        private set

    var inventory: MutableList<InventoryItem> = source.syntheticInventory().toMutableList()
        private set

    var demoConfirmed: Boolean = false
        private set

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
                state = "Manually entered receipt",
            )
        }
        val rowIds = rows.map(InventoryItem::id).toSet()
        if (rowIds.size != rows.size || inventory.any { it.id in rowIds }) return false
        inventory.addAll(rows)
        return true
    }

    fun adjustInventory(id: String, delta: Int) {
        val index = inventory.indexOfFirst { it.id == id }
        if (index < 0) return
        val current = inventory[index]
        inventory[index] = current.copy(
            quantity = (current.quantity + delta).coerceIn(
                MIN_INVENTORY_QUANTITY,
                MAX_INVENTORY_QUANTITY,
            ),
        )
    }

    fun restore(
        restoredReceipt: Receipt?,
        restoredInventory: List<InventoryItem>,
        restoredDemoConfirmed: Boolean,
    ) {
        receipt = if (presentationResult is ReceiptPresentationUiResult.Available) {
            restoredReceipt
        } else {
            null
        }
        val expectedReceiptRowIds = receipt
            ?.items
            ?.map { item -> "receipt-${item.id}" }
            .orEmpty()
        val restoredReceiptRowIds = restoredInventory
            .filter { item -> item.id.startsWith("receipt-") }
            .map(InventoryItem::id)
        val receiptRowsMatch = expectedReceiptRowIds.isNotEmpty() &&
            expectedReceiptRowIds.distinct().size == expectedReceiptRowIds.size &&
            restoredReceiptRowIds.size == expectedReceiptRowIds.size &&
            restoredReceiptRowIds.toSet() == expectedReceiptRowIds.toSet()
        demoConfirmed = restoredDemoConfirmed && receipt != null && receiptRowsMatch
        inventory = restoredInventory
            .filterNot { item ->
                item.id.startsWith("receipt-") && !demoConfirmed
            }
            .toMutableList()
    }

    private fun inventoryCompatibleReceipt(result: ReceiptPresentationUiResult): Receipt? =
        (result as? ReceiptPresentationUiResult.Available)
            ?.receipt
            ?.toInventoryCompatibleReceiptOrNull()
}
