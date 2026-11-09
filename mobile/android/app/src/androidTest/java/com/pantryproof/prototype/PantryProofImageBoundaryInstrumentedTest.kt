package com.pantryproof.prototype

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.doesNotExist
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.Intents.intended
import androidx.test.espresso.intent.Intents.intending
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.espresso.intent.matcher.IntentMatchers.anyIntent
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.withText
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

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
    fun unavailableSelectedUriShowsRecoveryWithoutAttributingFields() = withIntents {
        val unavailableUri = Uri.parse("content://com.pantryproof.prototype.test/missing-image.png")
        intending(anyIntent()).respondWith(ActivityResult(
            Activity.RESULT_OK,
            Intent().setData(unavailableUri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION),
        ))

        onView(withId(R.id.home_add_receipt)).perform(click())
        onView(withId(R.id.add_import_image)).perform(scrollTo(), click())

        onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
        onView(withText(R.string.preview_image_unavailable_title)).check(matches(isDisplayed()))
        onView(withId(R.id.preview_use_demo)).check(matches(isDisplayed()))
        onView(withText("Demo Grocery Store (Synthetic)")).check(doesNotExist())

        onView(withId(R.id.preview_use_demo)).perform(scrollTo(), click())
        onView(withText(R.string.preview_synthetic_status)).check(matches(isDisplayed()))
    }

    @Test
    fun controlledLocalImageRemainsSeparateAcrossRecreationAndDetails() = withIntents {
        val imageFile = createSyntheticImageFixture()
        val imageUri = Uri.fromFile(imageFile)
        try {
            intending(anyIntent()).respondWith(ActivityResult(
                Activity.RESULT_OK,
                Intent().setData(imageUri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION),
            ))

            onView(withId(R.id.home_add_receipt)).perform(click())
            onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
            onView(withText(R.string.preview_local_status)).check(matches(isDisplayed()))
            onView(withText(R.string.preview_local_warning_body)).check(matches(isDisplayed()))

            activityRule.scenario.recreate()
            onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
            onView(withText(R.string.preview_local_status)).check(matches(isDisplayed()))
            onView(withText(R.string.preview_local_warning_body)).check(matches(isDisplayed()))

            onView(withId(R.id.preview_continue)).perform(scrollTo(), click())
            onView(withText(R.string.details_local_demo_body)).check(matches(isDisplayed()))
            onView(withText("Demo Grocery Store (Synthetic)")).check(matches(isDisplayed()))
        } finally {
            imageFile.delete()
        }
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

    private inline fun withIntents(block: () -> Unit) {
        Intents.init()
        try {
            block()
        } finally {
            Intents.release()
        }
    }
}
