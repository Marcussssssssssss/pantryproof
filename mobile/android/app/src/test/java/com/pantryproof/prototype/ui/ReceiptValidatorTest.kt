package com.pantryproof.prototype.ui

import com.pantryproof.prototype.data.MockReceiptPresentationSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReceiptValidatorTest {
    private val source = MockReceiptPresentationSource()

    @Test
    fun syntheticReceipt_isValidAndRetainsMissingUnitPrice() {
        val result = ReceiptValidator.validate(EditableReceipt.from(source.syntheticReceipt()))

        assertTrue(result.errors.toString(), result.isValid)
        assertEquals(3, result.receipt?.items?.size)
        assertNull(result.receipt?.items?.last()?.unitPrice)
    }

    @Test
    fun invalidNumbers_areReportedWithoutThrowing() {
        val draft = EditableReceipt.from(source.syntheticReceipt()).apply {
            items[0].quantity = "1.5"
            items[1].lineTotal = "-4.20"
            receiptTotal = "twenty"
        }

        val result = ReceiptValidator.validate(draft)

        assertFalse(result.isValid)
        assertTrue(result.errors.containsKey("item.0.quantity"))
        assertTrue(result.errors.containsKey("item.1.lineTotal"))
        assertTrue(result.errors.containsKey("receiptTotal"))
    }

    @Test
    fun invalidDateAndRequiredText_areReported() {
        val draft = EditableReceipt.from(source.syntheticReceipt()).apply {
            storeName = " "
            purchaseDate = "31/10/2026"
            items[0].description = ""
        }

        val result = ReceiptValidator.validate(draft)

        assertFalse(result.isValid)
        assertTrue(result.errors.containsKey("storeName"))
        assertTrue(result.errors.containsKey("purchaseDate"))
        assertTrue(result.errors.containsKey("item.0.description"))
    }

    @Test
    fun syntheticReceipt_coversAllSevenReceiptFieldRoles() {
        val receipt = source.syntheticReceipt()

        assertTrue(receipt.storeName.isNotBlank())
        assertTrue(receipt.purchaseDate.toString().isNotBlank())
        assertTrue(receipt.items.all { it.description.isNotBlank() })
        assertTrue(receipt.items.all { it.quantity > 0 })
        assertTrue(receipt.items.any { it.unitPrice != null })
        assertTrue(receipt.items.all { it.lineTotal.signum() >= 0 })
        assertTrue(receipt.receiptTotal.signum() >= 0)
    }

    @Test
    fun validationReportsFirstInvalidFieldInVisualOrder() {
        val draft = EditableReceipt.from(source.syntheticReceipt()).apply {
            storeName = ""
            purchaseDate = "not-a-date"
            items[0].quantity = "0"
        }

        val result = ReceiptValidator.validate(draft)

        assertEquals("storeName", result.firstInvalidFieldKey)
        assertEquals(3, result.errors.size)
    }

    @Test
    fun optionalUnitPriceMayRemainBlankWithoutBlockingValidation() {
        val draft = EditableReceipt.from(source.syntheticReceipt()).apply {
            items.forEach { it.unitPrice = "" }
        }

        val result = ReceiptValidator.validate(draft)

        assertTrue(result.errors.toString(), result.isValid)
        assertTrue(result.receipt?.items?.all { it.unitPrice == null } == true)
    }

    @Test
    fun draftUpdateAndDeepCopyRetainUnsavedInvalidTextIndependently() {
        val original = EditableReceipt.from(source.syntheticReceipt())
        val recreated = original.deepCopy()

        assertTrue(recreated.updateField("item.1.lineTotal", "invalid-unsaved"))
        assertEquals("invalid-unsaved", recreated.items[1].lineTotal)
        assertEquals("4.20", original.items[1].lineTotal)
        assertFalse(recreated.updateField("item.1.lineTotal", "invalid-unsaved"))
    }

    @Test
    fun rebuildingDraftFromAppliedReceiptDiscardsUnsavedChanges() {
        val receipt = source.syntheticReceipt()
        val dirtyDraft = EditableReceipt.from(receipt).apply {
            updateField("storeName", "Unsaved store")
        }

        val discardedDraft = EditableReceipt.from(receipt)

        assertEquals("Unsaved store", dirtyDraft.storeName)
        assertEquals(receipt.storeName, discardedDraft.storeName)
    }
}
