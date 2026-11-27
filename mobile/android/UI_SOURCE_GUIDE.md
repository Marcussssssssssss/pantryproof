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
| Editable LIVE receipt review and item selection | MainActivity.kt | renderLiveReceiptReview(), liveReviewField() |
| LIVE inventory confirmation dialog | MainActivity.kt | confirmLiveReview() |
| Household inventory, search, sort, filters, source badges and quantities | MainActivity.kt | renderInventory(), inventorySearchRow(), PantryUiComponents.showChoicePopup(), updateInventoryBrowseResults(), renderInventoryRows(), inventoryItemRow(), adjustInventoryQuantity() |
| Inventory add/edit, deletion and refresh | MainActivity.kt | showInventoryItemDetails(), showInventoryItemEditor(), confirmInventoryDeletion(), refreshInventoryAfterChange(), restoreInventoryRowFocus() |
| Inventory success notification | MainActivity.kt, PantryUiComponents.kt | renderPendingInventorySuccess(), dismissInventorySuccess(), inventorySuccess() |
| T09 LIVE Debug Configuration | app/src/t09Live/java/com/pantryproof/prototype/T09DebugConfigurationActivity.kt | onCreate(), applyConfiguration() |

- MainActivity.setScreen() builds the shared frame and render() dispatches screens. Inventory is the root and pins the household count and browse controls above the list. The scan button opens a modal source sheet. Receipt stages use one sticky primary action where applicable. handleBackNavigation(), navigate(), returnToInventory(), and goBack() handle navigation.
- PantryUiComponents.kt provides the Sage app bar, floating scan control, progress header, banners, buttons, cards, source cards, bottom sheets, and status chips. SageExpandableSections.kt handles inventory and form expansion. SageInventoryGroups.kt checks whether source grouping can preserve the projected inventory order. SageReceiptScanView.kt draws the active-state scan indicator. ReceiptImageViews.kt contains ZoomReceiptView and ReceiptCropView for custom drawing and gestures. SageCropEditor.kt presents the same normalized crop in a full-screen dialog with a separate unapplied draft.
- Visual resources are in app/src/main/res/values/ for strings, colors, dimensions, IDs and styles, values-v27/ for the theme override, and drawable/ for the original app asset, calendar, Sage outline icons, and dialog background. Layouts are built in Kotlin.
- The T09 configuration Activity is declared as non-exported in app/src/t09Live/AndroidManifest.xml. Its strings are in app/src/t09Live/res/values/t09_debug_configuration_strings.xml. The debuggable-only development destination (renderDevelopment()) checks T09 capability and component availability before showing configuration. S04 Fake uses the shared UI and keeps its binding, network configuration and instrumentation in the existing S04 source sets.
