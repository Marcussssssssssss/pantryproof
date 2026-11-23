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
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withTagValue
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.data.InventoryItem
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
                    onView(withId(R.id.home_add_receipt)).perform(scrollTo(), click())
                    onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
                    onView(withId(R.id.preview_continue)).perform(scrollTo(), click())
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
                    onView(withId(R.id.manual_review_action)).perform(scrollTo(), click())
                    onView(withText(R.string.review_keep_editing)).perform(click())
                    assertEquals(emptyList<InventoryItem>(), store.load())
                    scenario.onActivity { activity ->
                        activity.findViewById<EditText>(R.id.review_item_0_description).setText("Example oats")
                    }
                    onView(withId(R.id.manual_review_action)).perform(scrollTo(), click())
                    onView(withText(R.string.manual_confirm_action)).perform(click())
                    onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
                    val row = requireNotNull(store.load()).single()
                    assertEquals("Example oats", row.name)
                    assertEquals(2, row.quantity)
                    onView(withTagValue(equalTo("inventory-increase:${row.id}"))).perform(scrollTo(), click())
                    row.copy(quantity = 3).also { assertEquals(listOf(it), store.load()) }
                }
            } finally {
                Intents.release()
            }

            // Close and launch a new Activity instead of calling recreate(), which supplies saved state.
            ActivityScenario.launch(MainActivity::class.java).use {
                onView(withId(R.id.home_inventory)).perform(scrollTo(), click())
                onView(withText(committed.name)).perform(scrollTo()).check(matches(isDisplayed()))
                onView(withText(context.getString(R.string.inventory_quantity_label, 3)))
                    .perform(scrollTo()).check(matches(isDisplayed()))
                assertEquals(listOf(committed), ManualInventoryStore(context).load())
            }
        } finally {
            imageFile.delete()
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
            assertEquals(listOf(row.copy(quantity = 3)), ManualInventoryStore(snapshot).load())
        } finally {
            Files.deleteIfExists(snapshot)
            Files.deleteIfExists(directory)
        }
    }

    @Test
    fun unrecognizedStorageVersionIsNeverOverwritten() {
        val snapshot = Files.createTempFile(context.cacheDir.toPath(), "manual-stock-", ".json")
        try {
            val original = """{"version":2,"rows":[]}""".toByteArray(Charsets.UTF_8)
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
