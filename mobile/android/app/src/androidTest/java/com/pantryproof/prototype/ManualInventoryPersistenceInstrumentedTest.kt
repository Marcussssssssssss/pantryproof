package com.pantryproof.prototype

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.widget.EditText
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withContentDescription
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withTagValue
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryUnit
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.data.MockReceiptPresentationSource
import com.pantryproof.prototype.ui.PantryUiState
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import org.hamcrest.Matchers.equalTo
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ManualInventoryPersistenceInstrumentedTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun reviewedCorrectionAndNewQuantityReloadOnAFreshActivityLaunch() {
        val imageFile = File.createTempFile("manual-inventory-test-", ".png", context.cacheDir)
        try {
            val bitmap = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888)
            try {
                imageFile.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
            } finally {
                bitmap.recycle()
            }

            val store = ManualInventoryStore(context)
            assertEquals(emptyList<InventoryItem>(), store.load())
            Intents.init()
            val committed = try {
                val picker = if (Build.VERSION.SDK_INT >= 33) {
                    MediaStore.ACTION_PICK_IMAGES
                } else {
                    Intent.ACTION_OPEN_DOCUMENT
                }
                Intents.intending(hasAction(picker)).respondWith(
                    ActivityResult(Activity.RESULT_OK, Intent().setData(Uri.fromFile(imageFile))),
                )
                ActivityScenario.launch(MainActivity::class.java).use { scenario ->
                    onView(withId(R.id.home_add_receipt)).perform(sageScrollTo(), click())
                    onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
                    onView(withId(R.id.preview_continue)).perform(sageScrollTo(), click())
                    scenario.onActivity { activity ->
                        mapOf(
                            R.id.review_store_name to "Example Market",
                            R.id.review_purchase_date to "2026-11-23",
                            R.id.review_item_0_description to "Old description",
                            R.id.review_item_0_quantity to "2",
                            R.id.review_item_0_line_total to "8.00",
                            R.id.review_receipt_total to "8.00",
                        ).forEach { (id, value) -> activity.findViewById<EditText>(id).setText(value) }
                    }
                    onView(withId(R.id.manual_review_action)).perform(sageScrollTo(), click())
                    onView(withId(R.id.app_bar_back)).perform(click())
                    assertEquals(emptyList<InventoryItem>(), store.load())
                    assertTrue(store.history()!!.isEmpty())
                    scenario.onActivity { activity ->
                        activity.findViewById<EditText>(R.id.review_item_0_description).setText("Example oats")
                    }
                    onView(withId(R.id.manual_review_action)).perform(sageScrollTo(), click())
                    onView(withId(R.id.keep_receipt_original)).perform(sageScrollTo(), click())
                    onView(withId(R.id.manual_confirm)).perform(click())
                    awaitHouseholdInventory(scenario)
                    val row = requireNotNull(store.load()).single()
                    val saved = requireNotNull(store.history()).single()
                    assertEquals("Example oats", saved.rows.single().description)
                    assertArrayEquals(imageFile.readBytes(), store.originalFile(saved.confirmationId)!!.readBytes())
                    assertEquals("Example oats", row.name)
                    assertEquals(2.toBigDecimal(), row.quantity)
                    openSageInventoryDetails(row.id)
                    onView(withTagValue(equalTo("inventory-increase:${row.id}"))).perform(sageScrollTo(), click())
                    row.copy(quantity = 3.toBigDecimal()).also { assertEquals(listOf(it), store.load()) }
                }
            } finally {
                Intents.release()
            }

            // Close and launch a new Activity instead of calling recreate(), which supplies saved state.
            ActivityScenario.launch(MainActivity::class.java).use {
                onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
                openSageInventoryDetails(committed.id)
                onView(withText(committed.name)).check(matches(isDisplayed()))
                onView(withContentDescription(context.getString(R.string.inventory_quantity_label, 3)))
                    .perform(sageScrollTo()).check(matches(isDisplayed()))
                assertEquals(listOf(committed), ManualInventoryStore(context).load())
            }
        } finally {
            assertTrue(imageFile.isFile)
            imageFile.delete()
            context.getSharedPreferences("receipt-review-preferences", 0).edit().remove("keepOriginal").commit()
            val store = ManualInventoryStore(context)
            val saved = store.history().orEmpty().filter { it.store == "Example Market" }
            saved.forEach { assertTrue(store.deleteHistory(it.confirmationId)) }
            val added = saved.flatMap { it.rows }.mapTo(hashSetOf()) { ManualInventoryStore.ROW_PREFIX + it.id }
            if (added.isNotEmpty()) assertNotNull(store.update { rows -> rows.filterNot { it.id in added } })
        }
    }

    @Test
    fun failedAtomicReplaceKeepsPreviousSnapshotAndAllowsQuantityRetry() {
        val directory = Files.createTempDirectory(context.cacheDir.toPath(), "manual-stock-")
        val snapshot = directory.resolve("inventory.json")
        try {
            val row = InventoryItem("manual-receipt-oats", "Oats", 2, ManualInventoryStore.ROW_STATE)
            var rejectReplace = false
            val store = ManualInventoryStore(snapshot) { pending, target ->
                if (rejectReplace) throw IOException("Injected publication failure")
                Files.move(pending, target, ATOMIC_MOVE, REPLACE_EXISTING)
            }
            assertEquals(listOf(row), store.update { listOf(row) })
            val previousBytes = Files.readAllBytes(snapshot)
            val state = PantryUiState(MockReceiptPresentationSource(), store)

            rejectReplace = true
            assertFalse(state.adjustInventory(row.id, 1))
            assertEquals(row, state.inventory.last())
            assertArrayEquals(previousBytes, Files.readAllBytes(snapshot))
            assertEquals(listOf(row), ManualInventoryStore(snapshot).load())
            assertEquals(listOf("inventory.json"), directory.toFile().list()?.toList())

            rejectReplace = false
            assertTrue(state.adjustInventory(row.id, 1))
            assertEquals(listOf(row.copy(quantity = 3.toBigDecimal())), ManualInventoryStore(snapshot).load())
        } finally {
            Files.deleteIfExists(snapshot)
            Files.deleteIfExists(directory)
        }
    }

    @Test
    fun legacySnapshotMigratesOnSuccessfulDecimalStockWriteAndKeepsStableRows() {
        val directory = Files.createTempDirectory(context.cacheDir.toPath(), "decimal-stock-")
        val snapshot = directory.resolve("inventory.json")
        try {
            val original = """{"version":1,"rows":[{"id":"manual-inventory-legacy","name":"Oats","quantity":9}]}"""
                .toByteArray(Charsets.UTF_8)
            Files.write(snapshot, original)
            val legacy = InventoryItem("manual-inventory-legacy", "Oats", 9, ManualInventoryStore.STANDALONE_ROW_STATE)
            val weighted = InventoryItem("manual-inventory-weighted", "Rice", "0.750".toBigDecimal(),
                ManualInventoryStore.STANDALONE_ROW_STATE, InventoryUnit.KILOGRAM)
            var fail = true
            val store = ManualInventoryStore(snapshot) { pending, target ->
                if (fail) throw IOException("Injected publication failure")
                Files.move(pending, target, ATOMIC_MOVE, REPLACE_EXISTING)
            }
            assertEquals(listOf(legacy), store.load())
            assertNull(store.update { it + weighted })
            assertArrayEquals(original, Files.readAllBytes(snapshot))
            fail = false
            assertEquals(listOf(legacy, weighted), store.update { it + weighted })
            assertEquals(listOf(legacy, weighted), ManualInventoryStore(snapshot).load())
            val reloaded = PantryUiState(MockReceiptPresentationSource(), store)
            assertTrue(reloaded.adjustInventory(weighted.id, -1))
            assertEquals(listOf(legacy, weighted.copy(quantity = "0.749".toBigDecimal())), store.load())
        } finally {
            Files.deleteIfExists(snapshot)
            Files.deleteIfExists(directory)
        }
    }

    @Test
    fun unrecognizedStorageVersionIsNeverOverwritten() {
        val snapshot = Files.createTempFile(context.cacheDir.toPath(), "manual-stock-", ".json")
        try {
            val original = """{"version":4,"rows":[]}""".toByteArray(Charsets.UTF_8)
            Files.write(snapshot, original)
            val store = ManualInventoryStore(snapshot)

            assertNull(store.load())
            assertNull(store.update {
                listOf(InventoryItem("manual-receipt-oats", "Oats", 2, ManualInventoryStore.ROW_STATE))
            })
            assertArrayEquals(original, Files.readAllBytes(snapshot))
        } finally {
            Files.deleteIfExists(snapshot)
        }
    }
}
