package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryMetadata
import com.pantryproof.prototype.data.InventoryUnit
import com.pantryproof.prototype.data.InventoryWarning
import com.pantryproof.prototype.data.warnings
import java.time.LocalDate
import org.junit.Assert.*
import org.junit.Test

class InventoryWarningTest {
    private val today = LocalDate.of(2026, 11, 27)

    @Test fun expiryTransitionsAtLocalDateBoundariesAndIgnoresAbsentDates() {
        val row = item("0.751", "0.750")
        assertTrue(row.warnings(today).isEmpty())
        val pending = row.copy(household = row.household.copy(expiryDate = today.plusDays(4)))
        assertTrue(pending.warnings(today).isEmpty())
        assertEquals(listOf(InventoryWarning.EXPIRING_SOON), pending.warnings(today.plusDays(1)))
        assertEquals(listOf(InventoryWarning.EXPIRES_TODAY), pending.warnings(today.plusDays(4)))
        assertEquals(listOf(InventoryWarning.EXPIRED), pending.warnings(today.plusDays(5)))
    }

    @Test fun explicitDecimalThresholdIsInclusiveAndZeroRemainsOutOfStock() {
        assertEquals(listOf(InventoryWarning.OUT_OF_STOCK), item("0.000", "0.750").warnings(today))
        assertEquals(listOf(InventoryWarning.LOW_STOCK), item("0.749", "0.750").warnings(today))
        assertEquals(listOf(InventoryWarning.LOW_STOCK), item("0.750", "0.750").warnings(today))
        assertTrue(item("0.751", "0.750").warnings(today).isEmpty())
        assertTrue(item("0.001", null).warnings(today).isEmpty())
        assertFalse(InventoryMetadata(minimumStock = "0.750".toBigDecimal()).validFor(InventoryUnit.EACH))
    }

    @Test fun expiryInputSupportsHistoricalTodayAndFutureAndRejectsInvalidDates() {
        for (date in listOf(today.minusDays(300), today, today.plusDays(300))) {
            assertEquals(date, PurchaseDateInput.parse(PurchaseDateInput.display(date)))
        }
        assertNull(PurchaseDateInput.parse("31-02-2027"))
        assertNull(PurchaseDateInput.parse(""))
    }

    private fun item(quantity: String, minimum: String?) =
        InventoryItem("stock", "Stock", quantity.toBigDecimal(), "", InventoryUnit.KILOGRAM,
            InventoryMetadata(minimumStock = minimum?.toBigDecimal()))
}
