package com.pantryproof.prototype

import android.graphics.Bitmap
import android.net.Uri
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.action.ViewActions.scrollTo
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.RootMatchers.isDialog
import androidx.test.espresso.matcher.ViewMatchers.*
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.pantryproof.prototype.contract.review.ReceiptReviewV1Decoder
import com.pantryproof.prototype.contract.review.ReviewContext
import com.pantryproof.prototype.contract.review.ReviewJson
import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.ReceiptPresentationResult
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder
import com.pantryproof.prototype.data.InventoryCategory
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryMetadata
import com.pantryproof.prototype.data.InventoryUnit
import com.pantryproof.prototype.data.M3eReceiptPresentationAdapter
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.data.MockReceiptPresentationSource
import com.pantryproof.prototype.data.ReceiptConfirmationMode
import com.pantryproof.prototype.data.ReceiptConfirmation
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle
import com.pantryproof.prototype.data.ReceiptProcessingRequest
import com.pantryproof.prototype.data.receiptHistoryMonths
import com.pantryproof.prototype.image.CropEdge
import com.pantryproof.prototype.image.PreparedReceiptImage
import com.pantryproof.prototype.image.ReceiptCrop
import com.pantryproof.prototype.image.SelectedImageSnapshotEncoder
import com.pantryproof.prototype.ui.LiveReceiptReviewDraft
import com.pantryproof.prototype.ui.InventoryBrowseProjection
import com.pantryproof.prototype.ui.PantryUiState
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import java.time.LocalDate
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ReceiptReviewPersistenceInstrumentedTest {
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext
    private val today = LocalDate.of(2026, 11, 28)

    @Test fun atomicHistoryRollbackReplayRetentionAndDeletion() {
        val directory = Files.createTempDirectory(context.cacheDir.toPath(), "task06-")
        val file = directory.resolve("manual-inventory.json")
        val external = Files.createTempFile(context.cacheDir.toPath(), "acquisition-", ".png")
        Files.write(external, byteArrayOf(3, 7, 1))
        var fail = false
        val store = ManualInventoryStore(file) { pending, target ->
            if (fail) throw IOException("Injected before rename")
            Files.move(pending, target, ATOMIC_MOVE, REPLACE_EXISTING)
        }
        Files.write(file, """{"version":1,"rows":[{"id":"manual-inventory-old","name":"Legacy","quantity":9}]}""".encodeToByteArray())
        val baseline = Files.readAllBytes(file)
        val fixture = fixture("13-exact-weighted-quantity")
        val draft = fixture.draft
        includeWeighted(draft)
        draft.keepOriginal = true
        val inventoryOnly = approved(draft, ReceiptConfirmationMode.INVENTORY_ONLY)
        val full = approved(draft, ReceiptConfirmationMode.INVENTORY_AND_RECEIPT)
        assertEquals(ManualInventoryStore.Commit.FAILED,
            PantryUiState(MockReceiptPresentationSource(), store).commitReview(draft, full, Files.readAllBytes(external)))
        fail = true
        assertEquals(ManualInventoryStore.Commit.FAILED, store.commit(full, fixture.bytes, Files.readAllBytes(external)))
        assertArrayEquals(baseline, Files.readAllBytes(file))
        assertTrue(store.history()!!.isEmpty())
        assertEquals(listOf("manual-inventory.json"), files(directory.toFile()))
        fail = false
        assertEquals(ManualInventoryStore.Commit.COMMITTED, store.commit(full, fixture.bytes, Files.readAllBytes(external)))

        val reopened = ManualInventoryStore(file)
        assertEquals(setOf(full.identity), reopened.recover())
        assertEquals(ManualInventoryStore.Commit.REPLAYED, reopened.commit(full, fixture.bytes, null))
        assertEquals(ManualInventoryStore.Commit.CONFLICT, reopened.commit(inventoryOnly, fixture.bytes, null))
        val saved = reopened.history()!!.single()
        assertEquals("0.750", saved.rows.single().quantity.toPlainString())
        assertEquals("6.00", receiptHistoryMonths(listOf(saved), "kopi").single().spending.toPlainString())
        assertEquals(InventoryUnit.UNKNOWN, reopened.load()!!.first().unit)
        assertEquals("manual-inventory-old", reopened.load()!!.first().id)
        assertEquals("9", reopened.load()!!.first().quantity.toPlainString())
        assertArrayEquals(Files.readAllBytes(external), reopened.originalFile(full.identity)!!.readBytes())
        assertArrayEquals(fixture.bytes, directory.resolve(saved.evidenceFile!!).toFile().readBytes())
        assertTrue(reopened.acknowledge(setOf(full.identity)))
        assertTrue(reopened.recover()!!.isEmpty())

        val state = PantryUiState(MockReceiptPresentationSource(), reopened)
        assertTrue(state.adjustInventory(full.stock.single().id, -1))
        assertEquals("0.749", reopened.load()!!.last().quantity.toPlainString())
        assertEquals("0.750", reopened.history()!!.single().rows.single().quantity.toPlainString())
        val stock = reopened.load()
        assertTrue(reopened.deleteHistory(full.identity))
        assertTrue(reopened.history()!!.isEmpty())
        assertEquals(stock, reopened.load())
        assertEquals(listOf("manual-inventory.json"), files(directory.toFile()))
        assertTrue(Files.exists(external))
        assertEquals(ManualInventoryStore.Commit.REPLAYED, ManualInventoryStore(file).commit(full, fixture.bytes, null))
        assertEquals(stock, reopened.load())
        external.toFile().delete()
        directory.toFile().deleteRecursively()
    }

    @Test fun boundConfirmationUsesExactOriginalAndRejectsStaleOrFutureDrafts() {
        val directory = Files.createTempDirectory(context.cacheDir.toPath(), "task06-bound-")
        val acquisition = directory.resolve("acquisition.png").toFile()
        val pixels = Bitmap.createBitmap(640, 640, Bitmap.Config.ARGB_8888)
        val prepared = PreparedReceiptImage()
        try {
            acquisition.outputStream().use { assertTrue(pixels.compress(Bitmap.CompressFormat.PNG, 100, it)) }
            val crop = ReceiptCrop.FULL.adjust(CropEdge.RIGHT, 0.75f)
            assertTrue(prepared.prepare(SelectedImageSnapshotEncoder(context.contentResolver), Uri.fromFile(acquisition), crop))
            val submitted = prepared.uploadBytes()
            assertEquals(480, prepared.bitmap!!.width)
            assertEquals(640, prepared.bitmap!!.height)
            assertFalse(submitted.contentEquals(acquisition.readBytes()))

            val (draft, _) = fixture("13-exact-weighted-quantity", liveDouble = true)
            includeWeighted(draft)
            draft.keepOriginal = true
            val earlierDay = LocalDate.parse(requireNotNull(draft.purchaseDate.displayed)).minusDays(1)
            val store = ManualInventoryStore(directory.resolve("manual-inventory.json"))
            var localDay = today
            val state = PantryUiState(MockReceiptPresentationSource(), store, today = { localDay })
            val plan = approved(draft, ReceiptConfirmationMode.INVENTORY_AND_RECEIPT)

            localDay = earlierDay
            val check = draft.confirmation(ReceiptConfirmationMode.INVENTORY_ONLY, localDay, acknowledged = true)
            assertEquals("Purchase date cannot be in the future.",
                (check as LiveReceiptReviewDraft.ConfirmationCheck.Blocked).explanation)
            assertEquals(ManualInventoryStore.Commit.CONFLICT, state.commitReview(draft, plan, prepared.originalBytes()))
            assertTrue(store.history()!!.isEmpty())
            assertTrue(store.load()!!.isEmpty())
            localDay = today

            val (stale, _) = fixture("13-exact-weighted-quantity", liveDouble = true)
            includeWeighted(stale)
            stale.keepOriginal = true
            stale.discard()
            assertEquals(ManualInventoryStore.Commit.CONFLICT, state.commitReview(stale, plan, prepared.originalBytes()))
            assertTrue(store.load()!!.isEmpty())

            assertEquals(ManualInventoryStore.Commit.COMMITTED, state.commitReview(draft, plan, prepared.originalBytes()))
            val reloaded = ManualInventoryStore(directory.resolve("manual-inventory.json"))
            assertArrayEquals(acquisition.readBytes(), reloaded.originalFile(plan.identity)!!.readBytes())
            assertEquals("0.750 kg", reloaded.load()!!.single().quantityLabel)
            assertEquals("0.750", reloaded.history()!!.single().rows.single().quantity.toPlainString())
            assertEquals(ManualInventoryStore.Commit.REPLAYED, state.commitReview(draft, plan, null))
            assertEquals(1, reloaded.history()!!.size)
            assertEquals(1, reloaded.load()!!.size)

            val stock = reloaded.load()
            assertTrue(reloaded.deleteHistory(plan.identity))
            assertNull(reloaded.originalFile(plan.identity))
            assertArrayEquals(acquisition.readBytes(), prepared.originalBytes())
            assertTrue(acquisition.isFile)
            assertEquals(stock, reloaded.load())
            assertEquals(ManualInventoryStore.Commit.REPLAYED, state.commitReview(draft, plan, null))
            assertTrue(reloaded.history()!!.isEmpty())
        } finally {
            prepared.release()
            pixels.recycle()
            directory.toFile().deleteRecursively()
        }
    }

    @Test fun inventoryOnlyNeverRetainsOriginalOrCreatesPurchaseHistory() {
        val directory = Files.createTempDirectory(context.cacheDir.toPath(), "task06-only-")
        val store = ManualInventoryStore(directory.resolve("manual-inventory.json"))
        val fixture = fixture("13-exact-weighted-quantity")
        val draft = fixture.draft
        includeWeighted(draft)
        draft.keepOriginal = true
        draft.omittedPurchasedRow = true
        val mode = ReceiptConfirmationMode.INVENTORY_ONLY
        val plan = (draft.confirmation(mode, today, acknowledged = true) as LiveReceiptReviewDraft.ConfirmationCheck.Ready)
            .also { assertTrue(it.needsIncompleteAcknowledgement) }.confirmation
        assertFalse(plan.keepOriginal)
        assertTrue(plan.incompleteAcknowledged)
        assertTrue(draft.confirmation(ReceiptConfirmationMode.INVENTORY_AND_RECEIPT, today, false) is
            LiveReceiptReviewDraft.ConfirmationCheck.Blocked)
        assertEquals(ManualInventoryStore.Commit.COMMITTED, store.commit(plan, fixture.bytes, byteArrayOf(1)))
        assertTrue(store.history()!!.isEmpty())
        assertEquals(listOf("manual-inventory.json"), files(directory.toFile()))
        directory.toFile().deleteRecursively()
    }

    @Test fun fiveReviewStatesBulkConflictsAndLegitimateOptionalPrice() {
        val selected = LiveReceiptReviewDraft.CandidateSource.SELECTED_PRE_REVIEW
        val alternative = LiveReceiptReviewDraft.CandidateSource.ALTERNATIVE
        val unverified = fixture("04-unverified-development-draft").draft
        val item = unverified.items.single().apply { this.selected = true; inventoryUnit = InventoryUnit.EACH }
        val description = item.description
        assertEquals(LiveReceiptReviewDraft.UserReviewState.UNREVIEWED, description.reviewState)
        assertNull(description.eligible(today))
        val oldOffer = unverified.bulkOffer(today)
        description.reject()
        assertEquals(LiveReceiptReviewDraft.UserReviewState.USER_REJECTED, description.reviewState)
        assertNull(description.eligible(today))
        assertFalse(unverified.acceptBulk(oldOffer, today))
        val recommendation = description.backend!!.alternatives.first()
        assertTrue(description.accept(description.offer(alternative, recommendation.value.id, today)!!, today))
        assertEquals(LiveReceiptReviewDraft.UserReviewState.USER_CONFIRMED, description.reviewState)
        assertEquals(recommendation.value.canonical, description.eligible(today))
        description.leaveUnresolved()
        assertEquals(LiveReceiptReviewDraft.UserReviewState.UNRESOLVED, description.reviewState)
        assertTrue(unverified.bulkOffer(today).offers.none { it.fieldId == description.original.id })
        assertTrue(description.edit("Reviewed milk", today))
        assertEquals(LiveReceiptReviewDraft.UserReviewState.USER_MODIFIED, description.reviewState)
        assertEquals("Reviewed milk", description.eligible(today))
        assertTrue(unverified.acceptBulk(unverified.bulkOffer(today), today))
        assertEquals(LiveReceiptReviewDraft.UserReviewState.USER_CONFIRMED, item.quantity.reviewState)

        val conflict = fixture("03-review-required-with-alternatives").draft
        assertEquals(true, conflict.items.single().description.backend!!.conflict)
        assertTrue(conflict.bulkOffer(today).offers.none { it.fieldId == conflict.items.single().description.original.id })

        val missing = fixture("02-retained-original-and-missing-price").draft
        val row = missing.items.single().apply { this.selected = true; inventoryUnit = InventoryUnit.EACH }
        assertNotNull(approved(missing, ReceiptConfirmationMode.INVENTORY_AND_RECEIPT).history!!.rows.single().unitPriceAbsence)
        row.unitPrice.reject()
        assertTrue(row.unitPrice.edit("", today))
        assertNull(row.unitPrice.legitimateAbsence())
        assertTrue(missing.confirmation(ReceiptConfirmationMode.INVENTORY_AND_RECEIPT, today, false) is
            LiveReceiptReviewDraft.ConfirmationCheck.Blocked)
        val absence = row.unitPrice.offer(selected, row.unitPrice.backend!!.selected.id, today)!!
        assertTrue(row.unitPrice.accept(absence, today))
        assertNull(approved(missing, ReceiptConfirmationMode.INVENTORY_AND_RECEIPT).history!!.rows.single().unitPrice)
    }

    @Test fun nativeReviewConfirmationWeightedInventoryAndHistoryScreens() {
        val fixture = fixture("13-exact-weighted-quantity")
        val draft = fixture.draft
        val store = ManualInventoryStore(context)
        val launchIntent = android.content.Intent(context, MainActivity::class.java)
        lateinit var plan: ReceiptConfirmation
        ActivityScenario.launch<MainActivity>(launchIntent).use { scenario ->
            scenario.onActivity { activity ->
                val screen = activity.javaClass.getDeclaredField("currentScreen").apply { isAccessible = true }
                val reviewScreen = requireNotNull(screen.type.enumConstants).first { (it as Enum<*>).name == "T09_PROCESSING" }
                screen.set(activity, reviewScreen)
                activity.javaClass.getDeclaredField("liveReviewDraft").apply { isAccessible = true }.set(activity, draft)
                val method = activity.javaClass.getDeclaredMethod("renderLiveReceiptReview", LiveReceiptReviewDraft::class.java)
                method.isAccessible = true
                method.invoke(activity, draft)
            }
            onView(withText("Choose confirmation mode")).check(matches(isDisplayed()))
            screenshot("review")
            onView(withContentDescription("Include item 1 in inventory")).perform(sageScrollTo(), click())
            onView(withText("Inventory unit: Not specified")).perform(sageScrollTo(), click())
            onView(withText("kg")).perform(click())
            scenario.onActivity {
                plan = approved(draft, ReceiptConfirmationMode.INVENTORY_AND_RECEIPT)
            }
            onView(withText("Choose confirmation mode")).perform(click())
            onView(withText("Inventory and receipt")).perform(click())
            onView(withText("Confirm inventory and save receipt")).check(matches(isDisplayed()))
            screenshot("confirmation")
        }
        val seeded = InventoryItem("manual-inventory-v532-scan-seed", "Fixture beans", 1, ManualInventoryStore.STANDALONE_ROW_STATE)
            .copy(household = InventoryMetadata(InventoryCategory.DRY_FOOD))
        assertNotNull(store.update { it + seeded })
        try {
            assertEquals(ManualInventoryStore.Commit.COMMITTED, store.commit(plan, fixture.bytes, null))
            assertTrue(store.acknowledge(setOf(plan.identity)))
            ActivityScenario.launch<MainActivity>(launchIntent).use {
                val group = context.getString(R.string.category_uncategorized)
                onView(withText(group)).perform(sageScrollTo(), click())
                onView(withText("0.750 kg")).perform(sageScrollTo()).check(matches(isDisplayed()))
                onView(withText(R.string.category_dry_food)).perform(sageScrollTo()).check(matches(isDisplayed()))
                assertEquals(listOf(seeded) + plan.stock, store.load())
                screenshot("weighted-inventory")
                onView(withId(R.id.receipt_history)).perform(click())
                onView(withText("Receipt History")).check(matches(isDisplayed()))
                onView(withText("1 receipt · RM 6.00 recorded spending")).check(matches(isDisplayed()))
                screenshot("history")
                onView(withText("SUNNY MART")).perform(scrollTo(), click())
                onView(withText("Purchased quantity · 0.750")).check(matches(isDisplayed()))
                screenshot("history-detail")
                onView(withText("Delete receipt")).perform(sageScrollTo(), click())
                onView(withText("Delete this receipt?")).inRoot(isDialog()).check(matches(isDisplayed()))
                onView(withText("Delete receipt")).inRoot(isDialog()).perform(click())
                onView(withText("No saved receipts yet")).check(matches(isDisplayed()))
                assertTrue(store.history()!!.isEmpty())
                assertTrue(store.load()!!.containsAll(plan.stock))
            }
        } finally {
            if (store.history()!!.any { it.confirmationId == plan.identity }) {
                assertTrue(store.deleteHistory(plan.identity))
            }
            val fixtureIds = plan.stock.map { it.id } + seeded.id
            assertNotNull(store.update { it.filterNot { row -> row.id in fixtureIds } })
        }
    }

    private fun screenshot(name: String) {
        if (InstrumentationRegistry.getArguments().getString("task06Screenshots") != "true") return
        instrumentation.waitForIdleSync()
        // Window/dialog surface composition can lag behind Espresso idle.
        android.os.SystemClock.sleep(500)
        val image = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        try {
            val file = File(context.filesDir, "task06-$name.png")
            file.outputStream().use { assertTrue(image.compress(Bitmap.CompressFormat.PNG, 100, it)) }
        } finally { image.recycle() }
    }

    private fun includeWeighted(draft: LiveReceiptReviewDraft) {
        draft.items.first().selected = true
        draft.items.first().inventoryUnit = InventoryUnit.KILOGRAM
    }

    private fun approved(draft: LiveReceiptReviewDraft, mode: ReceiptConfirmationMode) =
        (draft.confirmation(mode, today, false) as LiveReceiptReviewDraft.ConfirmationCheck.Ready).confirmation

    private fun files(directory: File) = directory.list().orEmpty().sorted()
    private data class TestFixture(val draft: LiveReceiptReviewDraft, val bytes: ByteArray)

    private fun fixture(id: String, liveDouble: Boolean = false): TestFixture {
        val bytes = instrumentation.context.assets.open("fixtures/$id.json").use { it.readBytes() }
        val parsed = ReceiptPresentationV1Decoder.strictObject(bytes) as ReceiptPresentationResult.Accepted
        val root = ReviewJson(parsed.value, "$")
        val context = root["consumerContext"]
        val mode = if (liveDouble) PresentationConsumerMode.LIVE else PresentationConsumerMode.FIXTURE
        val ids = PresentationConsumerContext(context["expectedRequestId"].string(), context["expectedImageId"].string(), mode)
        val span = root["envelope"].objectNode()
        val fixtureBytes = bytes.copyOfRange(span.byteStart, span.byteEnd)
        // Exercise the app's LIVE source guard using an in-memory test double. No transport runs.
        val wrapperBytes = if (liveDouble) fixtureBytes.decodeToString()
            .replaceFirst("\"type\":\"SYNTHETIC_FIXTURE\"", "\"type\":\"LOCAL_IMAGE\"").encodeToByteArray()
            else fixtureBytes
        val reviewContext = if (liveDouble) ReviewContext(ids, context["expectedImageWidth"].integer(),
            context["expectedImageHeight"].integer()) else ReviewContext(ids)
        val review = ReceiptReviewV1Decoder.decode(wrapperBytes, reviewContext) as ReceiptPresentationResult.Accepted
        val available = M3eReceiptPresentationAdapter().mapReview(review.value) as ReceiptPresentationUiResult.Available
        val request = ReceiptProcessingRequest(ReceiptProcessingRequest.Selection(ReceiptProcessingRequest.Owner(), ids.expectedImageId),
            ReceiptProcessingRequest.Submission(), ids)
        if (liveDouble) {
            val finished = ReceiptProcessingLifecycle.State.Finished(request, ReceiptProcessingLifecycle.Outcome.Presentation(available))
            return TestFixture(requireNotNull(LiveReceiptReviewDraft.from(finished)), wrapperBytes)
        }
        val constructor = LiveReceiptReviewDraft::class.java.declaredConstructors.single { it.parameterCount == 3 }
        constructor.isAccessible = true
        return TestFixture(constructor.newInstance(request, available.liveEvidence, available) as LiveReceiptReviewDraft, wrapperBytes)
    }
}
