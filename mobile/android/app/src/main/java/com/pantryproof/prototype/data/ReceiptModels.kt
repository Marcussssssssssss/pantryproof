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
    val quantity: BigDecimal,
    val state: String,
    val unit: InventoryUnit = InventoryUnit.UNKNOWN,
) {
    constructor(id: String, name: String, quantity: Int, state: String) :
        this(id, name, quantity.toBigDecimal(), state)

    val quantityLabel: String
        get() = listOf(quantity.toPlainString(), unit.symbol).filter(String::isNotEmpty).joinToString(" ")
}
