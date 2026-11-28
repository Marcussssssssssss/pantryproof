# PantryProof Android UI source guide

Open **D:\PantryProof\mobile\android** in Android Studio. Shared visual Kotlin files are in **app/src/main/java/com/pantryproof/prototype/ui/**. Search for the function or class shown below. The physical folder groups the visual source, and the Kotlin package declarations preserve the original class identities.

| Screen or UI surface | Source file | Rendering function |
|---|---|---|
| Inventory launch, sticky branding and floating scan action | MainActivity.kt, PantryUiComponents.kt | renderInventory(), setScreen(), floatingScanAction() |
| Receipt source sheet and image-input recovery | MainActivity.kt, PantryUiComponents.kt | showReceiptSources(), showInventorySheet(), imageInputNoticePanel(), bottomSheet() |
| Synthetic receipt preview | MainActivity.kt | renderPreview(), syntheticReceiptPreview() |
| Camera or imported-image preview | MainActivity.kt | renderPreview(), selectedImagePreview() |
| Zoom and full-screen crop editor | MainActivity.kt, SageCropEditor.kt, ReceiptImageViews.kt | selectedImagePreview(), showCropEditor(), showSageCropEditor(), ZoomReceiptView.onDraw(), ReceiptCropView.onDraw() |
| Synthetic Processing Demo | MainActivity.kt | renderProcessingDemo() |
| Selected-image simulated processing and result | MainActivity.kt | renderSelectedImageProcessing(), presentationStatePanel(), receiptItemCard() |
| T09 LIVE processing and result | MainActivity.kt | renderSelectedImageProcessing(live = true), liveProcessingPanel() |
| Receipt Details | MainActivity.kt | renderDetails(), receiptSummary(), receiptItemCard(), receiptImageAction(), presentationStatePanel() |
| Synthetic receipt review and temporary confirmation | MainActivity.kt | renderReview(), reviewField(), applyReviewFieldError(), showTemporaryReceiptResult() |
| Synthetic review discard and revert dialogs | MainActivity.kt | confirmDiscardEdits(), confirmRevertDemo() |
| Manual receipt entry, date input and image dialog | MainActivity.kt, PurchaseDateInput.kt, SageExpandableSections.kt | renderManualReceipt(), configureManualDatePicker(), PurchaseDateInput.install(), selectedImagePreview(), confirmDiscardManualDraft() |
| Full-screen manual receipt pre-commit review | MainActivity.kt | renderManualReceiptReview(), manualReceiptPresentation(), receiptSummary(), receiptItemCard() |
| Seven-field receipt review, candidate actions and exact source crops | MainActivity.kt, LiveReceiptReviewDraft.kt | renderLiveReceiptReview(), showFieldEvidence(), addFieldSource(), showBulkOffer() |
| Confirmation modes and incomplete-purchase acknowledgement | MainActivity.kt, LiveReceiptReviewDraft.kt | chooseReceiptConfirmation(), showFinalConfirmation(), confirmation() |
| Receipt history, read-only details and deletion | MainActivity.kt, data/ReceiptHistory.kt | renderReceiptHistory(), renderReceiptHistoryDetail(), confirmReceiptDeletion(), receiptHistoryMonths() |
| Submitted frame and original-image retention | MainActivity.kt, image/PreparedReceiptImage.kt | renderPreview(), renderSelectedImageProcessing(), uploadBytes(), originalBytes() |
| Household inventory, search, sort, filters, source badges and quantities | MainActivity.kt | renderInventory(), inventorySearchRow(), PantryUiComponents.showChoicePopup(), updateInventoryBrowseResults(), renderInventoryRows(), inventoryItemRow(), adjustInventoryQuantity() |
| Inventory add/edit, deletion and refresh | MainActivity.kt | showInventoryItemDetails(), showInventoryItemEditor(), confirmInventoryDeletion(), refreshInventoryAfterChange(), restoreInventoryRowFocus() |
| Inventory success notification | MainActivity.kt, PantryUiComponents.kt | renderPendingInventorySuccess(), dismissInventorySuccess(), inventorySuccess() |
| T09 LIVE Debug Configuration | app/src/t09Live/java/com/pantryproof/prototype/T09DebugConfigurationActivity.kt | onCreate(), applyConfiguration() |

- MainActivity.setScreen() builds the shared frame and render() dispatches screens. Inventory is the root and pins the household count and browse controls above the list. The scan button opens a modal source sheet. Receipt stages use one sticky primary action where applicable. handleBackNavigation(), navigate(), returnToInventory(), and goBack() handle navigation.
- PantryUiComponents.kt provides the Sage app bar, floating scan control, progress header, banners, buttons, cards, source cards, bottom sheets, and status chips. SageExpandableSections.kt handles inventory and form expansion. SageInventoryGroups.kt checks whether category grouping can preserve the projected inventory order. SageReceiptScanView.kt draws the active-state scan indicator. ReceiptImageViews.kt contains ZoomReceiptView and ReceiptCropView for custom drawing and gestures. SageCropEditor.kt presents the same normalized crop in a full-screen dialog with a separate unapplied draft.
- Visual resources are in app/src/main/res/values/ for strings, colors, dimensions, IDs and styles, values-v27/ for the theme override, and drawable/ for the original app asset, calendar, Sage outline icons, and dialog background. Layouts are built in Kotlin.
- The T09 configuration Activity is declared as non-exported in app/src/t09Live/AndroidManifest.xml. Its strings are in app/src/t09Live/res/values/t09_debug_configuration_strings.xml. The debuggable-only development destination (renderDevelopment()) checks T09 capability and component availability before showing configuration. S04 Fake uses the shared UI and keeps its binding, network configuration and instrumentation in the existing S04 source sets.

## Local review and inventory

- The T09 LIVE candidate explicitly requests `receipt-review-v1` over the emulator's `http://10.0.2.2:8765` alias. `T09HttpTransport` binds the request to the exact prepared PNG and passes the original response bytes and submitted dimensions to `ReceiptReviewV1Decoder`. Candidate review uses only the current result. The canonical fixture directory is shared, with fixture assets included only in the test APK.
- `LiveReceiptReviewDraft` keeps user actions separate from the backend record. Inclusion and stock units are explicit. The user applies edits in a field dialog, approves a displayed list for bulk acceptance, and confirms inventory only or inventory and receipt in a separate dialog. For a known omitted row, mark it in the review to block history admission.
- `InventoryUnit` supports `each`, `g`, `kg`, `mL`, and `L`. `each` requires a whole number and permits up to 999999. Metric units preserve up to three fractional places through 999999.999, with a 0.001 adjustment step in the stored unit. An unknown unit preserves the legacy whole range of 0–99. The app creates independent stock rows, leaves unit conversion to explicit user entry and preserves the exact receipt quantity separately from stock. The standalone editor can assign a supported unit to an unknown row. The manual receipt workflow continues to enter whole quantities.
- `ManualInventoryStore` reads versions 1–3 and writes version 3 on the next successful mutation. It preserves old row IDs and quantities, keeps legacy units unknown and carries forward the identities of previously saved scanned receipts. Version 3 publishes rows, purchase history, a consumed-confirmation ledger and acknowledgement markers in one atomic replacement. History evidence and opt-in originals are synced before publication. The next launch reports any saved confirmation awaiting acknowledgement.
- The original-image option starts off and remembers the last choice. It applies only to the history-saving mode. Removing history also releases its app-owned original and review evidence. The stock and consumed confirmation entry stay in the snapshot. New confirmed manual purchases use the same atomic ledger and history with a manual source, without inventing backend evidence. Earlier manual stock remains inventory-only.

- Stock metadata is separate from the receipt snapshot. Item sheets edit category, optional expiry and optional minimum in the stock unit. Scanned items expose only metadata editing and their existing quantity adjustments. Category cards preserve the projected order and yield to a flat list when that order interleaves categories. The inventory screen recalculates expiry warnings against the current local date.
