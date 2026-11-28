package com.pantryproof.prototype

import android.content.res.Configuration
import android.graphics.Bitmap
import android.os.SystemClock
import android.widget.EditText
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onData
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.replaceText
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.RootMatchers.isDialog
import androidx.test.espresso.matcher.RootMatchers.isPlatformPopup
import androidx.test.espresso.matcher.ViewMatchers.*
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.data.InventoryCategory
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryMetadata
import com.pantryproof.prototype.data.InventoryUnit
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.data.MockReceiptPresentationSource
import com.pantryproof.prototype.data.PurchaseSource
import com.pantryproof.prototype.data.receiptHistoryMonths
import com.pantryproof.prototype.ui.EditableReceipt
import com.pantryproof.prototype.ui.EditableReceiptItem
import com.pantryproof.prototype.ui.PantryUiState
import com.pantryproof.prototype.ui.PurchaseDateInput
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import java.time.LocalDate
import org.hamcrest.CoreMatchers.containsString
import org.hamcrest.CoreMatchers.equalTo
import org.hamcrest.CoreMatchers.not
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

internal fun awaitHouseholdInventory(scenario: ActivityScenario<MainActivity>) {
    val deadline = SystemClock.uptimeMillis() + 5000
    while (SystemClock.uptimeMillis() < deadline) {
        var inventory = false
        scenario.onActivity { inventory = it.findViewById<android.view.View>(R.id.screen_inventory) != null }
        if (inventory) return
        SystemClock.sleep(40)
    }
    onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
}

@RunWith(AndroidJUnit4::class)
class HouseholdFunctionalInstrumentedTest {
    private val instrument get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrument.targetContext
    private val store get() = ManualInventoryStore(context)
    private val example = "Task14 Market"
    private val fruit = InventoryCategory.VEGETABLES_FRUITS

    @Test fun manualPurchaseWithoutImageAppearsInSearchSpendingAndDetailsAndDeletesWithoutStockReversal() {
        try {
            ActivityScenario.launch(MainActivity::class.java).use { scene ->
                onView(withId(R.id.home_add_receipt)).perform(click())
                onView(withId(R.id.manual_without_image)).perform(sageScrollTo(), click())
                scene.onActivity { activity ->
                    mapOf(R.id.review_store_name to example, R.id.review_purchase_date to "2025-01-10",
                        R.id.review_item_0_description to "Task14 pears", R.id.review_item_0_quantity to "2",
                        R.id.review_item_0_line_total to "8.30", R.id.review_receipt_total to "8.31").forEach { (id, value) ->
                        activity.findViewById<EditText>(id).setText(value)
                    }
                }
                onView(withId(R.id.inventory_category)).perform(sageScrollTo(), click())
                onData(equalTo("Vegetables & Fruits")).inAdapterView(withId(R.id.inventory_category_choices)).perform(click())
                onView(withId(R.id.manual_review_action)).perform(sageScrollTo(), click())
                assertTrue(store.history()!!.isEmpty())
                onView(withId(R.id.manual_confirm)).check(matches(withText("Confirm as entered")))
                screenshot("01-manual-confirmation")
                onView(withId(R.id.manual_confirm)).perform(click())
                awaitHouseholdInventory(scene)
                val purchase = store.history()!!.single()
                assertEquals(PurchaseSource.MANUAL, purchase.source)
                assertTrue(purchase.arithmeticAcknowledged)
                assertNull(purchase.originalFile)
                assertNull(purchase.rows.single().unitPrice)
                assertEquals("8.30", purchase.rows.single().lineTotal.toPlainString())
                assertEquals("8.31", purchase.total.toPlainString())
                val row = store.load()!!.single()
                assertEquals(fruit, row.household.category)

                onView(withId(R.id.receipt_history)).perform(click())
                onView(withText("1 receipt \u00B7 RM 8.31 recorded spending")).check(matches(isDisplayed()))
                screenshot("02-manual-history-and-monthly-spending")
                onView(withId(R.id.receipt_history_search)).perform(replaceText("pears"))
                onView(withText(example)).perform(sageScrollTo(), click())
                onView(withText("Manual entry")).check(matches(isDisplayed()))
                onView(withText("Purchased quantity \u00B7 2")).check(matches(isDisplayed()))
                screenshot("03-manual-purchase-details")
                onView(withText("Delete receipt")).perform(sageScrollTo(), click())
                onView(withText("Delete receipt")).inRoot(isDialog()).perform(click())
                onView(withText("No saved receipts yet")).check(matches(isDisplayed()))
                assertEquals(listOf(row), store.load())
            }
        } finally {
            store.history().orEmpty().filter { it.store == example }.forEach { store.deleteHistory(it.confirmationId) }
            assertNotNull(store.update { rows -> rows.filterNot { it.name == "Task14 pears" } })
        }
    }

    @Test fun failedManualWriteRollsBackAndReplaySurvivesStockEditsAndDeletion() {
        val directory = Files.createTempDirectory(context.cacheDir.toPath(), "task14-manual-")
        try {
            val file = directory.resolve("inventory.json")
            val old = """{"version":1,"rows":[{"id":"manual-receipt-old","name":"Legacy","quantity":9}]}""".encodeToByteArray()
            Files.write(file, old)
            var fail = true
            val inventory = ManualInventoryStore(file) { pending, target ->
                if (fail) throw IOException("Injected failure")
                Files.move(pending, target, ATOMIC_MOVE, REPLACE_EXISTING)
            }
            var today = LocalDate.of(2025, 1, 11)
            val state = PantryUiState(MockReceiptPresentationSource(), inventory, today = { today })
            val draft = EditableReceipt(example, "2025-01-10",
                mutableListOf(EditableReceiptItem("new", "Apples", "2", "", "8.30", fruit)), "8.31", "receipt-test-id")
            val original = byteArrayOf(1, 2, 3)
            assertEquals(ManualInventoryStore.Commit.CONFLICT, state.commitManualReceipt(draft, false, original))
            assertEquals(ManualInventoryStore.Commit.FAILED, state.commitManualReceipt(draft, true, original))
            assertArrayEquals(old, Files.readAllBytes(file))
            assertTrue(inventory.history()!!.isEmpty())
            assertEquals(listOf("inventory.json"), directory.toFile().list()!!.toList())
            fail = false
            today = LocalDate.of(2025, 1, 9)
            assertEquals(ManualInventoryStore.Commit.CONFLICT, state.commitManualReceipt(draft, true, original))
            today = LocalDate.of(2025, 1, 11)
            assertEquals(ManualInventoryStore.Commit.COMMITTED, state.commitManualReceipt(draft, true, original))

            val reopened = ManualInventoryStore(file)
            val saved = reopened.history()!!.single()
            assertEquals("8.31", receiptHistoryMonths(listOf(saved), "apples").single().spending.toPlainString())
            assertArrayEquals(original, reopened.originalFile(saved.confirmationId)!!.readBytes())
            assertEquals(InventoryMetadata(), reopened.load()!!.first().household)
            assertEquals("manual-receipt-old", reopened.load()!!.first().id)
            val reread = PantryUiState(MockReceiptPresentationSource(), reopened, today = { today })
            assertTrue(reread.adjustInventory("manual-receipt-new", 1))
            assertEquals("2", reopened.history()!!.single().rows.single().quantity.toPlainString())
            val rows = reopened.load()
            assertEquals(ManualInventoryStore.Commit.REPLAYED, reread.commitManualReceipt(draft, true, original))
            assertEquals(ManualInventoryStore.Commit.CONFLICT, reread.commitManualReceipt(draft, true, byteArrayOf(9)))
            assertTrue(reopened.deleteHistory(saved.confirmationId))
            assertNull(reopened.originalFile(saved.confirmationId))
            assertEquals(ManualInventoryStore.Commit.REPLAYED, reread.commitManualReceipt(draft, true, original))
            assertEquals(rows, reopened.load())
            assertTrue(reopened.history()!!.isEmpty())
            assertEquals(listOf("inventory.json"), directory.toFile().list()!!.toList())
        } finally {
            directory.toFile().deleteRecursively()
        }
    }

    @Test fun versionTwoMigrationPreservesScannedHistoryLedgerAndOriginal() {
        val directory = Files.createTempDirectory(context.cacheDir.toPath(), "task14-v2-")
        try {
            val file = directory.resolve("inventory.json")
            val identity = "a".repeat(64)
            val fingerprint = "b".repeat(64)
            val sidecar = "saved-receipt-00000000-0000-0000-0000-000000000001"
            val original = byteArrayOf(8, 9)
            Files.write(directory.resolve("$sidecar.original"), original)
            Files.write(directory.resolve("$sidecar.review"), byteArrayOf(6))
            val legacy = """{"version":2,"rows":[{"id":"live-receipt-$identity-row-1","name":"Legacy milk","quantity":"0.750","unit":"kg"}],
"history":[{"confirmationId":"$identity","store":"Legacy Store","date":"2025-01-10","total":"4.50",
"rows":[{"id":"row-1","description":"Legacy milk","quantity":"0.750","inventoryUnit":"kg","included":true,
"unitPrice":null,"unitPriceAbsence":"MISSING","lineTotal":"4.50"}],"evidence":"$sidecar.review","original":"$sidecar.original","fieldAudit":[]}],
"ledger":{"$identity":"$fingerprint"},"legacy":[],"pendingAcknowledgements":["$identity"]}""".encodeToByteArray()
            Files.write(file, legacy)
            val initial = ManualInventoryStore(file)
            val old = initial.load()!!.single()
            val purchase = initial.history()!!.single()
            assertEquals(InventoryMetadata(), old.household)
            assertEquals("0.750", old.quantity.toPlainString())
            assertArrayEquals(legacy, Files.readAllBytes(file))
            val fields = InventoryMetadata(InventoryCategory.DAIRY_EGGS, LocalDate.of(2028, 2, 29), "0.750".toBigDecimal())
            val state = PantryUiState(MockReceiptPresentationSource(), initial)
            assertEquals(PantryUiState.InventoryChange.NOT_SAVED, state.editInventoryItem(old.id, "Protected", "1.00"))
            assertFalse(state.deleteInventoryItem(old.id))
            assertTrue(state.editInventoryMetadata(old.id, old.unit, fields))
            val reopened = ManualInventoryStore(file)
            assertEquals(old.copy(household = fields), reopened.load()!!.single())
            assertEquals(purchase, reopened.history()!!.single())
            assertEquals(setOf(identity), reopened.recover())
            assertArrayEquals(original, reopened.originalFile(identity)!!.readBytes())
            assertEquals(fingerprint, org.json.JSONObject(file.toFile().readText()).getJSONObject("ledger").getString(identity))
            assertEquals(PantryUiState.InventoryChange.SAVED, state.addInventoryItem("Standalone", "1"))
            assertEquals(listOf(purchase), reopened.history())
        } finally {
            directory.toFile().deleteRecursively()
        }
    }

    @Test fun categoryWarningsMetadataControlsAndLargeText() {
        val today = LocalDate.now()
        val dry = InventoryCategory.DRY_FOOD
        val rows = listOf(
            row("past", "Task14 lemons", "0.000", InventoryMetadata(fruit, today.minusDays(1))),
            row("soon", "Task14 apples", "0.750", InventoryMetadata(fruit, today.plusDays(3), "0.750".toBigDecimal())),
            row("normal", "Task14 cereal", "1.000", InventoryMetadata(dry)),
        )
        val ids = rows.mapTo(hashSetOf()) { it.id }
        assertNotNull(store.update { it + rows })
        try {
            ActivityScenario.launch(MainActivity::class.java).use { scene ->
                onView(withText("Vegetables & Fruits")).check(matches(isDisplayed()))
                onView(withText("Task14 lemons")).check(matches(not(isDisplayed())))
                screenshot("04-product-category-groups")
                onView(withText("Vegetables & Fruits")).perform(sageScrollTo(), click())
                onView(withText("Expired")).check(matches(isDisplayed()))
                onView(withText("Out of stock")).check(matches(isDisplayed()))
                onView(withText("Expiring soon")).perform(sageScrollTo()).check(matches(isDisplayed()))
                onView(withText("Low stock")).check(matches(isDisplayed()))
                screenshot("05-expiry-and-stock-warnings")
                onView(withText("Dry Food")).perform(sageScrollTo(), click())
                onView(withText("Task14 cereal")).perform(sageScrollTo()).check(matches(isDisplayed()))
                screenshot("06-normal-stock-without-warning")
                openSageInventoryDetails(rows.last().id)
                onView(withId(R.id.sage_inventory_details)).check(matches(isDisplayed()))
                onView(withText(context.getString(R.string.inventory_edit_item))).perform(sageScrollTo(), click())
                onView(withId(R.id.inventory_category)).perform(sageScrollTo(), click())
                screenshot("07-category-selection")
                onData(equalTo("Household Supplies")).inRoot(isPlatformPopup()).inAdapterView(withId(R.id.inventory_category_choices)).perform(click())
                onView(withId(R.id.inventory_expiry)).perform(sageScrollTo(), replaceText("31-02-2027"))
                onView(withId(android.R.id.button1)).perform(click())
                assertNull(store.load()!!.last().household.expiryDate)
                onView(withId(R.id.inventory_expiry_calendar)).perform(sageScrollTo(), click())
                onView(isAssignableFrom(android.widget.DatePicker::class.java)).inRoot(isDialog()).check(matches(isDisplayed()))
                onView(withId(android.R.id.button2)).inRoot(isDialog()).perform(click())
                val future = today.plusDays(8)
                onView(withId(R.id.inventory_expiry))
                    .perform(sageScrollTo(), replaceText(PurchaseDateInput.display(future)))
                onView(withId(R.id.inventory_minimum)).perform(sageScrollTo(), replaceText("1.000"))
                screenshot("08-expiry-date-editor")
                onView(withId(android.R.id.button1)).perform(click())
                val edited = store.load()!!.last()
                assertEquals(rows.last().id, edited.id)
                assertEquals(InventoryCategory.HOUSEHOLD_SUPPLIES, edited.household.category)
                assertEquals(future, edited.household.expiryDate)
                assertEquals("1.000", edited.household.minimumStock?.toPlainString())

                openSageInventoryDetails(edited.id)
                onView(withText(context.getString(R.string.inventory_edit_item))).perform(sageScrollTo(), click())
                onView(withText("Remove expiry date")).perform(sageScrollTo(), click())
                onView(withId(R.id.inventory_minimum)).perform(sageScrollTo(), replaceText(""))
                onView(withId(android.R.id.button1)).perform(click())
                assertNull(store.load()!!.last().household.expiryDate)
                assertNull(store.load()!!.last().household.minimumStock)
                selectInventoryFilter("Direct")
                selectInventorySort("Quantity low to high")
                onView(withId(R.id.inventory_search)).perform(replaceText("Task14"))
                onView(withText("Task14 lemons")).perform(sageScrollTo()).check(matches(isDisplayed()))
                screenshot("09-search-filter-sort")

                scene.onActivity { activity ->
                    val original = Configuration(activity.resources.configuration)
                    val large = Configuration(original).apply { fontScale = 1.5f }
                    @Suppress("DEPRECATION")
                    activity.resources.updateConfiguration(large, activity.resources.displayMetrics)
                    assertEquals(1.5f, activity.resources.configuration.fontScale, 0f)
                    activity.javaClass.getDeclaredMethod("render").apply { isAccessible = true }.invoke(activity)
                }
                onView(withText("Expired")).perform(sageScrollTo()).check(matches(isDisplayed()))
                screenshot("10-inventory-large-text")
            }
        } finally {
            assertNotNull(store.update { items -> items.filterNot { it.id in ids } })
        }
    }

    private fun row(id: String, name: String, quantity: String, metadata: InventoryMetadata) =
        InventoryItem("manual-inventory-task14-$id", name, quantity.toBigDecimal(), ManualInventoryStore.STANDALONE_ROW_STATE,
            InventoryUnit.KILOGRAM, metadata)

    private fun screenshot(name: String) {
        if (InstrumentationRegistry.getArguments().getString("task14Screenshots") != "true") return
        instrument.waitForIdleSync()
        SystemClock.sleep(300)
        val bitmap = requireNotNull(instrument.uiAutomation.takeScreenshot())
        try {
            File(context.filesDir, "task14-$name.png").outputStream().use {
                assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it))
            }
        } finally { bitmap.recycle() }
    }
}
