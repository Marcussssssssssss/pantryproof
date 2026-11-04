package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.Receipt
import com.pantryproof.prototype.data.ReceiptPresentationSource

class PantryUiState(private val source: ReceiptPresentationSource) {
    companion object {
        const val MIN_INVENTORY_QUANTITY = 0
        const val MAX_INVENTORY_QUANTITY = 99
    }

    var receipt: Receipt = source.syntheticReceipt()
        private set

    var inventory: MutableList<InventoryItem> = source.syntheticInventory().toMutableList()
        private set

    var demoConfirmed: Boolean = false
        private set

    fun applyReceipt(updated: Receipt) {
        receipt = updated
        demoConfirmed = false
        inventory.removeAll { it.id.startsWith("receipt-") }
    }

    fun revertReceipt() {
        receipt = source.syntheticReceipt()
        demoConfirmed = false
        inventory.removeAll { it.id.startsWith("receipt-") }
    }

    fun confirmForInventoryPreview() {
        val adjustedStockById = inventory
            .filterNot { it.id.startsWith("receipt-") }
            .associateBy(InventoryItem::id)
        val existingStock = source.syntheticInventory().map { baseline ->
            adjustedStockById[baseline.id]?.let { adjusted ->
                baseline.copy(quantity = adjusted.quantity)
            } ?: baseline
        }
        val receiptPreview = receipt.items.map { item ->
            InventoryItem(
                id = "receipt-${item.id}",
                name = item.description,
                quantity = item.quantity,
                state = "Temporary receipt preview",
            )
        }
        inventory = (existingStock + receiptPreview).toMutableList()
        demoConfirmed = true
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
        restoredReceipt: Receipt,
        restoredInventory: List<InventoryItem>,
        restoredDemoConfirmed: Boolean,
    ) {
        receipt = restoredReceipt
        inventory = restoredInventory.toMutableList()
        demoConfirmed = restoredDemoConfirmed
    }
}
