package com.pantryproof.prototype.data

/**
 * UI integration seam. A future approved Android runtime adapter can implement this
 * interface without coupling this prototype to Python evaluation objects.
 */
interface ReceiptPresentationSource {
    fun syntheticPresentation(): ReceiptPresentationUiResult

    fun syntheticReceipt(): Receipt =
        ((syntheticPresentation() as? ReceiptPresentationUiResult.Available)
            ?.receipt
            ?.toInventoryCompatibleReceiptOrNull())
            ?: error("Synthetic presentation is not inventory-compatible")

    fun syntheticInventory(): List<InventoryItem>
}
