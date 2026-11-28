package com.pantryproof.prototype.ui

import com.pantryproof.prototype.contract.v1.AutomaticExtractionStatus
import com.pantryproof.prototype.data.ReceiptPresentationUiResult

/** A review annotation, not a technical failure or permission to mutate inventory. */
internal object ReceiptReviewAnnotationPolicy {
    fun requiresManualReviewAnnotation(result: ReceiptPresentationUiResult): Boolean =
        (result as? ReceiptPresentationUiResult.Available)
            ?.receipt?.automaticExtractionStatus == AutomaticExtractionStatus.FAILED
}
