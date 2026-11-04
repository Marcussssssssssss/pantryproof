package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.Receipt
import com.pantryproof.prototype.data.ReceiptItem
import java.math.BigDecimal
import java.time.LocalDate
import java.time.format.DateTimeParseException

data class EditableReceiptItem(
    val id: String,
    var description: String,
    var quantity: String,
    var unitPrice: String,
    var lineTotal: String,
)

data class EditableReceipt(
    var storeName: String,
    var purchaseDate: String,
    val items: MutableList<EditableReceiptItem>,
    var receiptTotal: String,
) {
    fun deepCopy() = copy(items = items.map(EditableReceiptItem::copy).toMutableList())

    fun updateField(key: String, value: String): Boolean {
        when (key) {
            "storeName" -> {
                if (storeName == value) return false
                storeName = value
            }
            "purchaseDate" -> {
                if (purchaseDate == value) return false
                purchaseDate = value
            }
            "receiptTotal" -> {
                if (receiptTotal == value) return false
                receiptTotal = value
            }
            else -> {
                val segments = key.split('.')
                val index = segments.getOrNull(1)?.toIntOrNull() ?: return false
                val item = items.getOrNull(index) ?: return false
                when (segments.getOrNull(2)) {
                    "description" -> {
                        if (item.description == value) return false
                        item.description = value
                    }
                    "quantity" -> {
                        if (item.quantity == value) return false
                        item.quantity = value
                    }
                    "unitPrice" -> {
                        if (item.unitPrice == value) return false
                        item.unitPrice = value
                    }
                    "lineTotal" -> {
                        if (item.lineTotal == value) return false
                        item.lineTotal = value
                    }
                    else -> return false
                }
            }
        }
        return true
    }

    companion object {
        fun from(receipt: Receipt) = EditableReceipt(
            storeName = receipt.storeName,
            purchaseDate = receipt.purchaseDate.toString(),
            items = receipt.items.map { item ->
                EditableReceiptItem(
                    id = item.id,
                    description = item.description,
                    quantity = item.quantity.toString(),
                    unitPrice = item.unitPrice?.toPlainString().orEmpty(),
                    lineTotal = item.lineTotal.toPlainString(),
                )
            }.toMutableList(),
            receiptTotal = receipt.receiptTotal.toPlainString(),
        )
    }
}

data class ReceiptValidationResult(
    val receipt: Receipt?,
    val errors: Map<String, String>,
) {
    val isValid: Boolean get() = receipt != null && errors.isEmpty()
    val firstInvalidFieldKey: String? get() = errors.keys.firstOrNull()
}

object ReceiptValidator {
    fun validate(draft: EditableReceipt): ReceiptValidationResult {
        val errors = linkedMapOf<String, String>()
        val store = draft.storeName.trim()
        if (store.isEmpty()) errors["storeName"] = "Store name is required."

        val date = try {
            LocalDate.parse(draft.purchaseDate.trim())
        } catch (_: DateTimeParseException) {
            errors["purchaseDate"] = "Use a valid date in YYYY-MM-DD format."
            null
        }

        val items = draft.items.mapIndexed { index, item ->
            val prefix = "item.$index"
            val description = item.description.trim()
            if (description.isEmpty()) {
                errors["$prefix.description"] = "Item description is required."
            }

            val quantity = item.quantity.trim().toIntOrNull()
            if (quantity == null || quantity <= 0) {
                errors["$prefix.quantity"] = "Quantity must be a whole number above zero."
            }

            val unitPrice = if (item.unitPrice.isBlank()) {
                null
            } else {
                parseMoney(item.unitPrice, "$prefix.unitPrice", errors)
            }
            val lineTotal = parseMoney(item.lineTotal, "$prefix.lineTotal", errors)

            if (description.isNotEmpty() && quantity != null && quantity > 0 && lineTotal != null) {
                ReceiptItem(item.id, description, quantity, unitPrice, lineTotal)
            } else {
                null
            }
        }

        val receiptTotal = parseMoney(draft.receiptTotal, "receiptTotal", errors)
        val receipt = if (errors.isEmpty() && date != null && receiptTotal != null) {
            Receipt(store, date, items.filterNotNull(), receiptTotal)
        } else {
            null
        }
        return ReceiptValidationResult(receipt, errors)
    }

    private fun parseMoney(
        raw: String,
        key: String,
        errors: MutableMap<String, String>,
    ): BigDecimal? {
        val value = raw.trim().toBigDecimalOrNull()
        if (value == null || value < BigDecimal.ZERO) {
            errors[key] = "Enter a non-negative amount, for example 6.50."
            return null
        }
        if (value.scale() > 2) {
            errors[key] = "Use no more than two decimal places."
            return null
        }
        return value
    }
}
