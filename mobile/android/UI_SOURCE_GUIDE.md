# PantryProof Android UI source guide

Open **D:\PantryProof\mobile\android** in Android Studio. Shared visual Kotlin files are in **app/src/main/java/com/pantryproof/prototype/ui/**. Search for the function or class shown below. The physical folder groups the visual source, and the Kotlin package declarations preserve the original class identities.

| Screen or UI surface | Source file | Rendering function |
|---|---|---|
| Home dashboard and development tool entries | MainActivity.kt | renderHome() |
| Add Receipt and image-input recovery | MainActivity.kt | renderAddReceipt(), imageInputNoticePanel() |
| Synthetic receipt preview | MainActivity.kt | renderPreview(), syntheticReceiptPreview() |
| Camera or imported-image preview | MainActivity.kt | renderPreview(), selectedImagePreview() |
| Zoom and crop editor | MainActivity.kt, ReceiptImageViews.kt | showCropEditor(), selectedImagePreview(), ZoomReceiptView.onDraw(), ReceiptCropView.onDraw() |
| Synthetic Processing Demo | MainActivity.kt | renderProcessingDemo() |
| Selected-image simulated processing and result | MainActivity.kt | renderSelectedImageProcessing(), presentationStatePanel(), receiptItemCard() |
| T09 LIVE processing and result | MainActivity.kt | renderSelectedImageProcessing(live = true), liveProcessingPanel() |
| Receipt Details | MainActivity.kt | renderDetails(), receiptItemCard(), detailMetric(), presentationStatePanel() |
| Synthetic receipt review and temporary confirmation | MainActivity.kt | renderReview(), reviewField(), applyReviewFieldError() |
| Synthetic review discard and revert dialogs | MainActivity.kt | confirmDiscardEdits(), confirmRevertDemo() |
| Manual Receipt Entry and image dialog | MainActivity.kt | renderManualReceipt(), selectedImagePreview(), configureManualDatePicker(), showManualDateEntry(), confirmRemoveManualItem(), confirmDiscardManualDraft() |
| Manual receipt review and save confirmation dialog | MainActivity.kt | reviewManualReceipt() |
| Editable LIVE receipt review and item selection | MainActivity.kt | renderLiveReceiptReview(), liveReviewField() |
| LIVE inventory confirmation dialog | MainActivity.kt | confirmLiveReview() |
| Household inventory, search, sort, filters, source badges and quantities | MainActivity.kt | renderInventory(), updateInventoryBrowseResults(), inventoryItemCard(), adjustInventoryQuantity() |
| Inventory add/edit, deletion and refresh | MainActivity.kt | showInventoryItemEditor(), confirmInventoryDeletion(), refreshInventoryAfterChange() |
| T09 LIVE Debug Configuration | app/src/t09Live/java/com/pantryproof/prototype/T09DebugConfigurationActivity.kt | onCreate(), applyConfiguration() |

- Start with the screen's renderer for screen-specific layout. MainActivity.setScreen() builds the shared frame, and render() dispatches screens. handleBackNavigation(), navigate(), navigateHome(), and goBack() handle navigation.
- PantryUiComponents.kt provides the app bar, progress header, banners, buttons, cards, Home hero, state panels, and status chips. ReceiptImageViews.kt contains ZoomReceiptView and ReceiptCropView for custom drawing and gestures.
- Visual resources are in app/src/main/res/values/ for strings, colors, dimensions, IDs and styles, values-v27/ for the theme override, and drawable/ for the app and calendar icons. Layouts are built in Kotlin.
- The T09 configuration Activity is declared as non-exported in app/src/t09Live/AndroidManifest.xml. Its strings are in app/src/t09Live/res/values/t09_debug_configuration_strings.xml. The Home entry checks T09 capability and component availability. S04 Fake uses the shared UI and keeps its binding, network configuration and instrumentation in the existing S04 source sets.
