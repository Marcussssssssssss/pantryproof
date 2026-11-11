package com.pantryproof.prototype

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.provider.MediaStore
import android.view.MotionEvent
import android.view.View
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.DatePicker
import android.widget.EditText
import android.widget.SeekBar
import androidx.core.view.ViewCompat
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.UiController
import androidx.test.espresso.ViewAction
import androidx.test.espresso.action.ViewActions.click
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
import androidx.test.espresso.matcher.RootMatchers.isDialog
import androidx.test.espresso.matcher.ViewMatchers.isCompletelyDisplayed
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.isAssignableFrom
import androidx.test.espresso.matcher.ViewMatchers.isDescendantOfA
import androidx.test.espresso.matcher.ViewMatchers.withContentDescription
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.image.ReceiptCrop
import com.pantryproof.prototype.image.ReceiptCropView
import com.pantryproof.prototype.ui.EditableReceipt
import com.pantryproof.prototype.ui.PantryUiState
import com.pantryproof.prototype.ui.ReceiptValidator
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.time.LocalDate
import java.util.GregorianCalendar
import java.util.concurrent.atomic.AtomicReference
import org.hamcrest.Matchers.allOf
import org.hamcrest.Matcher
import org.hamcrest.Matchers.containsString
import org.hamcrest.Matchers.not
import org.junit.Assert.assertEquals
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import kotlin.math.roundToInt

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
            onView(withId(R.id.review_error_summary)).check(doesNotExist())
            onView(allOf(
                withText("Store name is required."),
                isDescendantOfA(withId(R.id.screen_manual)),
            )).check(matches(isDisplayed()))
            onView(withText(R.string.manual_confirm_action)).check(doesNotExist())

            enterGalleryField(R.id.review_store_name, "Fictional Kedai")
            onView(allOf(
                withText("Use a valid date in YYYY-MM-DD format."),
                isDescendantOfA(withId(R.id.screen_manual)),
            )).perform(scrollTo()).check(matches(isDisplayed()))
            chooseManualDate()
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
            onView(withText(R.string.manual_remove_confirm_action)).perform(click())
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
        chooseManualDate()
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
            chooseManualDate()

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
                values.filterKeys { it != R.id.review_purchase_date }.forEach { (id, value) ->
                    activity.findViewById<EditText>(id).setText(value)
                }
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

    private fun chooseManualDate(date: LocalDate = LocalDate.of(2026, 11, 10)) {
        onView(withId(R.id.review_purchase_date)).perform(scrollTo(), click())
        onView(isAssignableFrom(DatePicker::class.java)).perform(object : ViewAction {
            override fun getConstraints(): Matcher<View> = isAssignableFrom(DatePicker::class.java)
            override fun getDescription() = "select a synthetic date using the native picker"
            override fun perform(controller: UiController, view: View) {
                val picker = view as DatePicker
                val target = GregorianCalendar(date.year, date.monthValue - 1, date.dayOfMonth)
                assertTrue("Date must be in the selectable range", target.timeInMillis in picker.minDate..picker.maxDate)
                picker.updateDate(date.year, date.monthValue - 1, date.dayOfMonth)
                assertEquals(date, LocalDate.of(picker.year, picker.month + 1, picker.dayOfMonth))
                controller.loopMainThreadUntilIdle()
            }
        })
        onView(withId(android.R.id.button1)).perform(click())
        onView(withId(R.id.review_purchase_date)).check(matches(withText(date.toString())))
    }

    @Test
    fun manualCalendarPreservesDateDomainAndRejectsInvalidManualDate() = withIntents {
        val image = createSyntheticImageFixture()
        try {
            openGalleryPreview(image)
            onView(withId(R.id.preview_continue)).perform(scrollTo(), click())
            enterManualField(R.id.review_store_name, "Fictional Kedai")
            chooseManualDate(LocalDate.of(1899, 12, 31))
            chooseManualDate(LocalDate.of(2101, 1, 1))

            val date = onView(withId(R.id.review_purchase_date))
            val manualInput = onView(isAssignableFrom(EditText::class.java)).inRoot(isDialog())
            date.perform(scrollTo(), click())
            onView(withId(android.R.id.button3)).perform(click())
            manualInput.perform(replaceText("2101-02-29"))
            onView(withId(android.R.id.button1)).perform(click())
            date.check(matches(withText("2101-02-29")))
            onView(withId(R.id.manual_review_action)).perform(scrollTo(), click())
            val dateError = onView(allOf(
                withText("Use a valid date in YYYY-MM-DD format."),
                isDescendantOfA(withId(R.id.screen_manual)),
            ))
            dateError.check(matches(isDisplayed()))
            onView(withText(R.string.manual_confirm_action)).check(doesNotExist())
            chooseManualDate()
            dateError.check(doesNotExist())

            date.perform(scrollTo(), click())
            onView(withId(android.R.id.button3)).perform(click())
            manualInput.perform(replaceText("0000-02-29"))
            onView(withId(android.R.id.button1)).perform(click())
            date.check(matches(withText("0000-02-29")))
            date.perform(scrollTo(), click())
            manualInput.check(matches(withText("0000-02-29")))
            onView(withId(android.R.id.button2)).perform(click())
            enterManualField(R.id.review_item_0_description, "Synthetic rice")
            enterManualField(R.id.review_item_0_quantity, "1")
            enterManualField(R.id.review_item_0_line_total, "6.00")
            enterManualField(R.id.review_receipt_total, "6.00")
            onView(withId(R.id.manual_review_action)).perform(scrollTo(), click())
            onView(withId(android.R.id.message)).check(matches(withText(containsString("0000-02-29"))))
            onView(withText(R.string.manual_confirm_action)).check(matches(isDisplayed()))
        } finally {
            image.delete()
        }
    }

    @Test
    fun minimumCropCenterDragsMoveAndCornersStillResize() {
        activityRule.scenario.onActivity { activity ->
            val density = activity.resources.displayMetrics.density
            val minimum = requireNotNull(ReceiptCrop.from(floatArrayOf(0.46f, 0.46f, 0.54f, 0.54f)))
            for ((imageWidth, imageHeight, viewHeightDp) in listOf(
                Triple(8, 8, 320),
                Triple(80, 320, 140),
                Triple(320, 80, 140),
            )) {
                val bitmap = Bitmap.createBitmap(imageWidth, imageHeight, Bitmap.Config.ARGB_8888)
                try {
                    val view = ReceiptCropView(activity, bitmap, minimum)
                    val width = (280 * density).toInt()
                    val height = (viewHeightDp * density).toInt()
                    view.layout(0, 0, width, height)
                    val fit = minOf((width - 24 * density) / imageWidth, (height - 24 * density) / imageHeight)
                    val fitWidth = imageWidth * fit
                    val fitHeight = imageHeight * fit
                    fun x(normalized: Float) = width / 2f + (normalized - 0.5f) * fitWidth
                    fun y(normalized: Float) = height / 2f + (normalized - 0.5f) * fitHeight

                    dragCrop(view, x(0.5f), y(0.5f), x(0.62f), y(0.60f))
                    assertArrayEquals(floatArrayOf(0.58f, 0.56f, 0.66f, 0.64f), view.crop.values(), 0.0001f)
                    assertNotNull(ReceiptCrop.from(view.crop.values()))

                    val moved = view.crop
                    dragCrop(view, x(moved.left), y(moved.top), x(-0.1f), y(-0.1f))
                    assertArrayEquals(floatArrayOf(0f, 0f, moved.right, moved.bottom), view.crop.values(), 0.0001f)
                    assertNotNull(ReceiptCrop.from(view.crop.values()))
                } finally {
                    bitmap.recycle()
                }
            }
        }
    }

    private fun dragCrop(view: ReceiptCropView, startX: Float, startY: Float, endX: Float, endY: Float) {
        val start = SystemClock.uptimeMillis()
        val actions = listOf(MotionEvent.ACTION_DOWN, MotionEvent.ACTION_MOVE, MotionEvent.ACTION_UP)
        actions.forEachIndexed { index, action ->
            val x = if (index == 0) startX else endX
            val y = if (index == 0) startY else endY
            val event = MotionEvent.obtain(start, start + index * 16L, action, x, y, 0)
            try {
                assertTrue(view.dispatchTouchEvent(event))
            } finally {
                event.recycle()
            }
        }
    }

    @Test
    fun cropApplyCancelResetAndRecreationKeepOriginalGalleryImage() = withIntents {
        val image = createSyntheticImageFixture(twoTone = true)
        val original = image.readBytes()
        try {
            openGalleryPreview(image)
            assertPreviewColor(Color.GREEN)
            onView(withId(R.id.preview_crop_receipt)).perform(scrollTo(), click())
            onView(withId(R.id.crop_editor_image)).check(matches(withContentDescription(R.string.crop_editor_description)))
            moveCropLeftEdge(60)
            onView(withText(android.R.string.cancel)).perform(scrollTo(), click())
            onView(withId(R.id.preview_crop_status)).check(doesNotExist())
            assertPreviewColor(Color.GREEN)

            onView(withId(R.id.preview_crop_receipt)).perform(scrollTo(), click())
            moveCropLeftEdge(60)
            onView(withText(R.string.crop_apply)).perform(scrollTo(), click())
            onView(withId(R.id.preview_crop_status)).check(matches(withText(R.string.crop_applied)))
            assertPreviewColor(Color.RED)
            activityRule.scenario.recreate()
            assertPreviewColor(Color.RED)
            checkZoomControls()

            onView(withId(R.id.preview_continue)).perform(scrollTo(), click())
            onView(withText(R.string.manual_view_image)).perform(scrollTo(), click())
            assertPreviewColor(Color.RED)
            checkZoomControls()
            onView(withText(android.R.string.ok)).perform(click())
            onView(withId(R.id.app_bar_back)).perform(click())
            onView(withText(R.string.review_discard_confirm)).perform(click())
            onView(withId(R.id.preview_crop_receipt)).perform(scrollTo(), click())
            onView(withText(R.string.crop_reset)).perform(scrollTo(), click())
            onView(withText(R.string.crop_apply)).perform(scrollTo(), click())
            onView(withId(R.id.preview_crop_status)).check(doesNotExist())
            assertPreviewColor(Color.GREEN)
            assertArrayEquals(original, image.readBytes())
        } finally {
            image.delete()
        }
    }

    @Test
    fun manualCalendarAndRemovalPreserveOtherValuesAndAcceptBlankUnitPrice() = withIntents {
        val image = createSyntheticImageFixture()
        try {
            openGalleryPreview(image)
            onView(withId(R.id.preview_continue)).perform(scrollTo(), click())
            val date = onView(withId(R.id.review_purchase_date))
            date.perform(scrollTo(), click())
            onView(withText(android.R.string.cancel)).perform(click())
            date.check(matches(withText("")))
            enterManualField(R.id.review_store_name, "Fictional Kedai")
            onView(withId(R.id.manual_review_action)).perform(scrollTo(), click())
            onView(withId(R.id.review_error_summary)).check(doesNotExist())
            val dateError = onView(allOf(
                withText("Use a valid date in YYYY-MM-DD format."),
                isDescendantOfA(withId(R.id.screen_manual)),
            ))
            dateError.check(matches(isDisplayed()))
            date.check { view, exception ->
                if (exception != null) throw exception
                val input = view as EditText
                val node = input.createAccessibilityNodeInfo()
                assertEquals("android.widget.Button", node.className.toString())
                assertTrue(!node.isEditable && input.keyListener == null && input.isFocused)
                assertTrue(node.error.toString().contains("Use a valid date"))
            }
            chooseManualDate()
            dateError.check(doesNotExist())
            date.perform(scrollTo(), click())
            onView(withText(android.R.string.cancel)).perform(click())
            activityRule.scenario.recreate()
            date.check(matches(withText("2026-11-10")))

            val removeFirst = onView(withText(context.getString(R.string.manual_remove_item, 1)))
            removeFirst.perform(scrollTo(), click())
            onView(withText(R.string.manual_keep_one_body)).check(matches(isDisplayed()))
            onView(withText(android.R.string.ok)).perform(click())
            onView(withId(R.id.review_item_0_description)).check(matches(withText("")))
            enterManualField(R.id.review_item_0_description, "Synthetic rice")
            onView(withId(R.id.manual_add_item)).perform(scrollTo(), click())
            enterManualField(R.id.review_item_1_description, "Synthetic tea")
            enterManualField(R.id.review_item_1_quantity, "2")
            enterManualField(R.id.review_item_1_line_total, "6.00")
            enterManualField(R.id.review_receipt_total, "6.00")
            removeFirst.perform(scrollTo(), click())
            onView(withId(android.R.id.message)).check(matches(withText(containsString("Synthetic rice"))))
            onView(withText(android.R.string.cancel)).perform(click())
            onView(withId(R.id.review_item_0_description)).check(matches(withText("Synthetic rice")))
            onView(withId(R.id.review_item_1_description)).check(matches(withText("Synthetic tea")))
            removeFirst.perform(scrollTo(), click())
            onView(withText(R.string.manual_remove_confirm_action)).perform(click())
            onView(withId(R.id.review_item_1_description)).check(doesNotExist())
            onView(withId(R.id.review_item_0_description)).check(matches(withText("Synthetic tea")))
            onView(withId(R.id.review_item_0_quantity)).check(matches(withText("2")))
            onView(withId(R.id.review_item_0_unit_price)).check(matches(withText("")))
            onView(withId(R.id.manual_review_action)).perform(scrollTo(), click())
            onView(withId(android.R.id.message)).check(matches(withText(
                containsString(context.getString(R.string.manual_unit_price_not_entered)),
            )))
            onView(withText(R.string.manual_confirm_action)).perform(click())
            onView(withText("Synthetic tea")).perform(scrollTo()).check(matches(isDisplayed()))
            onView(withText("Synthetic rice")).check(doesNotExist())
        } finally {
            image.delete()
        }
    }

    private fun openGalleryPreview(image: File) {
        intending(hasAction(expectedPickerAction())).respondWith(
            ActivityResult(Activity.RESULT_OK, Intent().setData(Uri.fromFile(image))),
        )
        onView(withId(R.id.home_add_receipt)).perform(scrollTo(), click())
        onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
        onView(withId(R.id.preview_selected_image)).perform(scrollTo()).check(matches(isDisplayed()))
    }

    @Test
    fun cropMovementButtonsClampAndPreserveApplyCancelReset() = withIntents {
        if (InstrumentationRegistry.getArguments().getString("m3jCompactLayout") == "true") {
            activityRule.scenario.onActivity { activity ->
                val configuration = activity.resources.configuration
                assertTrue("Compact width: ${configuration.screenWidthDp} dp", configuration.screenWidthDp <= 320)
                assertEquals(2f, configuration.fontScale, 0.01f)
            }
        }
        val image = createSyntheticImageFixture(twoTone = true)
        val original = image.readBytes()
        try {
            openGalleryPreview(image)
            openCropEditor()
            assertCropMovementControlsReachable()

            setCropEdges(1, 1, 9, 9)
            repeat(2) {
                clickCropMove(R.id.crop_move_left)
                clickCropMove(R.id.crop_move_up)
                assertCropBounds(0f, 0f, 0.08f, 0.08f)
            }
            assertCropSliderPositions(0, 0, 8, 8)

            setCropEdges(91, 91, 99, 99)
            repeat(2) {
                clickCropMove(R.id.crop_move_right)
                clickCropMove(R.id.crop_move_down)
                assertCropBounds(0.92f, 0.92f, 1f, 1f)
            }
            assertCropSliderPositions(92, 92, 100, 100)
            onView(withText(R.string.crop_apply)).perform(scrollTo(), click())
            assertPreviewColor(Color.RED)
            activityRule.scenario.recreate()
            openCropEditor()
            assertCropBounds(0.92f, 0.92f, 1f, 1f)

            clickCropMove(R.id.crop_move_left)
            assertCropBounds(0.87f, 0.92f, 0.95f, 1f)
            onView(withText(android.R.string.cancel)).perform(scrollTo(), click())
            openCropEditor()
            assertCropBounds(0.92f, 0.92f, 1f, 1f)
            onView(withText(R.string.crop_reset)).perform(scrollTo(), click())
            assertCropBounds(0f, 0f, 1f, 1f)
            assertCropSliderPositions(0, 0, 100, 100)
            onView(withText(R.string.crop_apply)).perform(scrollTo(), click())
            onView(withId(R.id.preview_crop_status)).check(doesNotExist())
            assertPreviewColor(Color.GREEN)
            assertArrayEquals(original, image.readBytes())
        } finally {
            image.delete()
        }
    }

    @Test
    fun cropMovementButtonsTranslateTallAndWideMinimumSelections() = withIntents {
        val tall = createSyntheticImageFixture(width = 8, height = 64)
        val wide = createSyntheticImageFixture(width = 64, height = 8)
        val selected = AtomicReference(Uri.fromFile(tall))
        try {
            intending(hasAction(expectedPickerAction())).respondWithFunction {
                ActivityResult(Activity.RESULT_OK, Intent().setData(selected.get()))
            }
            onView(withId(R.id.home_add_receipt)).perform(click())
            onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
            for (image in listOf(tall, wide)) {
                if (image == wide) {
                    selected.set(Uri.fromFile(wide))
                    onView(withId(R.id.preview_choose_another)).perform(scrollTo(), click())
                }
                val original = image.readBytes()
                openCropEditor()
                setCropEdges(46, 46, 54, 54)
                clickCropMove(R.id.crop_move_right)
                assertCropBounds(0.51f, 0.46f, 0.59f, 0.54f)
                clickCropMove(R.id.crop_move_down)
                assertCropBounds(0.51f, 0.51f, 0.59f, 0.59f)
                clickCropMove(R.id.crop_move_left)
                assertCropBounds(0.46f, 0.51f, 0.54f, 0.59f)
                clickCropMove(R.id.crop_move_up)
                assertCropBounds(0.46f, 0.46f, 0.54f, 0.54f)
                onView(withText(android.R.string.cancel)).perform(scrollTo(), click())
                assertArrayEquals(original, image.readBytes())
            }
        } finally {
            tall.delete()
            wide.delete()
        }
    }

    private fun openCropEditor() {
        onView(withId(R.id.preview_crop_receipt)).perform(scrollTo(), click())
    }

    private fun assertCropMovementControlsReachable() {
        for ((buttonId, label) in listOf(
            R.id.crop_move_left to R.string.crop_move_left,
            R.id.crop_move_right to R.string.crop_move_right,
            R.id.crop_move_up to R.string.crop_move_up,
            R.id.crop_move_down to R.string.crop_move_down,
        )) {
            val button = onView(withId(buttonId))
            button.perform(scrollTo()).check(matches(allOf(isCompletelyDisplayed(), withContentDescription(label))))
            button.check { view, exception ->
                if (exception != null) throw exception
                val minimum = (48 * view.resources.displayMetrics.density).roundToInt()
                assertTrue(view.isFocusable && view.isClickable)
                assertTrue(view.width >= minimum && view.height >= minimum)
            }
        }
    }

    private fun clickCropMove(id: Int) {
        onView(withId(id)).perform(scrollTo(), click())
    }

    private fun assertCropBounds(left: Float, top: Float, right: Float, bottom: Float) {
        onView(withId(R.id.crop_editor_image)).check { view, exception ->
            if (exception != null) throw exception
            val bounds = (view as ReceiptCropView).crop.values()
            assertArrayEquals(floatArrayOf(left, top, right, bottom), bounds, 0.0001f)
            assertNotNull(ReceiptCrop.from(bounds))
        }
    }

    private fun assertCropSliderPositions(left: Int, top: Int, right: Int, bottom: Int) {
        val expected = listOf(
            R.id.crop_edge_left to left,
            R.id.crop_edge_top to top,
            R.id.crop_edge_right to right,
            R.id.crop_edge_bottom to bottom,
        )
        for ((id, position) in expected) {
            onView(withId(id)).check { view, exception ->
                if (exception != null) throw exception
                assertEquals(position, (view as SeekBar).progress)
            }
        }
    }

    private fun setCropEdges(left: Int, top: Int, right: Int, bottom: Int) {
        setCropEdge(R.id.crop_edge_right, right)
        setCropEdge(R.id.crop_edge_bottom, bottom)
        setCropEdge(R.id.crop_edge_left, left)
        setCropEdge(R.id.crop_edge_top, top)
    }

    private fun moveCropLeftEdge(progress: Int) = setCropEdge(R.id.crop_edge_left, progress)

    private fun setCropEdge(id: Int, progress: Int) {
        onView(withId(id)).perform(scrollTo(), object : ViewAction {
            override fun getConstraints(): Matcher<View> = isAssignableFrom(SeekBar::class.java)
            override fun getDescription() = "adjust the crop with its accessible edge slider"
            override fun perform(controller: UiController, view: View) {
                if ((view as SeekBar).progress == progress) return
                val arguments = Bundle().apply {
                    putFloat(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE, progress.toFloat())
                }
                assertTrue(view.performAccessibilityAction(
                    AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.id, arguments,
                ))
                controller.loopMainThreadUntilIdle()
            }
        })
    }

    private fun assertPreviewColor(expected: Int) {
        onView(withId(R.id.preview_selected_image)).check { view, exception ->
            if (exception != null) throw exception
            val rendered = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            try {
                view.draw(Canvas(rendered))
                assertEquals(expected, rendered.getPixel((view.width * 0.42f).toInt(), view.height / 2))
            } finally {
                rendered.recycle()
            }
        }
    }

    private fun checkZoomControls() {
        val zoomIn = onView(withId(R.id.preview_zoom_in))
        val zoomOut = onView(withId(R.id.preview_zoom_out))
        val reset = onView(withId(R.id.preview_zoom_reset))
        zoomIn.check(matches(withContentDescription(R.string.preview_zoom_in)))
        zoomOut.check(matches(withContentDescription(R.string.preview_zoom_out)))
        fun assertZoom(percent: Int) {
            onView(withId(R.id.preview_selected_image)).check { view, exception ->
                if (exception != null) throw exception
                assertEquals(context.getString(R.string.preview_zoom_level, percent), ViewCompat.getStateDescription(view))
            }
        }
        assertZoom(100)
        zoomIn.perform(scrollTo(), click())
        assertZoom(150)
        zoomOut.perform(scrollTo(), click())
        assertZoom(100)
        zoomIn.perform(scrollTo(), click())
        reset.perform(scrollTo(), click())
        assertZoom(100)
    }

    private fun enterManualField(id: Int, value: String) {
        onView(withId(id)).perform(scrollTo(), replaceText(value))
        onView(withId(id)).check(matches(withText(value)))
    }

    private fun expectedPickerAction(): String =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            MediaStore.ACTION_PICK_IMAGES
        } else {
            Intent.ACTION_OPEN_DOCUMENT
        }

    private fun createSyntheticImageFixture(twoTone: Boolean = false, width: Int = 8, height: Int = 8): File {
        val fixture = File(context.cacheDir, "pantryproof-test-${System.nanoTime()}.png")
        fixture.outputStream().use { output ->
            Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888).apply {
                if (twoTone) {
                    for (y in 0 until height) {
                        for (x in 0 until width) setPixel(x, y, if (x < width / 2) Color.GREEN else Color.RED)
                    }
                } else {
                    eraseColor(Color.rgb(23, 107, 82))
                }
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
