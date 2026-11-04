package com.pantryproof.prototype.data

/**
 * UI integration seam. A future approved Android runtime adapter can implement this
 * interface without coupling this prototype to Python evaluation objects.
 */
interface ReceiptPresentationSource {
    fun syntheticReceipt(): Receipt
    fun syntheticInventory(): List<InventoryItem>
}
