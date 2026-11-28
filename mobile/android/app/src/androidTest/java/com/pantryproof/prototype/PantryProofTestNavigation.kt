package com.pantryproof.prototype

import android.graphics.Rect
import android.view.View
import android.widget.ScrollView
import androidx.test.espresso.UiController
import androidx.test.espresso.ViewAction
import androidx.test.espresso.Espresso.onData
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.espresso.matcher.ViewMatchers.isAssignableFrom
import androidx.test.espresso.matcher.ViewMatchers.withTagValue
import com.pantryproof.prototype.data.ReceiptSubmissionBinding
import com.pantryproof.prototype.ui.SelectedImageProcessingController
import org.hamcrest.Matcher
import org.hamcrest.core.IsEqual.equalTo

internal fun openSyntheticPreviewFromAddReceipt() {
    onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
    onView(withId(R.id.home_add_receipt)).perform(click())
    onView(withId(R.id.screen_add_receipt)).check(matches(isDisplayed()))
    onView(withId(R.id.add_use_demo)).perform(scrollTo(), click())
    onView(withId(R.id.screen_preview)).check(matches(isDisplayed()))
}

internal fun openReceiptDetails() {
    openSyntheticPreviewFromAddReceipt()
    onView(withId(R.id.preview_continue)).perform(sageScrollTo(), click())
    onView(withId(R.id.screen_details)).check(matches(isDisplayed()))
}

internal fun openManualReview() {
    openReceiptDetails()
    onView(withId(R.id.details_review)).perform(sageScrollTo(), click())
    onView(withId(R.id.screen_review)).check(matches(isDisplayed()))
}

internal fun confirmAndOpenInventory() {
    openManualReview()
    onView(withId(R.id.review_confirm)).perform(sageScrollTo(), click())
    onView(withId(R.id.review_success)).check(matches(isDisplayed()))
    onView(withId(R.id.review_view_inventory)).perform(sageScrollTo(), click())
    onView(withId(R.id.screen_inventory)).check(matches(isDisplayed()))
}

/** A screen action can be in scrollable content or docked in the surrounding frame. */
internal fun sageScrollTo(): ViewAction = object : ViewAction {
    override fun getDescription() = "reveal view within its scroll containers"
    override fun getConstraints(): Matcher<View> = isAssignableFrom(View::class.java)
    override fun perform(uiController: UiController, view: View) {
        uiController.loopMainThreadUntilIdle()
        val scroll = generateSequence(view.parent) { it.parent }.filterIsInstance<ScrollView>().firstOrNull()
        if (scroll != null) {
            val target = IntArray(2)
            val viewport = IntArray(2)
            view.getLocationOnScreen(target)
            scroll.getLocationOnScreen(viewport)
            val available = scroll.height - scroll.paddingTop - scroll.paddingBottom
            val offset = target[1] - viewport[1] - scroll.paddingTop - (available - view.height).coerceAtLeast(0) / 2
            scroll.scrollBy(0, offset)
            uiController.loopMainThreadForAtLeast(120L)
        } else {
            view.requestRectangleOnScreen(Rect(0, 0, view.width, view.height), true)
        }
        uiController.loopMainThreadUntilIdle()
    }
}

internal fun openSageProcessingDemo() {
    onView(withId(R.id.sage_development_tools)).perform(sageScrollTo(), click())
    onView(withId(R.id.home_processing_demo)).perform(sageScrollTo(), click())
}

internal fun openSageInventoryDetails(rowId: String) {
    onView(withTagValue(equalTo(rowId))).perform(object : ViewAction {
        override fun getDescription() = "show the exact inventory row, expanding its source if needed"
        override fun getConstraints(): Matcher<View> = isAssignableFrom(View::class.java)
        override fun perform(uiController: UiController, view: View) {
            val expandAll = view.rootView.findViewById<View>(R.id.sage_expand_all)
            repeat(2) {
                if (!view.isShown) {
                    expandAll?.performClick()
                    uiController.loopMainThreadUntilIdle()
                }
            }
            sageScrollTo().perform(uiController, view)
        }
    }, click())
}

/** Observes the existing local snapshot through its lifecycle owner. */
internal fun selectedImageSnapshot(controller: SelectedImageProcessingController): ReceiptSubmissionBinding.Snapshot {
    fun field(owner: Any, name: String): Any = requireNotNull(owner.javaClass.getDeclaredField(name).apply {
        isAccessible = true
    }.get(owner))
    val lifecycle = field(field(controller, "processing"), "lifecycle")
    return field(field(lifecycle, "transport"), "snapshot") as ReceiptSubmissionBinding.Snapshot
}

internal fun selectInventorySort(label: String) {
    onView(withId(R.id.inventory_sort)).perform(sageScrollTo(), click())
    onData(equalTo(label)).inAdapterView(withId(R.id.inventory_sort_choices)).perform(click())
}

internal fun selectInventoryFilter(label: String) {
    val context = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().targetContext
    val longLabels = context.resources.getStringArray(R.array.inventory_filter_options)
    val shortLabels = context.resources.getStringArray(R.array.sage_inventory_filter_labels)
    val displayed = shortLabels.getOrNull(longLabels.indexOf(label)) ?: label
    onView(withId(R.id.inventory_filter)).perform(click())
    onData(equalTo(displayed)).inAdapterView(withId(R.id.inventory_filter_choices)).perform(click())
}

internal fun refreshInventoryFixture(activity: MainActivity) {
    MainActivity::class.java.getDeclaredMethod("refreshInventoryAfterChange").apply { isAccessible = true }.invoke(activity)
}
