package com.pantryproof.prototype.ui

import java.math.BigDecimal
import org.junit.Assert.assertEquals
import org.junit.Test

class MoneyFormatterTest {
    @Test
    fun ringgitAlwaysUsesRmPrefixAndTwoDecimalPlaces() {
        assertEquals("RM 23.00", MoneyFormatter.ringgit(BigDecimal("23")))
        assertEquals("RM 4.20", MoneyFormatter.ringgit(BigDecimal("4.2")))
        assertEquals("RM 0.00", MoneyFormatter.ringgit(BigDecimal.ZERO))
    }
}
