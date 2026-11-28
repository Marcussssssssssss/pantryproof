package com.pantryproof.prototype

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.espresso.matcher.ViewMatchers.*
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ReceiptRetentionPreferenceInstrumentedTest {
    @Test fun firstUseOffAndLastChoiceSurvivesASeparateActivityLaunch() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val source = File.createTempFile("test-acquisition-", ".png", context.cacheDir)
        val bitmap = Bitmap.createBitmap(32, 48, Bitmap.Config.ARGB_8888)
        try {
            source.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
            Intents.init()
            try {
                val picker = if (Build.VERSION.SDK_INT >= 33) MediaStore.ACTION_PICK_IMAGES else Intent.ACTION_OPEN_DOCUMENT
                Intents.intending(hasAction(picker)).respondWith(ActivityResult(Activity.RESULT_OK, Intent().setData(Uri.fromFile(source))))
                fun openImage() {
                    onView(withId(R.id.home_add_receipt)).perform(click())
                    onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
                }
                ActivityScenario.launch(MainActivity::class.java).use {
                    openImage()
                    onView(withId(R.id.keep_receipt_original)).perform(sageScrollTo()).check(matches(isNotChecked()))
                    onView(withText("Save receipt details only")).check(matches(isDisplayed()))
                    onView(withId(R.id.keep_receipt_original)).perform(click()).check(matches(isChecked()))
                    onView(withText("Save image to receipt history")).check(matches(isDisplayed()))
                }
                ActivityScenario.launch(MainActivity::class.java).use {
                    openImage()
                    onView(withId(R.id.keep_receipt_original)).perform(sageScrollTo()).check(matches(isChecked()))
                    onView(withText("Save image to receipt history")).check(matches(isDisplayed()))
                }
                assertTrue(source.isFile)
            } finally { Intents.release() }
        } finally {
            bitmap.recycle()
            source.delete()
        }
    }
}
