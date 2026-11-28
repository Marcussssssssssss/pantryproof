package com.pantryproof.prototype

import android.annotation.SuppressLint
import android.app.AlertDialog
import android.app.DatePickerDialog
import android.app.Dialog
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.graphics.Rect
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.MediaStore
import android.security.NetworkSecurityPolicy
import android.text.Editable
import android.text.InputFilter
import android.text.InputType
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.inputmethod.EditorInfo
import android.widget.AdapterView
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.Spinner
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.AccessibilityDelegateCompat
import androidx.core.view.ViewCompat
import androidx.core.view.accessibility.AccessibilityNodeInfoCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowCompat
import androidx.lifecycle.Lifecycle
import com.pantryproof.prototype.data.BoundSyntheticReceiptProcessingTransport
import com.pantryproof.prototype.image.SelectedImageSnapshotEncoder
import com.pantryproof.prototype.ui.SelectedImageProcessingController
import com.pantryproof.prototype.data.MockReceiptPresentationSource
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryCategory
import com.pantryproof.prototype.data.InventoryMetadata
import com.pantryproof.prototype.data.InventoryWarning
import com.pantryproof.prototype.data.warnings
import com.pantryproof.prototype.data.InventoryUnit
import com.pantryproof.prototype.data.PurchaseSource
import com.pantryproof.prototype.data.ReceiptConfirmationMode
import com.pantryproof.prototype.data.PurchaseRecord
import com.pantryproof.prototype.data.receiptHistoryMonths
import com.pantryproof.prototype.contract.review.ReviewReadiness
import com.pantryproof.prototype.contract.review.ReviewField
import com.pantryproof.prototype.contract.v1.ReceiptFieldRole
import com.pantryproof.prototype.image.PreparedReceiptImage
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.data.PresentedField
import com.pantryproof.prototype.data.PresentedFieldStatus
import com.pantryproof.prototype.data.PresentedReceipt
import com.pantryproof.prototype.data.PresentedReceiptItem
import com.pantryproof.prototype.data.Receipt
import com.pantryproof.prototype.data.ReceiptItem
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle
import com.pantryproof.prototype.data.ReceiptProcessingRequest
import com.pantryproof.prototype.data.SyntheticReceiptProcessingTransport
import com.pantryproof.prototype.data.T09HttpTransport
import com.pantryproof.prototype.data.T09ProcessingConfig
import com.pantryproof.prototype.image.ReceiptCaptureStore
import com.pantryproof.prototype.image.ReceiptCrop
import com.pantryproof.prototype.image.ReceiptZoom
import com.pantryproof.prototype.image.ZoomReceiptView
import com.pantryproof.prototype.ui.InventoryBrowseProjection
import com.pantryproof.prototype.ui.InventoryRowContent
import com.pantryproof.prototype.ui.sageCategoryGroups
import com.pantryproof.prototype.ui.EditableReceipt
import com.pantryproof.prototype.ui.EditableReceiptItem
import com.pantryproof.prototype.ui.LiveReceiptReviewDraft
import com.pantryproof.prototype.ui.MoneyFormatter
import com.pantryproof.prototype.ui.PantryActionStyle
import com.pantryproof.prototype.ui.PantryBannerTone
import com.pantryproof.prototype.ui.PantryUiState
import com.pantryproof.prototype.ui.PantryUiComponents
import com.pantryproof.prototype.ui.SageExpandableSections
import com.pantryproof.prototype.ui.showSageCropEditor
import com.pantryproof.prototype.ui.SageReceiptScanView
import com.pantryproof.prototype.ui.PurchaseDateInput
import com.pantryproof.prototype.ui.ReceiptValidator
import com.pantryproof.prototype.ui.ReceiptValidationResult
import com.pantryproof.prototype.ui.ReceiptReviewAnnotationPolicy
import com.pantryproof.prototype.ui.ReceiptProcessingUiController
import java.math.BigDecimal
import java.time.LocalDate
import java.time.Duration
import java.time.ZonedDateTime
import java.util.ArrayDeque
import java.util.GregorianCalendar
import java.util.Locale
import java.util.UUID
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import kotlin.math.roundToInt

@SuppressLint("SetTextI18n", "ExifInterface")
class MainActivity : ComponentActivity() {
    private enum class Screen {
        INVENTORY, DEVELOPMENT, PREVIEW, DETAILS, REVIEW, MANUAL, MANUAL_REVIEW, PROCESSING_DEMO, SELECTED_PROCESSING, T09_PROCESSING, HISTORY, HISTORY_DETAIL,
    }

    private enum class LocalImageSource {
        GALLERY, CAMERA,
    }

    private enum class ImageInputNotice {
        CAMERA_UNAVAILABLE, CAMERA_CANCELLED, CAMERA_INVALID, IMAGE_UNAVAILABLE,
    }

    private class GrantedTakePicture : ActivityResultContracts.TakePicture() {
        override fun createIntent(context: Context, input: Uri): Intent =
            super.createIntent(context, input).apply {
                clipData = ClipData.newRawUri("PantryProof receipt photo", input)
                addFlags(
                    Intent.FLAG_GRANT_READ_URI_PERMISSION or
                        Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
                )
            }
    }

    private companion object {
        const val MAX_PREVIEW_IMAGE_DIMENSION = 1600
    }

    private data class ItemEditFields(
        val description: ReviewFieldUi,
        val quantity: ReviewFieldUi,
        val unitPrice: ReviewFieldUi,
        val lineTotal: ReviewFieldUi,
    )

    private data class ReviewFieldUi(
        val key: String,
        val field: EditText,
        val inputSurface: LinearLayout,
        val helper: TextView,
        val defaultHelper: String,
        val container: View,
    )

    private lateinit var state: PantryUiState
    private val ui by lazy { PantryUiComponents(this) }
    private val captureStore by lazy { ReceiptCaptureStore(this) }
    private val backStack = ArrayDeque<Screen>()
    private var currentScreen = Screen.INVENTORY
    private var inventoryScrollY = 0
    private var inventoryImeVisible = false
    private val inventorySheets = mutableListOf<Dialog>()
    private val inventorySheet: Dialog? get() = inventorySheets.lastOrNull { it.isShowing }
    private val developmentAvailable: Boolean
        get() = applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
    private var selectedImageUri: Uri? = null
    private var selectedImageCrop: ReceiptCrop? = null
    private var cropEditorDialog: Dialog? = null
    private var cropEditorDraft: CropEditorDraft? = null

    private data class CropEditorDraft(val uri: Uri, val crop: ReceiptCrop, val expanded: Boolean)
    private var selectedImageSource: LocalImageSource? = null
    private var ownsSelectedGalleryReadGrant = false
    private var selectedCaptureFileName: String? = null
    private var pendingCaptureUri: Uri? = null
    private var pendingCaptureFileName: String? = null
    private var imageInputNotice: ImageInputNotice? = null
    private var manualDraft: EditableReceipt? = null
    private var manualValidationAttempted = false
    private var manualReviewedDraft: EditableReceipt? = null
    private var manualReviewError: Int? = null
    private var reviewHasUnsavedChanges = false
    private var reviewDraft: EditableReceipt? = null
    private var reviewSavedTemporarily = false
    private var temporaryConfirmationVisible = false
    private var temporaryResultDialog: Dialog? = null
    private var restoreTemporaryResultSheet = false
    private var reviewValidationAttempted = false
    private val reviewValidationErrors = linkedMapOf<String, String>()
    private val inventoryBrowse = InventoryBrowseProjection()
    private var inventoryResults: LinearLayout? = null
    private var inventoryBrowseCount: TextView? = null
    private val inventoryBrowseHandler = Handler(Looper.getMainLooper())
    private var inventoryCountAnnouncement: Runnable? = null
    private var screenScrollView: ScrollView? = null
    private var screenPrimary: View? = null
    private val inventoryGroupOverrides = mutableMapOf<InventoryCategory, Boolean>()
    private val matchingInventoryGroupOverrides = mutableMapOf<InventoryCategory, Boolean>()
    private var inventoryWarningDate: LocalDate? = null
    private val inventoryDateRefresh = Runnable {
        if (currentScreen == Screen.INVENTORY && lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
            if (inventoryWarningDate != state.currentLocalDate()) updateInventoryBrowseResults()
            else scheduleInventoryDateRefresh()
        }
    }
    private data class InventorySuccess(val title: Int, val message: String = "", val addedIds: List<String> = emptyList())
    private var pendingInventorySuccess: InventorySuccess? = null
    private var inventorySuccessDismissal: Runnable? = null
    private val syntheticCollapsed = mutableSetOf<String>()
    private val manualCollapsed = mutableSetOf<String>()
    private val liveCollapsed = mutableSetOf<String>()
    private var boundLiveImage: BoundLiveImage? = null

    private data class BoundLiveImage(val uri: Uri, val crop: ReceiptCrop, val source: LocalImageSource)
    private var selectedProcessingController: SelectedImageProcessingController? = null
    private var preparedLiveImage: PreparedReceiptImage? = null
    private var historyQuery = ""
    private var historyIdentity: String? = null
    private var receiptCommitInProgress = false
    private var pendingReceiptAcknowledgements = emptySet<String>()
    private val reviewPreferences by lazy { getSharedPreferences("receipt-review-preferences", MODE_PRIVATE) }
    private var keepOriginal = false
    private var liveSession: T09ProcessingConfig.Session? = null
    private var livePhase = T09HttpTransport.Phase.PREPARING
    private var liveCancelled = false
    private var liveReviewDraft: LiveReceiptReviewDraft? = null
    private var liveReviewConfirmation: AlertDialog? = null
    private var selectedProcessingWorker: ExecutorService? = null
    private var selectedProcessingHandler: Handler? = null
    private var renderAfterFixtureTeardown = false
    private var processingController: ReceiptProcessingUiController? = null
    private var processingWorker: ExecutorService? = null
    private var processingHandler: Handler? = null
    @Volatile
    private var processingScenario = SyntheticReceiptProcessingTransport.Scenario.AVAILABLE

    private val imagePicker = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        handleImageResult(result.resultCode, result.data)
    }

    private val cameraCapture = registerForActivityResult(
        GrantedTakePicture(),
    ) { captured ->
        handleCameraCaptureResult(captured)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = true
            isAppearanceLightNavigationBars = Build.VERSION.SDK_INT >= 26
        }
        state = PantryUiState(MockReceiptPresentationSource(), ManualInventoryStore(applicationContext))
        pendingReceiptAcknowledgements = state.recoverConfirmations().orEmpty()
        keepOriginal = reviewPreferences.getBoolean("keepOriginal", false)
        historyQuery = savedInstanceState?.getString("historyQuery").orEmpty()
        historyIdentity = savedInstanceState?.getString("historyIdentity")
        @Suppress("DEPRECATION")
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        selectedImageUri = savedInstanceState?.getString("selectedImageUri")?.let(Uri::parse)
        selectedImageCrop = selectedImageUri?.let {
            ReceiptCrop.from(savedInstanceState?.getFloatArray("selectedImageCrop"))
        }
        selectedImageSource = savedInstanceState?.getString("selectedImageSource")
            ?.let { runCatching { LocalImageSource.valueOf(it) }.getOrNull() }
            ?: selectedImageUri?.let { LocalImageSource.GALLERY }
        ownsSelectedGalleryReadGrant =
            savedInstanceState?.getBoolean("ownsSelectedGalleryReadGrant") == true
        selectedCaptureFileName = savedInstanceState?.getString("selectedCaptureFileName")
        pendingCaptureUri = savedInstanceState?.getString("pendingCaptureUri")?.let(Uri::parse)
        pendingCaptureFileName = savedInstanceState?.getString("pendingCaptureFileName")
        fun restoreScreen(name: String): Screen? = when (name) {
            "HOME", "ADD_RECEIPT" -> Screen.INVENTORY
            Screen.DEVELOPMENT.name, Screen.PROCESSING_DEMO.name ->
                Screen.valueOf(name).takeIf { developmentAvailable }
            else -> runCatching { Screen.valueOf(name) }.getOrNull()
        }
        currentScreen = savedInstanceState?.getString("currentScreen")?.let(::restoreScreen) ?: Screen.INVENTORY
        savedInstanceState?.getStringArrayList("backStack")?.mapNotNull(::restoreScreen)?.forEach { screen ->
            if (screen != currentScreen && backStack.peekLast() != screen) backStack.addLast(screen)
        }
        inventoryScrollY = savedInstanceState?.getInt("inventoryScrollY") ?: 0
        if (currentScreen == Screen.T09_PROCESSING) {
            currentScreen = backStack.pollLast() ?: Screen.PREVIEW
        }
        imageInputNotice = savedInstanceState?.getString("imageInputNotice")
            ?.let { runCatching { ImageInputNotice.valueOf(it) }.getOrNull() }
        restoreCaptureFiles()
        savedInstanceState?.let(::restoreSessionState)
        if (currentScreen == Screen.MANUAL || currentScreen == Screen.MANUAL_REVIEW) {
            manualDraft = savedInstanceState?.getBundle("manualDraft")?.let(::readDraft)
            if (manualDraft == null) {
                manualDraft = null
                if (backStack.peekLast() == Screen.MANUAL) backStack.removeLast()
                currentScreen = backStack.pollLast() ?: Screen.PREVIEW
            } else {
                if (currentScreen == Screen.MANUAL_REVIEW) {
                    manualReviewedDraft = savedInstanceState?.getBundle("manualReviewedDraft")?.let(::readDraft)
                    manualReviewError = savedInstanceState?.getInt("manualReviewError")?.takeIf { it != 0 }
                }
                manualValidationAttempted = savedInstanceState?.getBoolean("manualValidationAttempted") == true
            }
        }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() = handleBackNavigation()
        })
        if (currentScreen == Screen.PREVIEW && savedInstanceState != null) {
            val uri = selectedImageUri
            val crop = ReceiptCrop.from(savedInstanceState.getFloatArray("cropEditorDraft"))
            if (uri != null && crop != null && savedInstanceState.getString("cropEditorUri") == uri.toString()) {
                cropEditorDraft = CropEditorDraft(uri, crop, savedInstanceState.getBoolean("cropEditorExpanded"))
            }
        }
        render()
    }

    override fun onPostResume() {
        super.onPostResume()
        val draft = cropEditorDraft ?: return
        if (cropEditorDialog == null && currentScreen == Screen.PREVIEW && selectedImageUri == draft.uri) {
            val bitmap = decodePreviewBitmap(draft.uri)
            if (bitmap == null) {
                cropEditorDraft = null
            } else {
                showCropEditor(draft.uri, bitmap, draft.crop, draft.expanded)
            }
        }
    }

    override fun onStart() {
        super.onStart()
        if (renderAfterFixtureTeardown ||
            (currentScreen == Screen.PROCESSING_DEMO && processingController == null) ||
            (currentScreen == Screen.SELECTED_PROCESSING && selectedProcessingController == null)
        ) render()
        if (currentScreen == Screen.INVENTORY) {
            updateInventoryBrowseResults(announceImmediately = true)
        }
    }

    private fun scheduleInventoryDateRefresh() {
        inventoryBrowseHandler.removeCallbacks(inventoryDateRefresh)
        val now = ZonedDateTime.now()
        val midnight = now.toLocalDate().plusDays(1).atStartOfDay(now.zone)
        val delay = Duration.between(now, midnight).toMillis().coerceIn(1L, 60_000L)
        inventoryBrowseHandler.postDelayed(inventoryDateRefresh, delay)
    }

    override fun onStop() {
        inventoryCountAnnouncement?.let(inventoryBrowseHandler::removeCallbacks)
        inventoryBrowseHandler.removeCallbacks(inventoryDateRefresh)
        disposeProcessingDemo()
        val hadFixture = selectedProcessingController?.isFixture == true
        val hadLive = currentScreen == Screen.T09_PROCESSING
        disposeSelectedImageProcessing()
        if (hadFixture) leaveFixtureProcessingScreen(renderNow = false)
        if (hadLive) {
            currentScreen = backStack.pollLast() ?: Screen.PREVIEW
            renderAfterFixtureTeardown = true
        }
        super.onStop()
    }

    override fun onDestroy() {
        inventoryBrowseHandler.removeCallbacksAndMessages(null)
        temporaryResultDialog?.dismiss()
        pendingInventorySuccess = null
        inventorySheets.toList().asReversed().forEach(Dialog::dismiss)
        cropEditorDialog?.dismiss()
        disposeProcessingDemo()
        disposeSelectedImageProcessing()
        super.onDestroy()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        val browseScroll = if (currentScreen == Screen.INVENTORY) screenScrollView?.scrollY else null
        outState.putInt("inventoryScrollY", browseScroll ?: inventoryScrollY)
        outState.putStringArrayList("sageSyntheticCollapsed", ArrayList(syntheticCollapsed))
        outState.putStringArrayList("sageManualCollapsed", ArrayList(manualCollapsed))
        inventoryGroupOverrides.forEach { (category, open) -> outState.putBoolean("inventoryCategory." + category.code, open) }
        matchingInventoryGroupOverrides.forEach { (category, open) ->
            outState.putBoolean("matchingInventoryCategory." + category.code, open)
        }
        outState.putString("inventoryBrowseQuery", inventoryBrowse.query)
        outState.putString("inventoryBrowseSort", inventoryBrowse.sort.name)
        outState.putString("inventoryBrowseSource", inventoryBrowse.source.name)
        outState.putString("selectedImageUri", selectedImageUri?.toString())
        outState.putFloatArray("selectedImageCrop", selectedImageCrop?.values())
        cropEditorDraft?.let {
            outState.putString("cropEditorUri", it.uri.toString())
            outState.putFloatArray("cropEditorDraft", it.crop.values())
            outState.putBoolean("cropEditorExpanded", it.expanded)
        }
        outState.putString("selectedImageSource", selectedImageSource?.name)
        outState.putBoolean("ownsSelectedGalleryReadGrant", ownsSelectedGalleryReadGrant)
        outState.putString("selectedCaptureFileName", selectedCaptureFileName)
        outState.putString("pendingCaptureUri", pendingCaptureUri?.toString())
        outState.putString("pendingCaptureFileName", pendingCaptureFileName)
        outState.putString("currentScreen", currentScreen.name)
        outState.putString("historyQuery", historyQuery)
        outState.putString("historyIdentity", historyIdentity)
        outState.putStringArrayList(
            "backStack",
            ArrayList(backStack.map(Screen::name)),
        )
        outState.putString("imageInputNotice", imageInputNotice?.name)
        outState.putBoolean("reviewHasUnsavedChanges", reviewHasUnsavedChanges)
        outState.putBoolean("reviewSavedTemporarily", reviewSavedTemporarily)
        outState.putBoolean("temporaryConfirmationVisible", temporaryConfirmationVisible)
        outState.putBoolean("sageTemporaryResultSheet", temporaryResultDialog?.isShowing == true)
        outState.putBoolean("reviewValidationAttempted", reviewValidationAttempted)
        state.receipt?.let { writeReceipt(outState, "receipt", it) }
        writeInventory(outState, state.inventory.filterNot { ManualInventoryStore.isDurableRowId(it.id) })
        outState.putBoolean("demoConfirmed", state.demoConfirmed)
        reviewDraft?.let { writeDraft(outState, it) }
        manualDraft?.let { draft ->
            outState.putBundle("manualDraft", Bundle().apply { writeDraft(this, draft) })
            outState.putBoolean("manualValidationAttempted", manualValidationAttempted)
        }
        manualReviewedDraft?.let { draft ->
            outState.putBundle("manualReviewedDraft", Bundle().apply { writeDraft(this, draft) })
        }
        manualReviewError?.let { outState.putInt("manualReviewError", it) }
        outState.putStringArrayList("reviewErrorKeys", ArrayList(reviewValidationErrors.keys))
        outState.putStringArrayList("reviewErrorValues", ArrayList(reviewValidationErrors.values))
        super.onSaveInstanceState(outState)
    }

    private fun handleBackNavigation() {
        if (receiptCommitInProgress) return
        if (currentScreen == Screen.SELECTED_PROCESSING || currentScreen == Screen.T09_PROCESSING) {
            disposeSelectedImageProcessing()
            currentScreen = backStack.pollLast() ?: Screen.PREVIEW
            render()
        } else if (currentScreen == Screen.PROCESSING_DEMO) {
            disposeProcessingDemo()
            currentScreen = backStack.pollLast() ?: Screen.INVENTORY
            render()
        } else if (currentScreen == Screen.MANUAL_REVIEW) {
            manualReviewedDraft = null
            manualReviewError = null
            goBack()
        } else if (currentScreen == Screen.MANUAL) {
            confirmDiscardManualDraft()
        } else if (currentScreen == Screen.PREVIEW) {
            switchToSyntheticDemo()
            goBack()
        } else if (currentScreen == Screen.REVIEW && reviewHasUnsavedChanges) {
            confirmDiscardEdits { goBack() }
        } else if (currentScreen == Screen.INVENTORY) {
            switchToSyntheticDemo()
            finish()
        } else {
            goBack()
        }
    }

    private fun handleImageResult(resultCode: Int, data: Intent?) {
        if (resultCode != RESULT_OK) return
        val uri = data?.data ?: data?.clipData?.firstUri()
        if (uri == null) {
            imageInputNotice = ImageInputNotice.IMAGE_UNAVAILABLE
            if (selectedImageUri == null) selectedImageSource = LocalImageSource.GALLERY
            if (currentScreen == Screen.PREVIEW) render() else navigate(Screen.PREVIEW)
            return
        }

        val preview = decodePreviewBitmap(uri)
        if (preview == null) {
            imageInputNotice = ImageInputNotice.IMAGE_UNAVAILABLE
            if (selectedImageUri == null) selectedImageSource = LocalImageSource.GALLERY
            if (currentScreen == Screen.PREVIEW) render() else navigate(Screen.PREVIEW)
            return
        }
        preview.recycle()
        val ownsReadGrant = persistGalleryReadPermission(uri, data?.flags ?: 0)
        replaceSelectedImage(uri, LocalImageSource.GALLERY, captureFileName = null)
        ownsSelectedGalleryReadGrant = ownsReadGrant
        if (currentScreen == Screen.PREVIEW) {
            render()
        } else {
            navigate(Screen.PREVIEW)
        }
    }

    private fun handleCameraCaptureResult(captured: Boolean) {
        val uri = pendingCaptureUri
        val fileName = pendingCaptureFileName
        pendingCaptureUri = null
        pendingCaptureFileName = null
        if (!captured) {
            captureStore.delete(fileName)
            imageInputNotice = ImageInputNotice.CAMERA_CANCELLED
            render()
            return
        }
        val preview = if (uri != null && fileName != null) decodePreviewBitmap(uri) else null
        if (uri == null || fileName == null || preview == null) {
            captureStore.delete(fileName)
            imageInputNotice = ImageInputNotice.CAMERA_INVALID
            render()
            return
        }

        preview.recycle()
        replaceSelectedImage(uri, LocalImageSource.CAMERA, fileName)
        if (currentScreen == Screen.PREVIEW) {
            render()
        } else {
            navigate(Screen.PREVIEW)
        }
    }

    private fun ClipData.firstUri(): Uri? =
        if (itemCount > 0) getItemAt(0).uri else null

    private fun render() {
        renderAfterFixtureTeardown = false
        when (currentScreen) {
            Screen.DEVELOPMENT -> renderDevelopment()
            Screen.PREVIEW -> renderPreview()
            Screen.DETAILS -> renderDetails()
            Screen.REVIEW -> {
                renderReview()
                if (restoreTemporaryResultSheet) {
                    restoreTemporaryResultSheet = false
                    if (temporaryConfirmationVisible && state.demoConfirmed) showTemporaryReceiptResult()
                }
            }
            Screen.MANUAL -> renderManualReceipt()
            Screen.MANUAL_REVIEW -> renderManualReceiptReview()
            Screen.INVENTORY -> renderInventory()
            Screen.PROCESSING_DEMO -> renderProcessingDemo()
            Screen.SELECTED_PROCESSING -> renderSelectedImageProcessing()
            Screen.T09_PROCESSING -> renderSelectedImageProcessing(live = true)
            Screen.HISTORY -> renderReceiptHistory()
            Screen.HISTORY_DETAIL -> renderReceiptHistoryDetail()
        }
    }

    private fun developmentEntry(): View = ui.iconButton(
        R.drawable.ic_sage_flask, getString(R.string.sage_tools), R.id.sage_development_tools,
    ) { navigate(Screen.DEVELOPMENT) }

    private fun renderDevelopment() = setScreen(getString(R.string.sage_tools), true) {
        add(ui.actionButton(getString(R.string.home_demo_action), PantryActionStyle.SECONDARY,
            viewId = R.id.home_synthetic_demo) {
            switchToSyntheticDemo()
            navigate(Screen.PREVIEW)
        })
        add(ui.actionButton(getString(R.string.processing_demo_title), PantryActionStyle.SECONDARY,
            viewId = R.id.home_processing_demo) { navigate(Screen.PROCESSING_DEMO) })
        add(ui.actionButton(getString(R.string.v5_selected_test_source), PantryActionStyle.SECONDARY,
            viewId = R.id.v5_development_image) { launchImagePicker() })
        if (T09ProcessingConfig.isCapable(packageName)) {
            val configuration = Intent().setClassName(
                packageName, "com.pantryproof.prototype.T09DebugConfigurationActivity",
            )
            packageManager.resolveActivity(configuration, 0)?.let { entry ->
                add(ui.actionButton(entry.loadLabel(packageManager).toString(), PantryActionStyle.SECONDARY) {
                    startActivity(configuration)
                })
            }
        }
    }

    private fun enqueueProcessingWorker(worker: ExecutorService, action: () -> Unit) {
        if (worker.isShutdown) return
        try {
            worker.execute(action)
        } catch (_: RejectedExecutionException) {
            // Disposal can shut down the executor between the check and enqueue.
        }
    }

    private fun ensureProcessingController(): ReceiptProcessingUiController {
        processingController?.let { return it }
        val handler = Handler(Looper.getMainLooper())
        val worker = Executors.newSingleThreadExecutor()
        processingHandler = handler
        processingWorker = worker
        val transport = SyntheticReceiptProcessingTransport(
            scenario = { processingScenario },
            dispatchResponse = { action ->
                handler.postDelayed({ enqueueProcessingWorker(worker, action) }, 500L)
            },
        )
        val controller = ReceiptProcessingUiController(
            transport = transport,
            postWorker = { action -> enqueueProcessingWorker(worker, action) },
            postUi = { action -> handler.post { action() } },
            schedule = { delay, action -> handler.postDelayed({ action() }, delay) },
            nowMillis = { SystemClock.elapsedRealtime() },
            timeoutMillis = 10_000L,
            newImageId = { "synthetic-image-" + UUID.randomUUID() },
            newRequestId = { "synthetic-request-" + UUID.randomUUID() },
            onStateChanged = { next ->
                if (currentScreen == Screen.PROCESSING_DEMO && processingController?.state === next) {
                    render()
                }
            },
        )
        controller.selectInput()
        processingController = controller
        return controller
    }

    private fun disposeProcessingDemo() {
        processingController?.dispose()
        processingController = null
        processingHandler?.removeCallbacksAndMessages(null)
        processingHandler = null
        processingWorker?.shutdown()
        processingWorker = null
    }

    private fun processingFocusedView(view: View, accessibility: Boolean): View? {
        val focused = if (accessibility) view.isAccessibilityFocused else view.isFocused
        if (focused && view.id != View.NO_ID) return view
        if (view is ViewGroup) {
            for (index in 0 until view.childCount) {
                processingFocusedView(view.getChildAt(index), accessibility)?.let { return it }
            }
        }
        return null
    }

    private fun restoreProcessingFocus(
        root: View,
        inputId: Int?,
        inputInTouchMode: Boolean,
        accessibilityId: Int?,
        statusId: Int,
        initialEntry: Boolean,
    ) {
        val input = inputId?.let { root.findViewById<View>(it) }?.takeIf { it.isEnabled }
            ?: if (inputId != null || initialEntry) root.findViewById<View>(statusId)?.takeIf { it.isEnabled } else null
        if (input != null) {
            if (inputInTouchMode) input.isFocusableInTouchMode = true
            if (!input.isFocused) input.requestFocus()
        }
        // A missing/disabled reader target has no forced substitute. Pane/live-region
        // behavior remains unchanged, and the accessibility service owns its navigation.
        val reader = accessibilityId?.let { root.findViewById<View>(it) }?.takeIf { it.isEnabled }
        if (reader != null && !reader.isAccessibilityFocused) reader.performAccessibilityAction(
            android.view.accessibility.AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS, null,
        )
    }

    private fun renderProcessingDemo() {
        val controller = ensureProcessingController()
        // Only the current controller's rendered tree may supply restoration intent.
        val previousRoot = findViewById<View>(R.id.screen_processing_demo)?.takeIf { it.tag === controller }
        val inputFocus = previousRoot?.let { processingFocusedView(it, accessibility = false) }
        val inputId = inputFocus?.id
        val inputInTouchMode = inputFocus?.isFocusableInTouchMode == true
        val accessibilityId = previousRoot?.let { processingFocusedView(it, accessibility = true) }?.id
        val current = controller.state
        setScreen(getString(R.string.processing_demo_title), true) {
            add(bodyText(getString(R.string.processing_demo_body)))
            add(space(12))
            add(TextView(this@MainActivity).apply {
                text = getString(R.string.processing_sample_label)
                labelFor = R.id.processing_scenario
            })
            add(Spinner(this@MainActivity, Spinner.MODE_DROPDOWN).apply {
                id = R.id.processing_scenario
                contentDescription = getString(R.string.processing_sample_label)
                minimumHeight = dp(48)
                ui.styleDropdown(this, resources.getStringArray(R.array.processing_scenarios))
                setSelection(processingScenario.ordinal, false)
                onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                    override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, rowId: Long) {
                        val selected = SyntheticReceiptProcessingTransport.Scenario.values()[position]
                        if (processingController === controller && selected != processingScenario) {
                            processingScenario = selected
                            controller.selectInput()
                        }
                    }
                    override fun onNothingSelected(parent: AdapterView<*>?) = Unit
                }
            })
            add(space(12))
            val status: View = when (current) {
                ReceiptProcessingLifecycle.State.Idle -> ui.statePanel(
                    getString(R.string.processing_idle), getString(R.string.processing_idle_body), PantryBannerTone.INFO,
                )
                is ReceiptProcessingLifecycle.State.Ready -> ui.statePanel(
                    getString(R.string.processing_ready), getString(R.string.processing_ready_body), PantryBannerTone.INFO,
                )
                is ReceiptProcessingLifecycle.State.Pending -> ui.statePanel(
                    getString(R.string.processing_pending), getString(R.string.processing_pending_body), PantryBannerTone.INFO,
                )
                is ReceiptProcessingLifecycle.State.Finished -> when (val outcome = current.outcome) {
                    is ReceiptProcessingLifecycle.Outcome.Presentation -> presentationStatePanel(outcome.result)
                    ReceiptProcessingLifecycle.Outcome.LocalFailure.MISSING_RESPONSE -> ui.statePanel(
                        getString(R.string.processing_missing), getString(R.string.processing_missing_body), PantryBannerTone.INFO,
                    )
                    ReceiptProcessingLifecycle.Outcome.LocalFailure.TIMEOUT -> ui.statePanel(
                        getString(R.string.processing_timeout), getString(R.string.processing_timeout_body), PantryBannerTone.INFO,
                    )
                    else -> ui.statePanel(
                        getString(R.string.processing_execution_failure), getString(R.string.processing_execution_failure_body), PantryBannerTone.ERROR,
                    )
                }
            }
            add(status.apply {
                id = R.id.processing_status
                accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
                isFocusable = true
                isFocusableInTouchMode = true
            })
            add(space(12))
            if (current is ReceiptProcessingLifecycle.State.Pending) {
                add(SageReceiptScanView(this@MainActivity).apply { id = R.id.processing_progress })
                sticky(ui.actionButton(
                    getString(R.string.processing_cancel), PantryActionStyle.PRIMARY,
                    viewId = R.id.processing_cancel,
                ) { if (processingController === controller) controller.cancel() })
            } else {
                val ready = current is ReceiptProcessingLifecycle.State.Ready
                val start = ui.actionButton(
                    getString(R.string.processing_start), PantryActionStyle.PRIMARY,
                    enabled = ready, viewId = R.id.processing_start,
                ) { if (processingController === controller) controller.start() }
                if (ready) sticky(start) else add(start)
            }
            val newInput = ui.actionButton(
                getString(R.string.processing_new_input),
                if (current is ReceiptProcessingLifecycle.State.Pending || current is ReceiptProcessingLifecycle.State.Ready)
                    PantryActionStyle.SECONDARY else PantryActionStyle.PRIMARY,
                viewId = R.id.processing_new_input,
            ) { if (processingController === controller) controller.selectInput() }
            if (current is ReceiptProcessingLifecycle.State.Pending || current is ReceiptProcessingLifecycle.State.Ready) {
                add(newInput)
            } else {
                sticky(newInput)
            }
            if (current is ReceiptProcessingLifecycle.State.Finished) {
                val result = (current.outcome as? ReceiptProcessingLifecycle.Outcome.Presentation)?.result
                if (result is ReceiptPresentationUiResult.ProcessingFailed) {
                    add(bodyText(getString(R.string.processing_failure_stage, result.stage.name)))
                }
                if (result is ReceiptPresentationUiResult.Available) {
                    add(space(12))
                    add(sectionTitle(getString(R.string.processing_review_title)).apply { id = R.id.processing_receipt_heading })
                    if (ReceiptReviewAnnotationPolicy.requiresManualReviewAnnotation(result)) {
                        add(ui.banner(
                            getString(R.string.review_extraction_failed_title),
                            getString(R.string.review_extraction_failed_annotation),
                            PantryBannerTone.INFO,
                        ).apply { id = R.id.review_extraction_failed_annotation })
                    }
                    add(ui.card {
                        id = R.id.processing_receipt
                        val receipt = result.receipt
                        addView(summaryRow(getString(R.string.field_store_name), presentedText(receipt.storeName),
                            needsAttention = receipt.storeName.status != PresentedFieldStatus.EXTRACTED))
                        addView(summaryRow(getString(R.string.field_purchase_date), presentedDate(receipt.purchaseDate),
                            needsAttention = receipt.purchaseDate.status != PresentedFieldStatus.EXTRACTED))
                        addView(summaryRow(getString(R.string.field_receipt_total), presentedMoney(receipt.receiptTotal),
                            needsAttention = receipt.receiptTotal.status != PresentedFieldStatus.EXTRACTED))
                    })
                    result.receipt.items.forEachIndexed { index, item ->
                        add(space(10))
                        add(receiptItemCard(index + 1, item))
                    }
                }
            }
        }
        if (currentScreen != Screen.PROCESSING_DEMO || processingController !== controller) return
        val root = findViewById<View>(R.id.screen_processing_demo) ?: return
        root.tag = controller
        restoreProcessingFocus(root, inputId, inputInTouchMode, accessibilityId,
            R.id.processing_status, initialEntry = previousRoot == null)
    }

    private fun ensureSelectedImageProcessing(live: Boolean): SelectedImageProcessingController {
        selectedProcessingController?.let { return it }
        val handler = Handler(Looper.getMainLooper())
        val worker = Executors.newSingleThreadExecutor()
        selectedProcessingHandler = handler
        selectedProcessingWorker = worker
        val postWorker: (() -> Unit) -> Unit = { action -> enqueueProcessingWorker(worker, action) }
        val postUi: (() -> Unit) -> Unit = { action -> handler.post { action() } }
        val schedule: (Long, () -> Unit) -> Unit = { delay, action ->
            handler.postAtTime({ action() }, handler, SystemClock.uptimeMillis() + delay)
        }
        val processingScreen = if (live) Screen.T09_PROCESSING else Screen.SELECTED_PROCESSING
        val onChanged: () -> Unit = {
            if (currentScreen == processingScreen &&
                selectedProcessingHandler === handler && selectedProcessingController != null
            ) render()
        }
        // Capture exactly this URI and crop. No worker reads later Activity selection values.
        val uri = selectedImageUri
        val crop = selectedImageCrop ?: ReceiptCrop.FULL
        val fixture = if (live) null else SelectedImageProcessingController.claimFixture(
            owner = this,
            preview = uri.takeIf { selectedImageSource == LocalImageSource.GALLERY && crop == ReceiptCrop.FULL },
        )
        val controller = if (live) {
            boundLiveImage = uri?.let { imageUri ->
                selectedImageSource?.let { BoundLiveImage(imageUri, crop, it) }
            }
            val encoder = SelectedImageSnapshotEncoder(applicationContext.contentResolver)
            val prepared = PreparedReceiptImage()
            preparedLiveImage = prepared
            val transport = T09HttpTransport(
                session = checkNotNull(liveSession),
                nowMillis = SystemClock::elapsedRealtime,
                preparePng = prepared::uploadBytes,
                onPhase = { request, phase ->
                    handler.post {
                        val pending = selectedProcessingController?.state as? ReceiptProcessingLifecycle.State.Pending
                        if (currentScreen == processingScreen && selectedProcessingHandler === handler &&
                            pending?.request === request
                        ) {
                            livePhase = phase
                            render()
                        }
                    }
                },
            )
            SelectedImageProcessingController(
                transport = transport,
                postWorker = postWorker,
                postUi = postUi,
                schedule = schedule,
                nowMillis = SystemClock::elapsedRealtime,
                newImageId = { "selected-image-" + UUID.randomUUID() },
                newRequestId = { "selected-request-" + UUID.randomUUID() },
                onChanged = onChanged,
            ).also { it.selectLiveInput { uri != null && prepared.prepare(encoder, uri, crop) } }
        } else if (fixture != null) {
            SelectedImageProcessingController(fixture, postWorker, postUi, schedule, onChanged).also {
                it.prepareInput(fixture.preparedInput)
            }
        } else {
            val transport = BoundSyntheticReceiptProcessingTransport(
                scenario = { SyntheticReceiptProcessingTransport.Scenario.AVAILABLE },
                dispatchResponse = { action ->
                    handler.postDelayed({ enqueueProcessingWorker(worker, action) }, 500L)
                },
            )
            val encoder = SelectedImageSnapshotEncoder(applicationContext.contentResolver)
            SelectedImageProcessingController(
                transport = transport,
                postWorker = postWorker,
                postUi = postUi,
                schedule = schedule,
                nowMillis = { SystemClock.elapsedRealtime() },
                timeoutMillis = 10_000L,
                newImageId = { "selected-image-" + UUID.randomUUID() },
                newRequestId = { "selected-request-" + UUID.randomUUID() },
                maximumBytes = SelectedImageSnapshotEncoder.MAX_RETAINED_BYTES,
                onChanged = onChanged,
            ).also { it.prepareInput { encoder.encode(checkNotNull(uri), crop) } }
        }
        selectedProcessingController = controller
        return controller
    }

    internal fun resetSelectedImageFixture(binding: SelectedImageProcessingController.FixtureBinding) {
        check(Looper.myLooper() === Looper.getMainLooper())
        if (selectedProcessingController?.ownsFixture(binding) != true) return
        disposeSelectedImageProcessing()
        leaveFixtureProcessingScreen(
            renderNow = lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED) &&
                !isFinishing && !isDestroyed,
        )
    }

    private fun leaveFixtureProcessingScreen(renderNow: Boolean) {
        if (currentScreen != Screen.SELECTED_PROCESSING) return
        currentScreen = backStack.pollLast() ?: Screen.PREVIEW
        renderAfterFixtureTeardown = !renderNow
        if (renderNow) render()
    }

    private fun disposeSelectedImageProcessing() {
        liveReviewDraft?.discard()
        liveReviewDraft = null
        liveCollapsed.clear()
        boundLiveImage = null
        preparedLiveImage?.release()
        preparedLiveImage = null
        liveReviewConfirmation?.dismiss()
        liveReviewConfirmation = null
        val controller = selectedProcessingController
        val handler = selectedProcessingHandler
        val worker = selectedProcessingWorker
        selectedProcessingController = null
        selectedProcessingHandler = null
        selectedProcessingWorker = null
        try {
            controller?.dispose()
        } finally {
            liveSession = null
            // Remove only deadline callbacks. Queued preparation callbacks release stale snapshots.
            handler?.removeCallbacksAndMessages(handler)
            worker?.shutdown()
        }
    }

    private fun renderSelectedImageProcessing(live: Boolean = false) {
        val controller = ensureSelectedImageProcessing(live)
        val processingScreen = if (live) Screen.T09_PROCESSING else Screen.SELECTED_PROCESSING
        // Only the current controller's rendered tree may supply restoration intent.
        val previousRoot = findViewById<View>(R.id.screen_selected_processing)?.takeIf { it.tag === controller }
        val inputFocus = previousRoot?.let { processingFocusedView(it, accessibility = false) }
        val inputId = inputFocus?.id
        val inputInTouchMode = inputFocus?.isFocusableInTouchMode == true
        val accessibilityId = previousRoot?.let { processingFocusedView(it, accessibility = true) }?.id
        val current = controller.state
        liveReviewDraft?.takeIf { live && (current as? ReceiptProcessingLifecycle.State.Finished)?.request === it.request }
            ?.let { return renderLiveReceiptReview(it) }
        val input = controller.inputState
        val finished = current as? ReceiptProcessingLifecycle.State.Finished
        val result = (finished?.outcome as? ReceiptProcessingLifecycle.Outcome.Presentation)?.result
        if (live && (finished?.outcome as? ReceiptProcessingLifecycle.Outcome.HttpRefusal)?.status in setOf(401, 503) &&
            T09ProcessingConfig.current() === liveSession
        ) T09ProcessingConfig.clear()
        setScreen(getString(if (live) R.string.t09_processing_title else R.string.selected_processing_title), true) {
            if (live || current !is ReceiptProcessingLifecycle.State.Pending && result !is ReceiptPresentationUiResult.Available) {
                add(bodyText(getString(if (live) R.string.t09_processing_notice else R.string.v4_test_boundary)))
                add(space(6))
            }
            val panel = if (live) when (input) {
                SelectedImageProcessingController.InputState.PREPARING -> ui.statePanel(
                    "Preparing submitted frame", "Orienting, cropping and resizing the receipt.", PantryBannerTone.INFO,
                )
                SelectedImageProcessingController.InputState.ERROR -> ui.statePanel(
                    "Receipt image could not be prepared", "Go back and recrop or choose a smaller image.", PantryBannerTone.ERROR,
                )
                else -> liveProcessingPanel(current)
            } else when (input) {
                SelectedImageProcessingController.InputState.PREPARING -> ui.statePanel(
                    getString(R.string.selected_processing_preparing),
                    getString(R.string.selected_processing_limits), PantryBannerTone.INFO,
                )
                SelectedImageProcessingController.InputState.ERROR -> ui.statePanel(
                    getString(R.string.selected_processing_error),
                    getString(R.string.selected_processing_error_body), PantryBannerTone.ERROR,
                )
                else -> when (current) {
                    ReceiptProcessingLifecycle.State.Idle -> ui.statePanel(
                        getString(R.string.processing_idle), getString(R.string.selected_processing_error_body), PantryBannerTone.INFO,
                    )
                    is ReceiptProcessingLifecycle.State.Ready -> ui.statePanel(
                        getString(R.string.selected_processing_ready), getString(R.string.selected_processing_ready_body), PantryBannerTone.INFO,
                    )
                    is ReceiptProcessingLifecycle.State.Pending -> ui.statePanel(
                        getString(R.string.processing_pending), getString(R.string.selected_processing_fictional), PantryBannerTone.INFO,
                    )
                    is ReceiptProcessingLifecycle.State.Finished -> when (val outcome = current.outcome) {
                        is ReceiptProcessingLifecycle.Outcome.Presentation ->
                            if (outcome.result is ReceiptPresentationUiResult.Available) ui.statePanel(
                                getString(R.string.v4_test_success), getString(R.string.selected_processing_fictional),
                                PantryBannerTone.SUCCESS,
                            ) else presentationStatePanel(outcome.result)
                        ReceiptProcessingLifecycle.Outcome.LocalFailure.MISSING_RESPONSE -> ui.statePanel(
                            getString(R.string.processing_missing), getString(R.string.processing_missing_body), PantryBannerTone.INFO,
                        )
                        ReceiptProcessingLifecycle.Outcome.LocalFailure.TIMEOUT -> ui.statePanel(
                            getString(R.string.processing_timeout), getString(R.string.processing_timeout_body), PantryBannerTone.INFO,
                        )
                        else -> ui.statePanel(
                            getString(R.string.processing_execution_failure), getString(R.string.processing_execution_failure_body), PantryBannerTone.ERROR,
                        )
                    }
                }
            }
            add(panel.apply {
                id = R.id.selected_processing_status
                accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
                isFocusable = true
                isFocusableInTouchMode = true
            })
            add(space(6))
            add(bodyText(getString(if (selectedImageCrop == null) {
                R.string.selected_processing_full
            } else R.string.selected_processing_cropped)).apply {
                textSize = 12f
                setTextColor(ui.color(R.color.pantry_on_surface))
            })
            add(space(8))
            if (input == SelectedImageProcessingController.InputState.PREPARING || current is ReceiptProcessingLifecycle.State.Pending) {
                add(SageReceiptScanView(this@MainActivity).apply { id = R.id.selected_processing_progress })
            }
            if (current is ReceiptProcessingLifecycle.State.Pending) {
                sticky(ui.actionButton(
                    getString(R.string.processing_cancel), PantryActionStyle.PRIMARY,
                    viewId = R.id.selected_processing_cancel,
                ) {
                    if (selectedProcessingController === controller) {
                        if (live) liveCancelled = true
                        controller.cancel()
                    }
                })
            } else {
                val refusal = finished?.outcome as? ReceiptProcessingLifecycle.Outcome.HttpRefusal
                val canRetry = live && finished != null && result !is ReceiptPresentationUiResult.Available &&
                    refusal?.status !in setOf(401, 406, 503) &&
                    (result as? ReceiptPresentationUiResult.ProcessingFailed)?.retryable != false
                val canStart = controller.canStart || canRetry
                val start = ui.actionButton(
                    getString(if (live) R.string.t09_processing_start else R.string.selected_processing_start),
                    PantryActionStyle.PRIMARY,
                    enabled = canStart, viewId = R.id.selected_processing_start,
                ) {
                    if (selectedProcessingController === controller) {
                        if (live) {
                            livePhase = T09HttpTransport.Phase.PREPARING
                            liveCancelled = false
                            if (canRetry) controller.allowExplicitRetry()
                        }
                        controller.start()
                    }
                }
                if (canStart) sticky(start) else add(start)
            }
            if (live && current is ReceiptProcessingLifecycle.State.Ready) {
                preparedLiveImage?.bitmap?.let { bitmap ->
                    add(bodyText("Exact image to submit"))
                    add(submittedImageView(bitmap))
                }
            }
            if (!live) {
                val recover = (input == SelectedImageProcessingController.InputState.ERROR ||
                    current is ReceiptProcessingLifecycle.State.Finished || current is ReceiptProcessingLifecycle.State.Ready) &&
                    !controller.canStart
                val prepare = ui.actionButton(
                    getString(R.string.selected_processing_prepare_again),
                    if (recover) PantryActionStyle.PRIMARY else PantryActionStyle.SECONDARY,
                    viewId = R.id.selected_processing_prepare_again,
                ) {
                    if (selectedProcessingController === controller) {
                        disposeSelectedImageProcessing()
                        render()
                    }
                }
                if (recover) sticky(prepare) else add(prepare)
            }
            if (result is ReceiptPresentationUiResult.Available) {
                add(sectionTitle(getString(if (live) R.string.processing_review_title else R.string.v4_test_result)))
                if (ReceiptReviewAnnotationPolicy.requiresManualReviewAnnotation(result)) {
                    add(ui.banner(
                        getString(R.string.review_extraction_failed_title),
                        getString(R.string.review_extraction_failed_annotation), PantryBannerTone.INFO,
                    ))
                }
                if (live && result.liveEvidence != null) {
                    add(ui.progressHeader(2, getString(R.string.sage_step_details)))
                    add(space(8))
                    sticky(ui.actionButton(getString(R.string.live_review_action), PantryActionStyle.PRIMARY) {
                        if (currentScreen == Screen.T09_PROCESSING &&
                            selectedProcessingController === controller && controller.state === finished &&
                            liveReviewDraft == null
                        ) {
                            liveReviewDraft = LiveReceiptReviewDraft.from(finished)?.also { it.keepOriginal = keepOriginal }
                            if (liveReviewDraft != null) render()
                        }
                    })
                }
                if (live) finished?.request?.let(::liveReceiptImage)?.let { add(it); add(space(8)) }
                add(receiptSummary(result.receipt))
                add(space(8))
                add(ui.card {
                    result.receipt.items.forEachIndexed { index, item ->
                        if (index > 0) addView(divider())
                        addView(receiptItemCard(index + 1, item))
                    }
                })
            }
        }
        if (currentScreen != processingScreen || selectedProcessingController !== controller) return
        val root = findViewById<View>(R.id.screen_selected_processing) ?: return
        root.tag = controller
        restoreProcessingFocus(root, inputId, inputInTouchMode, accessibilityId,
            R.id.selected_processing_status, initialEntry = previousRoot == null)
    }

    private fun renderLiveReceiptReview(draft: LiveReceiptReviewDraft) =
        setScreen(getString(R.string.live_review_title), true, formWidth = true) {
            val review = requireNotNull(draft.wrapper?.review)
            add(ui.progressHeader(3, getString(R.string.sage_step_review)))
            if (review.readiness == ReviewReadiness.NOT_READY) {
                add(ui.banner("Unverified draft", "Approve each value you use. Automated verification is unavailable.",
                    PantryBannerTone.INFO))
            }
            liveReceiptImage(draft.request)?.let { add(it) }
            add(space(8))
            val sections = SageExpandableSections(this@MainActivity, ui, liveCollapsed)
            add(sectionBar("Receipt fields", sections.allAction()))
            val receiptFields = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                draft.receiptFields.forEach { addView(reviewFieldRow(draft, it)) }
            }
            add(sections.add("receipt", "Store, date and total", receiptFields, subtitle = draft.storeName.displayed))
            add(space(8))
            val included = bodyText("").apply { accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE }
            fun updateCounts() {
                val count = draft.items.count { it.selected }
                included.text = "$count included · ${draft.items.size - count} excluded from inventory"
            }
            updateCounts()
            add(included)
            draft.items.forEachIndexed { index, item ->
                val itemFields = LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.VERTICAL
                    addView(CheckBox(this@MainActivity).apply {
                        text = "Include in inventory"
                        contentDescription = "Include item ${index + 1} in inventory"
                        minHeight = dp(48)
                        isChecked = item.selected
                        setOnCheckedChangeListener { _, checked -> item.selected = checked; updateCounts() }
                    })
                    addView(inventoryUnitChoice(item.inventoryUnit) { item.inventoryUnit = it })
                    item.allFields.forEach { addView(reviewFieldRow(draft, it)) }
                    review.pantryMappings.firstOrNull { it.rowId == item.rowId }?.selection?.let { mapping ->
                        if (item.description.displayed == item.description.backend?.selected?.canonical &&
                            item.description.reviewState != LiveReceiptReviewDraft.UserReviewState.USER_MODIFIED
                        ) {
                            addView(bodyText("Pantry terminology suggestion · ${mapping.identity}" +
                                (mapping.referenceUnit?.let { " · Reference unit $it" } ?: "")))
                        }
                    }
                }
                add(sections.add(item.rowId, "Item ${index + 1}", itemFields, subtitle = item.description.displayed))
                add(space(8))
            }
            add(CheckBox(this@MainActivity).apply {
                text = "A purchased item is missing from this review"
                isChecked = draft.omittedPurchasedRow
                minHeight = dp(48)
                setOnCheckedChangeListener { _, checked -> draft.omittedPurchasedRow = checked }
            })
            add(ui.actionButton("Review values for bulk acceptance", PantryActionStyle.SECONDARY) { showBulkOffer(draft) })
            sticky(ui.actionButton("Choose confirmation mode", PantryActionStyle.PRIMARY) { chooseReceiptConfirmation(draft) })
        }

    private fun reviewRoleLabel(role: ReceiptFieldRole): String = getString(when (role) {
        ReceiptFieldRole.STORE_NAME -> R.string.field_store_name
        ReceiptFieldRole.PURCHASE_DATE -> R.string.field_purchase_date
        ReceiptFieldRole.RECEIPT_TOTAL -> R.string.field_receipt_total
        ReceiptFieldRole.ITEM_DESCRIPTION -> R.string.field_description
        ReceiptFieldRole.QUANTITY -> R.string.field_quantity
        ReceiptFieldRole.UNIT_PRICE -> R.string.field_unit_price
        ReceiptFieldRole.LINE_TOTAL -> R.string.field_line_total
    })

    private fun reviewFieldRow(draft: LiveReceiptReviewDraft, field: LiveReceiptReviewDraft.Field): View {
        val backend = requireNotNull(field.backend)
        val status = when (field.reviewState) {
            LiveReceiptReviewDraft.UserReviewState.UNREVIEWED -> when (backend.disposition.name) {
                "AUTO_ACCEPTED" -> "Policy accepted"
                "REVIEW_REQUIRED" -> "Review required"
                else -> "Unverified"
            }
            LiveReceiptReviewDraft.UserReviewState.USER_CONFIRMED -> "You approved"
            LiveReceiptReviewDraft.UserReviewState.USER_MODIFIED -> "You edited"
            LiveReceiptReviewDraft.UserReviewState.USER_REJECTED -> "You rejected"
            LiveReceiptReviewDraft.UserReviewState.UNRESOLVED -> "Left unresolved"
        }
        val value = field.displayed?.let { current ->
            when (backend.role) {
                ReceiptFieldRole.UNIT_PRICE, ReceiptFieldRole.LINE_TOTAL, ReceiptFieldRole.RECEIPT_TOTAL -> "RM\u00A0$current"
                else -> current
            }
        } ?: if (field.legitimateAbsence() != null) "No unit price printed" else "No approved value"
        val conflict = if (backend.price.status == "PRICE_CONFLICT") " · Price conflict" else ""
        return ui.actionRow(reviewRoleLabel(backend.role), "$value · $status$conflict",
            resource = null, chevron = ui.icon(R.drawable.ic_sage_right), action = { showFieldEvidence(draft, field) })
    }

    private fun preserveReviewScroll() {
        val position = screenScrollView?.scrollY ?: 0
        render()
        screenScrollView?.let { it.post { it.scrollTo(0, position) } }
    }

    private fun showFieldEvidence(draft: LiveReceiptReviewDraft, field: LiveReceiptReviewDraft.Field) {
        val backend = requireNotNull(field.backend)
        val today = state.currentLocalDate()
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(8), dp(20), dp(8))
        }
        val dialog = AlertDialog.Builder(this).setTitle(reviewRoleLabel(backend.role))
            .setView(ScrollView(this).apply { addView(content) })
            .setNegativeButton(android.R.string.cancel, null).create()
        fun text(value: String) { content.addView(bodyText(value)) }
        fun action(label: String, block: () -> Unit) {
            content.addView(ui.actionButton(label, PantryActionStyle.SECONDARY) {
                if (liveReviewDraft !== draft) return@actionButton
                dialog.dismiss()
                block()
            })
        }
        fun candidate(label: String, source: LiveReceiptReviewDraft.CandidateSource, candidateId: String, raw: String?) {
            text("$label · ${raw ?: "Missing"}")
            val offer = field.offer(source, candidateId, today)
            if (offer != null) action("Accept $label") {
                if (field.accept(offer, state.currentLocalDate())) preserveReviewScroll()
            }
        }
        candidate("Selected pre-review value", LiveReceiptReviewDraft.CandidateSource.SELECTED_PRE_REVIEW,
            backend.selected.id, backend.selected.raw)
        candidate("Original B2 value", LiveReceiptReviewDraft.CandidateSource.ORIGINAL_B2_C0,
            backend.original.value.id, backend.original.value.raw)
        backend.recommendation?.let {
            val recommendation = (listOf(backend.original.value) + backend.alternatives.map { item -> item.value })
                .first { item -> item.id == it.candidateId }
            text("Development recommendation · ${it.recommendation} · ${recommendation.raw ?: "Missing"} · ${it.reason}")
        }
        text("Backend decision · ${backend.disposition.name}")
        text("Calibrated probability · ${backend.probability?.toPlainString() ?: "Unavailable · ${backend.probabilityUnavailableReason}"}")
        text("Correction reason · ${backend.correctionReason}")
        if (backend.suspicionReasons.isNotEmpty()) text("Review cues · ${backend.suspicionReasons.joinToString()}")
        if (backend.conflict == true) text("Backend recorded an unresolved conflict.")
        text("Retailer evidence · ${backend.retailer.status} · ${backend.retailer.reason}")
        backend.retailer.refs.forEach { text("${it.entryId} · ${it.resource}") }
        text(priceEvidenceLabel(backend.price))
        addFieldSource(content, draft, backend.selected.tokenIds, "Selected OCR evidence")
        if (backend.original.value.tokenIds != backend.selected.tokenIds) {
            addFieldSource(content, draft, backend.original.value.tokenIds, "Original B2 OCR evidence")
        }
        backend.alternatives.forEachIndexed { index, alternative ->
            content.addView(divider())
            candidate("Alternative ${index + 1}", LiveReceiptReviewDraft.CandidateSource.ALTERNATIVE,
                alternative.value.id, alternative.value.raw)
            text("${alternative.status} · Calibrated probability ${alternative.probability?.toPlainString() ?: "unavailable"}")
            if (alternative.constraints.isNotEmpty()) text(alternative.constraints.joinToString())
            if (alternative.replacementSupport.isNotEmpty()) text(alternative.replacementSupport.joinToString())
            text("Retailer evidence · ${alternative.retailer.status} · ${alternative.retailer.reason}")
            text(priceEvidenceLabel(alternative.price))
            alternative.references.forEach { ref ->
                ref.observed?.let { text("Observed · $it") }
                ref.spans.forEach { text("OCR span · ${it.text}") }
            }
            addFieldSource(content, draft, alternative.value.tokenIds, "Alternative OCR evidence")
        }
        content.addView(divider())
        action("Edit value") { editLiveReviewField(field) }
        if (backend.role == ReceiptFieldRole.UNIT_PRICE) {
            action("I checked that no unit price was printed") { field.markPriceNotPrinted(); preserveReviewScroll() }
        }
        action("Reject this field") { field.reject(); preserveReviewScroll() }
        action("Leave unresolved") { field.leaveUnresolved(); preserveReviewScroll() }
        dialog.show()
    }

    private fun priceEvidenceLabel(price: com.pantryproof.prototype.contract.review.PriceEvidence): String =
        listOfNotNull("Price evidence · ${price.status} · ${price.reason}",
            price.observed?.let { "Observed RM $it" }, price.basis?.let { "Comparison basis $it" },
            price.low?.let { "Reference band RM $it–${price.high}" }).joinToString(" · ")

    private fun submittedImageView(bitmap: Bitmap) = android.widget.ImageView(this).apply {
        setImageBitmap(bitmap)
        adjustViewBounds = true
        scaleType = android.widget.ImageView.ScaleType.FIT_CENTER
        maxHeight = dp(340)
        contentDescription = "Submitted receipt image"
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
    }

    private fun addFieldSource(content: LinearLayout, draft: LiveReceiptReviewDraft, ids: List<String>, label: String) {
        val ocr = draft.wrapper?.review?.ocr ?: return
        val indexed = ocr.tokens.associateBy { it.id }
        val tokens = ids.mapNotNull(indexed::get)
        if (tokens.isEmpty()) return
        content.addView(bodyText("$label · ${tokens.joinToString(" ") { it.text }}"))
        val bitmap = preparedLiveImage?.bitmap
        val current = selectedProcessingController?.state as? ReceiptProcessingLifecycle.State.Finished
        if (current?.request !== draft.request || bitmap == null || bitmap.width != ocr.width || bitmap.height != ocr.height) {
            content.addView(bodyText("Submitted image unavailable. The OCR text is shown above."))
            return
        }
        content.addView(ui.actionButton("View source region", PantryActionStyle.TERTIARY) {
            if (liveReviewDraft !== draft) return@actionButton
            val points = tokens.flatMap { it.polygon }
            val left = (kotlin.math.floor(points.minOf { it.x }.toDouble()).toInt() - 8).coerceIn(0, bitmap.width - 1)
            val top = (kotlin.math.floor(points.minOf { it.y }.toDouble()).toInt() - 8).coerceIn(0, bitmap.height - 1)
            val right = (kotlin.math.ceil(points.maxOf { it.x }.toDouble()).toInt() + 8).coerceIn(left + 1, bitmap.width)
            val bottom = (kotlin.math.ceil(points.maxOf { it.y }.toDouble()).toInt() + 8).coerceIn(top + 1, bitmap.height)
            val crop = Bitmap.createBitmap(bitmap, left, top, right - left, bottom - top)
            showReceiptImageDialog(R.string.submitted_source_region, submittedImageView(crop))
        })
    }

    private fun editLiveReviewField(field: LiveReceiptReviewDraft.Field) {
        val role = requireNotNull(field.backend).role
        val control = EditText(this).apply {
            isSaveEnabled = false
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
            imeOptions = EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING
            setSingleLine()
            setText(field.displayed ?: field.backend.selected.canonical.orEmpty())
            if (role in setOf(ReceiptFieldRole.QUANTITY, ReceiptFieldRole.UNIT_PRICE, ReceiptFieldRole.LINE_TOTAL, ReceiptFieldRole.RECEIPT_TOTAL)) {
                inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            }
            if (role == ReceiptFieldRole.PURCHASE_DATE) hint = "YYYY-MM-DD"
        }
        val dialog = AlertDialog.Builder(this).setTitle("Edit ${reviewRoleLabel(role).lowercase(Locale.ROOT)}")
            .setView(control).setPositiveButton("Apply edit", null).setNegativeButton(android.R.string.cancel, null).show()
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            if (!field.edit(control.text.toString(), state.currentLocalDate())) {
                control.error = when (role) {
                    ReceiptFieldRole.PURCHASE_DATE -> "Enter a valid purchase date in YYYY-MM-DD."
                    ReceiptFieldRole.QUANTITY -> "Enter a positive decimal with up to three fractional places."
                    ReceiptFieldRole.STORE_NAME, ReceiptFieldRole.ITEM_DESCRIPTION -> "Enter a value."
                    else -> "Enter an MYR amount with two decimal places."
                }
                return@setOnClickListener
            }
            dialog.dismiss()
            preserveReviewScroll()
        }
    }

    private fun showBulkOffer(draft: LiveReceiptReviewDraft) {
        val shown = draft.bulkOffer(state.currentLocalDate())
        val fields = draft.allFields.associateBy { it.original.id }
        val explanation = if (shown.offers.isEmpty()) "There are no displayed values eligible for bulk acceptance."
        else shown.offers.joinToString("\n") { offer ->
            val field = requireNotNull(fields.getValue(offer.fieldId).backend)
            val row = field.rowId?.let { id -> "Item ${draft.items.indexOfFirst { it.rowId == id } + 1} · " }.orEmpty()
            "$row${reviewRoleLabel(field.role)} · ${offer.value} · Selected pre-review"
        }
        AlertDialog.Builder(this).setTitle("Approve displayed values").setMessage(explanation)
            .setNegativeButton(android.R.string.cancel, null).apply {
                if (shown.offers.isNotEmpty()) setPositiveButton("Approve listed values") { _, _ ->
                    if (liveReviewDraft === draft && draft.acceptBulk(shown, state.currentLocalDate())) preserveReviewScroll()
                    else showReviewMessage("The draft changed. Review the updated list.")
                }
            }.show()
    }

    private fun chooseReceiptConfirmation(draft: LiveReceiptReviewDraft) {
        val count = draft.items.count { it.selected }
        AlertDialog.Builder(this).setTitle("Choose confirmation mode")
            .setMessage("$count included · ${draft.items.size - count} excluded from inventory")
            .setNegativeButton(android.R.string.cancel, null)
            .setNeutralButton("Inventory only") { _, _ -> showFinalConfirmation(draft, ReceiptConfirmationMode.INVENTORY_ONLY) }
            .setPositiveButton("Inventory and receipt") { _, _ -> showFinalConfirmation(draft, ReceiptConfirmationMode.INVENTORY_AND_RECEIPT) }
            .show()
    }

    private fun showFinalConfirmation(draft: LiveReceiptReviewDraft, mode: ReceiptConfirmationMode) {
        if (liveReviewDraft !== draft || liveReviewConfirmation != null) return
        val selection = draft.confirmation(mode, state.currentLocalDate(), acknowledged = false)
        if (selection is LiveReceiptReviewDraft.ConfirmationCheck.Blocked) return showReviewMessage(selection.explanation)
        val check = selection as LiveReceiptReviewDraft.ConfirmationCheck.Ready
        val plan = check.confirmation
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), 0, dp(20), 0)
            addView(bodyText("${plan.stock.size} included · ${plan.decisions.size - plan.stock.size} excluded from inventory"))
            plan.stock.forEach { addView(bodyText("${it.name} · ${it.quantityLabel}")) }
            draft.items.forEachIndexed { index, item ->
                if (!plan.decisions[index].second) {
                    val name = item.description.displayed ?: getString(R.string.review_item_number, index + 1)
                    addView(bodyText(getString(R.string.confirmation_item_excluded, name)))
                }
            }
            plan.history?.let { addView(bodyText("${purchaseCount(it)} · RM ${it.total.toPlainString()}"))
                addView(bodyText(if (plan.keepOriginal) "Save image to receipt history" else "Save receipt details only")) }
        }
        val acknowledgement = if (check.needsIncompleteAcknowledgement) CheckBox(this).apply {
            text = "I understand the purchase information is incomplete."
            minHeight = dp(48)
            content.addView(this)
        } else null
        val dialog = AlertDialog.Builder(this)
            .setTitle(if (plan.history == null) "Confirm inventory only" else "Confirm inventory and save receipt")
            .setView(ScrollView(this).apply { addView(content) })
            .setNegativeButton(R.string.review_keep_editing, null)
            .setPositiveButton("Confirm", null)
            .create()
        liveReviewConfirmation = dialog
        dialog.setOnDismissListener { if (liveReviewConfirmation === dialog) liveReviewConfirmation = null }
        dialog.show()
        val confirm = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
        confirm.isEnabled = acknowledgement == null
        acknowledgement?.setOnCheckedChangeListener { _, checked -> confirm.isEnabled = checked }
        confirm.setOnClickListener {
            val current = selectedProcessingController?.state as? ReceiptProcessingLifecycle.State.Finished
            if (liveReviewDraft !== draft || current?.request !== draft.request || receiptCommitInProgress) return@setOnClickListener
            val approved = plan.copy(incompleteAcknowledged = acknowledgement?.isChecked == true)
            val original = if (approved.keepOriginal) preparedLiveImage?.originalBytes() else null
            dialog.dismiss()
            if (approved.keepOriginal && original == null) return@setOnClickListener showReviewMessage("The original image is unavailable. Review the retention choice or scan again.")
            val worker = selectedProcessingWorker ?: return@setOnClickListener
            receiptCommitInProgress = true
            val saving = AlertDialog.Builder(this).setTitle("Saving confirmation")
                .setMessage("Saving the approved items on this device.")
                .setCancelable(false).show()
            liveReviewConfirmation = saving
            enqueueProcessingWorker(worker) {
                val outcome = try { state.commitReview(draft, approved, original) } finally { original?.fill(0) }
                runOnUiThread {
                    receiptCommitInProgress = false
                    if (liveReviewConfirmation === saving) liveReviewConfirmation = null
                    saving.dismiss()
                    if (isDestroyed || isFinishing) return@runOnUiThread
                    when (outcome) {
                        ManualInventoryStore.Commit.COMMITTED, ManualInventoryStore.Commit.REPLAYED -> {
                            state.refreshDurableInventory()
                            if (liveReviewDraft === draft && lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
                                pendingInventorySuccess = receiptSuccess(approved.stock.map { it.id })
                                returnToInventory()
                                state.acknowledgeConfirmations(setOf(approved.identity))
                            } else {
                                pendingReceiptAcknowledgements = state.recoverConfirmations().orEmpty()
                                if (currentScreen == Screen.INVENTORY) render()
                            }
                        }
                        ManualInventoryStore.Commit.FAILED -> if (liveReviewDraft === draft) {
                            showReviewMessage("The confirmation could not be saved. Try again.")
                        }
                        ManualInventoryStore.Commit.CONFLICT -> if (liveReviewDraft === draft) {
                            showReviewMessage("The confirmation changed or was already used. Review the current values.")
                        }
                    }
                }
            }
        }
    }

    private fun showReviewMessage(message: String) {
        AlertDialog.Builder(this).setTitle("Receipt review").setMessage(message)
            .setPositiveButton(android.R.string.ok, null).show()
    }

    private fun liveProcessingPanel(current: ReceiptProcessingLifecycle.State): View {
        if (current is ReceiptProcessingLifecycle.State.Finished) {
            return when (val outcome = current.outcome) {
                is ReceiptProcessingLifecycle.Outcome.Presentation ->
                    if (outcome.result is ReceiptPresentationUiResult.Available) {
                        ui.statePanel(
                            getString(R.string.t09_processing_success), getString(R.string.t09_processing_read_only),
                            PantryBannerTone.SUCCESS,
                        )
                    } else presentationStatePanel(outcome.result, live = true)
                is ReceiptProcessingLifecycle.Outcome.HttpRefusal -> httpRefusalPanel(outcome.status)
                ReceiptProcessingLifecycle.Outcome.LocalFailure.PROTOCOL_FAILURE -> ui.statePanel(
                    "Invalid backend response", "Confirm the backend build supports receipt-review v1 before retrying.",
                    PantryBannerTone.ERROR,
                )
                ReceiptProcessingLifecycle.Outcome.LocalFailure.IMAGE_LIMIT -> ui.statePanel(
                    "Image cannot be sent", "Go back and recrop or choose a smaller receipt image.", PantryBannerTone.ERROR,
                )
                ReceiptProcessingLifecycle.Outcome.LocalFailure.TIMEOUT -> ui.statePanel(
                    getString(R.string.t09_processing_timeout), getString(R.string.t09_processing_recovery),
                    PantryBannerTone.INFO,
                )
                else -> ui.statePanel(
                    getString(R.string.t09_processing_failure), getString(R.string.t09_processing_recovery),
                    PantryBannerTone.ERROR,
                )
            }
        }
        val title = if (current is ReceiptProcessingLifecycle.State.Pending) {
            when (livePhase) {
                T09HttpTransport.Phase.PREPARING -> R.string.selected_processing_preparing
                T09HttpTransport.Phase.UPLOADING -> R.string.t09_processing_uploading
                T09HttpTransport.Phase.WAITING_FOR_RESULT -> R.string.t09_processing_waiting
            }
        } else if (liveCancelled) R.string.t09_processing_cancelled else R.string.t09_processing_ready
        val body = when {
            current is ReceiptProcessingLifecycle.State.Pending -> R.string.t09_processing_can_cancel
            liveCancelled -> R.string.t09_processing_cancelled_body
            else -> R.string.t09_processing_ready_body
        }
        return ui.statePanel(getString(title), getString(body), PantryBannerTone.INFO)
    }

    private fun httpRefusalPanel(status: Int): View {
        val message = when (status) {
            400 -> "The backend refused this request. Go back, reopen the submitted frame and try again."
            401 -> "The session credential was refused. Open Development Tools and enter the current approved credential."
            406 -> "This backend does not offer receipt-review v1. Ask the operator to verify the approved backend build."
            413 -> "The image is too large. Go back and crop it more tightly."
            415 -> "The backend refused the image format. Try importing or capturing a fresh image."
            422 -> "The backend could not read the submitted image. Recrop, replace it, or enter the receipt manually."
            429 -> "The backend is busy and may still be releasing the prior attempt. Wait, then tap Process to retry."
            500 -> "The backend failed to produce a result. Retry once it is ready, or enter the receipt manually."
            503 -> "The backend is unavailable. Ask the operator to confirm cleanup and session authorization, then configure the fresh credential."
            504 -> "The backend reached its time limit. Wait for cleanup before making a new explicit attempt."
            else -> "Go back and check the approved local backend."
        }
        return ui.statePanel("Receipt processing · HTTP $status", message, PantryBannerTone.INFO)
    }

    private fun showReceiptSources() {
        if (inventorySheet?.isShowing == true) return
        inventoryScrollY = screenScrollView?.scrollY ?: 0
        val content = LinearLayout(this).apply {
            id = R.id.screen_add_receipt
            orientation = LinearLayout.VERTICAL
            val takePhoto = ui.sourceCard(
                getString(R.string.sage_take_photo), getString(R.string.sage_camera_source),
                R.drawable.ic_sage_camera, R.id.add_capture_image,
            ) {
                inventorySheet?.dismiss()
                launchCameraCapture()
            }
            val importImage = ui.sourceCard(
                getString(R.string.sage_import_image), getString(R.string.sage_gallery_source),
                R.drawable.ic_sage_image, R.id.add_import_image,
            ) {
                inventorySheet?.dismiss()
                launchImagePicker()
            }
            addView(LinearLayout(this@MainActivity).apply {
                val stacked = ui.stacked()
                orientation = if (stacked) LinearLayout.VERTICAL else LinearLayout.HORIZONTAL
                listOf(takePhoto, importImage).forEachIndexed { index, card ->
                    addView(card, if (stacked) {
                        LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                            .apply { if (index > 0) topMargin = dp(8) }
                    } else {
                        LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
                            .apply { if (index > 0) marginStart = dp(8) }
                    })
                }
            })
            add(space(8))
            add(ui.actionButton(getString(R.string.manual_start_action), PantryActionStyle.SECONDARY,
                viewId = R.id.manual_without_image) {
                inventorySheet?.dismiss()
                switchToSyntheticDemo()
                startManualReceipt()
            })
            add(space(8))
            add(ui.banner(getString(R.string.add_receipt_privacy_title),
                getString(R.string.add_receipt_privacy_body), PantryBannerTone.INFO))
            if (developmentAvailable) {
                add(ui.actionButton(getString(R.string.add_receipt_demo), PantryActionStyle.TERTIARY,
                    viewId = R.id.add_use_demo, iconResource = R.drawable.ic_sage_flask) {
                    inventorySheet?.dismiss()
                    switchToSyntheticDemo()
                    navigate(Screen.PREVIEW)
                })
            }
        }
        showInventorySheet(getString(R.string.add_receipt_title), content)
    }

    private fun launchImagePicker() {
        val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Intent(MediaStore.ACTION_PICK_IMAGES).apply {
                type = "image/*"
            }
        } else {
            Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                type = "image/*"
                addCategory(Intent.CATEGORY_OPENABLE)
                addFlags(
                    Intent.FLAG_GRANT_READ_URI_PERMISSION or
                        Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION,
                )
            }
        }
        imagePicker.launch(intent)
    }

    private fun launchCameraCapture() {
        imageInputNotice = null
        pendingCaptureFileName?.let(captureStore::delete)
        pendingCaptureUri = null
        pendingCaptureFileName = null
        val target = runCatching { captureStore.createTarget() }.getOrElse {
            imageInputNotice = ImageInputNotice.CAMERA_UNAVAILABLE
            render()
            return
        }
        pendingCaptureUri = target.uri
        pendingCaptureFileName = target.fileName
        try {
            cameraCapture.launch(target.uri)
        } catch (_: ActivityNotFoundException) {
            handleCameraLaunchFailure()
        } catch (_: SecurityException) {
            handleCameraLaunchFailure()
        }
    }

    private fun handleCameraLaunchFailure() {
        captureStore.delete(pendingCaptureFileName)
        pendingCaptureUri = null
        pendingCaptureFileName = null
        imageInputNotice = ImageInputNotice.CAMERA_UNAVAILABLE
        render()
    }

    private fun replaceSelectedImage(
        uri: Uri,
        source: LocalImageSource,
        captureFileName: String?,
    ) {
        disposeSelectedImageProcessing()
        releaseSelectedGalleryPermission(replacementUri = uri)
        if (selectedImageUri != uri || selectedImageSource != source) {
            manualDraft = null
            selectedImageCrop = null
        }
        ownsSelectedGalleryReadGrant = false
        if (selectedCaptureFileName != captureFileName) {
            captureStore.delete(selectedCaptureFileName)
        }
        selectedImageUri = uri
        selectedImageSource = source
        selectedCaptureFileName = captureFileName
        imageInputNotice = null
    }

    private fun switchToSyntheticDemo() {
        disposeSelectedImageProcessing()
        releaseSelectedGalleryPermission(replacementUri = null)
        manualDraft = null
        ownsSelectedGalleryReadGrant = false
        captureStore.delete(selectedCaptureFileName)
        captureStore.delete(pendingCaptureFileName)
        selectedImageUri = null
        selectedImageCrop = null
        selectedImageSource = null
        selectedCaptureFileName = null
        pendingCaptureUri = null
        pendingCaptureFileName = null
        imageInputNotice = null
    }

    private fun persistGalleryReadPermission(uri: Uri, resultFlags: Int): Boolean {
        val alreadyOwnsGrant = uri == selectedImageUri && ownsSelectedGalleryReadGrant
        val canPersistRead =
            resultFlags and Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION != 0 &&
                resultFlags and Intent.FLAG_GRANT_READ_URI_PERMISSION != 0
        if (!canPersistRead) return alreadyOwnsGrant
        return runCatching {
            if (contentResolver.persistedUriPermissions.any { it.uri == uri && it.isReadPermission }) {
                return@runCatching alreadyOwnsGrant
            }
            contentResolver.takePersistableUriPermission(
                uri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION,
            )
            true
        }.getOrDefault(alreadyOwnsGrant)
    }

    private fun releaseSelectedGalleryPermission(replacementUri: Uri?) {
        val activeUri = selectedImageUri ?: return
        if (!ownsSelectedGalleryReadGrant || selectedImageSource != LocalImageSource.GALLERY ||
            activeUri == replacementUri
        ) return
        runCatching {
            contentResolver.releasePersistableUriPermission(
                activeUri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION,
            )
        }
    }

    private fun restoreCaptureFiles() {
        captureStore.cleanupOrphans(
            setOfNotNull(selectedCaptureFileName, pendingCaptureFileName),
        )
        if (selectedImageSource == LocalImageSource.CAMERA) {
            val expectedUri = captureStore.uriFor(selectedCaptureFileName)
            if (expectedUri == null || expectedUri != selectedImageUri ||
                !canReadSelectedImage(expectedUri)
            ) {
                captureStore.delete(selectedCaptureFileName)
                selectedImageUri = null
                selectedImageCrop = null
                selectedCaptureFileName = null
                imageInputNotice = ImageInputNotice.CAMERA_INVALID
            }
        } else if (selectedCaptureFileName != null) {
            captureStore.delete(selectedCaptureFileName)
            selectedCaptureFileName = null
        }

        if (pendingCaptureFileName != null) {
            val expectedPendingUri = captureStore.uriFor(pendingCaptureFileName)
            if (expectedPendingUri == null || expectedPendingUri != pendingCaptureUri) {
                captureStore.delete(pendingCaptureFileName)
                pendingCaptureUri = null
                pendingCaptureFileName = null
            }
        } else {
            pendingCaptureUri = null
        }
    }

    private fun imageInputNoticePanel(notice: ImageInputNotice): View =
        when (notice) {
            ImageInputNotice.CAMERA_UNAVAILABLE -> ui.statePanel(
                getString(R.string.camera_capture_unavailable_title),
                getString(R.string.camera_capture_unavailable_body),
                PantryBannerTone.ERROR,
            )
            ImageInputNotice.CAMERA_CANCELLED -> ui.statePanel(
                getString(R.string.camera_capture_cancelled_title),
                getString(R.string.camera_capture_cancelled_body),
                PantryBannerTone.INFO,
            )
            ImageInputNotice.CAMERA_INVALID -> ui.statePanel(
                getString(R.string.camera_capture_invalid_title),
                getString(R.string.camera_capture_invalid_body),
                PantryBannerTone.ERROR,
            )
            ImageInputNotice.IMAGE_UNAVAILABLE -> ui.statePanel(
                getString(R.string.preview_image_unavailable_title),
                getString(R.string.preview_image_unavailable_body),
                PantryBannerTone.ERROR,
            )
        }

    private fun renderPreview() = setScreen(getString(R.string.preview_title), true) {
        val uri = selectedImageUri
        val imageSource = selectedImageSource
        val liveAvailable = T09ProcessingConfig.isCapable(packageName) && T09ProcessingConfig.isConfigured() &&
            NetworkSecurityPolicy.getInstance().isCleartextTrafficPermitted(T09ProcessingConfig.HOST)
        if (liveAvailable || (imageSource == null && state.presentationResult is ReceiptPresentationUiResult.Available)) {
            add(ui.progressHeader(1, getString(R.string.v5_step_preview)))
            add(space(10))
        }
        val previewBitmap = uri?.let(::decodePreviewBitmap)
        when {
            imageSource == null -> {
                val presentation = state.presentationResult
                if (presentation is ReceiptPresentationUiResult.Available) {
                    add(syntheticReceiptPreview(presentation.receipt))
                    add(space(12))
                    add(ui.banner(getString(R.string.preview_synthetic_status),
                        getString(R.string.preview_synthetic_status_body), PantryBannerTone.INFO))
                    sticky(ui.actionButton(getString(R.string.preview_view_sample_fields), PantryActionStyle.PRIMARY,
                        viewId = R.id.preview_continue) { navigate(Screen.DETAILS) })
                } else {
                    add(presentationStatePanel(presentation))
                }
                add(ui.actionButton(getString(R.string.preview_choose_image), PantryActionStyle.SECONDARY) { launchImagePicker() })
            }
            uri == null || previewBitmap == null -> {
                add((imageInputNotice?.let(::imageInputNoticePanel) ?: ui.statePanel(
                    getString(R.string.preview_image_unavailable_title),
                    getString(R.string.preview_image_unavailable_body), PantryBannerTone.ERROR,
                )).apply { id = R.id.preview_image_error })
                add(ui.actionButton(getString(R.string.selected_processing_action), PantryActionStyle.SECONDARY,
                    enabled = false, viewId = R.id.preview_process_selected) {})
                sticky(ui.actionButton(getString(R.string.preview_choose_another), PantryActionStyle.PRIMARY,
                    viewId = R.id.preview_choose_another) { launchImagePicker() })
                add(ui.actionButton(getString(R.string.preview_use_demo_instead), PantryActionStyle.TERTIARY,
                    viewId = R.id.preview_use_demo) { switchToSyntheticDemo(); render() })
            }
            else -> {
                add(selectedImagePreview(previewBitmap, imageSource))
                add(receiptToolbar(
                    ui.compactToolbarAction(getString(R.string.sage_crop), R.drawable.ic_sage_crop, R.id.preview_crop_receipt) {
                        showCropEditor(uri, previewBitmap)
                    },
                    ui.compactToolbarAction(getString(R.string.sage_replace), R.drawable.ic_sage_replace, R.id.preview_choose_another) {
                        launchImagePicker()
                    }.apply { contentDescription = getString(R.string.preview_choose_another) },
                    ui.compactToolbarAction(getString(R.string.sage_remove), R.drawable.ic_sage_trash, R.id.preview_remove_image) {
                        switchToSyntheticDemo()
                        render()
                    }.apply { contentDescription = getString(R.string.preview_remove_image) },
                ))
                imageInputNotice?.let { notice ->
                    add(imageInputNoticePanel(notice).apply { id = R.id.image_input_notice })
                    add(space(8))
                }
                add(LinearLayout(this@MainActivity).apply {
                    id = R.id.preview_source_status
                    orientation = LinearLayout.VERTICAL
                    addView(bodyText(getString(if (imageSource == LocalImageSource.CAMERA)
                        R.string.preview_camera_status else R.string.preview_local_status)).apply {
                        setTextColor(ui.color(R.color.pantry_primary))
                    })
                    addView(bodyText(getString(if (imageSource == LocalImageSource.CAMERA)
                        R.string.preview_camera_status_body else R.string.preview_local_status_body)))
                })
                if (selectedImageCrop != null) {
                    add(bodyText(getString(R.string.crop_applied)).apply { id = R.id.preview_crop_status })
                }
                val test = ui.actionButton(getString(R.string.selected_processing_action),
                    if (liveAvailable) PantryActionStyle.SECONDARY else PantryActionStyle.PRIMARY,
                    viewId = R.id.preview_process_selected) { navigate(Screen.SELECTED_PROCESSING) }
                add(originalRetentionChoice())
                if (liveAvailable) {
                    add(space(8))
                    add(test)
                    sticky(ui.actionButton(getString(R.string.t09_processing_action), PantryActionStyle.PRIMARY) {
                        T09ProcessingConfig.current()?.let { session ->
                            liveSession = session
                            livePhase = T09HttpTransport.Phase.PREPARING
                            liveCancelled = false
                            navigate(Screen.T09_PROCESSING)
                        }
                    })
                } else {
                    sticky(test)
                }
                add(space(8))
                add(ui.actionButton(getString(R.string.manual_start_action), PantryActionStyle.TERTIARY,
                    viewId = R.id.preview_continue) {
                    startManualReceipt()
                })
            }
        }
    }

    private fun originalRetentionChoice(): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        fun explanation() = getString(if (keepOriginal) R.string.keep_original_on else R.string.keep_original_off)
        val details = bodyText(explanation())
        addView(android.widget.Switch(this@MainActivity).apply {
            id = R.id.keep_receipt_original
            text = getString(R.string.keep_original_label)
            minHeight = dp(48)
            isChecked = keepOriginal
            setOnCheckedChangeListener { _, enabled ->
                keepOriginal = enabled
                reviewPreferences.edit().putBoolean("keepOriginal", enabled).apply()
                details.text = explanation()
            }
        })
        addView(details)
    }

    private fun syntheticReceiptPreview(receipt: PresentedReceipt): View = ui.card {
        gravity = Gravity.CENTER_HORIZONTAL
        setPadding(dp(28), dp(28), dp(28), dp(28))
        addView(TextView(this@MainActivity).apply {
            text = presentedText(receipt.storeName).uppercase(Locale.ROOT)
            textSize = 18f
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            setTextColor(ui.color(R.color.pantry_on_surface))
        })
        addView(TextView(this@MainActivity).apply {
            text = buildString {
                append("SYNTHETIC RECEIPT\n")
                append(presentedDate(receipt.purchaseDate))
                append("\n\n")
                receipt.items.forEach { item ->
                    append(presentedText(item.description).uppercase(Locale.ROOT))
                    append("    ")
                    append(presentedMoney(item.lineTotal))
                    append('\n')
                }
                append("---------------------------\n")
                append("TOTAL    ")
                append(presentedMoney(receipt.receiptTotal))
            }
            typeface = Typeface.MONOSPACE
            textSize = 13f
            setTextColor(ui.color(R.color.pantry_on_surface))
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(0, dp(18), 0, 0)
        })
        contentDescription = getString(R.string.preview_synthetic_image_description)
    }

    private fun selectedImagePreview(
        bitmap: Bitmap,
        source: LocalImageSource,
        inDialog: Boolean = false,
        crop: ReceiptCrop = selectedImageCrop ?: ReceiptCrop.FULL,
    ): View {
        val container = ui.card(R.color.pantry_surface_container) { setPadding(dp(4), dp(4), dp(4), 0) }
        val image = ZoomReceiptView(this, bitmap, crop).apply {
            id = R.id.preview_selected_image
            contentDescription = getString(
                if (source == LocalImageSource.CAMERA) {
                    R.string.preview_captured_image_description
                } else {
                    R.string.preview_selected_image_description
                },
            )
        }
        val height = if (inDialog) {
            (resources.configuration.screenHeightDp * 0.38f).roundToInt().coerceIn(140, 400)
        } else {
            val fraction = if (ui.stacked()) 0.44f else 0.57f
            (resources.configuration.screenHeightDp * fraction).roundToInt().coerceIn(120, 540)
        }
        container.addView(
            image,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(height)),
        )
        val zoomIn = ui.compactToolbarAction(getString(R.string.preview_zoom_in), R.drawable.ic_sage_zoom_in,
            R.id.preview_zoom_in) { image.changeZoom(1.5f) }
        val zoomOut = ui.compactToolbarAction(getString(R.string.preview_zoom_out), R.drawable.ic_sage_zoom_out,
            R.id.preview_zoom_out) { image.changeZoom(1f / 1.5f) }
        val reset = ui.compactToolbarAction(getString(R.string.sage_reset), R.drawable.ic_sage_reset,
            R.id.preview_zoom_reset) { image.resetZoom() }.apply {
            contentDescription = getString(R.string.preview_zoom_reset)
        }
        image.onZoomChanged = { scale ->
            zoomIn.isEnabled = scale < ReceiptZoom.MAX_SCALE
            zoomOut.isEnabled = scale > 1f
            reset.isEnabled = scale > 1f
            val label = getString(R.string.preview_zoom_level, (scale * 100).roundToInt())
            if (ViewCompat.getStateDescription(image) != label) ViewCompat.setStateDescription(image, label)
        }
        image.onZoomChanged(1f)
        container.addView(receiptToolbar(zoomOut, zoomIn, reset))
        return container
    }

    private fun receiptToolbar(vararg actions: View): View = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        actions.forEach { addView(it, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)) }
    }

    private fun showCropEditor(
        uri: Uri,
        bitmap: Bitmap,
        initial: ReceiptCrop = selectedImageCrop ?: ReceiptCrop.FULL,
        expanded: Boolean = false,
    ) {
        if (cropEditorDialog?.isShowing == true) return
        cropEditorDraft = CropEditorDraft(uri, initial, expanded)
        lateinit var dialog: Dialog
        dialog = showSageCropEditor(this, ui, bitmap, initial, expanded,
            onChange = { bounds, precise -> cropEditorDraft = CropEditorDraft(uri, bounds, precise) },
            onApply = { crop ->
                if (selectedImageUri == uri) {
                    val bounds = ReceiptCrop.from(crop.values())
                    if (bounds != null && canReadSelectedImage(uri)) {
                        disposeSelectedImageProcessing()
                        selectedImageCrop = bounds.takeUnless { it == ReceiptCrop.FULL }
                    }
                    render()
                }
            },
            onDismiss = {
                if (cropEditorDialog === dialog) {
                    cropEditorDialog = null
                    cropEditorDraft = null
                }
            },
        )
        cropEditorDialog = dialog
    }

    private fun canReadSelectedImage(uri: Uri): Boolean = runCatching {
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        contentResolver.openInputStream(uri)?.use { input ->
            BitmapFactory.decodeStream(input, null, options)
        }
        options.outWidth > 0 && options.outHeight > 0
    }.getOrDefault(false)

    private fun decodePreviewBitmap(uri: Uri): Bitmap? = runCatching {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        contentResolver.openInputStream(uri)?.use { input ->
            BitmapFactory.decodeStream(input, null, bounds)
        }
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return@runCatching null
        var sampleSize = 1
        while (bounds.outWidth / sampleSize > MAX_PREVIEW_IMAGE_DIMENSION ||
            bounds.outHeight / sampleSize > MAX_PREVIEW_IMAGE_DIMENSION
        ) {
            sampleSize *= 2
        }
        val options = BitmapFactory.Options().apply { inSampleSize = sampleSize }
        val decoded = contentResolver.openInputStream(uri)?.use { input ->
            BitmapFactory.decodeStream(input, null, options)
        }
        decoded?.let { applyExifOrientation(uri, it) }
    }.getOrNull()

    private fun applyExifOrientation(uri: Uri, bitmap: Bitmap): Bitmap {
        val orientation = runCatching {
            contentResolver.openInputStream(uri)?.use { input ->
                SelectedImageSnapshotEncoder.readOrientation(input)
            }
        }.getOrNull() ?: android.media.ExifInterface.ORIENTATION_NORMAL
        val matrix = Matrix().apply {
            when (orientation) {
                android.media.ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> setScale(-1f, 1f)
                android.media.ExifInterface.ORIENTATION_ROTATE_180 -> setRotate(180f)
                android.media.ExifInterface.ORIENTATION_FLIP_VERTICAL -> setScale(1f, -1f)
                android.media.ExifInterface.ORIENTATION_TRANSPOSE -> {
                    setRotate(90f)
                    postScale(-1f, 1f)
                }
                android.media.ExifInterface.ORIENTATION_ROTATE_90 -> setRotate(90f)
                android.media.ExifInterface.ORIENTATION_TRANSVERSE -> {
                    setRotate(-90f)
                    postScale(-1f, 1f)
                }
                android.media.ExifInterface.ORIENTATION_ROTATE_270 -> setRotate(-90f)
            }
        }
        if (matrix.isIdentity) return bitmap
        return Bitmap.createBitmap(
            bitmap,
            0,
            0,
            bitmap.width,
            bitmap.height,
            matrix,
            true,
        ).also { oriented ->
            if (oriented !== bitmap) bitmap.recycle()
        }
    }

    private fun renderDetails() = setScreen(getString(R.string.details_title), true) {
        add(ui.progressHeader(2, getString(R.string.sage_step_details)))
        add(space(12))
        val available = state.presentationResult as? ReceiptPresentationUiResult.Available
        if (available == null) {
            add(presentationStatePanel(state.presentationResult))
        } else {
            if (selectedImageSource == null) {
                add(receiptImageAction(R.string.sage_sample_receipt) {
                    showReceiptImageDialog(R.string.sage_sample_receipt, syntheticReceiptPreview(available.receipt))
                })
                add(space(8))
            }
            val receipt = receiptForDetails(available.receipt)
            add(receiptSummary(receipt))
            add(space(12))
            add(sectionTitle(getString(R.string.details_items_title)))
            add(space(8))
            add(ui.card {
                receipt.items.forEachIndexed { index, item ->
                    if (index > 0) addView(divider())
                    addView(receiptItemCard(index + 1, item))
                }
            })
            add(space(12))
            add(ui.banner(getString(R.string.details_demo_title),
                getString(if (selectedImageSource == null) R.string.details_demo_body else R.string.details_local_demo_body),
                PantryBannerTone.DEMO))
            sticky(ui.actionButton(getString(R.string.details_review_action), PantryActionStyle.PRIMARY,
                viewId = R.id.details_review) { navigate(Screen.REVIEW) })
        }
    }

    private fun receiptImageAction(title: Int, onClick: () -> Unit): View = ui.card {
        id = R.id.sage_receipt_image
        addView(ui.actionRow(getString(title), getString(R.string.sage_view_image),
            R.drawable.ic_sage_receipt, ui.icon(R.drawable.ic_sage_right), action = onClick))
    }

    private fun showReceiptImageDialog(title: Int, image: View?) {
        val dialog = AlertDialog.Builder(this).setTitle(title).setPositiveButton(android.R.string.ok, null)
        if (image == null) dialog.setMessage(R.string.preview_image_unavailable_body)
        else dialog.setView(ScrollView(this).apply { addView(image) })
        dialog.show()
    }

    private fun liveReceiptImage(request: ReceiptProcessingRequest): View? {
        val image = boundLiveImage ?: return null
        val finished = selectedProcessingController?.state as? ReceiptProcessingLifecycle.State.Finished
        if (currentScreen != Screen.T09_PROCESSING || finished?.request !== request ||
            selectedImageUri != image.uri || (selectedImageCrop ?: ReceiptCrop.FULL) != image.crop ||
            !canReadSelectedImage(image.uri)
        ) return null
        return receiptImageAction(R.string.sage_original_receipt) {
            val current = selectedProcessingController?.state as? ReceiptProcessingLifecycle.State.Finished
            if (boundLiveImage !== image || current?.request !== request) return@receiptImageAction
            val preview = decodePreviewBitmap(image.uri)?.let {
                selectedImagePreview(it, image.source, inDialog = true, crop = ReceiptCrop.FULL)
            }
            showReceiptImageDialog(R.string.sage_original_receipt, preview)
        }
    }

    private fun receiptSummary(receipt: PresentedReceipt): View = ui.card {
        val identity = LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.VERTICAL
            addView(receiptValue(receipt.storeName, presentedText(receipt.storeName), prominent = true))
            addView(receiptValue(receipt.purchaseDate, presentedDate(receipt.purchaseDate)))
            val count = receipt.items.size
            addView(bodyText(resources.getQuantityString(R.plurals.home_inventory_count, count, count)))
        }
        val total = LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.VERTICAL
            addView(bodyText(getString(R.string.field_receipt_total)).apply {
                if (!ui.stacked()) gravity = Gravity.END
            })
            addView(receiptValue(receipt.receiptTotal, presentedMoney(receipt.receiptTotal), prominent = true).apply {
                if (!ui.stacked()) gravity = Gravity.END
            })
        }
        addView(LinearLayout(this@MainActivity).apply {
            if (ui.stacked()) {
                orientation = LinearLayout.VERTICAL
                addView(identity)
                addView(space(6))
            } else {
                gravity = Gravity.CENTER_VERTICAL
                addView(ui.icon(R.drawable.ic_sage_store, tile = true))
                addView(identity, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                    .apply { marginStart = dp(10); marginEnd = dp(10) })
            }
            addView(total, if (ui.stacked()) LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            ) else LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 0.65f))
        })
    }

    private fun receiptItemCard(number: Int, item: PresentedReceiptItem): View = LinearLayout(this).apply {
        id = when (number) {
            1 -> R.id.details_item_0
            2 -> R.id.details_item_1
            3 -> R.id.details_item_2
            else -> View.NO_ID
        }
        orientation = if (ui.stacked()) LinearLayout.VERTICAL else LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(0, dp(10), 0, dp(10))
        val identity = LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.VERTICAL
            addView(receiptValue(item.description, presentedText(item.description), prominent = true))
            addView(receiptItemMetadata(item))
        }
        val lineTotal = receiptValue(item.lineTotal, presentedMoney(item.lineTotal), prominent = true).apply {
            contentDescription = getString(R.string.sage_field_value, getString(R.string.field_line_total), text)
        }
        if (ui.stacked()) {
            addView(identity)
            addView(lineTotal)
        } else {
            gravity = Gravity.TOP
            addView(identity, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            lineTotal.gravity = Gravity.END
            addView(lineTotal, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 0.40f)
                .apply { marginStart = dp(8) })
        }
    }

    private fun receiptItemMetadata(item: PresentedReceiptItem): TextView {
        val quantity = presentedText(item.quantity)
        val unitPrice = when (item.unitPrice.status) {
            PresentedFieldStatus.EXTRACTED -> getString(R.string.v4_price_each, presentedMoney(item.unitPrice))
            PresentedFieldStatus.MISSING -> getString(R.string.v4_unit_price_optional)
            PresentedFieldStatus.UNRESOLVED -> getString(R.string.sage_field_value,
                getString(R.string.field_unit_price), presentedMoney(item.unitPrice))
        }
        val metadata = SpannableStringBuilder()
        fun append(value: String, needsAttention: Boolean) {
            val start = metadata.length
            metadata.append(value)
            if (needsAttention) metadata.setSpan(ForegroundColorSpan(ui.color(R.color.pantry_secondary)),
                start, metadata.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
        append(getString(R.string.v4_qty_value, quantity), item.quantity.status != PresentedFieldStatus.EXTRACTED)
        metadata.append(if (item.unitPrice.status == PresentedFieldStatus.MISSING) "\n" else " · ")
        append(unitPrice, item.unitPrice.status == PresentedFieldStatus.UNRESOLVED)
        return bodyText("").apply {
            setTextColor(ui.color(R.color.pantry_on_surface_variant))
            text = metadata
            contentDescription = getString(R.string.sage_field_value, getString(R.string.field_quantity), quantity) +
                ". " + if (item.unitPrice.status == PresentedFieldStatus.EXTRACTED)
                    getString(R.string.sage_field_value, getString(R.string.field_unit_price), presentedMoney(item.unitPrice))
                else unitPrice
        }
    }

    private fun receiptValue(field: PresentedField, value: String, prominent: Boolean = false,
        quietMissing: Boolean = false): TextView {
        val warning = field.status != PresentedFieldStatus.EXTRACTED &&
            !(quietMissing && field.status == PresentedFieldStatus.MISSING)
        if (warning) return ui.statusChip(value)
        return if (prominent) TextView(this, null, 0, R.style.TextAppearance_PantryProof_ItemTitle).apply {
            text = value
        } else bodyText(value)
    }

    private fun presentedText(field: PresentedField): String =
        when (field.status) {
            PresentedFieldStatus.EXTRACTED -> requireNotNull(field.value)
            PresentedFieldStatus.MISSING -> getString(R.string.presentation_field_missing)
            PresentedFieldStatus.UNRESOLVED -> getString(R.string.presentation_field_unresolved)
        }

    private fun presentedMoney(field: PresentedField): String =
        if (field.status == PresentedFieldStatus.EXTRACTED) {
            MoneyFormatter.ringgit(BigDecimal(requireNotNull(field.value)))
        } else {
            presentedText(field)
        }

    private fun presentedDate(field: PresentedField): String =
        if (field.status == PresentedFieldStatus.EXTRACTED) {
            PurchaseDateInput.display(requireNotNull(field.value))
        } else {
            presentedText(field)
        }

    private fun receiptForDetails(automatic: PresentedReceipt): PresentedReceipt {
        if (!reviewSavedTemporarily) return automatic
        val reviewed = state.receipt ?: return automatic
        val reviewedItems = reviewed.items.associateBy(ReceiptItem::id)
        return automatic.copy(
            storeName = automatic.storeName.withReviewedValue(reviewed.storeName),
            purchaseDate = automatic.purchaseDate.withReviewedValue(reviewed.purchaseDate.toString()),
            receiptTotal = automatic.receiptTotal.withReviewedValue(
                reviewed.receiptTotal.toPlainString(),
            ),
            items = automatic.items.map { item ->
                val reviewedItem = reviewedItems[item.rowId] ?: return@map item
                item.copy(
                    description = item.description.withReviewedValue(reviewedItem.description),
                    quantity = item.quantity.withReviewedValue(reviewedItem.quantity.toString()),
                    unitPrice = reviewedItem.unitPrice?.let { value ->
                        item.unitPrice.withReviewedValue(value.toPlainString())
                    } ?: item.unitPrice.copy(
                        status = PresentedFieldStatus.MISSING,
                        value = null,
                    ),
                    lineTotal = item.lineTotal.withReviewedValue(
                        reviewedItem.lineTotal.toPlainString(),
                    ),
                )
            },
        )
    }

    private fun PresentedField.withReviewedValue(reviewedValue: String): PresentedField =
        copy(
            status = PresentedFieldStatus.EXTRACTED,
            value = reviewedValue,
            absenceReason = null,
        )

    private fun presentationStatePanel(result: ReceiptPresentationUiResult, live: Boolean = false): View =
        when (result) {
            is ReceiptPresentationUiResult.Available -> ui.statePanel(
                getString(R.string.presentation_available_title),
                getString(R.string.presentation_available_body),
                PantryBannerTone.SUCCESS,
            )
            is ReceiptPresentationUiResult.ProcessingUnavailable -> ui.statePanel(
                getString(R.string.presentation_unavailable_title),
                getString(if (live) R.string.sage_live_unavailable else R.string.presentation_unavailable_body, result.failureCode),
                PantryBannerTone.INFO,
            )
            is ReceiptPresentationUiResult.ProcessingFailed -> ui.statePanel(
                getString(R.string.presentation_failed_title),
                getString(if (live) R.string.sage_live_failed else R.string.presentation_failed_body, result.failureCode),
                PantryBannerTone.ERROR,
            )
            is ReceiptPresentationUiResult.InsufficientEvidence -> ui.statePanel(
                getString(R.string.presentation_insufficient_title),
                getString(if (live) R.string.sage_live_insufficient else R.string.presentation_insufficient_body),
                PantryBannerTone.INFO,
            )
            is ReceiptPresentationUiResult.Rejected -> ui.statePanel(
                getString(R.string.presentation_rejected_title),
                getString(R.string.presentation_rejected_body, result.issue.code),
                PantryBannerTone.ERROR,
            )
        }

    private fun renderReview() = setScreen(getString(R.string.review_title), true, formWidth = true) {
        add(ui.progressHeader(3, getString(R.string.sage_step_review)))
        add(space(16))
        val available = state.presentationResult as? ReceiptPresentationUiResult.Available
        if (available == null) {
            add(presentationStatePanel(state.presentationResult))
            return@setScreen
        }
        val draft = reviewDraft ?: currentEditableDraft(available.receipt).also { reviewDraft = it }
        val sections = SageExpandableSections(this@MainActivity, ui, syntheticCollapsed)
        if (selectedImageSource == null) {
            add(receiptImageAction(R.string.sage_sample_receipt) {
                showReceiptImageDialog(R.string.sage_sample_receipt, syntheticReceiptPreview(available.receipt))
            })
            add(space(8))
        }
        if (ReceiptReviewAnnotationPolicy.requiresManualReviewAnnotation(available)) {
            add(ui.banner(
                getString(R.string.review_extraction_failed_title),
                getString(R.string.review_extraction_failed_annotation),
                PantryBannerTone.INFO,
            ).apply { id = R.id.review_extraction_failed_annotation })
            add(space(12))
        }
        add(ui.banner(
            getString(R.string.review_boundary_title),
            getString(R.string.review_boundary_body),
            PantryBannerTone.DEMO,
        ))
        if (temporaryConfirmationVisible && state.demoConfirmed) {
            add(space(12))
            add(ui.banner(
                getString(R.string.review_success_title),
                getString(R.string.review_success_body),
                PantryBannerTone.SUCCESS,
            ).apply {
                id = R.id.review_success
                accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
            })
            add(space(10))
            add(ui.actionButton(
                getString(R.string.review_view_inventory),
                PantryActionStyle.SECONDARY,
                viewId = R.id.review_view_inventory,
            ) { returnToInventory() })
        }
        add(space(14))

        val errorSummaryTitle = TextView(
            this@MainActivity,
            null,
            0,
            R.style.TextAppearance_PantryProof_Label,
        ).apply { setTextColor(ui.color(R.color.pantry_on_error_container)) }
        val errorSummaryBody = TextView(
            this@MainActivity,
            null,
            0,
            R.style.TextAppearance_PantryProof_Body,
        ).apply {
            text = getString(R.string.review_error_summary_body)
            setTextColor(ui.color(R.color.pantry_on_error_container))
            setPadding(0, dp(4), 0, 0)
        }
        val errorSummary = ui.card(R.color.pantry_error_container) {
            id = R.id.review_error_summary
            addView(errorSummaryTitle)
            addView(errorSummaryBody)
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        fun updateErrorSummary() {
            val count = reviewValidationErrors.size
            errorSummary.visibility = if (count == 0) View.GONE else View.VISIBLE
            if (count > 0) {
                errorSummaryTitle.text = resources.getQuantityString(
                    R.plurals.review_error_summary_title,
                    count,
                    count,
                )
            }
        }
        updateErrorSummary()
        add(errorSummary)
        add(space(10))

        val status = TextView(
            this@MainActivity,
            null,
            0,
            R.style.TextAppearance_PantryProof_Body,
        ).apply {
            id = R.id.review_status
            text = getString(
                when {
                    reviewHasUnsavedChanges -> R.string.review_status_dirty
                    reviewSavedTemporarily -> R.string.review_status_saved
                    else -> R.string.review_status_clean
                },
            )
            setTextColor(ui.color(
                if (reviewHasUnsavedChanges) R.color.pantry_secondary
                else R.color.pantry_on_surface_variant,
            ))
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        add(status)
        add(space(14))
        add(sectionBar(getString(R.string.review_receipt_section), sections.allAction()))
        add(space(8))

        val storeField = reviewField(
            key = "storeName",
            label = getString(R.string.field_store_name),
            value = draft.storeName,
            helper = getString(R.string.review_required_helper),
        )
        val dateField = reviewField(
            key = "purchaseDate",
            label = getString(R.string.field_purchase_date),
            value = PurchaseDateInput.display(draft.purchaseDate),
            helper = getString(R.string.v51_date_hint),
            type = InputType.TYPE_CLASS_DATETIME,
        ).also { it.field.isSaveEnabled = false }
        val receiptSection = LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.VERTICAL
            addView(storeField.container)
            addView(space(8))
            addView(dateField.container)
        }
        add(sections.add("receipt", getString(R.string.details_summary_title), receiptSection))
        add(space(12))
        add(sectionTitle(getString(R.string.review_items_section)))
        add(space(10))

        val itemFields = mutableListOf<ItemEditFields>()
        draft.items.forEachIndexed { index, item ->
            val description = reviewField(
                "item.$index.description",
                getString(R.string.field_description),
                item.description,
                getString(R.string.review_required_helper),
            )
            val quantity = reviewField(
                "item.$index.quantity",
                getString(R.string.field_quantity),
                item.quantity,
                getString(R.string.review_required_helper),
                InputType.TYPE_CLASS_NUMBER,
            )
            val unitPrice = reviewField(
                "item.$index.unitPrice",
                getString(R.string.field_unit_price),
                item.unitPrice,
                getString(R.string.review_unit_price_helper),
                InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL,
                prefix = "RM",
            )
            val lineTotal = reviewField(
                "item.$index.lineTotal",
                getString(R.string.field_line_total),
                item.lineTotal,
                getString(R.string.review_money_helper),
                InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL,
                prefix = "RM",
            )
            itemFields += ItemEditFields(description, quantity, unitPrice, lineTotal)
            val fields = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                listOf(description, quantity, unitPrice, lineTotal).forEach { field ->
                    addView(space(8))
                    addView(field.container)
                }
            }
            add(sections.add(item.id, getString(R.string.review_item_number, index + 1), fields,
                subtitle = item.description.takeIf(String::isNotBlank)))
            add(space(8))
        }

        val receiptTotal = reviewField(
            key = "receiptTotal",
            label = getString(R.string.field_receipt_total),
            value = draft.receiptTotal,
            helper = getString(R.string.review_money_helper),
            type = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL,
            prefix = "RM",
        )
        receiptSection.addView(space(8))
        receiptSection.addView(receiptTotal.container)
        add(space(12))

        val allFields = buildList {
            add(storeField)
            add(dateField)
            itemFields.forEach {
                add(it.description)
                add(it.quantity)
                add(it.unitPrice)
                add(it.lineTotal)
            }
            add(receiptTotal)
        }
        val discardActionButton = ui.actionButton(
            getString(R.string.review_discard_action),
            PantryActionStyle.TERTIARY,
            enabled = reviewHasUnsavedChanges,
            viewId = R.id.review_discard,
        ) { confirmDiscardEdits { discardReviewDraft() } }
        val lastField = itemFields.lastOrNull()?.lineTotal ?: receiptTotal
        fun updateSectionIssues() {
            sections.issues(allFields.filter { it.key in reviewValidationErrors }.map { it.field })
        }
        allFields.forEach { binding ->
            binding.field.imeOptions = if (binding === lastField) {
                EditorInfo.IME_ACTION_DONE
            } else {
                EditorInfo.IME_ACTION_NEXT
            }
            applyReviewFieldError(binding, reviewValidationErrors[binding.key])
            binding.field.addTextChangedListener(simpleTextWatcher {
                val entered = binding.field.text.toString()
                val changed = draft.updateField(binding.key, if (binding.key == "purchaseDate")
                    PurchaseDateInput.draftValue(entered) else entered)
                if (!changed) return@simpleTextWatcher
                reviewHasUnsavedChanges = true
                temporaryConfirmationVisible = false
                discardActionButton.isEnabled = true
                status.text = getString(R.string.review_status_dirty)
                status.setTextColor(ui.color(R.color.pantry_secondary))
                if (reviewValidationAttempted) {
                    val refreshedError = ReceiptValidator.validate(draft).errors[binding.key]
                    if (refreshedError == null) reviewValidationErrors.remove(binding.key)
                    else reviewValidationErrors[binding.key] = refreshedError
                    applyReviewFieldError(binding, refreshedError)
                    updateErrorSummary()
                    updateSectionIssues()
                }
            })
        }
        updateSectionIssues()

        fun validateAndApply(confirm: Boolean) {
            val result = ReceiptValidator.validate(draft)
            reviewValidationAttempted = true
            reviewValidationErrors.clear()
            reviewValidationErrors.putAll(result.errors)
            allFields.forEach { applyReviewFieldError(it, result.errors[it.key]) }
            updateErrorSummary()
            updateSectionIssues()
            if (!result.isValid) {
                result.firstInvalidFieldKey
                    ?.let { firstKey -> allFields.firstOrNull { it.key == firstKey } }
                    ?.let { binding -> sections.reveal(binding.field); focusInvalidField(binding) }
                return
            }

            state.applyReceipt(requireNotNull(result.receipt))
            reviewDraft = EditableReceipt.from(requireNotNull(state.receipt))
            reviewHasUnsavedChanges = false
            reviewSavedTemporarily = true
            reviewValidationAttempted = false
            reviewValidationErrors.clear()
            if (confirm) {
                temporaryConfirmationVisible = state.confirmForInventoryPreview()
            }
            render()
            if (confirm && temporaryConfirmationVisible) showTemporaryReceiptResult()
        }

        sticky(ui.actionButton(
            getString(R.string.review_confirm_action),
            PantryActionStyle.PRIMARY,
            viewId = R.id.review_confirm,
        ) { validateAndApply(confirm = true) })
        add(space(10))
        add(ui.actionButton(
            getString(R.string.review_apply_action),
            PantryActionStyle.SECONDARY,
            viewId = R.id.review_apply,
        ) { validateAndApply(confirm = false) })
        add(space(10))
        add(discardActionButton)
        add(space(4))
        add(ui.actionButton(
            getString(R.string.review_revert_action),
            PantryActionStyle.TERTIARY,
            viewId = R.id.review_revert,
        ) { confirmRevertDemo() })
        if (temporaryConfirmationVisible && state.demoConfirmed) {
            add(space(6))
            add(ui.actionButton(
                getString(R.string.review_view_inventory),
                PantryActionStyle.TERTIARY,
            ) { returnToInventory() })
        }
    }

    private fun showTemporaryReceiptResult() {
        val receipt = state.receipt ?: return
        if (temporaryResultDialog?.isShowing == true) return
        val content = LinearLayout(this).apply {
            id = R.id.sage_result_sheet
            orientation = LinearLayout.VERTICAL
            addView(ui.banner(getString(R.string.review_success_title), getString(R.string.review_success_body),
                PantryBannerTone.SUCCESS).apply {
                id = R.id.review_success
                accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
            })
            addView(summaryRow(getString(R.string.field_store_name), receipt.storeName))
            addView(summaryRow(getString(R.string.details_items_title), receipt.items.size.toString()))
            addView(summaryRow(getString(R.string.field_receipt_total), MoneyFormatter.ringgit(receipt.receiptTotal)))
            addView(space(8))
            addView(ui.actionButton(getString(R.string.review_view_inventory), PantryActionStyle.PRIMARY,
                viewId = R.id.review_view_inventory) {
                temporaryResultDialog?.dismiss()
                returnToInventory()
            })
        }
        temporaryResultDialog = ui.bottomSheet(getString(R.string.sage_receipt_confirmed), content,
            onDismiss = { temporaryResultDialog = null })
    }

    private fun sectionBar(title: String, action: View): View = LinearLayout(this).apply {
        if (ui.stacked()) {
            orientation = LinearLayout.VERTICAL
            addView(sectionTitle(title))
        } else {
            gravity = Gravity.CENTER_VERTICAL
            addView(sectionTitle(title), LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        addView(action)
    }

    private fun startManualReceipt() {
        manualDraft = EditableReceipt("", "", mutableListOf(blankManualItem()), "", UUID.randomUUID().toString())
        manualReviewedDraft = null
        manualReviewError = null
        manualCollapsed.clear()
        manualValidationAttempted = false
        navigate(Screen.MANUAL)
    }

    private fun blankManualItem() = EditableReceiptItem(UUID.randomUUID().toString(), "", "", "", "")

    private fun renderManualReceipt() =
        setScreen(getString(R.string.manual_title), true, formWidth = true) {
            val draft = checkNotNull(manualDraft)
            val sections = SageExpandableSections(this@MainActivity, ui, manualCollapsed)
            add(bodyText(getString(R.string.v51_manual_source)))
            add(space(6))
            if (selectedImageUri?.let(::canReadSelectedImage) == true) {
                add(receiptImageAction(R.string.sage_local_receipt_image) {
                    val bitmap = selectedImageUri?.let(::decodePreviewBitmap)
                    val source = selectedImageSource
                    showReceiptImageDialog(R.string.sage_local_receipt_image,
                        if (bitmap != null && source != null) selectedImagePreview(bitmap, source, inDialog = true)
                        else null)
                })
            }
            add(space(12))
            val itemLimitHint = if (draft.items.size >= ReceiptValidator.MAX_MANUAL_ITEMS) {
                getString(R.string.manual_item_limit, ReceiptValidator.MAX_MANUAL_ITEMS)
            } else {
                ""
            }
            val itemCountFeedback = bodyText(itemLimitHint).apply {
                accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
                visibility = if (itemLimitHint.isEmpty()) View.GONE else View.VISIBLE
            }
            val bindings = mutableListOf<ReviewFieldUi>()
            val removeItems = mutableListOf<View>()
            fun showValidation(validation: ReceiptValidationResult) {
                bindings.forEach {
                    applyReviewFieldError(it, validation.errors[it.key]?.let { error ->
                        if (it.key == "purchaseDate") {
                            if (error == ReceiptValidator.FUTURE_PURCHASE_DATE_ERROR) getString(R.string.purchase_date_future)
                            else dateError(it.field.text.toString())
                        } else error
                    })
                }
                sections.issues(bindings.filter { it.key in validation.errors }.map { it.field })
                val itemError = validation.errors["items"]
                val message = itemError ?: itemLimitHint
                if (itemCountFeedback.text.toString() != message) itemCountFeedback.text = message
                itemCountFeedback.setTextColor(ui.color(
                    if (itemError == null) R.color.pantry_on_surface_variant else R.color.pantry_error,
                ))
                itemCountFeedback.visibility = if (message.isEmpty()) View.GONE else View.VISIBLE
            }
            val amountType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            fun field(
                key: String,
                label: Int,
                value: String,
                helper: Int? = null,
                type: Int = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES,
                prefix: String? = null,
                datePicker: Boolean = false,
            ): View {
                val binding = reviewField(
                    key, getString(label), if (datePicker) PurchaseDateInput.display(value) else value,
                    helper?.let(::getString).orEmpty(), type, prefix,
                    manualEntry = true,
                )
                if (datePicker) configureManualDatePicker(binding)
                bindings += binding
                binding.field.addTextChangedListener(simpleTextWatcher {
                    val entered = binding.field.text.toString()
                    val valueForDraft = if (datePicker) PurchaseDateInput.draftValue(entered) else entered
                    if (draft.updateField(key, valueForDraft)) {
                        sections.refreshLabels()
                        if (manualValidationAttempted) showValidation(ReceiptValidator.validateManual(draft, state.currentLocalDate()))
                        else if (datePicker) showCompleteDateError(binding)
                    }
                })
                if (datePicker) showCompleteDateError(binding)
                return binding.container
            }
            fun rerenderAtCurrentPosition() {
                val scrollY = screenScrollView?.scrollY ?: 0
                render()
                screenScrollView?.let { scroll -> scroll.post { scroll.scrollTo(0, scrollY) } }
            }
            add(sectionBar(getString(R.string.review_receipt_section), sections.allAction()))
            val receiptSection = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                addView(field("storeName", R.string.field_store_name, draft.storeName))
                addView(field("purchaseDate", R.string.field_purchase_date, draft.purchaseDate, datePicker = true))
                addView(field("receiptTotal", R.string.field_receipt_total, draft.receiptTotal, type = amountType, prefix = "RM"))
            }
            add(sections.add("receipt", getString(R.string.details_summary_title), receiptSection, compact = true,
                labelForState = { expanded ->
                    getString(R.string.details_summary_title) to if (expanded) null else listOfNotNull(
                        draft.storeName.trim().takeIf(String::isNotEmpty),
                        PurchaseDateInput.parse(PurchaseDateInput.display(draft.purchaseDate))?.let(PurchaseDateInput::display),
                    ).joinToString(" · ").takeIf(String::isNotEmpty)
                }))
            add(space(6))
            val addItem = ui.iconButton(R.drawable.ic_sage_plus, getString(R.string.manual_add_item), R.id.manual_add_item) {
                val item = blankManualItem()
                draft.items.add(item)
                manualCollapsed.remove(item.id)
                render()
                val section = screenScrollView?.findViewWithTag<View>("manual-section:" + item.id)
                section?.post { section.requestRectangleOnScreen(Rect(0, 0, section.width, dp(64)), true) }
            }.apply {
                isEnabled = draft.items.size < ReceiptValidator.MAX_MANUAL_ITEMS
                ui.styleFilterControl(this, isEnabled)
                isSelected = false
            }
            add(LinearLayout(this@MainActivity).apply {
                gravity = Gravity.CENTER_VERTICAL
                addView(sectionTitle(getString(R.string.v51_item_count, draft.items.size)),
                    LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                addView(addItem)
            })
            draft.items.forEachIndexed { index, item ->
                val key = "item.$index"
                val fields = LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.VERTICAL
                    addView(field("$key.description", R.string.field_description, item.description))
                    addView(field("$key.quantity", R.string.field_quantity, item.quantity,
                        R.string.manual_quantity_helper, InputType.TYPE_CLASS_NUMBER))
                    addView(inventoryCategoryChoice(item.category) { item.category = it })
                    val unitPrice = field("$key.unitPrice", R.string.v51_unit_price, item.unitPrice,
                        R.string.v51_unit_price_help, type = amountType)
                    val lineTotal = field("$key.lineTotal", R.string.v51_line_total, item.lineTotal,
                        R.string.v51_line_total_help, type = amountType)
                    if (ui.stacked()) {
                        addView(unitPrice)
                        addView(lineTotal)
                    } else addView(LinearLayout(this@MainActivity).apply {
                        addView(unitPrice, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                            .apply { marginEnd = dp(8) })
                        addView(lineTotal, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                    })
                    val removeItem = ui.actionButton(
                        getString(R.string.manual_remove_item, index + 1),
                        PantryActionStyle.DESTRUCTIVE,
                    ) {
                        confirmRemoveManualItem(draft, item, index + 1, ::rerenderAtCurrentPosition)
                    }
                    removeItems += removeItem
                    addView(removeItem)
                }
                val fallback = getString(R.string.review_item_number, index + 1)
                add(sections.add(item.id, fallback, fields, compact = true, labelForState = { expanded ->
                    val name = item.description.trim().ifEmpty { fallback }
                    val subtitle = if (expanded) null else listOfNotNull(
                        item.quantity.trim().takeIf(String::isNotEmpty)?.let { getString(R.string.v4_qty_value, it) },
                        item.lineTotal.trim().takeIf(String::isNotEmpty)?.let { getString(R.string.v51_entered_amount, it) },
                    ).joinToString(" · ").takeIf(String::isNotEmpty)
                    name to subtitle
                }).apply { tag = "manual-section:" + item.id })
                add(space(8))
            }
            add(itemCountFeedback)
            add(space(8))
            if (manualValidationAttempted) showValidation(ReceiptValidator.validateManual(draft, state.currentLocalDate()))
            sticky(ui.actionButton(
                getString(R.string.manual_review_action),
                PantryActionStyle.PRIMARY,
                viewId = R.id.manual_review_action,
            ) {
                manualValidationAttempted = true
                val snapshot = draft.deepCopy()
                val validation = ReceiptValidator.validateManual(snapshot, state.currentLocalDate())
                showValidation(validation)
                val receipt = validation.receipt
                if (receipt == null) {
                    val firstInvalid = bindings.firstOrNull { it.key in validation.errors }
                    if (firstInvalid != null) {
                        sections.reveal(firstInvalid.field)
                        focusInvalidField(firstInvalid)
                    } else {
                        val rowAction = removeItems.lastOrNull() ?: addItem
                        sections.reveal(rowAction)
                        rowAction.isFocusableInTouchMode = true
                        rowAction.requestFocus()
                        rowAction.post {
                            rowAction.requestRectangleOnScreen(
                                Rect(0, 0, rowAction.width, rowAction.height), true,
                            )
                        }
                    }
                } else {
                    manualReviewedDraft = snapshot
                    manualReviewError = null
                    (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                        .hideSoftInputFromWindow(window.decorView.windowToken, 0)
                    navigate(Screen.MANUAL_REVIEW)
                }
            })
        }

    private fun dateError(value: String): String = getString(dateErrorResource(value))

    private fun dateErrorResource(value: String): Int =
        if (value.length < 10) R.string.v51_date_incomplete else R.string.v51_date_invalid

    private fun liveDateError(value: String): Int =
        if (ReceiptValidator.purchaseDateProblem(ReceiptValidator.parsePurchaseDate(value), state.currentLocalDate()) ==
            ReceiptValidator.PurchaseDateProblem.FUTURE
        ) R.string.purchase_date_future else dateErrorResource(PurchaseDateInput.display(value))

    private fun showCompleteDateError(binding: ReviewFieldUi) {
        val entered = binding.field.text.toString()
        val error = if (entered.length == 10) {
            when (ReceiptValidator.purchaseDateProblem(PurchaseDateInput.parse(entered), state.currentLocalDate())) {
                ReceiptValidator.PurchaseDateProblem.INVALID -> R.string.v51_date_invalid
                ReceiptValidator.PurchaseDateProblem.FUTURE -> R.string.purchase_date_future
                null -> null
            }
        } else null
        applyReviewFieldError(binding, error?.let(::getString))
    }

    private fun configureManualDatePicker(binding: ReviewFieldUi, expiry: Boolean = false) {
        val field = binding.field
        field.isSaveEnabled = false
        field.hint = getString(R.string.v51_date_hint)
        binding.helper.accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        ViewCompat.setAccessibilityDelegate(field, object : AccessibilityDelegateCompat() {
            override fun onInitializeAccessibilityNodeInfo(host: View, info: AccessibilityNodeInfoCompat) {
                super.onInitializeAccessibilityNodeInfo(host, info)
                if (binding.helper.visibility == View.VISIBLE && binding.helper.text.isNotEmpty()) {
                    info.error = binding.helper.text
                    info.isContentInvalid = true
                }
            }
        })
        PurchaseDateInput.install(field)
        binding.inputSurface.addView(ui.iconButton(R.drawable.ic_receipt_calendar,
            getString(if (expiry) R.string.inventory_choose_expiry else R.string.manual_choose_date),
            if (expiry) R.id.inventory_expiry_calendar else R.id.manual_calendar) {
            val first = LocalDate.of(1582, 10, 15)
            val last = if (expiry) LocalDate.of(9999, 12, 31)
                else minOf(state.currentLocalDate(), LocalDate.of(9999, 12, 31))
            val saved = PurchaseDateInput.parse(field.text.toString())
            val initial = (saved ?: state.currentLocalDate()).coerceIn(first, last)
            DatePickerDialog(this, { _, year, month, day ->
                val chosen = LocalDate.of(year, month + 1, day)
                if (expiry || !chosen.isAfter(state.currentLocalDate())) {
                    field.setText(PurchaseDateInput.display(chosen))
                    field.setSelection(field.length())
                }
            }, initial.year, initial.monthValue - 1, initial.dayOfMonth).apply {
                datePicker.minDate = GregorianCalendar(first.year, first.monthValue - 1, first.dayOfMonth).timeInMillis
                datePicker.maxDate = GregorianCalendar(last.year, last.monthValue - 1, last.dayOfMonth).timeInMillis
                datePicker.updateDate(initial.year, initial.monthValue - 1, initial.dayOfMonth)
                show()
            }
        })
    }

    private fun confirmRemoveManualItem(
        draft: EditableReceipt,
        item: EditableReceiptItem,
        number: Int,
        onRemoved: () -> Unit,
    ) {
        if (draft.items.size <= 1) {
            AlertDialog.Builder(this)
                .setTitle(R.string.manual_keep_one_title)
                .setMessage(R.string.manual_keep_one_body)
                .setPositiveButton(android.R.string.ok, null)
                .show()
            return
        }
        val description = item.description.trim()
        val itemLabel = if (description.isEmpty()) getString(R.string.review_item_number, number)
        else getString(R.string.manual_remove_item_description, number, description)
        AlertDialog.Builder(this)
            .setTitle(R.string.manual_remove_confirm_title)
            .setMessage(getString(R.string.manual_remove_confirm_body, itemLabel))
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.manual_remove_confirm_action) { _, _ ->
                if (manualDraft === draft && draft.items.size > 1) {
                    val selectedIndex = draft.items.indexOfFirst { it === item }
                    if (selectedIndex >= 0) {
                        draft.items.removeAt(selectedIndex)
                        manualCollapsed.remove(item.id)
                        onRemoved()
                    }
                }
            }
            .show()
    }

    private fun renderManualReceiptReview() = setScreen(getString(R.string.manual_review_title), true, formWidth = true) {
        val snapshot = manualReviewedDraft
        val validation = snapshot?.takeIf { it == manualDraft }?.let { ReceiptValidator.validateManual(it, state.currentLocalDate()) }
        val receipt = validation?.receipt
        add(bodyText(getString(R.string.v51_manual_source)))
        if (selectedImageUri != null) add(originalRetentionChoice())
        add(space(8))
        val error = when {
            validation?.errors?.get("purchaseDate") == ReceiptValidator.FUTURE_PURCHASE_DATE_ERROR ->
                R.string.purchase_date_future
            manualReviewError != null -> manualReviewError
            receipt == null -> R.string.manual_review_changed
            else -> null
        }
        error?.let {
            add(space(8))
            add(bodyText(getString(it)).apply {
                id = R.id.manual_review_error
                setTextColor(ui.color(R.color.pantry_error))
                accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
            })
        }
        val warnings = receipt?.let(ReceiptValidator::manualArithmeticWarnings)
        val lineWarnings = warnings?.mismatchedLineNumbers.orEmpty()
        val hasWarnings = lineWarnings.isNotEmpty() || warnings?.receiptTotalMismatch == true
        if (receipt != null) {
            val presentation = manualReceiptPresentation(receipt)
            add(receiptSummary(presentation))
            if (lineWarnings.isNotEmpty()) {
                add(space(8))
                add(ui.banner(resources.getQuantityString(R.plurals.v51_price_differences,
                    lineWarnings.size, lineWarnings.size), getString(R.string.manual_arithmetic_warning), PantryBannerTone.DEMO))
            }
            if (warnings?.receiptTotalMismatch == true) {
                add(space(8))
                add(ui.banner(getString(R.string.v51_total_difference), getString(R.string.manual_total_difference),
                    PantryBannerTone.DEMO))
            }
            add(space(8))
            add(ui.card {
                presentation.items.forEachIndexed { index, item ->
                    if (index > 0) addView(divider())
                    addView(receiptItemCard(index + 1, item))
                    if (index + 1 in lineWarnings) {
                        val row = receipt.items[index]
                        val calculated = requireNotNull(row.unitPrice).multiply(BigDecimal.valueOf(row.quantity.toLong()))
                        addView(bodyText(getString(R.string.v51_line_difference, MoneyFormatter.ringgit(calculated),
                            MoneyFormatter.ringgit(row.lineTotal))).apply {
                            setTextColor(ui.color(R.color.pantry_secondary))
                        })
                    }
                }
            })
        }
        val action = when {
            receipt == null -> R.string.v51_confirmation_unavailable
            hasWarnings -> R.string.manual_confirm_action
            else -> R.string.v51_confirm_receipt
        }
        sticky(ui.actionButton(getString(action), PantryActionStyle.PRIMARY, enabled = receipt != null,
            viewId = R.id.manual_confirm) {
            if (currentScreen != Screen.MANUAL_REVIEW || manualReviewedDraft !== snapshot) return@actionButton
            if (snapshot == null || snapshot != manualDraft || receipt == null) {
                manualReviewError = R.string.manual_review_changed
                render()
            } else {
                saveManualPurchase(snapshot, receipt, hasWarnings)
            }
        })
    }

    private fun saveManualPurchase(draft: EditableReceipt, receipt: Receipt, acknowledged: Boolean) {
        if (receiptCommitInProgress) return
        receiptCommitInProgress = true
        val uri = selectedImageUri.takeIf { keepOriginal }
        val saving = AlertDialog.Builder(this).setMessage(R.string.manual_saving_purchase).setCancelable(false).show()
        val worker = Executors.newSingleThreadExecutor()
        worker.execute {
            val original = uri?.let {
                runCatching { SelectedImageSnapshotEncoder(applicationContext.contentResolver).readOriginal(it) }.getOrNull()
            }
            val result = try {
                if (uri != null && original == null) ManualInventoryStore.Commit.FAILED
                else state.commitManualReceipt(draft, acknowledged, original)
            } finally {
                original?.fill(0)
            }
            runOnUiThread {
                receiptCommitInProgress = false
                saving.dismiss()
                if (isFinishing || isDestroyed) return@runOnUiThread
                when (result) {
                    ManualInventoryStore.Commit.COMMITTED, ManualInventoryStore.Commit.REPLAYED -> {
                        state.refreshDurableInventory()
                        pendingInventorySuccess = receiptSuccess(receipt.items.map { PantryUiState.MANUAL_ROW_PREFIX + it.id })
                        manualReviewedDraft = null
                        manualReviewError = null
                        returnToInventory()
                        state.acknowledgeConfirmations(setOf(state.manualReceiptIdentity(draft)))
                    }
                    else -> {
                        manualReviewError = when {
                            receipt.purchaseDate.isAfter(state.currentLocalDate()) -> R.string.purchase_date_future
                            uri != null && original == null -> R.string.manual_original_unavailable
                            else -> R.string.manual_confirmation_failed
                        }
                        render()
                    }
                }
            }
        }
        worker.shutdown()
    }

    private fun manualReceiptPresentation(receipt: Receipt): PresentedReceipt {
        fun field(role: String, value: String?) = PresentedField(role,
            if (value == null) PresentedFieldStatus.MISSING else PresentedFieldStatus.EXTRACTED,
            null, value, null)
        return PresentedReceipt("", "MYR", field("storeName", receipt.storeName),
            field("purchaseDate", receipt.purchaseDate.toString()), field("receiptTotal", receipt.receiptTotal.toPlainString()),
            receipt.items.map { item ->
                PresentedReceiptItem(item.id, field("description", item.description), field("quantity", item.quantity.toString()),
                    field("unitPrice", item.unitPrice?.toPlainString()), field("lineTotal", item.lineTotal.toPlainString()))
            })
    }

    private fun confirmDiscardManualDraft() {
        AlertDialog.Builder(this)
            .setTitle(R.string.manual_discard_title)
            .setMessage(R.string.manual_discard_body)
            .setNegativeButton(R.string.review_keep_editing, null)
            .setPositiveButton(R.string.review_discard_confirm) { _, _ ->
                manualDraft = null
                goBack()
            }
            .show()
    }

    private fun hasDurableInventory() =
        state.inventory.any { ManualInventoryStore.isDurableRowId(it.id) }

    private fun renderInventory() = setScreen(getString(R.string.app_name), false, pinned = {
        val count = TextView(this@MainActivity, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
            id = R.id.inventory_summary
            text = resources.getQuantityString(R.plurals.inventory_summary, state.inventory.size, state.inventory.size)
        }
        add(count)
        if (!ui.stacked()) add(space(8))
        add(inventorySearchRow())
        add(space(6))
    }) {
        imageInputNotice?.let { notice ->
            add(imageInputNoticePanel(notice).apply { id = R.id.image_input_notice })
            add(space(6))
        }
        if (pendingReceiptAcknowledgements.isNotEmpty()) {
            add(ui.banner("Receipt confirmation recovered", "The saved inventory and any receipt history are available.",
                PantryBannerTone.SUCCESS))
            add(ui.actionButton("Dismiss", PantryActionStyle.TERTIARY) {
                if (state.acknowledgeConfirmations(pendingReceiptAcknowledgements)) {
                    pendingReceiptAcknowledgements = emptySet()
                    render()
                }
            })
        }
        val temporary = state.inventory.any { !ManualInventoryStore.isDurableRowId(it.id) }
        when {
            state.manualInventoryLoadFailed -> add(ui.banner(
                getString(R.string.manual_inventory_load_failed_title),
                getString(R.string.manual_inventory_load_failed), PantryBannerTone.ERROR,
            ))
            hasDurableInventory() && temporary -> add(bodyText(getString(R.string.sage_mixed_stock)))
            hasDurableInventory() -> add(bodyText(getString(R.string.sage_durable_stock)))
            temporary -> add(bodyText(getString(
                if (state.demoConfirmed) R.string.inventory_banner_confirmed else R.string.sage_demo_stock,
            )))
        }
        add(TextView(this@MainActivity, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
            id = R.id.inventory_browse_count
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
            inventoryBrowseCount = this
        })
        add(space(14))
        add(LinearLayout(this@MainActivity).apply {
            id = R.id.inventory_browse_results
            orientation = LinearLayout.VERTICAL
            inventoryResults = this
        })
        updateInventoryBrowseResults(announceImmediately = true)
    }

    private fun receiptHistoryEntry(): View = ui.iconButton(R.drawable.ic_sage_receipt, "Receipt history", R.id.receipt_history) {
        historyIdentity = null
        navigate(Screen.HISTORY)
    }.apply { isEnabled = !state.manualInventoryLoadFailed }

    private fun renderReceiptHistory() = setScreen("Receipt History", true) {
        val records = state.receiptHistory()
        if (records == null) {
            add(ui.statePanel("Receipt history unavailable", "Return to inventory and try opening history again.", PantryBannerTone.ERROR))
            return@setScreen
        }
        val count = records.size
        add(bodyText(resources.getQuantityString(R.plurals.saved_receipts, count, count)))
        if (records.isEmpty()) {
            add(ui.statePanel("No saved receipts yet", "Receipts you confirm and save appear here.", PantryBannerTone.INFO))
            return@setScreen
        }
        val search = EditText(this@MainActivity).apply {
            id = R.id.receipt_history_search
            hint = "Search stores and purchased items"
            setSingleLine()
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
            imeOptions = EditorInfo.IME_ACTION_SEARCH or EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING
            minHeight = dp(48)
            setText(historyQuery)
        }
        add(search)
        val matches = LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.VERTICAL
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        }
        add(matches)
        val summaries = receiptHistoryMonths(records, "").associateBy { it.month }
        fun updateHistory() {
            matches.removeAllViews()
            val groups = receiptHistoryMonths(records, historyQuery)
            if (groups.isEmpty()) matches.addView(bodyText("No receipts match your search."))
            groups.forEach { group ->
                val summary = summaries.getValue(group.month)
                matches.addView(sectionTitle(group.month.format(java.time.format.DateTimeFormatter.ofPattern("MMMM yyyy", Locale.getDefault()))))
                val monthly = resources.getQuantityString(R.plurals.saved_receipts, summary.purchases.size, summary.purchases.size)
                matches.addView(bodyText("$monthly · RM ${summary.spending.toPlainString()} recorded spending"))
                group.purchases.forEach { receipt ->
                    matches.addView(space(8))
                    matches.addView(ui.card {
                        addView(ui.actionRow(receipt.store,
                            listOfNotNull("${receipt.date} · ${purchaseCount(receipt)} · RM\u00A0${receipt.total.toPlainString()}",
                                getString(R.string.history_manual_source).takeIf { receipt.source == PurchaseSource.MANUAL })
                                .joinToString(" · "),
                            R.drawable.ic_sage_receipt, ui.icon(R.drawable.ic_sage_right)) {
                            historyIdentity = receipt.confirmationId
                            navigate(Screen.HISTORY_DETAIL)
                        })
                    })
                }
                matches.addView(space(12))
            }
        }
        updateHistory()
        search.addTextChangedListener(simpleTextWatcher {
            historyQuery = search.text.toString()
            updateHistory()
        })
    }

    private fun purchaseCount(receipt: PurchaseRecord): String =
        resources.getQuantityString(R.plurals.purchased_items, receipt.rows.size, receipt.rows.size)

    private fun renderReceiptHistoryDetail() = setScreen("Receipt details", true) {
        val receipt = state.receiptHistory()?.firstOrNull { it.confirmationId == historyIdentity }
        if (receipt == null) {
            add(ui.statePanel("Receipt unavailable", "Go back to see the available receipts.", PantryBannerTone.INFO))
            return@setScreen
        }
        add(ui.card {
            addView(sectionTitle(receipt.store))
            addView(bodyText("${receipt.date} · ${purchaseCount(receipt)}"))
            if (receipt.source == PurchaseSource.MANUAL) addView(bodyText(getString(R.string.history_manual_source)))
            addView(bodyText("Receipt total · RM ${receipt.total.toPlainString()}"))
        })
        add(space(10))
        if (receipt.originalFile != null && state.originalReceipt(receipt.confirmationId) != null) {
            add(receiptImageAction(R.string.sage_original_receipt) {
                val file = state.originalReceipt(receipt.confirmationId)
                val image = file?.let { decodePreviewBitmap(Uri.fromFile(it)) }?.let(::submittedImageView)
                    ?.apply { contentDescription = "Retained original receipt" }
                showReceiptImageDialog(R.string.sage_original_receipt, image)
            })
        } else {
            add(bodyText(if (receipt.originalFile == null) "Receipt details saved." else "Original receipt image unavailable."))
        }
        add(space(10))
        add(sectionTitle("Purchased items"))
        receipt.rows.forEach { row ->
            add(ui.card {
                addView(sectionTitle(row.description))
                val unit = row.inventoryUnit?.symbol?.takeIf(String::isNotEmpty)
                addView(bodyText("Purchased quantity · ${row.quantity.toPlainString()}"))
                if (row.included) addView(bodyText(listOfNotNull("Included in inventory", unit).joinToString(" · ")))
                else addView(bodyText("Excluded from inventory"))
                if (row.unitPrice != null) addView(bodyText("Unit price · RM ${row.unitPrice.toPlainString()}"))
                else addView(bodyText("Unit price absent"))
                addView(bodyText("Line total · RM ${row.lineTotal.toPlainString()}"))
            })
            add(space(8))
        }
        add(ui.actionButton("Delete receipt", PantryActionStyle.DESTRUCTIVE, iconResource = R.drawable.ic_sage_trash) {
            confirmReceiptDeletion(receipt)
        })
    }

    private fun confirmReceiptDeletion(receipt: PurchaseRecord) {
        AlertDialog.Builder(this).setTitle("Delete this receipt?")
            .setMessage("This removes the purchase record, any saved image and private review evidence. Inventory stays as it is. The confirmation remains used.")
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton("Delete receipt") { _, _ ->
                if (state.deleteReceipt(receipt.confirmationId)) {
                    historyIdentity = null
                    goBack()
                } else showReviewMessage("The receipt could not be deleted. Try again.")
            }.show()
    }

    private fun inventorySearchRow(): View {
        val search = EditText(this@MainActivity).apply {
            id = R.id.inventory_search
            hint = getString(R.string.inventory_search_hint)
            setHintTextColor(ui.color(R.color.pantry_on_surface_variant))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            setSingleLine(true)
            textSize = 14f
            imeOptions = EditorInfo.IME_ACTION_SEARCH or EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
            minimumHeight = dp(48)
            setText(inventoryBrowse.query)
            val outline = getDrawable(R.drawable.ic_sage_search)
            setCompoundDrawablesRelativeWithIntrinsicBounds(outline, null, null, null)
            compoundDrawablePadding = dp(8)
            setPaddingRelative(dp(12), dp(8), dp(8), dp(8))
            background = null
        }
        val sortOptions = resources.getStringArray(R.array.inventory_sort_options)
        val sort = ui.iconButton(R.drawable.ic_sage_sort, getString(R.string.inventory_sort_label), R.id.inventory_sort) {
            val anchor = findViewById<View>(R.id.inventory_sort) ?: return@iconButton
            ui.showChoicePopup(anchor, sortOptions, inventoryBrowse.sort.ordinal) { position ->
                val selected = InventoryBrowseProjection.Sort.values()[position]
                if (selected != inventoryBrowse.sort) {
                    inventoryBrowse.sort = selected
                    ViewCompat.setStateDescription(anchor, sortOptions[position])
                    updateInventoryBrowseResults()
                }
            }
        }.apply { ViewCompat.setStateDescription(this, sortOptions[inventoryBrowse.sort.ordinal]) }
        val clear = ui.iconButton(R.drawable.ic_sage_close, getString(R.string.inventory_clear_search),
            R.id.inventory_clear_search) {
            search.text.clear()
            search.requestFocus()
        }
        fun updateClear() {
            clear.isEnabled = inventoryBrowse.query.isNotEmpty()
            clear.visibility = if (clear.isEnabled) View.VISIBLE else View.GONE
        }
        updateClear()
        val searchField = LinearLayout(this@MainActivity).apply {
            gravity = Gravity.CENTER_VERTICAL
            addView(search, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(clear)
            fun outline(focused: Boolean) = rounded(
                ui.color(R.color.pantry_surface_bright), 12f, ui.color(R.color.pantry_outline),
                strokeWidth = if (focused) 2 else 1,
            )
            background = outline(false)
            search.setOnFocusChangeListener { _, focused -> background = outline(focused) }
        }
        search.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(text: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(text: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(text: Editable?) {
                if (currentScreen != Screen.INVENTORY || findViewById<EditText>(R.id.inventory_search) !== search) return
                val query = text?.toString().orEmpty()
                if (query == inventoryBrowse.query) return
                inventoryBrowse.query = query
                matchingInventoryGroupOverrides.clear()
                updateClear()
                updateInventoryBrowseResults()
            }
        })
        val filterLabels = resources.getStringArray(R.array.sage_inventory_filter_labels)
        fun styleSourceFilter(control: View) {
            val active = inventoryBrowse.source != InventoryBrowseProjection.Source.ALL
            ui.styleFilterControl(control, active)
            ViewCompat.setStateDescription(control, filterLabels[inventoryBrowse.source.ordinal])
        }
        val filter = ui.iconButton(R.drawable.ic_sage_filter, getString(R.string.inventory_filter_label), R.id.inventory_filter) {
            val anchor = findViewById<View>(R.id.inventory_filter) ?: return@iconButton
            ui.showChoicePopup(anchor, filterLabels, inventoryBrowse.source.ordinal, R.id.inventory_filter_choices) { position ->
                val selected = InventoryBrowseProjection.Source.values()[position]
                if (selected != inventoryBrowse.source) {
                    inventoryBrowse.source = selected
                    matchingInventoryGroupOverrides.clear()
                    styleSourceFilter(anchor)
                    updateInventoryBrowseResults()
                }
            }
        }.apply { styleSourceFilter(this) }
        return LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            addView(searchField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(sort)
            addView(filter)
        }
    }

    private fun addInventoryEntry(): View = ui.iconButton(
        R.drawable.ic_sage_plus, getString(R.string.v5_inventory_add_description), R.id.inventory_add_item,
    ) { showInventoryItemEditor() }

    private fun receiptSuccess(ids: List<String>) = InventorySuccess(
        R.string.sage_receipt_confirmed,
        resources.getQuantityString(R.plurals.sage_saved_rows, ids.size, ids.size),
        ids,
    )

    private fun dismissInventorySuccess() {
        inventorySuccessDismissal?.let(inventoryBrowseHandler::removeCallbacks)
        inventorySuccessDismissal = null
        findViewById<FrameLayout>(R.id.inventory_success_host)?.apply {
            removeAllViews()
            visibility = View.GONE
        }
    }

    private fun renderPendingInventorySuccess() {
        if (currentScreen != Screen.INVENTORY || inventorySheet != null || inventoryImeVisible || isDestroyed) return
        val success = pendingInventorySuccess ?: return
        val host = findViewById<FrameLayout>(R.id.inventory_success_host) ?: return
        pendingInventorySuccess = null
        dismissInventorySuccess()
        val addedHidden = success.addedIds.any { inventoryResults?.findViewWithTag<View>(it)?.isShown != true }
        val message = listOfNotNull(success.message.takeIf(String::isNotBlank),
            getString(R.string.v51_stock_hidden).takeIf { addedHidden }).joinToString("\n")
        host.addView(ui.inventorySuccess(getString(success.title), message, ::dismissInventorySuccess))
        host.visibility = View.VISIBLE
        val timeout = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val manager = getSystemService(android.view.accessibility.AccessibilityManager::class.java)
            manager.getRecommendedTimeoutMillis(5_000,
                android.view.accessibility.AccessibilityManager.FLAG_CONTENT_ICONS or
                    android.view.accessibility.AccessibilityManager.FLAG_CONTENT_TEXT or
                    android.view.accessibility.AccessibilityManager.FLAG_CONTENT_CONTROLS)
        } else 5_000
        inventorySuccessDismissal = Runnable(::dismissInventorySuccess).also {
            inventoryBrowseHandler.postDelayed(it, timeout.toLong())
        }
    }

    private fun showInventorySheet(
        title: String, content: View, footer: View? = null, onDismiss: (() -> Unit)? = null,
    ): Dialog {
        lateinit var sheet: Dialog
        sheet = ui.bottomSheet(title, content, footer) {
            inventorySheets.remove(sheet)
            updateScanVisibility()
            onDismiss?.invoke()
        }
        inventorySheets.add(sheet)
        updateScanVisibility()
        return sheet
    }

    private fun updateScanVisibility() {
        val obscured = inventoryImeVisible || inventorySheet != null
        val visibility = if (obscured) View.INVISIBLE else View.VISIBLE
        findViewById<View>(R.id.home_add_receipt)?.let { scan ->
            if (scan.visibility != visibility) {
                scan.visibility = visibility
                val clearance = if (obscured) 0 else inventoryScanClearance(scan.layoutParams as FrameLayout.LayoutParams)
                screenScrollView?.setPadding(0, 0, 0, clearance)
            }
        }
        findViewById<FrameLayout>(R.id.inventory_success_host)?.let { host ->
            host.visibility = if (!obscured && host.childCount > 0) View.VISIBLE else View.GONE
        }
        if (!obscured) renderPendingInventorySuccess()
    }

    private fun inventoryScanClearance(layout: FrameLayout.LayoutParams): Int = layout.height + layout.bottomMargin + dp(8)

    private fun updateInventoryBrowseResults(announceImmediately: Boolean = false) {
        val results = inventoryResults ?: return
        if (currentScreen != Screen.INVENTORY) return
        val focusedTag = results.findFocus()?.tag
        fun readerTag(view: View): String? {
            if (view.isAccessibilityFocused && view.tag is String) return view.tag as String
            if (view is ViewGroup) for (index in 0 until view.childCount) {
                readerTag(view.getChildAt(index))?.let { return it }
            }
            return null
        }
        val focusedReaderTag = readerTag(results)
        val visible = inventoryBrowse.project(state.inventory)
        val today = state.currentLocalDate()
        inventoryWarningDate = today
        scheduleInventoryDateRefresh()
        results.removeAllViews()
        when {
            state.inventory.isEmpty() -> results.addView(inventoryEmpty(
                R.id.inventory_empty_state, R.drawable.ic_sage_basket,
                R.string.inventory_empty_title, R.string.inventory_empty_body,
                R.string.inventory_add_item,
            ) { showInventoryItemEditor() })
            visible.isEmpty() -> results.addView(inventoryEmpty(
                R.id.inventory_no_matches, R.drawable.ic_sage_search,
                R.string.inventory_no_matches, R.string.inventory_no_matches_body,
                R.string.inventory_clear_search.takeIf { inventoryBrowse.query.isNotEmpty() },
            ) { findViewById<EditText>(R.id.inventory_search)?.text?.clear() })
            else -> renderInventoryRows(results, visible, today)
        }
        if (focusedTag != null) results.findViewWithTag<View>(focusedTag)?.takeIf { it.isShown }?.requestFocus()
        if (focusedReaderTag != null) {
            results.findViewWithTag<View>(focusedReaderTag)?.takeIf { it.isShown }?.performAccessibilityAction(
                android.view.accessibility.AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS, null,
            )
        }
        inventoryCountAnnouncement?.let(inventoryBrowseHandler::removeCallbacks)
        val count = inventoryBrowseCount ?: return
        val message = resources.getQuantityString(
            R.plurals.inventory_browse_count, state.inventory.size, visible.size, state.inventory.size,
        )
        val announcement = Runnable {
            if (currentScreen == Screen.INVENTORY && inventoryResults === results && count.text.toString() != message) {
                count.text = message
            }
        }
        inventoryCountAnnouncement = announcement
        // One polite count after typing settles, rather than an announcement per keystroke.
        if (announceImmediately) announcement.run() else inventoryBrowseHandler.postDelayed(announcement, 500L)
    }

    private fun summaryRow(
        label: String,
        value: String,
        emphasize: Boolean = false,
        needsAttention: Boolean = false,
    ): View =
        LinearLayout(this).apply {
            val stack = resources.configuration.fontScale >= 1.3f ||
                resources.configuration.screenWidthDp < 360
            orientation = if (stack) LinearLayout.VERTICAL else LinearLayout.HORIZONTAL
            gravity = if (stack) Gravity.START else Gravity.CENTER_VERTICAL
            setPadding(0, dp(8), 0, dp(8))
            addView(TextView(
                this@MainActivity,
                null,
                0,
                R.style.TextAppearance_PantryProof_Label,
            ).apply { text = label }, if (stack) {
                LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                )
            } else {
                LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 0.38f)
            })
            addView(TextView(
                this@MainActivity,
                null,
                0,
                if (emphasize) R.style.TextAppearance_PantryProof_SectionTitle
                else R.style.TextAppearance_PantryProof_ItemTitle,
            ).apply {
                text = value
                setTextColor(ui.color(
                    when {
                        needsAttention -> R.color.pantry_secondary
                        emphasize -> R.color.pantry_primary
                        else -> R.color.pantry_on_surface
                    },
                ))
                gravity = if (stack) Gravity.START else Gravity.END
                if (stack) setPadding(0, dp(4), 0, 0)
            }, if (stack) {
                LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                )
            } else {
                LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 0.62f)
            })
        }

    private fun reviewField(
        key: String,
        label: String,
        value: String,
        helper: String,
        type: Int = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES,
        prefix: String? = null,
        manualEntry: Boolean = false,
        sessionOnly: Boolean = false,
        viewId: Int = reviewFieldId(key),
    ): ReviewFieldUi {
        val allowWrap = type and InputType.TYPE_MASK_CLASS == InputType.TYPE_CLASS_TEXT
        val input = EditText(this).apply {
            id = viewId
            if ((manualEntry || sessionOnly) && id == View.NO_ID) id = View.generateViewId()
            if (sessionOnly) isSaveEnabled = false
            if (manualEntry) filters = arrayOf(InputFilter.LengthFilter(160))
            hint = label
            setText(value)
            inputType = type
            textSize = 16f
            setTextColor(ui.color(R.color.pantry_on_surface))
            setHintTextColor(ui.color(R.color.pantry_outline))
            setPadding(if (prefix == null) dp(12) else dp(8), dp(11), dp(12), dp(11))
            background = null
            minHeight = ui.dimen(R.dimen.pantry_touch_target)
            isSingleLine = !allowWrap
            maxLines = if (allowWrap) 3 else 1
        }
        val inputSurface = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = ui.dimen(R.dimen.pantry_touch_target)
            background = rounded(
                ui.color(R.color.pantry_surface_bright),
                12f,
                ui.color(R.color.pantry_outline),
            )
            prefix?.let { prefixText ->
                addView(TextView(
                    this@MainActivity,
                    null,
                    0,
                    R.style.TextAppearance_PantryProof_ItemTitle,
                ).apply {
                    text = prefixText
                    setTextColor(ui.color(R.color.pantry_on_surface_variant))
                    setPadding(dp(12), 0, 0, 0)
                    importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                })
            }
            addView(input, LinearLayout.LayoutParams(
                0,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                1f,
            ))
        }
        val helperView = TextView(
            this,
            null,
            0,
            R.style.TextAppearance_PantryProof_Label,
        ).apply {
            text = helper
            setTextColor(ui.color(R.color.pantry_on_surface_variant))
            setPadding(dp(3), dp(4), dp(3), 0)
            minHeight = if (manualEntry) 0 else dp(22)
            if (helper.isEmpty()) visibility = View.GONE
        }
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            if (manualEntry || sessionOnly) setPadding(0, 0, 0, dp(8))
            addView(TextView(
                this@MainActivity,
                null,
                0,
                R.style.TextAppearance_PantryProof_Label,
            ).apply {
                text = label
                if (input.id != View.NO_ID) labelFor = input.id
                setTextColor(ui.color(R.color.pantry_on_surface))
                setPadding(0, 0, 0, dp(5))
            })
            addView(inputSurface, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ))
            addView(helperView, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ))
        }
        return ReviewFieldUi(key, input, inputSurface, helperView, helper, container)
    }

    private fun reviewFieldId(key: String): Int = when (key) {
        "storeName" -> R.id.review_store_name
        "purchaseDate" -> R.id.review_purchase_date
        "item.0.description" -> R.id.review_item_0_description
        "item.0.quantity" -> R.id.review_item_0_quantity
        "item.0.unitPrice" -> R.id.review_item_0_unit_price
        "item.0.lineTotal" -> R.id.review_item_0_line_total
        "item.1.description" -> R.id.review_item_1_description
        "item.1.quantity" -> R.id.review_item_1_quantity
        "item.1.unitPrice" -> R.id.review_item_1_unit_price
        "item.1.lineTotal" -> R.id.review_item_1_line_total
        "item.2.description" -> R.id.review_item_2_description
        "item.2.quantity" -> R.id.review_item_2_quantity
        "item.2.unitPrice" -> R.id.review_item_2_unit_price
        "item.2.lineTotal" -> R.id.review_item_2_line_total
        "receiptTotal" -> R.id.review_receipt_total
        else -> View.NO_ID
    }

    private fun applyReviewFieldError(binding: ReviewFieldUi, error: String?) {
        binding.helper.text = error ?: binding.defaultHelper
        binding.helper.visibility = if (error == null && binding.defaultHelper.isEmpty()) View.GONE else View.VISIBLE
        binding.helper.setTextColor(ui.color(
            if (error == null) R.color.pantry_on_surface_variant else R.color.pantry_error,
        ))
        if (binding.key != "purchaseDate" || binding.field.inputType and InputType.TYPE_MASK_CLASS != InputType.TYPE_CLASS_NUMBER) {
            binding.field.error = error
        }
        binding.inputSurface.background = rounded(
            ui.color(R.color.pantry_surface_bright),
            12f,
            ui.color(if (error == null) R.color.pantry_outline else R.color.pantry_error),
        )
    }

    private fun focusInvalidField(binding: ReviewFieldUi) {
        binding.field.requestFocus()
        screenScrollView?.post {
            binding.field.requestRectangleOnScreen(
                Rect(0, 0, binding.field.width, binding.field.height),
                true,
            )
            binding.field.sendAccessibilityEvent(AccessibilityEvent.TYPE_VIEW_FOCUSED)
        }
    }

    private fun discardReviewDraft() {
        reviewDraft = currentEditableDraft()
        reviewHasUnsavedChanges = false
        reviewValidationAttempted = false
        reviewValidationErrors.clear()
        temporaryConfirmationVisible = state.demoConfirmed
        render()
    }

    private fun confirmRevertDemo() {
        AlertDialog.Builder(this)
            .setTitle(R.string.review_revert_title)
            .setMessage(R.string.review_revert_message)
            .setNegativeButton(R.string.review_keep_editing, null)
            .setPositiveButton(R.string.review_revert_confirm) { _, _ ->
                state.revertReceipt()
                syntheticCollapsed.clear()
                reviewDraft = currentEditableDraft()
                reviewHasUnsavedChanges = false
                reviewSavedTemporarily = false
                reviewValidationAttempted = false
                reviewValidationErrors.clear()
                temporaryConfirmationVisible = false
                render()
            }
            .show()
    }

    private fun inventoryEmpty(
        id: Int, icon: Int, title: Int, message: Int, action: Int?, onAction: () -> Unit,
    ): View = ui.card {
        this.id = id
        gravity = Gravity.CENTER_HORIZONTAL
        addView(ui.icon(icon, tile = true))
        addView(sectionTitle(getString(title)).apply { gravity = Gravity.CENTER })
        addView(bodyText(getString(message)).apply { gravity = Gravity.CENTER })
        action?.let {
            addView(ui.actionButton(getString(it), PantryActionStyle.TERTIARY, action = onAction))
        }
    }

    private fun renderInventoryRows(container: LinearLayout, visible: List<InventoryItem>, today: LocalDate) {
        fun rows(items: List<InventoryItem>) = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(divider())
            items.forEachIndexed { index, item ->
                if (index > 0) addView(divider())
                addView(inventoryItemRow(item, today))
            }
        }

        val groups = sageCategoryGroups(state.inventory, visible)
        val matching = inventoryBrowse.query.isNotBlank() || inventoryBrowse.source != InventoryBrowseProjection.Source.ALL
        val overrides = if (matching) matchingInventoryGroupOverrides else inventoryGroupOverrides
        val initiallyOpen = matching || inventoryBrowse.sort != InventoryBrowseProjection.Sort.ORIGINAL
        val collapsed = groups.keys.filterNot { overrides[it] ?: initiallyOpen }.map { it.code }.toMutableSet()
        val sections = SageExpandableSections(this, ui, collapsed) { key, open ->
            overrides[checkNotNull(InventoryCategory.fromCode(key))] = open
        }
        container.addView(LinearLayout(this).apply {
            id = R.id.sage_inventory_groups
            orientation = LinearLayout.VERTICAL
            addView(sectionBar(getString(R.string.inventory_categories), sections.allAction()))
            groups.entries.forEachIndexed { index, (category, items) ->
                if (index > 0) addView(space(10))
                val count = resources.getQuantityString(R.plurals.home_inventory_count, items.size, items.size)
                addView(sections.add(category.code, inventoryCategoryLabel(category), rows(items), subtitle = count,
                    icon = inventoryCategoryIcon(category), compact = true, inventoryRow = true))
            }
            addView(space(6))
        })
    }

    private fun inventoryCategoryLabel(category: InventoryCategory): String = getString(when (category) {
        InventoryCategory.VEGETABLES_FRUITS -> R.string.category_vegetables_fruits
        InventoryCategory.DAIRY_EGGS -> R.string.category_dairy_eggs
        InventoryCategory.MEAT_SEAFOOD -> R.string.category_meat_seafood
        InventoryCategory.DRY_FOOD -> R.string.category_dry_food
        InventoryCategory.HOUSEHOLD_SUPPLIES -> R.string.category_household_supplies
        InventoryCategory.UNCATEGORIZED -> R.string.category_uncategorized
    })

    private fun inventoryCategoryIcon(category: InventoryCategory): Int = when (category) {
        InventoryCategory.VEGETABLES_FRUITS -> R.drawable.ic_sage_leaf
        InventoryCategory.DAIRY_EGGS -> R.drawable.ic_sage_milk
        InventoryCategory.MEAT_SEAFOOD -> R.drawable.ic_sage_fish
        InventoryCategory.DRY_FOOD -> R.drawable.ic_sage_grain
        InventoryCategory.HOUSEHOLD_SUPPLIES -> R.drawable.ic_sage_home
        InventoryCategory.UNCATEGORIZED -> R.drawable.ic_sage_package
    }

    private fun inventoryWarningLabel(warning: InventoryWarning): String = getString(when (warning) {
        InventoryWarning.EXPIRED -> R.string.inventory_expired
        InventoryWarning.EXPIRES_TODAY -> R.string.inventory_expires_today
        InventoryWarning.EXPIRING_SOON -> R.string.inventory_expiring_soon
        InventoryWarning.OUT_OF_STOCK -> R.string.inventory_out_of_stock
        InventoryWarning.LOW_STOCK -> R.string.inventory_low_stock
    })

    private fun inventorySourceLabel(source: InventoryBrowseProjection.Source): String? = when (source) {
        InventoryBrowseProjection.Source.BASELINE -> getString(R.string.inventory_source_demo)
        InventoryBrowseProjection.Source.RECEIPT_PREVIEW -> getString(R.string.inventory_source_preview)
        InventoryBrowseProjection.Source.MANUAL -> getString(R.string.inventory_source_manual)
        InventoryBrowseProjection.Source.LIVE -> getString(R.string.inventory_source_scanned)
        InventoryBrowseProjection.Source.STANDALONE -> getString(R.string.inventory_source_direct)
        InventoryBrowseProjection.Source.ALL -> null
    }

    private fun inventoryItemRow(item: InventoryItem, today: LocalDate): View = LinearLayout(this).apply {
        tag = item.id
        gravity = Gravity.CENTER_VERTICAL
        minimumHeight = dp(48)
        setPadding(dp(4), dp(5), dp(4), dp(5))
        val source = InventoryBrowseProjection.sourceOf(item)
        val sessionSource = when (source) {
            InventoryBrowseProjection.Source.BASELINE, InventoryBrowseProjection.Source.RECEIPT_PREVIEW ->
                inventorySourceLabel(source)
            else -> null
        }
        val expiry = item.household.expiryDate?.let {
            val label = when (it) {
                today -> getString(R.string.inventory_expiry_today)
                today.plusDays(1) -> getString(R.string.inventory_expiry_tomorrow)
                else -> PurchaseDateInput.display(it)
            }
            getString(R.string.inventory_expiry_short, label)
        }
        val warnings = item.warnings(today).map { it to inventoryWarningLabel(it) }
        addView(InventoryRowContent(this@MainActivity, ui, item.name, item.quantityLabel, expiry, sessionSource, warnings),
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        addView(ui.icon(R.drawable.ic_sage_right), LinearLayout.LayoutParams(dp(24), dp(24)).apply {
            marginStart = dp(4)
            topMargin = dp(6)
            gravity = Gravity.TOP
        })
        contentDescription = (listOfNotNull(item.name, getString(R.string.inventory_quantity_label, item.quantityLabel),
            expiry, inventorySourceLabel(source)) + warnings.map { it.second }).joinToString(". ")
        ui.markButton(this, inventoryRow = true)
        setOnClickListener { showInventoryItemDetails(item.id) }
    }

    private fun canEditInventory(id: String): Boolean =
        ManualInventoryStore.isDurableRowId(id) && !id.startsWith(ManualInventoryStore.LIVE_ROW_PREFIX)

    private fun restoreInventoryRowFocus(id: String, restoreKeyboard: Boolean, restoreReader: Boolean) {
        val results = inventoryResults ?: return
        results.post {
            if (currentScreen != Screen.INVENTORY || inventorySheet != null || inventoryResults !== results) return@post
            val row = results.findViewWithTag<View>(id)
            if (restoreKeyboard && !results.isInTouchMode) {
                val target = row?.takeIf { it.isShown } ?: inventoryBrowseCount
                target?.isFocusable = true
                target?.requestFocus()
            }
            if (restoreReader && row?.isShown == true) row.performAccessibilityAction(
                android.view.accessibility.AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS, null,
            )
        }
    }

    private fun showInventoryItemDetails(id: String) {
        val item = state.inventory.firstOrNull { it.id == id } ?: return
        val row = inventoryResults?.findViewWithTag<View>(id)
        val restoreReader = row?.isAccessibilityFocused == true
        val restoreKeyboard = row?.isFocused == true && !row.isInTouchMode
        lateinit var sheet: Dialog
        val body = LinearLayout(this).apply {
            this.id = R.id.sage_inventory_details
            orientation = LinearLayout.VERTICAL
        }
        val source = InventoryBrowseProjection.sourceOf(item)
        val sourceLabel = inventorySourceLabel(source)
        sourceLabel?.let { body.addView(bodyText(getString(R.string.inventory_source_field, it))) }
        val sourceState = when (source) {
            InventoryBrowseProjection.Source.MANUAL -> ManualInventoryStore.ROW_STATE
            InventoryBrowseProjection.Source.LIVE -> ManualInventoryStore.LIVE_ROW_STATE
            InventoryBrowseProjection.Source.STANDALONE -> ManualInventoryStore.STANDALONE_ROW_STATE
            else -> sourceLabel
        }
        if (item.state.isNotBlank() && item.state != sourceState) body.addView(bodyText(item.state))
        if (ManualInventoryStore.isDurableRowId(id)) {
            body.addView(bodyText(getString(R.string.inventory_category_value, inventoryCategoryLabel(item.household.category))))
            item.household.expiryDate?.let {
                body.addView(bodyText(getString(R.string.inventory_expiry_summary, PurchaseDateInput.display(it))))
            }
        }
        body.addView(space(8))
        val quantity = TextView(this, null, 0, R.style.TextAppearance_PantryProof_Display).apply {
            this.id = if (item.id == "stock-rice") R.id.inventory_stock_rice_value else View.NO_ID
            gravity = Gravity.CENTER
        }
        val label = bodyText(getString(R.string.sage_quantity))
        body.addView(label)
        val maximum = item.unit.maximum
        lateinit var decrease: View
        lateinit var increase: View
        fun updateQuantity() {
            val current = state.inventory.firstOrNull { it.id == id } ?: return
            val value = current.quantity
            quantity.text = current.quantityLabel
            val canDecrease = value >= current.unit.step
            val canIncrease = value + current.unit.step <= maximum
            val boundary = when {
                !canDecrease -> getString(R.string.inventory_minimum_hint)
                !canIncrease -> getString(R.string.inventory_maximum_hint)
                else -> null
            }
            quantity.contentDescription = listOfNotNull(
                getString(R.string.inventory_quantity_label, current.quantityLabel), boundary,
            ).joinToString(". ")
            val focused = decrease.hasFocus() && !canDecrease || increase.hasFocus() && !canIncrease
            decrease.isEnabled = canDecrease
            increase.isEnabled = canIncrease
            if (focused) {
                quantity.isFocusableInTouchMode = true
                quantity.requestFocus()
            }
        }
        fun step(delta: Int, label: String, description: Int, riceId: Int, tag: String) =
            ui.quantityButton(label, getString(description, item.name), true,
                if (id == "stock-rice") riceId else View.NO_ID) {
                if (adjustInventoryQuantity(id, delta)) updateQuantity()
            }.apply { this.tag = "$tag:$id" }
        decrease = step(-1, "−", R.string.inventory_decrease, R.id.inventory_stock_rice_decrease, "inventory-decrease")
        increase = step(1, "+", R.string.inventory_increase, R.id.inventory_stock_rice_increase, "inventory-increase")
        body.addView(LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            addView(decrease)
            addView(quantity, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(increase)
        })
        updateQuantity()
        if (canEditInventory(id)) {
            body.addView(space(12))
            body.addView(ui.actionButton(getString(R.string.inventory_edit_item), PantryActionStyle.PRIMARY,
                iconResource = R.drawable.ic_sage_edit) {
                state.inventory.firstOrNull { it.id == id }?.let { current ->
                    showInventoryItemEditor(current) { sheet.dismiss() }
                }
            }.apply {
                tag = "inventory-edit:$id"
                contentDescription = getString(R.string.inventory_edit_item_description, item.name)
            })
            body.addView(ui.actionButton(getString(R.string.inventory_delete_item), PantryActionStyle.DESTRUCTIVE,
                iconResource = R.drawable.ic_sage_trash) {
                confirmInventoryDeletion(item) { sheet.dismiss() }
            }.apply {
                tag = "inventory-delete:$id"
                contentDescription = getString(R.string.inventory_delete_item_description, item.name)
            })
        } else if (ManualInventoryStore.isDurableRowId(id)) {
            body.addView(ui.actionButton(getString(R.string.inventory_edit_metadata), PantryActionStyle.SECONDARY) {
                state.inventory.firstOrNull { it.id == id }?.let { current -> showStockMetadataEditor(current, sheet::dismiss) }
            })
        }
        sheet = showInventorySheet(item.name, body, onDismiss = { restoreInventoryRowFocus(id, restoreKeyboard, restoreReader) })
    }

    private fun inventoryUnitChoice(
        initial: InventoryUnit,
        onChanged: (InventoryUnit) -> Unit,
    ): View {
        val units = InventoryUnit.entries
        fun label(unit: InventoryUnit): String = unit.symbol.ifEmpty { getString(R.string.inventory_unit_unspecified) }
        var selected = initial
        lateinit var control: Button
        control = ui.actionButton(
            getString(R.string.inventory_unit_value, label(initial)), PantryActionStyle.SECONDARY,
        ) {
            ui.showChoicePopup(control, units.map(::label).toTypedArray(), selected.ordinal) { index ->
                selected = units[index]
                val value = getString(R.string.inventory_unit_value, label(selected))
                control.text = value
                control.contentDescription = value
                onChanged(selected)
            }
        }
        return control
    }

    private fun inventoryCategoryChoice(initial: InventoryCategory, onChanged: (InventoryCategory) -> Unit): View {
        var selected = initial
        lateinit var control: Button
        fun label() = getString(R.string.inventory_category_value, inventoryCategoryLabel(selected))
        control = ui.actionButton(label(), PantryActionStyle.SECONDARY, viewId = R.id.inventory_category) {
            val categories = InventoryCategory.entries
            ui.showChoicePopup(control, categories.map(::inventoryCategoryLabel).toTypedArray(), selected.ordinal,
                R.id.inventory_category_choices) { index ->
                selected = categories[index]
                control.text = label()
                control.contentDescription = label()
                onChanged(selected)
            }
        }
        return control
    }

    private inner class StockMetadataFields(form: LinearLayout, initial: InventoryMetadata) {
        private var category = initial.category
        private val expiry = reviewField("", getString(R.string.inventory_expiry_optional),
            initial.expiryDate?.let(PurchaseDateInput::display).orEmpty(), "", viewId = R.id.inventory_expiry)
        private val minimum = reviewField("", getString(R.string.inventory_minimum_optional),
            initial.minimumStock?.toPlainString().orEmpty(), getString(R.string.inventory_minimum_help),
            type = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL, viewId = R.id.inventory_minimum)

        init {
            configureManualDatePicker(expiry, expiry = true)
            form.addView(space(8))
            form.addView(inventoryCategoryChoice(category) { category = it })
            form.addView(expiry.container)
            val clear = ui.actionButton(getString(R.string.inventory_clear_expiry), PantryActionStyle.TERTIARY) {
                expiry.field.text.clear()
                applyReviewFieldError(expiry, null)
            }
            form.addView(clear)
            fun updateExpiry() {
                clear.visibility = if (expiry.field.text.isNotEmpty()) View.VISIBLE else View.GONE
                applyReviewFieldError(expiry, null)
            }
            expiry.field.addTextChangedListener(simpleTextWatcher(::updateExpiry))
            updateExpiry()
            form.addView(minimum.container)
        }

        fun clearMinimum() { minimum.field.text.clear() }

        fun read(unit: InventoryUnit): InventoryMetadata? {
            val rawDate = expiry.field.text.toString()
            val date = PurchaseDateInput.parse(rawDate)?.takeIf { it.year in 1..9999 }
            val rawMinimum = minimum.field.text.toString()
            val threshold = unit.parse(rawMinimum)?.takeIf(unit::stores)
            val badDate = rawDate.isNotBlank() && date == null
            val badMinimum = rawMinimum.isNotBlank() && threshold == null
            applyReviewFieldError(expiry, getString(R.string.v51_date_invalid).takeIf { badDate })
            applyReviewFieldError(minimum, getString(R.string.inventory_minimum_invalid).takeIf { badMinimum })
            if (badDate || badMinimum) {
                focusInvalidField(if (badDate) expiry else minimum)
                return null
            }
            return InventoryMetadata(category, date, threshold)
        }
    }

    private fun showStockMetadataEditor(item: InventoryItem, onSaved: () -> Unit) {
        val form = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val fields = StockMetadataFields(form, item.household)
        lateinit var dialog: Dialog
        val save = ui.actionButton(getString(R.string.sage_save_changes), PantryActionStyle.PRIMARY,
            viewId = android.R.id.button1) {
            val metadata = fields.read(item.unit) ?: return@actionButton
            if (!state.editInventoryMetadata(item.id, item.unit, metadata)) {
                showReviewMessage(getString(R.string.inventory_change_failed))
                return@actionButton
            }
            dialog.dismiss()
            refreshInventoryAfterChange()
            onSaved()
        }
        dialog = showInventorySheet(getString(R.string.inventory_edit_metadata), form, save)
    }

    private fun showInventoryItemEditor(item: InventoryItem? = null, onSaved: (() -> Unit)? = null) {
        val form = LinearLayout(this).apply {
            id = R.id.sage_inventory_editor
            orientation = LinearLayout.VERTICAL
        }
        val name = reviewField(
            "", getString(R.string.inventory_item_name), item?.name.orEmpty(), "",
            type = InputType.TYPE_CLASS_TEXT, viewId = R.id.inventory_item_name,
        ).also {
            it.field.setSingleLine(true)
            it.field.importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
            it.field.imeOptions = EditorInfo.IME_ACTION_NEXT or EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING
        }
        var unit = item?.unit ?: InventoryUnit.UNKNOWN
        val quantity = EditText(this).apply {
            id = R.id.inventory_item_quantity
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setSingleLine(true)
            minHeight = dp(48)
            gravity = Gravity.CENTER
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
            imeOptions = EditorInfo.IME_ACTION_DONE or EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING
            background = null
            setTextAppearance(R.style.TextAppearance_PantryProof_Display)
            setText(item?.quantity?.toPlainString().orEmpty())
        }
        form.addView(name.container)
        form.addView(space(8))
        fun maximum() = unit.maximum
        fun amount() = unit.parse(quantity.text.toString())?.takeIf(unit::stores)
        fun changeDraft(delta: Int) {
            val current = if (quantity.text.isBlank()) BigDecimal.ZERO else amount() ?: return
            val next = current + unit.step.multiply(delta.toBigDecimal())
            if (next.signum() >= 0 && next <= maximum()) {
                quantity.setText(next.toPlainString())
                quantity.setSelection(quantity.length())
            }
        }
        val decrease = ui.quantityButton("−", getString(R.string.inventory_decrease,
            getString(R.string.inventory_item_quantity)), false) { changeDraft(-1) }
        val increase = ui.quantityButton("+", getString(R.string.inventory_increase,
            getString(R.string.inventory_item_quantity)), true) { changeDraft(1) }
        fun stepperState() {
            val count = amount()
            decrease.isEnabled = count != null && count >= unit.step
            increase.isEnabled = quantity.text.isBlank() || count != null && count + unit.step <= maximum()
        }
        lateinit var metadataFields: StockMetadataFields
        if (unit == InventoryUnit.UNKNOWN) {
            form.addView(inventoryUnitChoice(unit) {
                if (unit != it) metadataFields.clearMinimum()
                unit = it
                quantity.error = null
                stepperState()
            })
        } else {
            form.addView(bodyText(getString(R.string.inventory_unit_value, unit.symbol)))
        }
        form.addView(bodyText(getString(R.string.inventory_item_quantity)).apply { labelFor = quantity.id })
        quantity.addTextChangedListener(simpleTextWatcher(::stepperState))
        stepperState()
        form.addView(LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            addView(decrease)
            addView(quantity, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(increase)
        })
        form.addView(bodyText(getString(R.string.sage_stepper_hint)).apply { gravity = Gravity.CENTER })
        metadataFields = StockMetadataFields(form, item?.household ?: InventoryMetadata())
        val feedback = bodyText(getString(R.string.inventory_change_failed)).apply {
            setTextColor(ui.color(R.color.pantry_error))
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
            visibility = View.GONE
        }
        form.addView(feedback)

        lateinit var dialog: Dialog
        if (item != null) form.addView(ui.actionButton(getString(R.string.inventory_delete_item),
            PantryActionStyle.DESTRUCTIVE, iconResource = R.drawable.ic_sage_trash) {
            confirmInventoryDeletion(item) { dialog.dismiss(); onSaved?.invoke() }
        })
        val save = ui.actionButton(
            getString(if (item == null) R.string.inventory_add_item else R.string.sage_save_changes),
            PantryActionStyle.PRIMARY, viewId = android.R.id.button1,
        ) {
            name.field.error = null
            quantity.error = null
            feedback.visibility = View.GONE
            val rawName = name.field.text.toString()
            val rawQuantity = quantity.text.toString()
            val metadata = metadataFields.read(unit) ?: return@actionButton
            val previouslySaved = if (item == null) state.inventory.mapTo(hashSetOf()) { it.id } else emptySet()
            val result = if (item == null) state.addInventoryItem(rawName, rawQuantity, unit, metadata)
                else state.editInventoryItem(item.id, rawName, rawQuantity, unit, metadata)
            when (result) {
                PantryUiState.InventoryChange.INVALID_NAME -> focusInvalidField(name.also {
                    applyReviewFieldError(it, getString(R.string.inventory_name_required))
                })
                PantryUiState.InventoryChange.INVALID_QUANTITY -> {
                    applyReviewFieldError(name, null)
                    quantity.error = if (unit == InventoryUnit.UNKNOWN) {
                        getString(R.string.inventory_quantity_invalid)
                    } else if (unit.fractionalPlaces == 0) {
                        getString(R.string.inventory_count_quantity_invalid, unit.maximum.toPlainString())
                    } else {
                        getString(R.string.inventory_decimal_quantity_invalid, unit.maximum.toPlainString())
                    }
                    quantity.requestFocus()
                }
                PantryUiState.InventoryChange.NOT_SAVED -> {
                    applyReviewFieldError(name, null)
                    feedback.visibility = View.VISIBLE
                    feedback.post {
                        feedback.requestRectangleOnScreen(Rect(0, 0, feedback.width, feedback.height), true)
                    }
                }
                PantryUiState.InventoryChange.SAVED -> {
                    pendingInventorySuccess = if (item == null) InventorySuccess(R.string.v51_item_added, rawName.trim(),
                        state.inventory.filter { it.id !in previouslySaved }.map { it.id })
                    else InventorySuccess(R.string.v51_changes_saved, rawName.trim())
                    dialog.dismiss()
                    refreshInventoryAfterChange()
                    onSaved?.invoke()
                }
            }
        }
        form.isFocusableInTouchMode = true
        form.requestFocus()
        dialog = showInventorySheet(
            getString(if (item == null) R.string.inventory_add_item else R.string.inventory_edit_item), form, save,
        )
    }

    private fun confirmInventoryDeletion(item: InventoryItem, onDeleted: (() -> Unit)? = null) {
        AlertDialog.Builder(this)
            .setTitle(R.string.inventory_delete_title)
            .setMessage(getString(R.string.inventory_delete_message, item.name))
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.inventory_delete_item) { _, _ ->
                if (state.deleteInventoryItem(item.id)) {
                    pendingInventorySuccess = InventorySuccess(R.string.v51_item_removed, item.name)
                    refreshInventoryAfterChange()
                    onDeleted?.invoke()
                } else {
                    AlertDialog.Builder(this)
                        .setTitle(R.string.inventory_change_failed_title)
                        .setMessage(R.string.inventory_change_failed)
                        .setPositiveButton(android.R.string.ok, null)
                        .show()
                }
            }
            .show().apply {
                getButton(AlertDialog.BUTTON_NEGATIVE).setAllCaps(false)
                getButton(AlertDialog.BUTTON_POSITIVE).apply {
                    setAllCaps(false)
                    setTextColor(ui.color(R.color.pantry_error))
                }
            }
    }

    private fun refreshInventoryAfterChange() {
        val scrollY = screenScrollView?.scrollY ?: 0
        render()
        screenScrollView?.let { scroll -> scroll.post { scroll.scrollTo(0, scrollY) } }
    }

    private fun adjustInventoryQuantity(id: String, delta: Int): Boolean {
        if (state.adjustInventory(id, delta)) {
            pendingInventorySuccess = InventorySuccess(R.string.v51_quantity_updated)
            updateInventoryBrowseResults()
            renderPendingInventorySuccess()
            return true
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.manual_inventory_quantity_failed_title)
            .setMessage(R.string.manual_inventory_quantity_failed)
            .setPositiveButton(android.R.string.ok, null)
            .show()
        return false
    }

    private fun sticky(action: View) {
        screenPrimary = action
    }

    private fun setScreen(
        title: String,
        showBack: Boolean,
        formWidth: Boolean = false,
        pinned: (LinearLayout.() -> Unit)? = null,
        content: LinearLayout.() -> Unit,
    ) {
        val inventory = currentScreen == Screen.INVENTORY
        val root = LinearLayout(this).apply {
            id = when (currentScreen) {
                Screen.DEVELOPMENT -> R.id.screen_development
                Screen.PREVIEW -> R.id.screen_preview
                Screen.DETAILS -> R.id.screen_details
                Screen.REVIEW -> R.id.screen_review
                Screen.MANUAL -> R.id.screen_manual
                Screen.MANUAL_REVIEW -> R.id.screen_manual_review
                Screen.INVENTORY -> R.id.screen_inventory
                Screen.PROCESSING_DEMO -> R.id.screen_processing_demo
                Screen.SELECTED_PROCESSING, Screen.T09_PROCESSING -> R.id.screen_selected_processing
                Screen.HISTORY, Screen.HISTORY_DETAIL -> View.NO_ID
            }
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(ui.color(R.color.pantry_surface))
            if (inventory) {
                isFocusableInTouchMode = true
                descendantFocusability = ViewGroup.FOCUS_BEFORE_DESCENDANTS
            }
        }
        inventoryImeVisible = false
        var keyboardVisible = false
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            view.setPadding(bars.left, 0, bars.right, maxOf(bars.bottom, ime.bottom))
            val keyboard = insets.isVisible(WindowInsetsCompat.Type.ime())
            if (inventory) {
                inventoryImeVisible = keyboard
                updateScanVisibility()
            }
            if (keyboard && !keyboardVisible) {
                (view.findFocus() as? EditText)?.let { field ->
                    field.post { field.requestRectangleOnScreen(Rect(0, 0, field.width, field.height), true) }
                }
            }
            keyboardVisible = keyboard
            insets
        }
        ViewCompat.setAccessibilityPaneTitle(root, title)
        val width = resources.configuration.screenWidthDp
        val maximum = if (formWidth) ui.dimen(R.dimen.pantry_form_max_width) else ui.dimen(R.dimen.pantry_content_max_width)
        val maximumDp = if (formWidth) 640 else 720
        val gutter = ui.pageGutter()
        fun centered(): FrameLayout.LayoutParams = FrameLayout.LayoutParams(
            if (width >= maximumDp) maximum else ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP or Gravity.CENTER_HORIZONTAL,
        )
        val stackedActions = inventory && ui.stacked()
        val headerActions = if (inventory) LinearLayout(this).apply {
            if (developmentAvailable) addView(developmentEntry())
            addView(receiptHistoryEntry())
            addView(addInventoryEntry())
        } else null
        root.addView(FrameLayout(this).apply {
            addView(ui.appBar(title, showBack, inventory, headerActions.takeUnless { stackedActions },
                onBack = ::handleBackNavigation), centered())
        })
        pinned?.let { build ->
            root.addView(FrameLayout(this).apply {
                addView(LinearLayout(this@MainActivity).apply {
                    id = R.id.inventory_pinned_controls
                    orientation = LinearLayout.VERTICAL
                    setPadding(gutter, 0, gutter, 0)
                    if (stackedActions) addView(headerActions, LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                    ).apply { gravity = Gravity.END })
                    addView(FrameLayout(this@MainActivity).apply {
                        id = R.id.inventory_success_host
                        setPadding(0, dp(4), 0, dp(6))
                        visibility = View.GONE
                    })
                    build()
                }, centered())
            })
        }
        screenPrimary = null
        val scanLayout = if (inventory) FrameLayout.LayoutParams(dp(56), dp(56), Gravity.BOTTOM or Gravity.END).apply {
            marginEnd = gutter
            bottomMargin = dp(16)
        } else null
        val body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(gutter, 0, gutter, if (inventory) 0 else dp(16))
            content()
        }
        val bodyHolder = FrameLayout(this).apply { addView(body, centered()) }
        val scrollView = ScrollView(this).apply {
            isFillViewport = true
            isSmoothScrollingEnabled = false
            scanLayout?.let {
                // The root already excludes system/IME insets. Clip scrolling content above the floating action.
                setPadding(0, 0, 0, inventoryScanClearance(it))
                clipToPadding = true
            }
            addView(bodyHolder)
        }
        screenScrollView = scrollView
        val viewport = FrameLayout(this).apply {
            addView(scrollView, FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT,
            ))
            scanLayout?.let { addView(ui.floatingScanAction(::showReceiptSources), it) }
        }
        root.addView(viewport, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        screenPrimary?.let { action ->
            root.addView(FrameLayout(this).apply {
                elevation = dp(3).toFloat()
                setBackgroundColor(ui.color(R.color.pantry_surface))
                addView(FrameLayout(this@MainActivity).apply {
                    setPadding(gutter, dp(8), gutter, dp(12))
                    addView(action, FrameLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                    ))
                }, centered())
            })
        }
        dismissInventorySuccess()
        setContentView(root)
        if (inventory) {
            root.requestFocus()
            renderPendingInventorySuccess()
        }
        if (inventory && inventoryScrollY > 0) {
            scrollView.post { scrollView.scrollTo(0, inventoryScrollY) }
        }
        ViewCompat.requestApplyInsets(root)
    }

    private fun writeReceipt(bundle: Bundle, prefix: String, receipt: Receipt) {
        bundle.putString("${prefix}StoreName", receipt.storeName)
        bundle.putString("${prefix}PurchaseDate", receipt.purchaseDate.toString())
        bundle.putString("${prefix}ReceiptTotal", receipt.receiptTotal.toPlainString())
        bundle.putStringArrayList("${prefix}ItemIds", ArrayList(receipt.items.map(ReceiptItem::id)))
        bundle.putStringArrayList(
            "${prefix}ItemDescriptions",
            ArrayList(receipt.items.map(ReceiptItem::description)),
        )
        bundle.putIntArray("${prefix}ItemQuantities", receipt.items.map(ReceiptItem::quantity).toIntArray())
        bundle.putStringArrayList(
            "${prefix}ItemUnitPrices",
            ArrayList(receipt.items.map { it.unitPrice?.toPlainString().orEmpty() }),
        )
        bundle.putStringArrayList(
            "${prefix}ItemLineTotals",
            ArrayList(receipt.items.map { it.lineTotal.toPlainString() }),
        )
    }

    private fun readReceipt(bundle: Bundle, prefix: String): Receipt? = runCatching {
        val ids = requireNotNull(bundle.getStringArrayList("${prefix}ItemIds"))
        val descriptions = requireNotNull(bundle.getStringArrayList("${prefix}ItemDescriptions"))
        val quantities = requireNotNull(bundle.getIntArray("${prefix}ItemQuantities"))
        val unitPrices = requireNotNull(bundle.getStringArrayList("${prefix}ItemUnitPrices"))
        val lineTotals = requireNotNull(bundle.getStringArrayList("${prefix}ItemLineTotals"))
        require(
            listOf(descriptions.size, quantities.size, unitPrices.size, lineTotals.size)
                .all { it == ids.size },
        )
        Receipt(
            storeName = requireNotNull(bundle.getString("${prefix}StoreName")),
            purchaseDate = LocalDate.parse(requireNotNull(bundle.getString("${prefix}PurchaseDate"))),
            items = ids.indices.map { index ->
                ReceiptItem(
                    id = ids[index],
                    description = descriptions[index],
                    quantity = quantities[index],
                    unitPrice = unitPrices[index].takeIf(String::isNotBlank)?.let(::BigDecimal),
                    lineTotal = BigDecimal(lineTotals[index]),
                )
            },
            receiptTotal = BigDecimal(requireNotNull(bundle.getString("${prefix}ReceiptTotal"))),
        )
    }.getOrNull()

    private fun writeInventory(bundle: Bundle, inventory: List<InventoryItem>) {
        bundle.putStringArrayList("inventoryIds", ArrayList(inventory.map(InventoryItem::id)))
        bundle.putStringArrayList("inventoryNames", ArrayList(inventory.map(InventoryItem::name)))
        bundle.putStringArrayList("inventoryDecimalQuantities", ArrayList(inventory.map { it.quantity.toPlainString() }))
        bundle.putStringArrayList("inventoryUnits", ArrayList(inventory.map { it.unit.code }))
        bundle.putStringArrayList("inventoryStates", ArrayList(inventory.map(InventoryItem::state)))
    }

    private fun readInventory(bundle: Bundle): List<InventoryItem>? = runCatching {
        val ids = requireNotNull(bundle.getStringArrayList("inventoryIds"))
        val names = requireNotNull(bundle.getStringArrayList("inventoryNames"))
        val quantities = if (bundle.containsKey("inventoryDecimalQuantities")) {
            requireNotNull(bundle.getStringArrayList("inventoryDecimalQuantities")).map(::BigDecimal)
        } else {
            requireNotNull(bundle.getIntArray("inventoryQuantities")).map { it.toBigDecimal() }
        }
        val states = requireNotNull(bundle.getStringArrayList("inventoryStates"))
        val units = if (bundle.containsKey("inventoryDecimalQuantities")) {
            requireNotNull(bundle.getStringArrayList("inventoryUnits")).map { requireNotNull(InventoryUnit.fromCode(it)) }
        } else {
            List(ids.size) { InventoryUnit.UNKNOWN }
        }
        require(listOf(names.size, quantities.size, states.size, units.size).all { it == ids.size })
        ids.indices.map { index ->
            InventoryItem(ids[index], names[index], quantities[index], states[index], units[index])
        }
    }.getOrNull()

    private fun writeDraft(bundle: Bundle, draft: EditableReceipt) {
        bundle.putBoolean("hasReviewDraft", true)
        bundle.putString("draftStoreName", draft.storeName)
        bundle.putString("draftPurchaseDate", draft.purchaseDate)
        bundle.putString("draftReceiptTotal", draft.receiptTotal)
        bundle.putString("manualConfirmationId", draft.manualConfirmationId)
        bundle.putStringArrayList("draftItemCategories", ArrayList(draft.items.map { it.category.code }))
        bundle.putStringArrayList("draftItemIds", ArrayList(draft.items.map(EditableReceiptItem::id)))
        bundle.putStringArrayList(
            "draftItemDescriptions",
            ArrayList(draft.items.map(EditableReceiptItem::description)),
        )
        bundle.putStringArrayList(
            "draftItemQuantities",
            ArrayList(draft.items.map(EditableReceiptItem::quantity)),
        )
        bundle.putStringArrayList(
            "draftItemUnitPrices",
            ArrayList(draft.items.map(EditableReceiptItem::unitPrice)),
        )
        bundle.putStringArrayList(
            "draftItemLineTotals",
            ArrayList(draft.items.map(EditableReceiptItem::lineTotal)),
        )
    }

    private fun readDraft(bundle: Bundle): EditableReceipt? = runCatching {
        if (!bundle.getBoolean("hasReviewDraft")) return@runCatching null
        val ids = requireNotNull(bundle.getStringArrayList("draftItemIds"))
        val descriptions = requireNotNull(bundle.getStringArrayList("draftItemDescriptions"))
        val quantities = requireNotNull(bundle.getStringArrayList("draftItemQuantities"))
        val unitPrices = requireNotNull(bundle.getStringArrayList("draftItemUnitPrices"))
        val lineTotals = requireNotNull(bundle.getStringArrayList("draftItemLineTotals"))
        val categories = bundle.getStringArrayList("draftItemCategories")
        require(categories == null || categories.size == ids.size)
        require(
            listOf(descriptions.size, quantities.size, unitPrices.size, lineTotals.size)
                .all { it == ids.size },
        )
        EditableReceipt(
            storeName = requireNotNull(bundle.getString("draftStoreName")),
            purchaseDate = requireNotNull(bundle.getString("draftPurchaseDate")),
            items = ids.indices.map { index ->
                EditableReceiptItem(
                    ids[index],
                    descriptions[index],
                    quantities[index],
                    unitPrices[index],
                    lineTotals[index],
                    categories?.get(index)?.let { requireNotNull(InventoryCategory.fromCode(it)) }
                        ?: InventoryCategory.UNCATEGORIZED,
                )
            }.toMutableList(),
            receiptTotal = requireNotNull(bundle.getString("draftReceiptTotal")),
            manualConfirmationId = bundle.getString("manualConfirmationId"),
        )
    }.getOrNull()

    private fun restoreSessionState(bundle: Bundle) {
        syntheticCollapsed.addAll(bundle.getStringArrayList("sageSyntheticCollapsed").orEmpty())
        manualCollapsed.addAll(bundle.getStringArrayList("sageManualCollapsed").orEmpty())
        InventoryCategory.entries.forEach { category ->
            val key = "inventoryCategory." + category.code
            if (bundle.containsKey(key)) inventoryGroupOverrides[category] = bundle.getBoolean(key)
            val matchingKey = "matchingInventoryCategory." + category.code
            if (bundle.containsKey(matchingKey)) matchingInventoryGroupOverrides[category] = bundle.getBoolean(matchingKey)
        }
        inventoryBrowse.query = bundle.getString("inventoryBrowseQuery").orEmpty()
        inventoryBrowse.sort = runCatching {
            InventoryBrowseProjection.Sort.valueOf(bundle.getString("inventoryBrowseSort").orEmpty())
        }.getOrDefault(InventoryBrowseProjection.Sort.ORIGINAL)
        inventoryBrowse.source = runCatching {
            InventoryBrowseProjection.Source.valueOf(bundle.getString("inventoryBrowseSource").orEmpty())
        }.getOrDefault(InventoryBrowseProjection.Source.ALL)
        val restoredReceipt = readReceipt(bundle, "receipt")
        val restoredInventory = readInventory(bundle)
        if (restoredInventory != null) {
            state.restore(
                restoredReceipt = restoredReceipt,
                restoredInventory = restoredInventory,
                restoredDemoConfirmed = bundle.getBoolean("demoConfirmed"),
            )
        }
        reviewDraft = readDraft(bundle)
        reviewHasUnsavedChanges = bundle.getBoolean("reviewHasUnsavedChanges")
        reviewSavedTemporarily = bundle.getBoolean("reviewSavedTemporarily")
        temporaryConfirmationVisible = bundle.getBoolean("temporaryConfirmationVisible")
        restoreTemporaryResultSheet = bundle.getBoolean("sageTemporaryResultSheet")
        reviewValidationAttempted = bundle.getBoolean("reviewValidationAttempted")
        val errorKeys = bundle.getStringArrayList("reviewErrorKeys").orEmpty()
        val errorValues = bundle.getStringArrayList("reviewErrorValues").orEmpty()
        reviewValidationErrors.clear()
        errorKeys.zip(errorValues).forEach { (key, value) ->
            reviewValidationErrors[key] = value
        }
    }

    private fun navigate(screen: Screen) {
        if (screen == currentScreen) return
        if (currentScreen == Screen.INVENTORY) inventoryScrollY = screenScrollView?.scrollY ?: 0
        backStack.addLast(currentScreen)
        currentScreen = screen
        render()
    }

    private fun returnToInventory() {
        switchToSyntheticDemo()
        backStack.clear()
        currentScreen = Screen.INVENTORY
        render()
    }

    private fun goBack() {
        currentScreen = backStack.pollLast() ?: Screen.INVENTORY
        render()
    }

    private fun confirmDiscardEdits(action: () -> Unit) {
        AlertDialog.Builder(this)
            .setTitle(R.string.review_discard_title)
            .setMessage(R.string.review_discard_message)
            .setNegativeButton(R.string.review_keep_editing, null)
            .setPositiveButton(R.string.review_discard_confirm) { _, _ ->
                reviewHasUnsavedChanges = false
                reviewDraft = currentEditableDraft()
                reviewValidationAttempted = false
                reviewValidationErrors.clear()
                temporaryConfirmationVisible = state.demoConfirmed
                action()
            }
            .show()
    }

    private fun currentEditableDraft(
        presentedReceipt: PresentedReceipt? =
            (state.presentationResult as? ReceiptPresentationUiResult.Available)?.receipt,
    ): EditableReceipt =
        state.receipt?.let(EditableReceipt::from)
            ?: EditableReceipt.from(requireNotNull(presentedReceipt))

    private fun LinearLayout.add(view: View) {
        addView(view)
    }

    private fun sectionTitle(textValue: String): TextView =
        TextView(this, null, 0, R.style.TextAppearance_PantryProof_SectionTitle).apply {
            text = textValue
        }

    private fun bodyText(textValue: String): TextView =
        TextView(this, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
            text = textValue
            setLineSpacing(0f, 1.18f)
        }

    private fun divider(): View =
        View(this).apply { setBackgroundColor(ui.color(R.color.pantry_outline_variant)) }.also {
            it.layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1))
        }

    private fun space(heightDp: Int): View =
        View(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(heightDp))
        }

    private fun rounded(
        fillColor: Int,
        radiusDp: Float,
        strokeColor: Int? = null,
        strokeWidth: Int = 1,
    ): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(fillColor)
            cornerRadius = dp(radiusDp.toInt()).toFloat()
            strokeColor?.let { setStroke(dp(strokeWidth), it) }
        }

    private fun simpleTextWatcher(onChange: () -> Unit): TextWatcher =
        object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = onChange()
            override fun afterTextChanged(s: Editable?) = Unit
        }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()

}
