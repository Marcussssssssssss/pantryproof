package com.pantryproof.prototype.ui

import java.math.BigDecimal
import java.math.RoundingMode

object MoneyFormatter {
    fun ringgit(value: BigDecimal): String =
        "RM " + value.setScale(2, RoundingMode.HALF_UP).toPlainString()
}
