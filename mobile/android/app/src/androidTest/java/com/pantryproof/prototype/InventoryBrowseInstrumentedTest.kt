package com.pantryproof.prototype

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.ParcelFileDescriptor.AutoCloseInputStream
import android.os.SystemClock
import android.provider.MediaStore
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.Spinner
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onData
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions.*
import androidx.test.espresso.assertion.ViewAssertions.doesNotExist
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.espresso.matcher.ViewMatchers.*
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.data.*
import com.pantryproof.prototype.ui.PantryUiState
import com.pantryproof.prototype.ui.SelectedImageProcessingController
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger
import org.hamcrest.Matchers.equalTo
import org.hamcrest.Matchers.not
import org.junit.After
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class InventoryBrowseInstrumentedTest {
    private var scenario: ActivityScenario<MainActivity>? = null
    private var expectedInventory: List<InventoryItem> = emptyList()
    private var expectedReceipt: Receipt? = null
    private var expectedPresentation: ReceiptPresentationUiResult? = null
    private var expectedConfirmation = false
    private val ownedDurableIds = mutableSetOf<String>()
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private val fixture = listOf(
        InventoryItem("stock-z", "Zulu rice", 4, "In pantry"),
        InventoryItem("stock-a", "apple", 1, "In fridge"),
        InventoryItem("receipt-one", "Rice preview", 7, "Temporary receipt preview"),
        InventoryItem("manual-receipt-one", "Manual rice", 2, "Manually entered receipt"),
        InventoryItem("stock-duplicate", "APPLE", 2, "In pantry"),
    )

    @After fun verifyNoUnintendedStockOrReceiptChanges() {
        try {
            scenario?.onActivity {
                val state = pantry(it)
                assertEquals(expectedInventory, state.inventory)
                assertEquals(expectedReceipt, state.receipt)
                assertEquals(expectedPresentation, state.presentationResult)
                assertEquals(expectedConfirmation, state.demoConfirmed)
            }
        } finally {
            try {
                scenario?.close()
            } finally {
                if (ownedDurableIds.isNotEmpty()) {
                    assertNotNull(ManualInventoryStore(context).update { rows ->
                        rows.filterNot { it.id in ownedDurableIds }
                    })
                }
            }
        }
    }

    @Test fun defaultInventoryAndOriginalOrderRemainVisible() {
        launch(null)
        assertRows("stock-rice", "stock-eggs", "stock-oil")
        onView(withText("Jasmine Rice 5kg")).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withId(R.id.inventory_browse_count)).check(matches(withText("Showing 3 of 3 items")))
        onView(withId(R.id.inventory_clear_search)).check(matches(not(isEnabled())))
    }

    @Test fun searchTrimsWhitespaceIgnoresCaseAndClearRestoresAllItems() {
        launch(); search("  rIcE  ")
        assertRows("stock-z", "receipt-one", "manual-receipt-one")
        awaitCount("Showing 3 of 5 items")
        onView(withId(R.id.inventory_clear_search)).perform(scrollTo(), click())
        assertRows(*fixture.map { it.id }.toTypedArray())
        onView(withId(R.id.inventory_search)).check(matches(withText("")))
        awaitCount("Showing 5 of 5 items")
    }

    @Test fun singleItemInventoryUsesSingularTotalCount() {
        launch(fixture.take(1))
        assertRows("stock-z")
        awaitCount("Showing 1 of 1 item")
        onView(withId(R.id.inventory_browse_count)).check(matches(withText("Showing 1 of 1 item")))
        search("no such fictional product")
        assertRows()
        awaitCount("Showing 0 of 1 item")
        onView(withId(R.id.inventory_clear_search)).perform(scrollTo(), click())
        assertRows("stock-z")
        awaitCount("Showing 1 of 1 item")
    }

    @Test fun oneVisibleItemOfFiveKeepsPluralTotalCount() {
        launch()
        search("Zulu")
        assertRows("stock-z")
        awaitCount("Showing 1 of 5 items")
        onView(withId(R.id.inventory_browse_count)).check(matches(withText("Showing 1 of 5 items")))
        onView(withId(R.id.inventory_clear_search)).perform(scrollTo(), click())
        assertRows(*fixture.map { it.id }.toTypedArray())
        awaitCount("Showing 5 of 5 items")
    }

    @Test fun allSortModesHaveDeterministicPresentationOrder() {
        launch()
        sort("Product name A–Z")
        assertRows("stock-a", "stock-duplicate", "manual-receipt-one", "receipt-one", "stock-z")
        sort("Quantity low to high")
        assertRows("stock-a", "manual-receipt-one", "stock-duplicate", "stock-z", "receipt-one")
        sort("Quantity high to low")
        assertRows("receipt-one", "stock-z", "manual-receipt-one", "stock-duplicate", "stock-a")
        sort("Original inventory order")
        assertRows(*fixture.map { it.id }.toTypedArray())
    }

    @Test fun sourceFiltersUseExistingIdGroupsAndPreserveBadges() {
        launch(); filter("Existing baseline/demo inventory")
        assertRows("stock-z", "stock-a", "stock-duplicate")
        filter("Temporary receipt-preview items"); assertRows("receipt-one")
        onView(withText(R.string.inventory_item_source)).perform(scrollTo()).check(matches(isDisplayed()))
        filter("Manually entered receipt items"); assertRows("manual-receipt-one")
        onView(withText(R.string.manual_inventory_source)).perform(scrollTo()).check(matches(isDisplayed()))
        filter("All items"); assertRows(*fixture.map { it.id }.toTypedArray())
    }

    @Test fun combinedSearchSortAndFilterDoNotChangeStock() {
        launch(); search(" APPLE "); sort("Quantity high to low"); filter("Existing baseline/demo inventory")
        assertRows("stock-duplicate", "stock-a"); awaitCount("Showing 2 of 5 items")
    }

    @Test fun noMatchesIsDistinctFromAnActuallyEmptyInventory() {
        launch(); search("no such fictional product")
        onView(withId(R.id.inventory_no_matches)).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withId(R.id.inventory_empty_state)).check(doesNotExist())
        awaitCount("Showing 0 of 5 items")
    }

    @Test fun emptyInventoryKeepsOriginalEmptyPanelEvenWithSearch() {
        launch(emptyList()); search("anything")
        onView(withId(R.id.inventory_empty_state)).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withText(R.string.inventory_empty_title)).check(matches(isDisplayed()))
        onView(withId(R.id.inventory_no_matches)).check(doesNotExist())
        awaitCount("Showing 0 of 0 items")
    }

    @Test fun sortedDuplicateNameControlsKeepExactIdsAndReorderAfterQuantityChange() {
        launch(); sort("Quantity high to low")
        repeat(2) { onView(withTagValue(equalTo("inventory-increase:stock-a"))).perform(scrollTo(), click()) }
        assertRows("receipt-one", "stock-z", "stock-a", "manual-receipt-one", "stock-duplicate")
        expectedInventory = fixture.map { if (it.id == "stock-a") it.copy(quantity = 3) else it }
        scenario!!.onActivity { assertEquals(expectedInventory, pantry(it).inventory) }
        search("apple"); assertRows("stock-a", "stock-duplicate")
    }

    @Test fun filteredControlsStillRespectBothQuantityBoundaries() {
        launch(listOf(InventoryItem("stock-low", "Limit low", 0, "In pantry"), InventoryItem("stock-high", "Limit high", 99, "In pantry")))
        search("limit"); sort("Quantity high to low")
        onView(withTagValue(equalTo("inventory-decrease:stock-low"))).check(matches(not(isEnabled())))
        onView(withTagValue(equalTo("inventory-increase:stock-high"))).check(matches(not(isEnabled())))
        onView(withTagValue(equalTo("inventory-increase:stock-low"))).perform(scrollTo(), click())
        onView(withTagValue(equalTo("inventory-decrease:stock-low"))).perform(scrollTo(), click())
        onView(withTagValue(equalTo("inventory-decrease:stock-low"))).check(matches(not(isEnabled())))
    }

    @Test fun typingKeepsSameSearchWidgetRootCursorAndKeyboard() {
        launch()
        onView(withId(R.id.inventory_search)).perform(scrollTo(), click(), replaceText("ri"))
        await { a -> ViewCompat.getRootWindowInsets(a.findViewById(R.id.inventory_search))?.isVisible(WindowInsetsCompat.Type.ime()) == true }
        scenario!!.onActivity { a ->
            val field = a.findViewById<EditText>(R.id.inventory_search)
            val root = a.findViewById<View>(R.id.screen_inventory)
            field.setSelection(1); field.text.insert(1, "c")
            assertSame(field, a.findViewById(R.id.inventory_search)); assertSame(root, a.findViewById(R.id.screen_inventory))
            assertTrue(field.hasFocus()); assertEquals(2, field.selectionStart); assertEquals(2, field.selectionEnd)
            assertTrue(ViewCompat.getRootWindowInsets(field)!!.isVisible(WindowInsetsCompat.Type.ime()))
        }
    }

    @Test fun navigationAwayAndBackKeepsAllBrowseControls() {
        launch(); search("rice"); sort("Product name A–Z"); filter("Existing baseline/demo inventory")
        onView(withText(R.string.inventory_add_receipt)).perform(scrollTo(), click())
        pressBack()
        onView(withId(R.id.inventory_search)).check(matches(withText("rice")))
        assertRows("stock-z")
        scenario!!.onActivity { a ->
            assertEquals("Product name A–Z", a.findViewById<Spinner>(R.id.inventory_sort).selectedItem)
            assertEquals("Existing baseline/demo inventory", a.findViewById<Spinner>(R.id.inventory_filter).selectedItem)
        }
    }

    @Test fun recreationRestoresBrowseStateWithoutCorruptingConfirmedInventory() {
        launch(null, confirmed = true)
        search(" rice "); sort("Quantity high to low"); filter("All items")
        var before = emptyList<String>(); scenario!!.onActivity { before = rows(it) }
        scenario!!.recreate()
        onView(withId(R.id.inventory_search)).check(matches(withText(" rice ")))
        scenario!!.onActivity {
            assertEquals(before, rows(it))
            assertEquals("Quantity high to low", it.findViewById<Spinner>(R.id.inventory_sort).selectedItem)
            assertTrue(pantry(it).demoConfirmed)
        }
    }

    @Test fun countsArePoliteAndDebouncedRatherThanPerKeystroke() {
        launch(); val changes = AtomicInteger()
        scenario!!.onActivity { a ->
            val count = a.findViewById<TextView>(R.id.inventory_browse_count)
            assertEquals(View.ACCESSIBILITY_LIVE_REGION_POLITE, count.accessibilityLiveRegion)
            count.addTextChangedListener(object : android.text.TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
                override fun afterTextChanged(s: android.text.Editable?) { changes.incrementAndGet() }
            })
            val search = a.findViewById<EditText>(R.id.inventory_search)
            listOf("a", "ap", "app", "apple").forEach(search::setText)
            assertEquals("Showing 5 of 5 items", count.text.toString())
            assertEquals(0, changes.get())
        }
        awaitCount("Showing 2 of 5 items"); assertEquals(1, changes.get())
    }

    @Test fun narrowTwoHundredPercentLayoutKeepsLabelsTargetsAndResultsReachable() {
        val oldFont = shell("settings get system font_scale").trim().toFloatOrNull() ?: 1f
        val oldSize = Regex("Override size: (\\S+)").find(shell("wm size"))?.groupValues?.get(1)
        val oldDensity = Regex("Override density: (\\S+)").find(shell("wm density"))?.groupValues?.get(1)
        try {
            shell("wm size 720x1280"); shell("wm density 360"); shell("settings put system font_scale 2.0")
            launch(fixture.filterNot { it.id.startsWith("receipt-") }); await { it.resources.configuration.fontScale >= 1.99f && it.resources.configuration.screenWidthDp <= 320 }
            onView(withText(R.string.inventory_browse_compact_title)).check(matches(isDisplayed()))
            search("rice")
            awaitCount("Showing 2 of 4 items")
            onView(withId(R.id.inventory_clear_search)).perform(scrollTo()).check(matches(isDisplayed()))
            onView(withId(R.id.inventory_sort)).perform(scrollTo()).check(matches(isDisplayed()))
            capture("inventory-browse-controls-narrow.png")
            onView(withId(R.id.inventory_filter)).perform(scrollTo()).check(matches(isDisplayed()))
            onView(withText("Zulu rice")).perform(scrollTo()).check(matches(isDisplayed()))
            capture("inventory-browse-results-narrow.png")
            scenario!!.onActivity { a ->
                for (id in listOf(R.id.inventory_sort, R.id.inventory_filter)) {
                    val selected = a.findViewById<Spinner>(id).selectedView as TextView
                    assertTrue(selected.maxLines > 1)
                    assertTrue((0 until selected.layout.lineCount).all { selected.layout.getEllipsisCount(it) == 0 })
                }
                val density = a.resources.displayMetrics.density
                for (id in listOf(R.id.inventory_search, R.id.inventory_clear_search, R.id.inventory_sort, R.id.inventory_filter)) {
                    assertTrue(a.findViewById<View>(id).height >= 48 * density)
                }
                val labels = listOf(R.string.inventory_search_label to R.id.inventory_search, R.string.inventory_sort_label to R.id.inventory_sort, R.string.inventory_filter_label to R.id.inventory_filter)
                for ((label, target) in labels) assertEquals(target, textView(a.window.decorView, context.getString(label))?.labelFor)
            }
            val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
            context.cacheDir.resolve("inventory-browse-narrow.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }; bitmap.recycle()
        } finally {
            shell("settings put system font_scale $oldFont"); shell("wm density ${oldDensity ?: "reset"}"); shell("wm size ${oldSize ?: "reset"}")
        }
    }

    @Test fun nonRiceNoIdQuantityActionRetainsExactInputFocus() {
        launch()
        changeFocusedQuantity("inventory-increase:stock-z")
        assertRows(*fixture.map { it.id }.toTypedArray())
    }

    @Test fun quantityReorderKeepsFocusOnTheSameItemAction() {
        launch(); sort("Quantity high to low")
        assertRows("receipt-one", "stock-z", "manual-receipt-one", "stock-duplicate", "stock-a")
        changeFocusedQuantity("inventory-increase:stock-a")
        assertRows("receipt-one", "stock-z", "stock-a", "manual-receipt-one", "stock-duplicate")
    }

    @Test fun duplicateNamesDoNotRedirectQuantityFocusToAnotherId() {
        launch(); sort("Product name A–Z")
        changeFocusedQuantity("inventory-increase:stock-duplicate")
        scenario!!.onActivity { a ->
            assertEquals(1, pantry(a).inventory.single { it.id == "stock-a" }.quantity)
            assertEquals(3, pantry(a).inventory.single { it.id == "stock-duplicate" }.quantity)
            assertFalse(a.findViewById<ViewGroup>(R.id.inventory_browse_results)
                .findViewWithTag<View>("inventory-increase:stock-a").isFocused)
        }
    }

    @Test fun manualReceiptRowRetainsItsStableActionFocus() {
        val manualRow = fixture.single { it.id == "manual-receipt-one" }
        seedDurableRows(listOf(manualRow))
        launch(fixture.filterNot { it.id == manualRow.id } + manualRow)
        filter("Manually entered receipt items")
        changeFocusedQuantity("inventory-decrease:manual-receipt-one")
        assertRows("manual-receipt-one")
        scenario!!.onActivity { a ->
            assertTrue(pantry(a).inventory.single { it.id == "manual-receipt-one" }.id
                .startsWith(PantryUiState.MANUAL_ROW_PREFIX))
        }
    }

    @Test fun mixedDurableRowsReloadWithCorrectFiltersAndManagementControls() {
        val manual = InventoryItem("manual-receipt-mixed", "Manual rice", 2, ManualInventoryStore.ROW_STATE)
        val standalone = InventoryItem("manual-inventory-mixed", "Standalone oats", 1, ManualInventoryStore.STANDALONE_ROW_STATE)
        val live = InventoryItem("live-receipt-mixed", "Scanned beans", 4, ManualInventoryStore.LIVE_ROW_STATE)
        val committed = listOf(manual, standalone, live)
        seedDurableRows(committed)
        launch(null)

        filter("Confirmed receipt scan items")
        assertRows(live.id)
        onView(withText(R.string.live_inventory_source)).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withTagValue(equalTo("inventory-edit:" + live.id))).check(doesNotExist())
        onView(withTagValue(equalTo("inventory-delete:" + live.id))).check(doesNotExist())
        filter("Manually entered receipt items")
        assertRows(manual.id)
        onView(withTagValue(equalTo("inventory-edit:" + manual.id))).perform(scrollTo()).check(matches(isDisplayed()))
        filter("Items added directly")
        assertRows(standalone.id)
        onView(withText(R.string.inventory_standalone_source)).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withTagValue(equalTo("inventory-delete:" + standalone.id))).perform(scrollTo()).check(matches(isDisplayed()))
        assertEquals(committed, committedRows())
    }

    @Test fun standaloneAddEditAndDeleteUseStableIdsAndSurviveFreshLaunch() {
        launch(null)
        assertTrue(committedRows().isEmpty())
        onView(withTagValue(equalTo("inventory-edit:stock-rice"))).check(doesNotExist())
        onView(withTagValue(equalTo("inventory-delete:stock-rice"))).check(doesNotExist())

        onView(withId(R.id.inventory_add_item)).perform(scrollTo(), click())
        saveItem()
        onView(withId(R.id.inventory_item_name))
            .check(matches(hasErrorText(context.getString(R.string.inventory_name_required))))
        editFields("Synthetic oats", "100")
        saveItem()
        onView(withId(R.id.inventory_item_quantity))
            .check(matches(hasErrorText(context.getString(R.string.inventory_quantity_invalid))))
        onView(withId(android.R.id.button2)).perform(click())
        assertTrue(committedRows().isEmpty())

        val first = addStandaloneItem("Synthetic oats", "0")
        val second = addStandaloneItem("Synthetic oats", "99")
        assertNotEquals(first.id, second.id)
        assertEquals(listOf(0, 99), committedRows().map { it.quantity })
        filter("Items added directly")
        search(" OATS ")
        sort("Quantity high to low")
        assertRows(second.id, first.id)

        onView(withTagValue(equalTo("inventory-edit:${first.id}"))).perform(scrollTo(), click())
        onView(withId(R.id.inventory_item_name)).check(matches(withText("Synthetic oats")))
        onView(withId(R.id.inventory_item_quantity)).check(matches(withText("0")))
        editFields("Rolled oats", "4")
        saveItem()
        val edited = first.copy(name = "Rolled oats", quantity = 4)
        expectedInventory = expectedInventory.map { if (it.id == first.id) edited else it }
        assertEquals(listOf(edited, second), committedRows())
        onView(withId(R.id.inventory_search)).check(matches(withText(" OATS ")))
        assertRows(second.id, first.id)

        onView(withTagValue(equalTo("inventory-delete:${second.id}"))).perform(scrollTo(), click())
        onView(withText(R.string.inventory_delete_title)).check(matches(isDisplayed()))
        onView(withId(android.R.id.button2)).perform(click())
        assertEquals(listOf(edited, second), committedRows())
        assertRows(second.id, first.id)

        onView(withTagValue(equalTo("inventory-delete:${second.id}"))).perform(scrollTo(), click())
        onView(withId(android.R.id.button1)).perform(click())
        expectedInventory = expectedInventory.filterNot { it.id == second.id }
        assertEquals(listOf(edited), committedRows())
        assertRows(first.id)

        scenario!!.close()
        scenario = null
        launch(null)
        filter("Items added directly")
        assertRows(first.id)
        onView(withText(edited.name)).perform(scrollTo()).check(matches(isDisplayed()))
        onView(withText(context.getString(R.string.inventory_quantity_label, edited.quantity)))
            .perform(scrollTo()).check(matches(isDisplayed()))
        assertEquals(listOf(edited), committedRows())
    }

    @Test fun failedInventoryWritesKeepExistingSnapshotAndEditorInputs() {
        val directory = Files.createTempDirectory(context.cacheDir.toPath(), "inventory-management-")
        val snapshot = directory.resolve("inventory.json")
        try {
            val row = InventoryItem("manual-receipt-pasta", "Synthetic pasta", 2, ManualInventoryStore.ROW_STATE)
            val initialStore = ManualInventoryStore(snapshot)
            assertEquals(listOf(row), initialStore.update { listOf(row) })
            val originalBytes = Files.readAllBytes(snapshot)
            val failing = ManualInventoryStore(snapshot) { _, _ -> throw IOException("Injected inventory write failure") }
            val state = PantryUiState(MockReceiptPresentationSource(), failing)
            launch(null, replacementState = state)

            onView(withId(R.id.inventory_add_item)).perform(scrollTo(), click())
            editFields("Uncommitted oats", "9")
            saveItem()
            assertEditorFailure("Uncommitted oats", "9")
            onView(withId(android.R.id.button2)).perform(click())

            onView(withTagValue(equalTo("inventory-edit:${row.id}"))).perform(scrollTo(), click())
            editFields("Uncommitted pasta", "8")
            saveItem()
            assertEditorFailure("Uncommitted pasta", "8")
            onView(withId(android.R.id.button2)).perform(click())

            onView(withTagValue(equalTo("inventory-delete:${row.id}"))).perform(scrollTo(), click())
            onView(withId(android.R.id.button1)).perform(click())
            onView(withText(R.string.inventory_change_failed)).check(matches(isDisplayed()))
            onView(withId(android.R.id.button1)).perform(click())
            assertArrayEquals(originalBytes, Files.readAllBytes(snapshot))
            assertEquals(listOf(row), initialStore.load())
            assertEquals(expectedInventory, state.inventory)
            onView(withText(row.name)).perform(scrollTo()).check(matches(isDisplayed()))
        } finally {
            Files.deleteIfExists(snapshot)
            Files.deleteIfExists(directory)
        }
    }

    @Test fun generatedFixtureBindingLeavesDurableInventoryUnchanged() {
        val row = InventoryItem(
            "manual-inventory-${UUID.randomUUID()}", "Synthetic pantry stock", 5,
            ManualInventoryStore.STANDALONE_ROW_STATE,
        )
        seedDurableRows(listOf(row))
        val before = committedRows()
        val image = File.createTempFile("inventory-fixture-boundary-", ".png", context.cacheDir)
        try {
            val bitmap = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888)
            try {
                image.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
            } finally {
                bitmap.recycle()
            }
            launch(null)
            pressBack()
            val previewUri = Uri.fromFile(image)
            val transport = BoundSyntheticReceiptProcessingTransport(
                { SyntheticReceiptProcessingTransport.Scenario.AVAILABLE },
                dispatchResponse = { it() },
            )
            val fixtureContext = PresentationConsumerContext(
                "inventory-fixture-request", "inventory-fixture-image", PresentationConsumerMode.FIXTURE,
            )
            val binding = SelectedImageProcessingController.FixtureBinding(
                transport = transport,
                replaceSnapshot = {
                    transport.replaceSnapshot(it)
                    true
                },
                start = SelectedImageProcessingController.FixtureStart(fixtureContext, Any(), SystemClock::elapsedRealtime),
                maximumBytes = 256 * 1024,
                preparedInput = image::readBytes,
                retire = { transport.replaceSnapshot(null) },
                release = {},
            )
            Intents.init()
            try {
                val picker = if (Build.VERSION.SDK_INT >= 33) MediaStore.ACTION_PICK_IMAGES else Intent.ACTION_OPEN_DOCUMENT
                Intents.intending(hasAction(picker)).respondWith(
                    ActivityResult(Activity.RESULT_OK, Intent().setData(previewUri)),
                )
                onView(withId(R.id.home_add_receipt)).perform(scrollTo(), click())
                onView(withId(R.id.add_import_image)).perform(scrollTo(), click())
                scenario!!.onActivity { SelectedImageProcessingController.offerFixture(it, previewUri, binding) }
                onView(withId(R.id.preview_process_selected)).perform(scrollTo(), click())
                await { selectedProcessing(it).inputState == SelectedImageProcessingController.InputState.READY }
                onView(withId(R.id.selected_processing_start)).perform(scrollTo(), click())
                await { selectedProcessing(it).state is ReceiptProcessingLifecycle.State.Finished }
                scenario!!.onActivity {
                    val controller = selectedProcessing(it)
                    assertTrue(controller.ownsFixture(binding))
                    val result = controller.state as ReceiptProcessingLifecycle.State.Finished
                    assertEquals(fixtureContext, result.request.context)
                    val presentation = result.outcome as ReceiptProcessingLifecycle.Outcome.Presentation
                    assertTrue(presentation.result is ReceiptPresentationUiResult.Available)
                }
                onView(withId(R.id.review_confirm)).check(doesNotExist())
                assertEquals(before, committedRows())
            } finally {
                try {
                    scenario!!.onActivity {
                        try { it.resetSelectedImageFixture(binding) } finally { binding.detach() }
                    }
                } finally {
                    Intents.release()
                }
            }
        } finally {
            image.delete()
        }
    }

    @Test fun disabledQuantityActionFallsBackToPassiveCountNotAnotherItem() {
        launch(listOf(
            InventoryItem("stock-low", "Low boundary", 1, "In pantry"),
            InventoryItem("stock-high", "High boundary", 98, "In pantry"),
        ))
        changeFocusedQuantity("inventory-decrease:stock-low", countFallback = true)
        changeFocusedQuantity("inventory-increase:stock-high", countFallback = true)
        scenario!!.onActivity { a ->
            assertEquals(listOf(0, 99), pantry(a).inventory.map { it.quantity })
        }
    }

    @Test fun resultRebuildDoesNotStealSearchCursorOrSpinnerInputFocus() {
        launch()
        onView(withId(R.id.inventory_search)).perform(scrollTo())
        scenario!!.onActivity { a ->
            val search = a.findViewById<EditText>(R.id.inventory_search)
            assertTrue(search.requestFocus()); search.setText("apple"); search.setSelection(2)
            a.findViewById<Spinner>(R.id.inventory_sort).setSelection(3)
        }
        await { rows(it) == listOf("stock-duplicate", "stock-a") }
        scenario!!.onActivity { a ->
            val search = a.findViewById<EditText>(R.id.inventory_search)
            assertTrue(search.isFocused); assertEquals(2, search.selectionStart); assertEquals(2, search.selectionEnd)
            val sort = a.findViewById<Spinner>(R.id.inventory_sort)
            sort.isFocusableInTouchMode = true; assertTrue(sort.requestFocus()); sort.setSelection(0)
        }
        await { rows(it) == listOf("stock-a", "stock-duplicate") }
        scenario!!.onActivity { a ->
            assertTrue(a.findViewById<Spinner>(R.id.inventory_sort).isFocused)
            val filter = a.findViewById<Spinner>(R.id.inventory_filter)
            filter.isFocusableInTouchMode = true; assertTrue(filter.requestFocus()); filter.setSelection(3)
        }
        await { it.findViewById<View>(R.id.inventory_no_matches) != null }
        scenario!!.onActivity { a ->
            assertTrue(a.findViewById<Spinner>(R.id.inventory_filter).isFocused)
            assertEquals(2, a.findViewById<EditText>(R.id.inventory_search).selectionStart)
        }
    }

    private fun changeFocusedQuantity(tag: String, countFallback: Boolean = false) {
        onView(withTagValue(equalTo(tag))).perform(scrollTo())
        scenario!!.onActivity { a ->
            val results = a.findViewById<ViewGroup>(R.id.inventory_browse_results)
            val original = requireNotNull(results.findViewWithTag<View>(tag))
            assertEquals(View.NO_ID, original.id); assertTrue(original.isEnabled)
            original.isFocusableInTouchMode = true; assertTrue(original.requestFocus()); assertTrue(original.isFocused)
            val id = tag.substringAfter(':')
            val delta = if (tag.startsWith("inventory-increase:")) 1 else -1
            expectedInventory = expectedInventory.map { if (it.id == id) it.copy(quantity = it.quantity + delta) else it }
            assertTrue(original.performClick())
            val replacement = requireNotNull(results.findViewWithTag<View>(tag))
            assertNotSame(original, replacement)
            assertEquals(expectedInventory, pantry(a).inventory)
            if (countFallback) {
                assertFalse(replacement.isEnabled)
                assertSame(a.findViewById<View>(R.id.inventory_browse_count), a.currentFocus)
            } else {
                assertTrue(replacement.isEnabled); assertSame(replacement, a.currentFocus)
                assertTrue(replacement.isFocused)
            }
            assertEquals(if (countFallback) emptyList<String>() else listOf(tag), focusedQuantityTags(results))
        }
    }

    private fun focusedQuantityTags(view: View): List<String> {
        val own = (view.tag as? String)?.takeIf {
            view.isFocused && (it.startsWith("inventory-increase:") || it.startsWith("inventory-decrease:"))
        }?.let(::listOf) ?: emptyList()
        return own + if (view is ViewGroup) (0 until view.childCount).flatMap { focusedQuantityTags(view.getChildAt(it)) } else emptyList()
    }


    @Test fun automatedReaderKeepsInventoryFocusChannelsOnIndependentTaggedActions() {
        launch(); sort("Quantity low to high")
        automatedReaderProbe("i2j-inventory-accessibility.json") { observe ->
            scenario!!.onActivity { a ->
                val results = a.findViewById<ViewGroup>(R.id.inventory_browse_results)
                val input = results.findViewWithTag<View>("inventory-increase:stock-a")
                val reader = results.findViewWithTag<View>("inventory-decrease:stock-duplicate")
                input.isFocusableInTouchMode = true; assertTrue(input.requestFocus())
                assertTrue(reader.performAccessibilityAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS, null))
                assertTrue(input.isFocused); assertTrue(reader.isAccessibilityFocused)
                expectedInventory = fixture.map { if (it.id == "stock-a") it.copy(quantity = 2) else it }
                assertTrue(input.performClick())
                assertSame(results.findViewWithTag<View>("inventory-increase:stock-a"), a.currentFocus)
                assertTrue(results.findViewWithTag<View>("inventory-decrease:stock-duplicate").isAccessibilityFocused)
            }
            observe("independent-input-and-reader-restored-by-tag")
            onView(withId(R.id.inventory_search)).perform(scrollTo())
            scenario!!.onActivity { a ->
                val search = a.findViewById<EditText>(R.id.inventory_search)
                assertTrue(search.requestFocus()); search.setText("apple"); search.setSelection(2)
                val reader = a.findViewById<ViewGroup>(R.id.inventory_browse_results)
                    .findViewWithTag<View>("inventory-decrease:stock-duplicate")
                assertTrue(reader.isAccessibilityFocused)
                expectedInventory = expectedInventory.map { if (it.id == "stock-duplicate") it.copy(quantity = 1) else it }
                assertTrue(reader.performClick())
                assertSame(search, a.currentFocus); assertEquals(2, search.selectionStart)
                assertTrue(a.findViewById<ViewGroup>(R.id.inventory_browse_results)
                    .findViewWithTag<View>("inventory-decrease:stock-duplicate").isAccessibilityFocused)
            }
            observe("search-input-preserved-reader-row-restored")
        }
    }


    /** Diagnostic automation service, not a TalkBack speech test. Focus observations are
     * retained even when they reveal a production policy gap outside this task's scope. */
    private fun automatedReaderProbe(name: String, block: ((String) -> Unit) -> Unit) {
        val inst = InstrumentationRegistry.getInstrumentation()
        val automation = inst.uiAutomation
        val originalFlags = automation.serviceInfo.flags
        val events = org.json.JSONArray()
        val snapshots = org.json.JSONArray()
        val report = org.json.JSONObject().put("service", "UiAutomation; NOT TalkBack")
            .put("manualSpeechVerified", false).put("originalServiceFlags", originalFlags)
            .put("events", events).put("snapshots", snapshots)
        automation.setOnAccessibilityEventListener { event ->
            synchronized(events) {
                if (events.length() < 512) events.put(org.json.JSONObject()
                    .put("type", event.eventType).put("contentChanges", event.contentChangeTypes)
                    .put("window", event.windowId))
            }
        }
        try {
            val info = automation.serviceInfo
            info.flags = originalFlags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_REQUEST_TOUCH_EXPLORATION_MODE
            automation.serviceInfo = info
            val manager = inst.targetContext.getSystemService(android.content.Context.ACCESSIBILITY_SERVICE)
                as android.view.accessibility.AccessibilityManager
            val deadline = SystemClock.uptimeMillis() + 5_000L
            while (!manager.isTouchExplorationEnabled && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(25L)
            assertTrue("Automation touch exploration is actually enabled", manager.isTouchExplorationEnabled)
            report.put("touchExplorationEnabled", true)
            val observe: (String) -> Unit = { stage ->
                inst.waitForIdleSync()
                scenario!!.onActivity { a ->
                    val readers = org.json.JSONArray()
                    fun visit(view: View) {
                        if (view.isAccessibilityFocused) readers.put(focusResourceName(a, view))
                        if (view is ViewGroup) for (i in 0 until view.childCount) visit(view.getChildAt(i))
                    }
                    visit(a.window.decorView)
                    snapshots.put(org.json.JSONObject().put("stage", stage)
                        .put("inputFocus", focusResourceName(a, a.currentFocus))
                        .put("accessibilityFocus", readers))
                }
            }
            block(observe)
            report.put("probeCompleted", true)
        } finally {
            automation.setOnAccessibilityEventListener(null)
            val restored = automation.serviceInfo
            restored.flags = originalFlags
            automation.serviceInfo = restored
            report.put("restoredServiceFlags", automation.serviceInfo.flags)
            synchronized(events) {
                inst.targetContext.cacheDir.resolve(name).writeText(report.toString(2))
            }
            assertEquals("Automation flags restored", originalFlags, automation.serviceInfo.flags)
        }
    }

    private fun focusResourceName(a: MainActivity, view: View?): String = when {
        view == null -> "NONE"
        view.id == View.NO_ID -> "NO_ID"
        else -> a.resources.getResourceEntryName(view.id)
    }


    private fun launch(
        items: List<InventoryItem>? = fixture,
        confirmed: Boolean = false,
        replacementState: PantryUiState? = null,
    ) {
        if (confirmed) {
            seedDurableRows(listOf(InventoryItem("manual-receipt-test", "Manual rice", 3, ManualInventoryStore.ROW_STATE)))
        }
        scenario = ActivityScenario.launch(MainActivity::class.java)
        scenario!!.onActivity { a ->
            if (replacementState != null) pantryField.set(a, replacementState)
            val state = pantry(a)
            if (confirmed) {
                assertTrue(state.confirmForInventoryPreview())
            } else if (items != null) { state.inventory.clear(); state.inventory.addAll(items) }
            expectedInventory = state.inventory.toList(); expectedReceipt = state.receipt
            expectedPresentation = state.presentationResult; expectedConfirmation = state.demoConfirmed
        }
        onView(withId(R.id.home_inventory)).perform(scrollTo(), click())
    }

    private fun seedDurableRows(rows: List<InventoryItem>) {
        val ids = rows.map { it.id }
        val store = ManualInventoryStore(context)
        assertNotNull(store.update { committed ->
            if (committed.any { it.id in ids }) null else committed + rows
        })
        ownedDurableIds.addAll(ids)
    }

    private fun committedRows() = requireNotNull(ManualInventoryStore(context).load())

    private fun addStandaloneItem(name: String, quantity: String): InventoryItem {
        val existingIds = committedRows().map { it.id }.toSet()
        onView(withId(R.id.inventory_add_item)).perform(scrollTo(), click())
        editFields(name, quantity)
        saveItem()
        val row = committedRows().single { it.id !in existingIds }
        ownedDurableIds.add(row.id)
        expectedInventory = expectedInventory + row
        assertTrue(row.id.startsWith(ManualInventoryStore.STANDALONE_ROW_PREFIX))
        UUID.fromString(row.id.removePrefix(ManualInventoryStore.STANDALONE_ROW_PREFIX))
        return row
    }

    private fun editFields(name: String, quantity: String) {
        onView(withId(R.id.inventory_item_name)).perform(replaceText(name), closeSoftKeyboard())
        onView(withId(R.id.inventory_item_quantity)).perform(replaceText(quantity), closeSoftKeyboard())
    }

    private fun saveItem() = onView(withId(android.R.id.button1)).perform(click())

    private fun assertEditorFailure(name: String, quantity: String) {
        onView(withText(R.string.inventory_change_failed)).check(matches(isDisplayed()))
        onView(withId(R.id.inventory_item_name)).check(matches(withText(name)))
        onView(withId(R.id.inventory_item_quantity)).check(matches(withText(quantity)))
    }

    private fun search(query: String) { onView(withId(R.id.inventory_search)).perform(scrollTo(), replaceText(query), closeSoftKeyboard()) }
    private fun sort(label: String) { choose(R.id.inventory_sort, label) }
    private fun filter(label: String) { choose(R.id.inventory_filter, label) }
    private fun choose(id: Int, label: String) { onView(withId(id)).perform(scrollTo(), click()); onData(equalTo(label)).perform(click()) }
    private fun assertRows(vararg ids: String) { scenario!!.onActivity { assertEquals(ids.toList(), rows(it)) } }
    private fun rows(a: MainActivity): List<String> {
        val group = a.findViewById<ViewGroup>(R.id.inventory_browse_results)
        return (0 until group.childCount).mapNotNull { group.getChildAt(it).tag as? String }
    }
    private fun awaitCount(expected: String) { await { it.findViewById<TextView>(R.id.inventory_browse_count).text.toString() == expected } }
    private fun await(predicate: (MainActivity) -> Boolean) {
        val deadline = SystemClock.uptimeMillis() + 5_000L
        while (SystemClock.uptimeMillis() < deadline) { var ok = false; scenario!!.onActivity { ok = predicate(it) }; if (ok) return; SystemClock.sleep(25) }
        fail("Expected inventory view state did not arrive")
    }
    private val pantryField get() = MainActivity::class.java.getDeclaredField("state").apply { isAccessible = true }
    private fun pantry(a: MainActivity) = pantryField.get(a) as PantryUiState
    private fun selectedProcessing(a: MainActivity) = MainActivity::class.java
        .getDeclaredField("selectedProcessingController").apply { isAccessible = true }
        .get(a) as SelectedImageProcessingController
    private fun capture(name: String) {
        instrumentation.waitForIdleSync()
        SystemClock.sleep(400L)
        val image = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        context.cacheDir.resolve(name).outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        image.recycle()
    }
    private fun textView(view: View, text: String): TextView? {
        if (view is TextView && view.text.toString() == text) return view
        if (view is ViewGroup) for (i in 0 until view.childCount) textView(view.getChildAt(i), text)?.let { return it }
        return null
    }
    private fun shell(command: String) = AutoCloseInputStream(instrumentation.uiAutomation.executeShellCommand(command)).bufferedReader().use { it.readText() }
}
