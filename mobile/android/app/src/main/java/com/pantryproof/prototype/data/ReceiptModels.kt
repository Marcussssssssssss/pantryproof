package com.pantryproof.prototype.data

import java.math.BigDecimal
import java.time.LocalDate

data class ReceiptItem(
    val id: String,
    val description: String,
    val quantity: Int,
    val unitPrice: BigDecimal?,
    val lineTotal: BigDecimal,
)

data class Receipt(
    val storeName: String,
    val purchaseDate: LocalDate,
    val items: List<ReceiptItem>,
    val receiptTotal: BigDecimal,
)

data class InventoryItem(
    val id: String,
    val name: String,
    val quantity: Int,
    val state: String,
)
