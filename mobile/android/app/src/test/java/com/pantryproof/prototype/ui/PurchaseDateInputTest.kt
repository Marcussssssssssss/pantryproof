package com.pantryproof.prototype.ui

import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PurchaseDateInputTest {
    private val full = "01-02-2026"

    @Test fun typingGroupsDigitsAndRejectsAnExtraDigit() {
        val expected = listOf("0", "01", "01-0", "01-02", "01-02-2", "01-02-20", "01-02-202", full, full)
        var current = ""
        "010220269".forEachIndexed { index, digit ->
            val edit = PurchaseDateInput.edit(current, current.length, current.length, digit.toString(), current.length)
            assertEquals(expected[index], edit.text)
            assertEquals(edit.text.length, edit.cursor)
            current = edit.text
        }
    }

    @Test fun deletingAroundBothSeparatorsUsesAdjacentDigits() {
        fun backspace(before: String, caret: Int) = PurchaseDateInput.edit(before, caret - 1, caret, "", caret)
        assertEquals(PurchaseDateInput.Edit("00-22-026", 1), backspace(full, 2))
        assertEquals(PurchaseDateInput.Edit("00-22-026", 1), backspace(full, 3))
        assertEquals(PurchaseDateInput.Edit("01-22-026", 2), backspace(full, 4))
        assertEquals(PurchaseDateInput.Edit("01-22-026", 2), PurchaseDateInput.edit(full, 2, 3, "", 2))
        assertEquals(PurchaseDateInput.Edit("01-02-026", 5), PurchaseDateInput.edit(full, 5, 6, "", 5))
        assertEquals(PurchaseDateInput.Edit("01-02-202", 9), backspace(full, 10))
    }

    @Test fun middleEditsPreserveUnaffectedDigitsAndCursor() {
        assertEquals(PurchaseDateInput.Edit("03-02-2026", 2), PurchaseDateInput.edit(full, 1, 2, "3", -1))
        assertEquals(PurchaseDateInput.Edit(full, 1), PurchaseDateInput.edit(full, 1, 1, "9", 1))
        assertEquals(PurchaseDateInput.Edit("01-12-2026", 5), PurchaseDateInput.edit(full, 3, 5, "1299", -1))
        assertEquals(PurchaseDateInput.Edit("01-02-2026", 2), PurchaseDateInput.edit("0-02-2026", 1, 1, "1", 1))
    }

    @Test fun replacingTheWholeDateAcceptsClipboardFormats() {
        listOf("29022024", "29-02-2024", "2024-02-29").forEach { pasted ->
            assertEquals(PurchaseDateInput.Edit("29-02-2024", 10),
                PurchaseDateInput.edit(full, 0, full.length, pasted, -1))
        }
    }

    @Test fun strictCalendarValidationKeepsIsoCanonicalAndInvalidDraftsUntouched() {
        assertEquals("2026-02-01", PurchaseDateInput.draftValue(full))
        assertEquals(full, PurchaseDateInput.display("2026-02-01"))
        assertEquals(LocalDate.of(2024, 2, 29), PurchaseDateInput.parse("29-02-2024"))
        assertEquals(LocalDate.of(0, 2, 29), PurchaseDateInput.parse("29-02-0000"))
        listOf("29-02-2026", "31-04-2026", "15-13-2026", "00-01-2026", "01-00-2026", "01-02-20").forEach {
            assertNull(PurchaseDateInput.parse(it))
            assertEquals(it, PurchaseDateInput.draftValue(it))
        }
    }
}
