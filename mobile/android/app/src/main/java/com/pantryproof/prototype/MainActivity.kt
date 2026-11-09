package com.pantryproof.prototype

import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.ClipData
import android.content.Intent
import android.graphics.Rect
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.pantryproof.prototype.data.MockReceiptPresentationSource
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.PresentedField
import com.pantryproof.prototype.data.PresentedFieldStatus
import com.pantryproof.prototype.data.PresentedReceipt
import com.pantryproof.prototype.data.PresentedReceiptItem
import com.pantryproof.prototype.data.Receipt
import com.pantryproof.prototype.data.ReceiptItem
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.ui.EditableReceipt
import com.pantryproof.prototype.ui.EditableReceiptItem
import com.pantryproof.prototype.ui.MoneyFormatter
import com.pantryproof.prototype.ui.PantryActionStyle
import com.pantryproof.prototype.ui.PantryBannerTone
import com.pantryproof.prototype.ui.PantryUiState
import com.pantryproof.prototype.ui.PantryUiComponents
import com.pantryproof.prototype.ui.ReceiptValidator
import java.math.BigDecimal
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.ArrayDeque
import java.util.Locale

@SuppressLint("SetTextI18n")
class MainActivity : ComponentActivity() {
    private enum class Screen {
        HOME, ADD_RECEIPT, PREVIEW, DETAILS, REVIEW, INVENTORY,
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
        val inputSurface: View,
        val helper: TextView,
        val defaultHelper: String,
        val container: View,
    )

    private val state = PantryUiState(MockReceiptPresentationSource())
    private val ui by lazy { PantryUiComponents(this) }
    private val backStack = ArrayDeque<Screen>()
    private var currentScreen = Screen.HOME
    private var selectedImageUri: Uri? = null
    private var previewMessage: String? = null
    private var reviewHasUnsavedChanges = false
    private var reviewDraft: EditableReceipt? = null
    private var reviewSavedTemporarily = false
    private var temporaryConfirmationVisible = false
    private var reviewValidationAttempted = false
    private val reviewValidationErrors = linkedMapOf<String, String>()
    private var screenScrollView: ScrollView? = null

    private val imagePicker = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        handleImageResult(result.resultCode, result.data)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        @Suppress("DEPRECATION")
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        selectedImageUri = savedInstanceState?.getString("selectedImageUri")?.let(Uri::parse)
        currentScreen = savedInstanceState?.getString("currentScreen")
            ?.let { runCatching { Screen.valueOf(it) }.getOrNull() }
            ?: Screen.HOME
        savedInstanceState?.getStringArrayList("backStack")
            ?.mapNotNull { runCatching { Screen.valueOf(it) }.getOrNull() }
            ?.forEach(backStack::addLast)
        previewMessage = savedInstanceState?.getString("previewMessage")
        savedInstanceState?.let(::restoreSessionState)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() = handleBackNavigation()
        })
        render()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("selectedImageUri", selectedImageUri?.toString())
        outState.putString("currentScreen", currentScreen.name)
        outState.putStringArrayList(
            "backStack",
            ArrayList(backStack.map(Screen::name)),
        )
        outState.putString("previewMessage", previewMessage)
        outState.putBoolean("reviewHasUnsavedChanges", reviewHasUnsavedChanges)
        outState.putBoolean("reviewSavedTemporarily", reviewSavedTemporarily)
        outState.putBoolean("temporaryConfirmationVisible", temporaryConfirmationVisible)
        outState.putBoolean("reviewValidationAttempted", reviewValidationAttempted)
        state.receipt?.let { writeReceipt(outState, "receipt", it) }
        writeInventory(outState, state.inventory)
        outState.putBoolean("demoConfirmed", state.demoConfirmed)
        reviewDraft?.let { writeDraft(outState, it) }
        outState.putStringArrayList("reviewErrorKeys", ArrayList(reviewValidationErrors.keys))
        outState.putStringArrayList("reviewErrorValues", ArrayList(reviewValidationErrors.values))
        super.onSaveInstanceState(outState)
    }

    private fun handleBackNavigation() {
        if (currentScreen == Screen.REVIEW && reviewHasUnsavedChanges) {
            confirmDiscardEdits { goBack() }
        } else if (currentScreen == Screen.HOME) {
            finish()
        } else {
            goBack()
        }
    }

    private fun handleImageResult(resultCode: Int, data: Intent?) {
        if (resultCode != RESULT_OK) return
        val uri = data?.data ?: data?.clipData?.firstUri()
        if (uri == null) {
            previewMessage = "The selected image could not be opened."
            navigate(Screen.PREVIEW)
            return
        }

        selectedImageUri = uri
        previewMessage = null
        val grantFlags = data?.flags ?: 0
        if (grantFlags and Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION != 0) {
            runCatching {
                contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION,
                )
            }
        }
        if (currentScreen == Screen.PREVIEW) {
            render()
        } else {
            navigate(Screen.PREVIEW)
        }
    }

    private fun ClipData.firstUri(): Uri? =
        if (itemCount > 0) getItemAt(0).uri else null

    private fun render() {
        when (currentScreen) {
            Screen.HOME -> renderHome()
            Screen.ADD_RECEIPT -> renderAddReceipt()
            Screen.PREVIEW -> renderPreview()
            Screen.DETAILS -> renderDetails()
            Screen.REVIEW -> renderReview()
            Screen.INVENTORY -> renderInventory()
        }
    }

    private fun renderHome() = setScreen(getString(R.string.app_name), false) {
        add(ui.homeHero())
        add(space(16))
        add(ui.actionButton(
            getString(R.string.home_add_receipt),
            PantryActionStyle.PRIMARY,
            viewId = R.id.home_add_receipt,
        ) { navigate(Screen.ADD_RECEIPT) })
        add(space(12))
        add(ui.banner(
            getString(R.string.home_local_note_title),
            getString(R.string.home_local_note_body),
            PantryBannerTone.INFO,
        ))
        add(space(20))
        add(ui.navigationCard(
            title = getString(R.string.home_inventory_title),
            description = resources.getQuantityString(
                R.plurals.home_inventory_count,
                state.inventory.size,
                state.inventory.size,
            ),
            actionLabel = getString(R.string.home_inventory_action),
            badge = getString(R.string.status_temporary),
            viewId = R.id.home_inventory,
        ) { navigate(Screen.INVENTORY) })
        add(space(12))
        add(ui.navigationCard(
            title = getString(R.string.home_demo_title),
            description = getString(R.string.home_demo_body),
            actionLabel = getString(R.string.home_demo_action),
            badge = getString(R.string.status_synthetic),
            viewId = R.id.home_synthetic_demo,
        ) {
            selectedImageUri = null
            previewMessage = null
            navigate(Screen.PREVIEW)
        })
        add(space(24))
        add(ui.banner(
            getString(R.string.home_boundary_title),
            getString(R.string.home_boundary_body),
            PantryBannerTone.DEMO,
        ))
    }

    private fun renderAddReceipt() = setScreen(getString(R.string.add_receipt_title), true) {
        add(ui.progressHeader(
            step = 1,
            title = getString(R.string.add_receipt_step_title),
            description = getString(R.string.add_receipt_step_description),
        ))
        add(space(18))
        add(ui.actionButton(
            getString(R.string.add_receipt_import),
            PantryActionStyle.PRIMARY,
            viewId = R.id.add_import_image,
        ) { launchImagePicker() })
        add(space(6))
        add(bodyText(getString(R.string.add_receipt_import_help)))
        add(space(16))
        add(ui.unavailableAction(
            getString(R.string.add_receipt_camera),
            getString(R.string.add_receipt_camera_help),
        ))
        add(space(16))
        add(ui.navigationCard(
            title = getString(R.string.add_receipt_demo),
            description = getString(R.string.add_receipt_demo_help),
            actionLabel = getString(R.string.home_demo_action),
            badge = getString(R.string.status_synthetic),
            viewId = R.id.add_use_demo,
        ) {
            selectedImageUri = null
            previewMessage = null
            navigate(Screen.PREVIEW)
        })
        add(space(20))
        add(ui.banner(
            getString(R.string.add_receipt_privacy_title),
            getString(R.string.add_receipt_privacy_body),
            PantryBannerTone.INFO,
        ))
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

    private fun renderPreview() = setScreen(getString(R.string.preview_title), true) {
        add(ui.progressHeader(
            step = 2,
            title = getString(R.string.preview_step_title),
            description = getString(R.string.preview_step_description),
        ))
        add(space(16))

        val uri = selectedImageUri
        val localImageAvailable = uri?.let(::canReadSelectedImage) == true
        when {
            uri == null -> {
                val presentation = state.presentationResult
                if (presentation is ReceiptPresentationUiResult.Available) {
                    add(ui.banner(
                        getString(R.string.preview_synthetic_status),
                        getString(R.string.preview_synthetic_status_body),
                        PantryBannerTone.SUCCESS,
                    ))
                    add(space(14))
                    add(syntheticReceiptPreview(presentation.receipt))
                    previewMessage?.let {
                        add(space(10))
                        add(ui.statePanel(
                            getString(R.string.selection_unavailable_title),
                            it,
                            PantryBannerTone.ERROR,
                        ))
                    }
                    add(space(18))
                    add(ui.actionButton(
                        getString(R.string.preview_view_sample_fields),
                        PantryActionStyle.PRIMARY,
                        viewId = R.id.preview_continue,
                    ) { navigate(Screen.DETAILS) })
                } else {
                    add(presentationStatePanel(presentation))
                }
                add(space(10))
                add(ui.actionButton(
                    getString(R.string.preview_choose_image),
                    PantryActionStyle.SECONDARY,
                ) { launchImagePicker() })
            }
            !localImageAvailable -> {
                add(ui.statePanel(
                    getString(R.string.preview_image_unavailable_title),
                    getString(R.string.preview_image_unavailable_body),
                    PantryBannerTone.ERROR,
                ))
                add(space(18))
                add(ui.actionButton(
                    getString(R.string.preview_choose_another),
                    PantryActionStyle.PRIMARY,
                    viewId = R.id.preview_choose_another,
                ) { launchImagePicker() })
                add(space(10))
                add(ui.actionButton(
                    getString(R.string.preview_use_demo_instead),
                    PantryActionStyle.SECONDARY,
                    viewId = R.id.preview_use_demo,
                ) {
                    selectedImageUri = null
                    previewMessage = null
                    render()
                })
            }
            else -> {
                add(ui.banner(
                    getString(R.string.preview_local_status),
                    getString(R.string.preview_local_status_body),
                    PantryBannerTone.INFO,
                ))
                add(space(14))
                add(selectedImagePreview(uri))
                add(space(14))
                add(ui.banner(
                    getString(R.string.preview_local_warning_title),
                    getString(R.string.preview_local_warning_body),
                    PantryBannerTone.DEMO,
                ))
                add(space(18))
                add(ui.actionButton(
                    getString(R.string.preview_continue_demo),
                    PantryActionStyle.PRIMARY,
                    viewId = R.id.preview_continue,
                ) { navigate(Screen.DETAILS) })
                add(space(10))
                add(ui.actionButton(
                    getString(R.string.preview_choose_another),
                    PantryActionStyle.SECONDARY,
                    viewId = R.id.preview_choose_another,
                ) { launchImagePicker() })
                add(space(6))
                add(ui.actionButton(
                    getString(R.string.preview_remove_image),
                    PantryActionStyle.TERTIARY,
                ) {
                    selectedImageUri = null
                    previewMessage = null
                    render()
                })
            }
        }
        add(space(6))
        add(ui.actionButton(
            getString(R.string.preview_cancel),
            PantryActionStyle.TERTIARY,
        ) { navigateHome() })
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
                append(presentedText(receipt.purchaseDate))
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

    private fun selectedImagePreview(uri: Uri): View {
        val container = ui.card { }
        val image = ImageView(this).apply {
            adjustViewBounds = true
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            minimumHeight = dp(200)
            maxHeight = dp(
                (resources.configuration.screenHeightDp * 0.52f)
                    .toInt()
                    .coerceIn(240, 460),
            )
            contentDescription = getString(R.string.preview_selected_image_description)
        }
        val result = runCatching { image.setImageURI(uri) }
        if (result.isFailure || image.drawable == null) {
            container.addView(ui.statePanel(
                getString(R.string.preview_image_unavailable_title),
                getString(R.string.preview_image_unavailable_body),
                PantryBannerTone.ERROR,
            ))
        } else {
            container.addView(
                image,
                LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT),
            )
        }
        return container
    }

    private fun canReadSelectedImage(uri: Uri): Boolean = runCatching {
        contentResolver.openInputStream(uri)?.use { true } ?: false
    }.getOrDefault(false)

    private fun renderDetails() = setScreen(getString(R.string.details_title), true) {
        add(ui.progressHeader(
            step = 3,
            title = getString(R.string.details_step_title),
            description = getString(R.string.details_step_description),
        ))
        add(space(16))
        add(ui.banner(
            getString(R.string.details_demo_title),
            getString(
                if (selectedImageUri == null) R.string.details_demo_body
                else R.string.details_local_demo_body,
            ),
            PantryBannerTone.DEMO,
        ))
        add(space(16))
        val available = state.presentationResult as? ReceiptPresentationUiResult.Available
        if (available == null) {
            add(presentationStatePanel(state.presentationResult))
        } else {
            val receipt = receiptForDetails(available.receipt)
            val missingOptionalCount = receipt.items.count {
                it.unitPrice.status == PresentedFieldStatus.MISSING
            }
            add(ui.card {
                addView(sectionTitle(getString(R.string.details_summary_title)))
                addView(space(8))
                addView(summaryRow(
                    getString(R.string.field_store_name),
                    presentedText(receipt.storeName),
                ))
                addView(divider())
                addView(summaryRow(
                    getString(R.string.field_purchase_date),
                    presentedDate(receipt.purchaseDate),
                ))
                addView(divider())
                addView(summaryRow(
                    getString(R.string.field_receipt_total),
                    presentedMoney(receipt.receiptTotal),
                    emphasize = receipt.receiptTotal.status == PresentedFieldStatus.EXTRACTED,
                ))
            })
            add(space(12))
            add(ui.statusChip(resources.getQuantityString(
                R.plurals.details_item_status,
                receipt.items.size,
                receipt.items.size,
                missingOptionalCount,
            )))
            add(space(20))
            add(sectionTitle(getString(R.string.details_items_title)))
            add(space(8))
            receipt.items.forEachIndexed { index, item ->
                add(receiptItemCard(index + 1, item))
                add(space(10))
            }
            add(space(8))
            add(ui.actionButton(
                getString(R.string.details_review_action),
                PantryActionStyle.PRIMARY,
                viewId = R.id.details_review,
            ) { navigate(Screen.REVIEW) })
        }
        add(space(10))
        add(ui.actionButton(
            getString(R.string.details_back_action),
            PantryActionStyle.SECONDARY,
        ) { goBack() })
    }

    private fun receiptItemCard(number: Int, item: PresentedReceiptItem): View = ui.card {
        id = when (number) {
            1 -> R.id.details_item_0
            2 -> R.id.details_item_1
            3 -> R.id.details_item_2
            else -> View.NO_ID
        }
        addView(TextView(this@MainActivity, null, 0, R.style.TextAppearance_PantryProof_Label).apply {
            text = getString(R.string.details_item_number, number).uppercase()
            setTextColor(ui.color(R.color.pantry_primary))
            letterSpacing = 0.12f
        })
        addView(TextView(this@MainActivity, null, 0, R.style.TextAppearance_PantryProof_ItemTitle).apply {
            text = presentedText(item.description)
            setPadding(0, dp(6), 0, dp(8))
        })
        addView(detailMetric(getString(R.string.field_quantity), presentedText(item.quantity)))
        addView(detailMetric(
            getString(R.string.field_unit_price),
            if (item.unitPrice.status == PresentedFieldStatus.MISSING) {
                getString(R.string.details_unit_price_missing)
            } else {
                presentedMoney(item.unitPrice)
            },
            optionalMissing = item.unitPrice.status == PresentedFieldStatus.MISSING,
        ))
        addView(detailMetric(
            getString(R.string.field_line_total),
            presentedMoney(item.lineTotal),
        ))
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
            LocalDate.parse(requireNotNull(field.value)).format(
                DateTimeFormatter.ofPattern(
                    "d MMMM yyyy",
                    Locale.Builder().setLanguage("en").setRegion("MY").build(),
                ),
            )
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

    private fun presentationStatePanel(result: ReceiptPresentationUiResult): View =
        when (result) {
            is ReceiptPresentationUiResult.Available -> ui.statePanel(
                getString(R.string.presentation_available_title),
                getString(R.string.presentation_available_body),
                PantryBannerTone.SUCCESS,
            )
            is ReceiptPresentationUiResult.ProcessingUnavailable -> ui.statePanel(
                getString(R.string.presentation_unavailable_title),
                getString(R.string.presentation_unavailable_body, result.failureCode),
                PantryBannerTone.INFO,
            )
            is ReceiptPresentationUiResult.ProcessingFailed -> ui.statePanel(
                getString(R.string.presentation_failed_title),
                getString(R.string.presentation_failed_body, result.failureCode),
                PantryBannerTone.ERROR,
            )
            is ReceiptPresentationUiResult.InsufficientEvidence -> ui.statePanel(
                getString(R.string.presentation_insufficient_title),
                getString(R.string.presentation_insufficient_body),
                PantryBannerTone.INFO,
            )
            is ReceiptPresentationUiResult.Rejected -> ui.statePanel(
                getString(R.string.presentation_rejected_title),
                getString(R.string.presentation_rejected_body, result.issue.code),
                PantryBannerTone.ERROR,
            )
        }

    private fun renderReview() = setScreen(getString(R.string.review_title), true, formWidth = true) {
        add(ui.progressHeader(
            step = 4,
            title = getString(R.string.review_step_title),
            description = getString(R.string.review_step_description),
        ))
        add(space(16))
        val available = state.presentationResult as? ReceiptPresentationUiResult.Available
        if (available == null) {
            add(presentationStatePanel(state.presentationResult))
            add(space(10))
            add(ui.actionButton(
                getString(R.string.review_back_action),
                PantryActionStyle.TERTIARY,
            ) { goBack() })
            return@setScreen
        }
        val draft = reviewDraft ?: currentEditableDraft(available.receipt).also { reviewDraft = it }
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
            ) { navigate(Screen.INVENTORY) })
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
        add(sectionTitle(getString(R.string.review_receipt_section)))
        add(space(10))

        val storeField = reviewField(
            key = "storeName",
            label = getString(R.string.field_store_name),
            value = draft.storeName,
            helper = getString(R.string.review_required_helper),
        )
        val dateField = reviewField(
            key = "purchaseDate",
            label = getString(R.string.field_purchase_date),
            value = draft.purchaseDate,
            helper = getString(R.string.review_date_helper),
            type = InputType.TYPE_CLASS_DATETIME,
        )
        add(storeField.container)
        add(space(10))
        add(dateField.container)
        add(space(20))
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
            add(ui.card {
                addView(TextView(
                    this@MainActivity,
                    null,
                    0,
                    R.style.TextAppearance_PantryProof_Label,
                ).apply {
                    text = getString(R.string.review_item_number, index + 1).uppercase()
                    setTextColor(ui.color(R.color.pantry_primary))
                    letterSpacing = 0.12f
                })
                addView(space(10))
                addView(description.container)
                addView(space(10))
                addView(quantity.container)
                addView(space(10))
                addView(unitPrice.container)
                addView(space(10))
                addView(lineTotal.container)
            })
            add(space(10))
        }

        val receiptTotal = reviewField(
            key = "receiptTotal",
            label = getString(R.string.field_receipt_total),
            value = draft.receiptTotal,
            helper = getString(R.string.review_money_helper),
            type = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL,
            prefix = "RM",
        )
        add(receiptTotal.container)
        add(space(18))

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
        allFields.forEachIndexed { index, binding ->
            binding.field.imeOptions = if (index == allFields.lastIndex) {
                EditorInfo.IME_ACTION_DONE
            } else {
                EditorInfo.IME_ACTION_NEXT
            }
            applyReviewFieldError(binding, reviewValidationErrors[binding.key])
            binding.field.addTextChangedListener(simpleTextWatcher {
                val changed = draft.updateField(binding.key, binding.field.text.toString())
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
                }
            })
        }

        fun validateAndApply(confirm: Boolean) {
            val result = ReceiptValidator.validate(draft)
            reviewValidationAttempted = true
            reviewValidationErrors.clear()
            reviewValidationErrors.putAll(result.errors)
            allFields.forEach { applyReviewFieldError(it, result.errors[it.key]) }
            updateErrorSummary()
            if (!result.isValid) {
                result.firstInvalidFieldKey
                    ?.let { firstKey -> allFields.firstOrNull { it.key == firstKey } }
                    ?.let(::focusInvalidField)
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
        }

        add(ui.actionButton(
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
        add(space(4))
        add(ui.actionButton(
            getString(R.string.review_back_action),
            PantryActionStyle.TERTIARY,
        ) {
            if (reviewHasUnsavedChanges) confirmDiscardEdits { goBack() } else goBack()
        })
        if (temporaryConfirmationVisible && state.demoConfirmed) {
            add(space(6))
            add(ui.actionButton(
                getString(R.string.review_return_home),
                PantryActionStyle.TERTIARY,
            ) { navigateHome() })
        }
    }

    private fun renderInventory() = setScreen(getString(R.string.inventory_title), true) {
        add(ui.banner(
            getString(R.string.inventory_banner_title),
            getString(
                if (state.demoConfirmed) R.string.inventory_banner_confirmed
                else R.string.inventory_banner_mock,
            ),
            PantryBannerTone.SUCCESS,
        ))
        add(space(16))
        add(TextView(this@MainActivity, null, 0, R.style.TextAppearance_PantryProof_Body).apply {
            id = R.id.inventory_summary
            text = resources.getQuantityString(
                R.plurals.inventory_summary,
                state.inventory.size,
                state.inventory.size,
            )
        })
        add(space(14))
        if (state.inventory.isEmpty()) {
            add(ui.statePanel(
                getString(R.string.inventory_empty_title),
                getString(R.string.inventory_empty_body),
                PantryBannerTone.INFO,
            ))
        } else {
            state.inventory.forEach { item ->
                add(inventoryItemCard(item))
                add(space(10))
            }
        }
        add(space(8))
        add(ui.actionButton(
            getString(R.string.inventory_add_receipt),
            PantryActionStyle.SECONDARY,
        ) { navigate(Screen.ADD_RECEIPT) })
        add(space(8))
        add(ui.actionButton(
            getString(R.string.inventory_back_home),
            PantryActionStyle.TERTIARY,
        ) { navigateHome() })
    }

    private fun summaryRow(label: String, value: String, emphasize: Boolean = false): View =
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
                    if (emphasize) R.color.pantry_primary else R.color.pantry_on_surface,
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

    private fun detailMetric(
        label: String,
        value: String,
        optionalMissing: Boolean = false,
    ): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(0, dp(7), 0, dp(7))
        addView(TextView(
            this@MainActivity,
            null,
            0,
            R.style.TextAppearance_PantryProof_Label,
        ).apply { text = label })
        addView(TextView(
            this@MainActivity,
            null,
            0,
            R.style.TextAppearance_PantryProof_Body,
        ).apply {
            text = value
            setTextColor(ui.color(
                if (optionalMissing) R.color.pantry_on_surface_variant
                else R.color.pantry_on_surface,
            ))
            typeface = if (optionalMissing) Typeface.DEFAULT else Typeface.DEFAULT_BOLD
            setPadding(0, dp(3), 0, 0)
        })
    }

    private fun reviewField(
        key: String,
        label: String,
        value: String,
        helper: String,
        type: Int = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES,
        prefix: String? = null,
    ): ReviewFieldUi {
        val allowWrap = type and InputType.TYPE_MASK_CLASS == InputType.TYPE_CLASS_TEXT
        val input = EditText(this).apply {
            id = reviewFieldId(key)
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
            minHeight = dp(22)
        }
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
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
        binding.helper.setTextColor(ui.color(
            if (error == null) R.color.pantry_on_surface_variant else R.color.pantry_error,
        ))
        binding.field.error = error
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

    private fun inventoryItemCard(item: InventoryItem): View = ui.card {
        addView(TextView(
            this@MainActivity,
            null,
            0,
            R.style.TextAppearance_PantryProof_ItemTitle,
        ).apply { text = item.name })
        val isReceiptPreview = item.id.startsWith("receipt-")
        addView(
            if (isReceiptPreview) {
                ui.statusChip(getString(R.string.inventory_item_source))
            } else {
                TextView(
                    this@MainActivity,
                    null,
                    0,
                    R.style.TextAppearance_PantryProof_Body,
                ).apply { text = item.state }
            },
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = dp(6) },
        )
        val atMinimum = item.quantity == PantryUiState.MIN_INVENTORY_QUANTITY
        val atMaximum = item.quantity == PantryUiState.MAX_INVENTORY_QUANTITY
        val boundaryHint = when {
            atMinimum -> getString(R.string.inventory_minimum_hint)
            atMaximum -> getString(R.string.inventory_maximum_hint)
            else -> null
        }
        addView(TextView(
            this@MainActivity,
            null,
            0,
            R.style.TextAppearance_PantryProof_Label,
        ).apply {
            text = getString(R.string.inventory_quantity_label, item.quantity)
            contentDescription = listOfNotNull(text.toString(), boundaryHint).joinToString(". ")
            setPadding(0, dp(14), 0, dp(7))
        })
        addView(LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(ui.quantityButton(
                label = "−",
                description = getString(R.string.inventory_decrease, item.name),
                enabled = !atMinimum,
                viewId = if (item.id == "stock-rice") {
                    R.id.inventory_stock_rice_decrease
                } else {
                    View.NO_ID
                },
            ) {
                state.adjustInventory(item.id, -1)
                render()
            })
            addView(TextView(
                this@MainActivity,
                null,
                0,
                R.style.TextAppearance_PantryProof_SectionTitle,
            ).apply {
                id = if (item.id == "stock-rice") {
                    R.id.inventory_stock_rice_value
                } else {
                    View.NO_ID
                }
                text = item.quantity.toString()
                gravity = Gravity.CENTER
                minWidth = dp(64)
                setPadding(dp(8), 0, dp(8), 0)
                contentDescription = getString(R.string.inventory_quantity_label, item.quantity)
            })
            addView(ui.quantityButton(
                label = "+",
                description = getString(R.string.inventory_increase, item.name),
                enabled = !atMaximum,
                viewId = if (item.id == "stock-rice") {
                    R.id.inventory_stock_rice_increase
                } else {
                    View.NO_ID
                },
            ) {
                state.adjustInventory(item.id, 1)
                render()
            })
        })
    }

    private fun setScreen(
        title: String,
        showBack: Boolean,
        formWidth: Boolean = false,
        content: LinearLayout.() -> Unit,
    ) {
        val root = LinearLayout(this).apply {
            id = when (currentScreen) {
                Screen.HOME -> R.id.screen_home
                Screen.ADD_RECEIPT -> R.id.screen_add_receipt
                Screen.PREVIEW -> R.id.screen_preview
                Screen.DETAILS -> R.id.screen_details
                Screen.REVIEW -> R.id.screen_review
                Screen.INVENTORY -> R.id.screen_inventory
            }
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(ui.color(R.color.pantry_surface))
        }
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val navigationBars = insets.getInsets(WindowInsetsCompat.Type.navigationBars())
            view.setPadding(0, 0, 0, navigationBars.bottom)
            insets
        }
        ViewCompat.setAccessibilityPaneTitle(root, title)
        root.addView(ui.appBar(title, showBack) {
            if (currentScreen == Screen.REVIEW && reviewHasUnsavedChanges) {
                confirmDiscardEdits { goBack() }
            } else {
                goBack()
            }
        })
        val pageGutter = resources.getDimensionPixelSize(
            if (resources.configuration.screenWidthDp >= 600) {
                R.dimen.pantry_page_gutter_wide
            } else {
                R.dimen.pantry_page_gutter
            },
        )
        val body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pageGutter, pageGutter, pageGutter, dp(32))
            content()
        }
        val bodyHolder = FrameLayout(this).apply {
            val maximumWidth = if (formWidth) {
                ui.dimen(R.dimen.pantry_form_max_width)
            } else {
                dp(720)
            }
            addView(
                body,
                FrameLayout.LayoutParams(
                    if (resources.configuration.screenWidthDp >= 720) maximumWidth
                    else ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                    Gravity.TOP or Gravity.CENTER_HORIZONTAL,
                ),
            )
        }
        val scrollView = ScrollView(this).apply {
            isFillViewport = true
            addView(bodyHolder)
        }
        screenScrollView = scrollView
        root.addView(
            scrollView,
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f),
        )
        setContentView(root)
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
        bundle.putIntArray("inventoryQuantities", inventory.map(InventoryItem::quantity).toIntArray())
        bundle.putStringArrayList("inventoryStates", ArrayList(inventory.map(InventoryItem::state)))
    }

    private fun readInventory(bundle: Bundle): List<InventoryItem>? = runCatching {
        val ids = requireNotNull(bundle.getStringArrayList("inventoryIds"))
        val names = requireNotNull(bundle.getStringArrayList("inventoryNames"))
        val quantities = requireNotNull(bundle.getIntArray("inventoryQuantities"))
        val states = requireNotNull(bundle.getStringArrayList("inventoryStates"))
        require(listOf(names.size, quantities.size, states.size).all { it == ids.size })
        ids.indices.map { index ->
            InventoryItem(ids[index], names[index], quantities[index], states[index])
        }
    }.getOrNull()

    private fun writeDraft(bundle: Bundle, draft: EditableReceipt) {
        bundle.putBoolean("hasReviewDraft", true)
        bundle.putString("draftStoreName", draft.storeName)
        bundle.putString("draftPurchaseDate", draft.purchaseDate)
        bundle.putString("draftReceiptTotal", draft.receiptTotal)
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
                )
            }.toMutableList(),
            receiptTotal = requireNotNull(bundle.getString("draftReceiptTotal")),
        )
    }.getOrNull()

    private fun restoreSessionState(bundle: Bundle) {
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
        backStack.addLast(currentScreen)
        currentScreen = screen
        render()
    }

    private fun navigateHome() {
        backStack.clear()
        currentScreen = Screen.HOME
        render()
    }

    private fun goBack() {
        currentScreen = if (backStack.isEmpty()) Screen.HOME else backStack.removeLast()
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
    ): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(fillColor)
            cornerRadius = dp(radiusDp.toInt()).toFloat()
            strokeColor?.let { setStroke(dp(1), it) }
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
