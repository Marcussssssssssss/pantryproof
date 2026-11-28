package com.pantryproof.prototype.ui

import com.pantryproof.prototype.contract.review.CandidateStatus
import com.pantryproof.prototype.contract.review.CandidateValue
import com.pantryproof.prototype.contract.review.FieldDisposition
import com.pantryproof.prototype.contract.review.ReviewField
import com.pantryproof.prototype.contract.review.canonical
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import com.pantryproof.prototype.contract.v1.PresentationSourceType
import com.pantryproof.prototype.contract.v1.ReceiptFieldRole
import com.pantryproof.prototype.data.ApprovedField
import com.pantryproof.prototype.data.InventoryItem
import com.pantryproof.prototype.data.InventoryUnit
import com.pantryproof.prototype.data.LiveReceiptEvidence
import com.pantryproof.prototype.data.ManualInventoryStore
import com.pantryproof.prototype.data.PresentedField
import com.pantryproof.prototype.data.PresentedReceiptItem
import com.pantryproof.prototype.data.PurchaseRecord
import com.pantryproof.prototype.data.PurchasedRow
import com.pantryproof.prototype.data.ReceiptConfirmation
import com.pantryproof.prototype.data.ReceiptConfirmationMode
import com.pantryproof.prototype.data.ReceiptPresentationUiResult
import com.pantryproof.prototype.data.ReceiptProcessingLifecycle
import com.pantryproof.prototype.data.ReceiptProcessingRequest
import com.pantryproof.prototype.data.confirmationDigest
import com.pantryproof.prototype.data.sha256
import java.time.LocalDate

/** In-memory corrections overlay the original validated evidence for this submission. */
internal class LiveReceiptReviewDraft private constructor(
    val request: ReceiptProcessingRequest,
    val evidence: LiveReceiptEvidence,
    available: ReceiptPresentationUiResult.Available,
) {
    enum class UserReviewState { UNREVIEWED, USER_CONFIRMED, USER_MODIFIED, USER_REJECTED, UNRESOLVED }
    enum class CandidateSource { SELECTED_PRE_REVIEW, ORIGINAL_B2_C0, ALTERNATIVE }
    data class Offer(val fieldId: String, val source: CandidateSource, val id: String, val value: String?, val absence: String?)
    data class BulkOffer(val revision: List<Any?>, val offers: List<Offer>)

    class Field(val original: PresentedField, val backend: ReviewField?) {
        val initialValue = original.value.orEmpty()
        var value = initialValue
        var reviewState = UserReviewState.UNREVIEWED
            private set
        private var approved: Offer? = null
        private var edited: String? = null
        private var markedNotPrinted = false
        val displayed: String? get() = when (reviewState) {
            UserReviewState.USER_CONFIRMED -> approved?.value
            UserReviewState.USER_MODIFIED -> edited
            UserReviewState.UNREVIEWED -> backend?.selected?.canonical
            else -> null
        }

        private fun candidate(source: CandidateSource, id: String): CandidateValue? {
            val review = backend ?: return null
            return when (source) {
                CandidateSource.SELECTED_PRE_REVIEW -> review.selected.takeIf { it.id == id }
                CandidateSource.ORIGINAL_B2_C0 -> review.original.value.takeIf { it.id == id }
                CandidateSource.ALTERNATIVE -> review.alternatives.firstOrNull {
                    it.value.id == id && it.status == CandidateStatus.SCORING_ELIGIBLE
                }?.value
            }
        }

        fun offer(source: CandidateSource, id: String, today: LocalDate): Offer? {
            val review = backend ?: return null
            val choice = candidate(source, id) ?: return null
            val absence = choice.absenceReason?.takeIf {
                review.role == ReceiptFieldRole.UNIT_PRICE && choice.status == "MISSING" && source != CandidateSource.ALTERNATIVE
            }
            if (absence == null && !valid(review.role, choice.canonical, today)) return null
            return Offer(review.id, source, id, choice.canonical, absence)
        }

        fun accept(offer: Offer, today: LocalDate): Boolean {
            if (offer != offer(offer.source, offer.id, today)) return false
            reset(UserReviewState.USER_CONFIRMED)
            approved = offer
            return true
        }

        fun edit(text: String, today: LocalDate): Boolean {
            val role = backend?.role ?: return false
            val provided = text.trim()
            val normalized = canonical(role, provided)
            if (!valid(role, normalized, today) && !(role == ReceiptFieldRole.UNIT_PRICE && provided.isEmpty())) return false
            reset(UserReviewState.USER_MODIFIED)
            edited = normalized
            return true
        }

        fun markPriceNotPrinted() {
            require(backend?.role == ReceiptFieldRole.UNIT_PRICE)
            reset(UserReviewState.USER_MODIFIED)
            markedNotPrinted = true
        }

        fun reject() = reset(UserReviewState.USER_REJECTED)
        fun leaveUnresolved() = reset(UserReviewState.UNRESOLVED)

        private fun reset(next: UserReviewState) {
            reviewState = next
            approved = null
            edited = null
            markedNotPrinted = false
        }

        fun eligible(today: LocalDate): String? {
            val review = backend ?: return null
            if (reviewState == UserReviewState.UNREVIEWED && review.disposition != FieldDisposition.AUTO_ACCEPTED) return null
            return displayed?.takeIf { valid(review.role, it, today) }
        }

        fun legitimateAbsence(): String? = when (reviewState) {
            UserReviewState.UNREVIEWED -> backend?.selected?.takeIf {
                backend.role == ReceiptFieldRole.UNIT_PRICE && it.status == "MISSING" && backend.conflict != true
            }?.absenceReason
            UserReviewState.USER_CONFIRMED -> approved?.absence
            UserReviewState.USER_MODIFIED -> "USER_CONFIRMED_PRICE_NOT_PRINTED".takeIf { markedNotPrinted }
            else -> null
        }

        fun audit(today: LocalDate) = ApprovedField(original.id, reviewState.name,
            approved?.source?.name ?: when {
                reviewState == UserReviewState.USER_MODIFIED -> "USER"
                eligible(today) != null || legitimateAbsence() != null -> "SELECTED_PRE_REVIEW"
                else -> null
            }, approved?.id ?: backend?.selected?.id?.takeIf {
                reviewState == UserReviewState.UNREVIEWED && (eligible(today) != null || legitimateAbsence() != null)
            }, eligible(today), legitimateAbsence())

        private fun valid(role: ReceiptFieldRole, raw: String?, today: LocalDate): Boolean {
            if (raw == null || canonical(role, raw) != raw) return false
            return role != ReceiptFieldRole.PURCHASE_DATE || !LocalDate.parse(raw).isAfter(today)
        }
    }

    class Item(original: PresentedReceiptItem, fields: Map<String, ReviewField>) {
        val rowId = original.rowId
        val description = Field(original.description, fields[original.description.id])
        val quantity = Field(original.quantity, fields[original.quantity.id])
        val unitPrice = Field(original.unitPrice, fields[original.unitPrice.id])
        val lineTotal = Field(original.lineTotal, fields[original.lineTotal.id])
        val allFields = listOf(description, quantity, unitPrice, lineTotal)
        var selected = fields.isEmpty()
        var inventoryUnit = InventoryUnit.UNKNOWN
    }

    enum class Problem { INACTIVE, PURCHASE_DATE, NO_ITEMS, DESCRIPTION, QUANTITY }

    sealed interface Selection {
        data class Invalid(val problem: Problem, val itemNumber: Int? = null) : Selection
        data class Ready(val receiptIdPrefix: String, val rows: List<InventoryItem>, val purchaseDate: LocalDate) : Selection
    }

    val wrapper = evidence.wrapper
    private val fields = wrapper?.review?.fields.orEmpty().associateBy(ReviewField::id)
    val storeName = Field(available.receipt.storeName, fields[available.receipt.storeName.id])
    val purchaseDate = Field(available.receipt.purchaseDate, fields[available.receipt.purchaseDate.id])
    val receiptTotal = Field(available.receipt.receiptTotal, fields[available.receipt.receiptTotal.id])
    val receiptFields = listOf(storeName, purchaseDate, receiptTotal)
    val currencyCode = available.receipt.currencyCode
    val items = available.receipt.items.map { Item(it, fields) }
    val allFields = receiptFields + items.flatMap(Item::allFields)
    var omittedPurchasedRow = false
    var keepOriginal = false
    @Volatile private var active = true

    private val legacyIdentity = confirmationDigest(evidence.envelope.requestId, evidence.envelope.imageId)
    private val receiptIdPrefix = ManualInventoryStore.LIVE_ROW_PREFIX + legacyIdentity + "-"
    private val confirmationIdentity = confirmationDigest(evidence.envelope.requestId, evidence.envelope.imageId, available.receipt.receiptId)
    private val evidenceDigest by lazy { sha256(requireNotNull(wrapper).evidenceBytes()) }

    sealed interface ConfirmationCheck {
        data class Blocked(val explanation: String) : ConfirmationCheck
        data class Ready(val confirmation: ReceiptConfirmation, val needsIncompleteAcknowledgement: Boolean) : ConfirmationCheck
    }

    fun bulkOffer(today: LocalDate): BulkOffer {
        val revision = allFields.map { it.audit(today) } + items.flatMap { listOf(it.selected, it.inventoryUnit) } +
            listOf(omittedPurchasedRow, keepOriginal)
        if (!active) return BulkOffer(revision, emptyList())
        val offers = allFields.mapNotNull { field ->
            val review = field.backend ?: return@mapNotNull null
            if (field.reviewState != UserReviewState.UNREVIEWED || review.conflict == true) return@mapNotNull null
            val offer = field.offer(CandidateSource.SELECTED_PRE_REVIEW, review.selected.id, today)
                ?.takeIf { it.value != null } ?: return@mapNotNull null
            if (review.role == ReceiptFieldRole.QUANTITY) {
                val unit = items.first { it.rowId == review.rowId }.inventoryUnit
                if (unit == InventoryUnit.UNKNOWN || !unit.stores(requireNotNull(offer.value).toBigDecimal())) return@mapNotNull null
            }
            offer
        }
        return BulkOffer(revision, offers)
    }

    fun acceptBulk(shown: BulkOffer, today: LocalDate): Boolean {
        if (shown.offers.isEmpty() || shown != bulkOffer(today)) return false
        val byId = allFields.associateBy { it.original.id }
        shown.offers.forEach { check(byId.getValue(it.fieldId).accept(it, today)) }
        return true
    }

    fun confirmation(mode: ReceiptConfirmationMode, today: LocalDate, acknowledged: Boolean): ConfirmationCheck {
        if (!active || wrapper == null) return ConfirmationCheck.Blocked("This review is no longer current.")
        val displayedDate = purchaseDate.displayed?.let(ReceiptValidator::parsePurchaseDate)
        if (ReceiptValidator.purchaseDateProblem(displayedDate, today) == ReceiptValidator.PurchaseDateProblem.FUTURE) {
            return ConfirmationCheck.Blocked(ReceiptValidator.FUTURE_PURCHASE_DATE_ERROR)
        }
        val included = items.filter(Item::selected)
        if (included.isEmpty()) return ConfirmationCheck.Blocked("Include at least one item in inventory.")
        val rows = included.map { item ->
            val number = items.indexOf(item) + 1
            val name = item.description.eligible(today) ?: return ConfirmationCheck.Blocked("Review the description for item $number.")
            val amount = item.quantity.eligible(today)?.toBigDecimal()
                ?: return ConfirmationCheck.Blocked("Review the quantity for item $number.")
            val unit = item.inventoryUnit
            if (unit == InventoryUnit.UNKNOWN || !unit.stores(amount)) {
                return ConfirmationCheck.Blocked("Choose a compatible inventory unit for item $number, edit the quantity, or exclude it.")
            }
            InventoryItem("${ManualInventoryStore.LIVE_ROW_PREFIX}$confirmationIdentity-${item.rowId}",
                name, amount, ManualInventoryStore.LIVE_ROW_STATE, unit)
        }
        val store = storeName.eligible(today)
        val date = purchaseDate.eligible(today)?.let(LocalDate::parse)
        val total = receiptTotal.eligible(today)?.toBigDecimal()
        val historyRows = items.mapNotNull { item ->
            val name = item.description.eligible(today) ?: return@mapNotNull null
            val amount = item.quantity.eligible(today)?.toBigDecimal() ?: return@mapNotNull null
            val line = item.lineTotal.eligible(today)?.toBigDecimal() ?: return@mapNotNull null
            val price = item.unitPrice.eligible(today)?.toBigDecimal()
            val absence = item.unitPrice.legitimateAbsence()
            if (price == null && absence == null) return@mapNotNull null
            PurchasedRow(item.rowId, name, amount, item.inventoryUnit.takeUnless { it == InventoryUnit.UNKNOWN }, item.selected,
                price, absence, line)
        }
        val complete = !omittedPurchasedRow && store != null && date != null && total != null && historyRows.size == items.size
        val saveHistory = mode == ReceiptConfirmationMode.INVENTORY_AND_RECEIPT
        if (saveHistory && !complete) {
            val explanation = when {
                omittedPurchasedRow -> "A purchased item is missing. Save inventory only or scan the receipt again."
                store == null || date == null || total == null -> "Review the store, purchase date and receipt total before saving a receipt."
                else -> "Review every purchased item, including excluded items. Confirm any missing unit price."
            }
            return ConfirmationCheck.Blocked(explanation)
        }
        val audit = allFields.map { it.audit(today) }
        val history = if (saveHistory) PurchaseRecord(confirmationIdentity, requireNotNull(store),
            requireNotNull(date), requireNotNull(total), historyRows,
            fieldAudit = audit) else null
        return ConfirmationCheck.Ready(ReceiptConfirmation(confirmationIdentity, legacyIdentity, mode, rows,
            items.map { it.rowId to it.selected }, audit, history, saveHistory && keepOriginal,
            !complete && acknowledged, evidenceDigest), !complete)
    }

    fun discard() {
        active = false
    }

    fun selection(today: LocalDate = LocalDate.now()): Selection {
        if (!active) return Selection.Invalid(Problem.INACTIVE)
        val finalDate = ReceiptValidator.parsePurchaseDate(purchaseDate.value)
        if (ReceiptValidator.purchaseDateProblem(finalDate, today) != null) {
            return Selection.Invalid(Problem.PURCHASE_DATE)
        }
        val rows = mutableListOf<InventoryItem>()
        items.forEachIndexed { index, item ->
            if (!item.selected) return@forEachIndexed
            val name = item.description.value.trim()
            if (name.isEmpty()) return Selection.Invalid(Problem.DESCRIPTION, index + 1)
            val unit = item.inventoryUnit
            val quantity = unit.parse(item.quantity.value)
            if (quantity == null || quantity.signum() <= 0 || !unit.stores(quantity)) {
                return Selection.Invalid(Problem.QUANTITY, index + 1)
            }
            rows.add(InventoryItem(receiptIdPrefix + item.rowId, name, quantity, ManualInventoryStore.LIVE_ROW_STATE, unit))
        }
        if (rows.isEmpty()) return Selection.Invalid(Problem.NO_ITEMS)
        return Selection.Ready(receiptIdPrefix, rows.toList(), requireNotNull(finalDate))
    }

    companion object {
        fun from(finished: ReceiptProcessingLifecycle.State.Finished): LiveReceiptReviewDraft? {
            val request = finished.request
            val context = request.context
            if (context.mode != PresentationConsumerMode.LIVE) return null
            val outcome = finished.outcome as? ReceiptProcessingLifecycle.Outcome.Presentation ?: return null
            val available = outcome.result as? ReceiptPresentationUiResult.Available ?: return null
            val evidence = available.liveEvidence ?: return null
            val envelope = evidence.envelope
            if (envelope.source.type != PresentationSourceType.LOCAL_IMAGE ||
                envelope.requestId != context.expectedRequestId ||
                envelope.imageId != context.expectedImageId ||
                envelope.imageId != request.selection.imageId
            ) return null
            return LiveReceiptReviewDraft(request, evidence, available)
        }

    }
}
