package com.pantryproof.prototype.data

import java.math.BigDecimal
import java.time.LocalDate

class MockReceiptPresentationSource : ReceiptPresentationSource {
    override fun syntheticReceipt() = Receipt(
        storeName = "Demo Grocery Store (Synthetic)",
        purchaseDate = LocalDate.of(2026, 10, 31),
        items = listOf(
            ReceiptItem(
                id = "demo-milk",
                description = "UHT Milk 1L",
                quantity = 2,
                unitPrice = BigDecimal("6.50"),
                lineTotal = BigDecimal("13.00"),
            ),
            ReceiptItem(
                id = "demo-bread",
                description = "Wholemeal Bread",
                quantity = 1,
                unitPrice = BigDecimal("4.20"),
                lineTotal = BigDecimal("4.20"),
            ),
            ReceiptItem(
                id = "demo-bananas",
                description = "Bananas (bunch)",
                quantity = 1,
                unitPrice = null,
                lineTotal = BigDecimal("5.80"),
            ),
        ),
        receiptTotal = BigDecimal("23.00"),
    )

    override fun syntheticInventory() = listOf(
        InventoryItem("stock-rice", "Jasmine Rice 5kg", 1, "In pantry"),
        InventoryItem("stock-eggs", "Eggs (10 pack)", 2, "In fridge"),
        InventoryItem("stock-oil", "Cooking Oil 1kg", 1, "In pantry"),
    )
}
