package com.pantryproof.prototype.data

class MockReceiptPresentationSource : ReceiptPresentationSource {
    private val presentation by lazy {
        M3eReceiptPresentationAdapter().decodeAndMap(
            SyntheticReceiptPresentationPayload.bytes(),
            SyntheticReceiptPresentationPayload.context,
        )
    }

    override fun syntheticPresentation(): ReceiptPresentationUiResult = presentation

    override fun syntheticInventory() = listOf(
        InventoryItem("stock-rice", "Jasmine Rice 5kg", 1, "In pantry"),
        InventoryItem("stock-eggs", "Eggs (10 pack)", 2, "In fridge"),
        InventoryItem("stock-oil", "Cooking Oil 1kg", 1, "In pantry"),
    )
}
