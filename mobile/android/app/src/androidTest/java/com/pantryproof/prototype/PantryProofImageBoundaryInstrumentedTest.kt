package com.pantryproof.prototype

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.widget.EditText
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.closeSoftKeyboard
import androidx.test.espresso.action.ViewActions.replaceText
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.doesNotExist
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.Intents.intended
import androidx.test.espresso.intent.Intents.intending
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.espresso.intent.matcher.IntentMatchers.hasExtraWithKey
import androidx.test.espresso.intent.matcher.IntentMatchers.hasFlag
import androidx.test.espresso.intent.matcher.IntentMatchers.anyIntent
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.ui.EditableReceipt
import com.pantryproof.prototype.ui.PantryUiState
import com.pantryproof.prototype.ui.ReceiptValidator
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.atomic.AtomicReference
import org.hamcrest.Matchers.allOf
import org.hamcrest.Matchers.containsString
import org.hamcrest.Matchers.not
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue

@RunWith(AndroidJUnit4::class)
class PantryProofImageBoundaryInstrumentedTest {
    @get:Rule
    val activityRule = ActivityScenarioRule(MainActivity::class.java)

    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun pickerCancellationKeepsSourceScreenAndSyntheticState() = withIntents {
        intending(anyIntent()).respondWith(ActivityResult(Activity.RESULT_CANCELED, null))

        onView(withId(R.id.home_add_receipt)).perform(click())
        onView(withId(R.id.add_import_image)).perform(scrollTo(), click())

        intended(hasAction(expectedPickerAction()))
        onView(withId(R.id.screen_add_receipt)).check(matches(isDisplayed()))
        onView(withId(R.id.screen_preview)).check(doesNotExist())

        onView(withId(R.id.add_use_demo)).perform(scrollTo(), click())
        onView(withText(R.string.preview_synthetic_status)).check(matches(isDisplayed()))
    }

    @Test
    fun cameraCancellationStaysOnAddReceiptAndCleansTemporaryOutput() = withIntents {
        clearCameraFixtures()
        intending(hasAction(MediaStore.ACTION_IMAGE_CAPTURE)).respondWith(
            ActivityResult(Activity.RESULT_CANCELED, null),
        )

        onView(withId(R.id.home_add_receipt)).perform(click())
        onView(withId(R.id.add_capture_image)).perform(scrollTo(), click())

        intended(allOf(
            hasAction(MediaStore.ACTION_IMAGE_CAPTURE),
            hasExtraWithKey(MediaStore.EXTRA_OUTPUT),
            hasFlag(Intent.FLAG_GRANT_READ_URI_PERMISSION),
            hasFlag(Intent.FLAG_GRANT_WRITE_URI_PERMISSION),
        ))
        onView(withId(R.id.screen_add_receipt)).check(matches(isDisplayed()))
        onView(withText(R.string.camera_capture_cancelled_title)).check(matches(isDisplayed()))
        onView(withId(R.id.screen_preview)).check(doesNotExist())
        assertTrue(cameraFixtures().isEmpty())
    }

    @Test
    fun emptyCameraResultIsRejectedAndTemporaryOutputIsRemoved() = withIntents {
        clearCameraFixtures()
        intending(hasAction(MediaStore.ACTION_IMAGE_CAPTURE)).respondWith(
            ActivityResult(Activity.RESULT_OK, null),
        )

        onView(withId(R.id.home_add_receipt)).perform(click())
        onView(withId(R.id.add_capture_image)).perform(scrollTo(), click())

        onView(withId(R.id.screen_add_receipt)).check(matches(isDisplayed()))
        onView(withText(R.string.camera_capture_invalid_title)).check(matches(isDisplayed()))
        onView(withId(R.id.screen_preview)).check(doesNotExist())
        onView(withText("Demo Grocery Store (Synthetic)")).check(doesNotExist())
        assertTrue(cameraFixtures().isEmpty())
    }

    @Test
    fun controlledCameraCaptureRemainsUnprocessedAcrossRecreationAndCleansOnRemoval() =
        withIntents {
            clearCameraFixtures()
            val capturedOutput = AtomicReference<Uri>()
            stubSuccessfulCameraCapture(capturedOutput)

            onView(withId(R.id.home_add_receipt)).perform(click())
            onView(withId(R.id.add_capture_image)).perform(scrollTo(), click())

            intended(allOf(
                hasAction(MediaStore.ACTION_IMAGE_CAPTURE),
                hasExtraWithKey(MediaStore.EXTRA_OUTPUT),
                hasFlag(Intent.FLAG_GRANT_READ_URI_PERMISSION),
                hasFlag(Intent.FLAG_GRANT_WRITE_URI_PERMISSION),
            ))
            assertEquals("content", capturedOutput.get().scheme)
            assertEquals("${context.packageName}.fileprovider", capturedOutput.get().authority)
            onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
            onView(withText(R.string.preview_camera_status)).check(matches(isDisplayed()))
            onView(withText(R.string.preview_camera_status_body)).check(matches(isDisplayed()))
            onView(withId(R.id.preview_selected_image)).check(matches(isDisplayed()))
            onView(withText("Demo Grocery Store (Synthetic)")).check(doesNotExist())

            activityRule.scenario.recreate()
            onView(withText(R.string.preview_camera_status)).check(matches(isDisplayed()))
            onView(withId(R.id.preview_selected_image)).check(matches(isDisplayed()))

            onView(withId(R.id.preview_continue)).perform(scrollTo(), click())
            onView(withId(R.id.screen_manual)).check(matches(isDisplayed()))
            onView(withText(R.string.manual_source_title)).check(matches(isDisplayed()))
            onView(withText("Demo Grocery Store (Synthetic)")).check(doesNotExist())

            onView(withId(R.id.app_bar_back)).perform(click())
            onView(withText(R.string.review_discard_confirm)).perform(click())
            onView(withId(R.id.preview_remove_image)).perform(scrollTo(), click())
            onView(withText(R.string.preview_synthetic_status)).check(matches(isDisplayed()))
            assertTrue(cameraFixtures().isEmpty())
        }

    @Test
    fun unreadableGalleryReplacementPreservesExistingCameraPhoto() = withIntents {
        clearCameraFixtures()
        val capturedOutput = AtomicReference<Uri>()
        stubSuccessfulCameraCapture(capturedOutput)

        onView(withId(R.id.home_add_receipt)).perform(click())
        onView(withId(R.id.add_capture_image)).perform(scrollTo(), click())
        onView(withText(R.string.preview_camera_status)).check(matches(isDisplayed()))
        assertEquals(1, cameraFixtures().size)

        onView(withId(R.id.app_bar_back)).perform(click())
        val unavailableUri = Uri.parse("content://com.pantryproof.prototype.test/revoked-image.png")
        intending(hasAction(expectedPickerAction())).respondWith(ActivityResult(
            Activity.RESULT_OK,
            Intent().setData(unavailableUri).addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION,
            ),
        ))
        onView(withId(R.id.add_import_image)).perform(scrollTo(), click())

        onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
        onView(withText(R.string.preview_image_unavailable_title)).check(matches(isDisplayed()))
        onView(withText(R.string.preview_camera_status)).check(matches(isDisplayed()))
        onView(withId(R.id.preview_selected_image)).check(matches(isDisplayed()))
        assertEquals(1, cameraFixtures().size)
        assertTrue(context.contentResolver.persistedUriPermissions.none {
            it.uri == unavailableUri
        })

        onView(withId(R.id.preview_remove_image)).perform(scrollTo(), click())
        assertTrue(cameraFixtures().isEmpty())
    }

    @Test
    fun unavailableSelectedUriShowsRecoveryWithoutAttributingFields() = withIntents {
        val unavailableUri = Uri.parse("content://com.pantryproof.prototype.test/missing-image.png")
        intending(anyIntent()).respondWith(ActivityResult(
            Activity.RESULT_OK,
            Intent().setData(unavailableUri).addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION,
            ),
        ))

        onView(withId(R.id.home_add_receipt)).perform(click())
        onView(withId(R.id.add_import_image)).perform(scrollTo(), click())

        onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
        onView(withText(R.string.preview_image_unavailable_title)).check(matches(isDisplayed()))
        onView(withId(R.id.preview_image_error)).check(matches(isDisplayed()))
        onView(withId(R.id.preview_use_demo)).check(matches(isDisplayed()))
        onView(withText("Demo Grocery Store (Synthetic)")).check(doesNotExist())
        assertTrue(context.contentResolver.persistedUriPermissions.none {
            it.uri == unavailableUri
        })

        onView(withId(R.id.preview_use_demo)).perform(scrollTo(), click())
        onView(withText(R.string.preview_synthetic_status)).check(matches(isDisplayed()))
    }

    @Test
    fun invalidGalleryReplacementKeepsSelectedGalleryImageUntilHome() = withIntents {
        val imageFile = createSyntheticImageFixture()
        val invalidFile = File.createTempFile("pantryproof-invalid-", ".png", context.cacheDir)
        val selectedUri = Uri.fromFile(imageFile)
        val invalidUri = Uri.fromFile(invalidFile)
        val pickerUri = AtomicReference(selectedUri)
        try {
            invalidFile.writeText("This fixture is not an image.")
            intending(hasAction(expectedPickerAction())).respondWithFunction {
                ActivityResult(
                    Activity.RESULT_OK,
                    Intent().setData(pickerUri.get()).addFlags(
                        Intent.FLAG_GRANT_READ_URI_PERMISSION or
                            Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION,
                    ),
                )
            }

            onView(withId(R.id.home_add_receipt)).perform(click())
            onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
            onView(withId(R.id.preview_selected_image)).check(matches(isDisplayed()))

            pickerUri.set(invalidUri)
            onView(withId(R.id.preview_choose_another)).perform(scrollTo(), click())
            onView(withText(R.string.preview_image_unavailable_title)).check(matches(isDisplayed()))
            onView(withText(R.string.preview_local_status)).check(matches(isDisplayed()))
            onView(withId(R.id.preview_selected_image)).check(matches(isDisplayed()))
            assertTrue(context.contentResolver.persistedUriPermissions.none { it.uri == invalidUri })

            onView(withText(R.string.preview_cancel)).perform(scrollTo(), click())
            onView(withId(R.id.home_add_receipt)).check(matches(isDisplayed()))
            onView(withId(R.id.home_add_receipt)).perform(click())
            onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
            onView(withId(R.id.preview_image_error)).check(matches(isDisplayed()))
            onView(withId(R.id.preview_selected_image)).check(doesNotExist())
            assertTrue(imageFile.isFile)
        } finally {
            invalidFile.delete()
            imageFile.delete()
        }
    }

    @Test
    fun galleryManualEntryValidatesRestoresAndConfirmsOnlyReviewedRows() = withIntents {
        fun enterGalleryField(id: Int, value: String) {
            onView(withId(id)).perform(scrollTo(), replaceText(value))
            onView(withId(id)).check(matches(withText(value)))
        }

        val imageFile = createSyntheticImageFixture()
        val imageUri = Uri.fromFile(imageFile)
        try {
            intending(anyIntent()).respondWith(ActivityResult(
                Activity.RESULT_OK,
                Intent().setData(imageUri).addFlags(
                    Intent.FLAG_GRANT_READ_URI_PERMISSION or
                        Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION,
                ),
            ))

            onView(withId(R.id.home_add_receipt)).perform(click())
            onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
            onView(withText(R.string.preview_local_status)).check(matches(isDisplayed()))

            activityRule.scenario.recreate()
            onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
            onView(withText(R.string.preview_local_status)).check(matches(isDisplayed()))

            onView(withId(R.id.preview_continue)).perform(scrollTo(), click())
            onView(withText(R.string.manual_source_title)).check(matches(isDisplayed()))
            onView(withText("Demo Grocery Store (Synthetic)")).check(doesNotExist())
            onView(withId(R.id.manual_review_action)).perform(scrollTo(), click())
            onView(withId(R.id.review_error_summary)).check(matches(isDisplayed()))
            onView(withText(R.string.manual_confirm_action)).check(doesNotExist())

            enterGalleryField(R.id.review_store_name, "Fictional Kedai")
            onView(withId(R.id.review_error_summary)).check(matches(withText(containsString("Use a valid date"))))
            enterGalleryField(R.id.review_purchase_date, "2026-11-10")
            enterGalleryField(R.id.review_item_0_description, "Synthetic oats")
            enterGalleryField(R.id.review_item_0_quantity, "2")
            enterGalleryField(R.id.review_item_0_line_total, "8.00")
            onView(withId(R.id.manual_add_item)).perform(scrollTo(), click())
            onView(withId(R.id.review_item_1_description))
                .perform(scrollTo(), replaceText("Discarded row"))
            onView(withId(R.id.review_item_1_description))
                .check(matches(withText("Discarded row")))
            activityRule.scenario.recreate()
            onView(withId(R.id.review_item_1_description)).check(matches(withText("Discarded row")))
            onView(withText(context.getString(R.string.manual_remove_item, 2))).perform(scrollTo(), click())
            enterGalleryField(R.id.review_receipt_total, "8.00")
            enterGalleryField(R.id.review_item_0_unit_price, "4.01")
            onView(withId(R.id.manual_review_action)).perform(scrollTo(), click())
            onView(withText(R.string.manual_review_title)).check(matches(isDisplayed()))
            onView(withId(android.R.id.message)).check(matches(withText(
                containsString(context.getString(R.string.manual_line_difference, 1)),
            )))
            onView(withText(R.string.review_keep_editing)).perform(click())
            onView(withId(R.id.screen_manual)).check(matches(isDisplayed()))
            enterGalleryField(R.id.review_item_0_unit_price, "4.00")
            onView(withId(R.id.manual_review_action)).perform(scrollTo(), click())
            onView(withId(android.R.id.message)).check(matches(withText(not(
                containsString(context.getString(R.string.manual_arithmetic_warning)),
            ))))
            // Exercise the defensive guard by changing the live draft behind the modal.
            activityRule.scenario.onActivity { activity ->
                activity.findViewById<EditText>(R.id.review_receipt_total).setText("8.01")
            }
            onView(withText(R.string.manual_confirm_action)).perform(click())
            onView(withText(R.string.manual_review_changed)).check(matches(isDisplayed()))
            onView(withId(R.id.screen_inventory)).check(doesNotExist())
            onView(withId(R.id.review_receipt_total)).check(matches(withText("8.01")))
            onView(withId(R.id.manual_review_action)).perform(scrollTo(), click())
            onView(withId(android.R.id.message)).check(matches(withText(
                containsString(context.getString(R.string.manual_total_difference)),
            )))
            onView(withText(R.string.manual_confirm_action)).perform(click())
            onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
            onView(withText("Synthetic oats")).perform(scrollTo()).check(matches(isDisplayed()))
            onView(withText("Discarded row")).check(doesNotExist())
            activityRule.scenario.recreate()
            onView(withText("Synthetic oats")).perform(scrollTo()).check(matches(isDisplayed()))
            assertTrue(imageFile.isFile)
            assertTrue(context.contentResolver.persistedUriPermissions.none {
                it.uri == imageUri
            })
        } finally {
            imageFile.delete()
        }
    }

    @Test
    fun confirmingCameraReceiptWithWarningAddsOnlyTheEnteredItemAndCleansCapture() = withIntents {
        clearCameraFixtures()
        stubSuccessfulCameraCapture(AtomicReference<Uri>())
        onView(withId(R.id.home_add_receipt)).perform(click())
        onView(withId(R.id.add_capture_image)).perform(scrollTo(), click())
        assertEquals(1, cameraFixtures().size)
        onView(withId(R.id.preview_continue)).perform(scrollTo(), click())
        enterManualField(R.id.review_store_name, "Fictional Mart")
        enterManualField(R.id.review_purchase_date, "2026-11-10")
        enterManualField(R.id.review_item_0_description, "Synthetic tea")
        enterManualField(R.id.review_item_0_quantity, "2")
        enterManualField(R.id.review_item_0_unit_price, "4.00")
        enterManualField(R.id.review_item_0_line_total, "7.50")
        enterManualField(R.id.review_receipt_total, "7.50")
        onView(withId(R.id.manual_review_action)).perform(scrollTo(), click())
        onView(withId(android.R.id.message)).check(matches(withText(
            containsString(context.getString(R.string.manual_arithmetic_warning)),
        )))
        onView(withText(R.string.manual_confirm_action)).perform(click())
        onView(withText("Synthetic tea")).perform(scrollTo()).check(matches(isDisplayed()))
        assertTrue(cameraFixtures().isEmpty())
    }

    @Test
    fun duplicateManualRowsShowRecoveryWithoutChangingDraftOrInventory() = withIntents {
        val image = createSyntheticImageFixture()
        try {
            intending(hasAction(expectedPickerAction())).respondWith(
                ActivityResult(Activity.RESULT_OK, Intent().setData(Uri.fromFile(image))),
            )
            onView(withId(R.id.home_add_receipt)).perform(click())
            onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
            onView(withId(R.id.preview_continue)).perform(scrollTo(), click())
            onView(withId(R.id.manual_add_item)).perform(scrollTo(), click())

            // Inject an impossible-by-normal-entry ID collision before review. Production still
            // validates, snapshots and confirms the draft through its normal button handlers.
            val draftField = MainActivity::class.java.getDeclaredField("manualDraft").apply { isAccessible = true }
            val stateField = MainActivity::class.java.getDeclaredField("state").apply { isAccessible = true }
            val values = mapOf(
                R.id.review_store_name to "Fictional Kedai",
                R.id.review_purchase_date to "2026-11-10",
                R.id.review_item_0_description to "Synthetic oats",
                R.id.review_item_0_quantity to "2",
                R.id.review_item_0_unit_price to "4.00",
                R.id.review_item_0_line_total to "8.00",
                R.id.review_item_1_description to "Synthetic tea",
                R.id.review_item_1_quantity to "1",
                R.id.review_item_1_unit_price to "3.00",
                R.id.review_item_1_line_total to "3.00",
                R.id.review_receipt_total to "11.00",
            )
            lateinit var reviewedDraft: EditableReceipt
            lateinit var inventoryBefore: List<InventoryItem>
            activityRule.scenario.onActivity { activity ->
                values.forEach { (id, value) -> activity.findViewById<EditText>(id).setText(value) }
                val draft = draftField.get(activity) as EditableReceipt
                draft.items[1] = draft.items[1].copy(id = draft.items[0].id)
                assertTrue(ReceiptValidator.validateManual(draft).isValid)
                reviewedDraft = draft.deepCopy()
                inventoryBefore = (stateField.get(activity) as PantryUiState).inventory.toList()
            }

            onView(withId(R.id.manual_review_action)).perform(scrollTo(), click())
            onView(withText(R.string.manual_review_title)).check(matches(isDisplayed()))
            activityRule.scenario.onActivity { activity ->
                assertEquals(reviewedDraft, draftField.get(activity))
            }
            onView(withText(R.string.manual_confirm_action)).perform(click())
            onView(withText(R.string.manual_confirmation_failed)).check(matches(isDisplayed()))
            onView(withText(R.string.manual_review_changed)).check(doesNotExist())
            onView(withId(R.id.screen_manual)).check(matches(isDisplayed()))
            onView(withId(R.id.screen_inventory)).check(doesNotExist())
            activityRule.scenario.onActivity { activity ->
                assertEquals(reviewedDraft, draftField.get(activity))
                assertEquals(inventoryBefore, (stateField.get(activity) as PantryUiState).inventory.toList())
            }
            values.forEach { (id, value) -> onView(withId(id)).check(matches(withText(value))) }
        } finally {
            image.delete()
        }
    }

    private fun enterManualField(id: Int, value: String) {
        onView(withId(id)).perform(scrollTo(), replaceText(value), closeSoftKeyboard())
    }

    private fun expectedPickerAction(): String =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            MediaStore.ACTION_PICK_IMAGES
        } else {
            Intent.ACTION_OPEN_DOCUMENT
        }

    private fun createSyntheticImageFixture(): File {
        val fixture = File(context.cacheDir, "pantryproof-test-${System.nanoTime()}.png")
        fixture.outputStream().use { output ->
            Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888).apply {
                eraseColor(Color.rgb(23, 107, 82))
                compress(Bitmap.CompressFormat.PNG, 100, output)
                recycle()
            }
        }
        return fixture
    }

    private fun cameraFixtures(): List<File> =
        File(context.cacheDir, "receipt_camera").listFiles().orEmpty().toList()

    private fun clearCameraFixtures() {
        cameraFixtures().forEach(File::delete)
    }

    private fun stubSuccessfulCameraCapture(capturedOutput: AtomicReference<Uri>) {
        intending(hasAction(MediaStore.ACTION_IMAGE_CAPTURE)).respondWithFunction { intent ->
            @Suppress("DEPRECATION")
            val output = requireNotNull(intent.getParcelableExtra<Uri>(MediaStore.EXTRA_OUTPUT))
            capturedOutput.set(output)
            assertEquals(output, intent.clipData?.getItemAt(0)?.uri)
            assertTrue(intent.flags and Intent.FLAG_GRANT_READ_URI_PERMISSION != 0)
            assertTrue(intent.flags and Intent.FLAG_GRANT_WRITE_URI_PERMISSION != 0)
            context.contentResolver.openOutputStream(output, "w")!!.use { stream ->
                Bitmap.createBitmap(12, 16, Bitmap.Config.ARGB_8888).apply {
                    eraseColor(Color.rgb(23, 107, 82))
                    compress(Bitmap.CompressFormat.JPEG, 90, stream)
                    recycle()
                }
            }
            ActivityResult(Activity.RESULT_OK, null)
        }
    }

    private inline fun withIntents(block: () -> Unit) {
        Intents.init()
        try {
            block()
        } finally {
            Intents.release()
        }
    }
}
