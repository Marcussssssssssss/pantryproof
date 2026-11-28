package com.pantryproof.prototype.data

import java.math.BigDecimal
import java.time.LocalDate
import java.time.temporal.ChronoUnit

enum class InventoryCategory(val code: String) {
    VEGETABLES_FRUITS("vegetables-fruits"),
    DAIRY_EGGS("dairy-eggs"),
    MEAT_SEAFOOD("meat-seafood"),
    DRY_FOOD("dry-food"),
    HOUSEHOLD_SUPPLIES("household-supplies"),
    UNCATEGORIZED("uncategorized");

    companion object {
        internal fun fromCode(code: String) = entries.firstOrNull { it.code == code }
    }
}

data class InventoryMetadata(
    val category: InventoryCategory = InventoryCategory.UNCATEGORIZED,
    val expiryDate: LocalDate? = null,
    val minimumStock: BigDecimal? = null,
) {
    internal fun validFor(unit: InventoryUnit): Boolean =
        (expiryDate == null || expiryDate.year in 1..9999) && (minimumStock == null || unit.stores(minimumStock))
}

internal enum class InventoryWarning {
    EXPIRED, EXPIRES_TODAY, EXPIRING_SOON, OUT_OF_STOCK, LOW_STOCK
}

internal const val EXPIRING_SOON_DAYS = 3L

internal fun InventoryItem.warnings(today: LocalDate): List<InventoryWarning> = buildList {
    household.expiryDate?.let {
        val days = ChronoUnit.DAYS.between(today, it)
        when {
            days < 0 -> add(InventoryWarning.EXPIRED)
            days == 0L -> add(InventoryWarning.EXPIRES_TODAY)
            days <= EXPIRING_SOON_DAYS -> add(InventoryWarning.EXPIRING_SOON)
        }
    }
    if (quantity.signum() == 0) add(InventoryWarning.OUT_OF_STOCK)
    else if (household.minimumStock?.let { quantity <= it } == true) add(InventoryWarning.LOW_STOCK)
}
