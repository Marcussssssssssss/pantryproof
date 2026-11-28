package com.pantryproof.prototype.data

import java.math.BigDecimal

/** Android-local stock units. UNKNOWN represents a legacy row without unit evidence. */
enum class InventoryUnit(val code: String, val symbol: String, val fractionalPlaces: Int) {
    UNKNOWN("unknown", "", 0),
    EACH("each", "each", 0),
    GRAM("g", "g", 3),
    KILOGRAM("kg", "kg", 3),
    MILLILITRE("ml", "mL", 3),
    LITRE("l", "L", 3),
    ;

    internal val step: BigDecimal
        get() = BigDecimal.ONE.movePointLeft(fractionalPlaces)

    fun represents(quantity: BigDecimal): Boolean =
        quantity.signum() >= 0 && quantity.scale() in 0..fractionalPlaces

    internal val maximum: BigDecimal
        get() = when (this) {
            UNKNOWN -> BigDecimal("99")
            EACH -> BigDecimal("999999")
            else -> BigDecimal("999999.999")
        }

    internal fun stores(quantity: BigDecimal): Boolean = represents(quantity) && quantity <= maximum

    internal fun parse(input: String): BigDecimal? {
        val trimmed = input.trim()
        if (!decimal.matches(trimmed)) return null
        return trimmed.toBigDecimalOrNull()?.takeIf(::represents)
    }

    companion object {
        private val decimal = Regex("[0-9]+(?:\\.[0-9]{1,3})?")
        internal fun fromCode(code: String): InventoryUnit? = entries.firstOrNull { it.code == code }
    }
}
