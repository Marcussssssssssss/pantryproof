package com.pantryproof.prototype.contract.review

import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.ReceiptFieldRole
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1
import java.math.BigDecimal
import java.util.Collections

internal data class ReviewContext(
    val presentation: PresentationConsumerContext,
    val imageWidth: Int? = null,
    val imageHeight: Int? = null,
)

internal class ReceiptReviewV1(
    val presentation: ReceiptPresentationV1,
    val review: ReviewExtension?,
    bytes: ByteArray,
) {
    private val evidence = bytes.copyOf()
    fun evidenceBytes(): ByteArray = evidence.copyOf()
}

internal enum class ReviewReadiness { POLICY_APPLIED, NOT_READY, NOT_VALID, NOT_EVALUATED }
internal enum class ReceiptDisposition { AUTO_RESOLVED, REVIEW_REQUIRED, UNVERIFIED_DRAFT, FALLBACK_NO_UPDATE, FAILED }
internal enum class FieldDisposition { AUTO_ACCEPTED, REVIEW_REQUIRED, UNVERIFIED_DRAFT }
internal enum class CandidateStatus { SCORING_ELIGIBLE, CONSTRAINT_REJECTED, REJECTED_PRICE_ONLY }

internal data class ReviewExtension(
    val readiness: ReviewReadiness,
    val disposition: ReceiptDisposition,
    val failureCode: String?,
    val region: String?,
    val ocr: ReviewOcr?,
    val fields: List<ReviewField>,
    val pantryMappings: List<PantryMapping>,
)

internal data class ReviewOcr(val width: Int, val height: Int, val tokens: List<ReviewToken>)
internal data class ReviewPoint(val x: BigDecimal, val y: BigDecimal)
internal data class ReviewToken(
    val id: String,
    val text: String,
    val polygon: List<ReviewPoint>,
    val rawConfidence: BigDecimal?,
)

internal data class CandidateValue(
    val id: String,
    val status: String,
    val raw: String?,
    val canonical: String?,
    val absenceReason: String?,
    val tokenIds: List<String>,
)

internal data class ReviewOriginal(
    val value: CandidateValue,
    val status: CandidateStatus,
    val probability: BigDecimal?,
    val nativeConfidence: BigDecimal?,
    val constraints: List<String>,
)

internal data class ReviewAlternative(
    val value: CandidateValue,
    val status: CandidateStatus,
    val probability: BigDecimal?,
    val constraints: List<String>,
    val replacementSupport: List<String>,
    val references: List<ReviewSourceReference>,
    val retailer: RetailerEvidence,
    val price: PriceEvidence,
)

internal data class ReviewRecommendation(val recommendation: String, val candidateId: String, val reason: String)
internal data class ReviewField(
    val id: String,
    val rowId: String?,
    val role: ReceiptFieldRole,
    val original: ReviewOriginal,
    val selected: CandidateValue,
    val disposition: FieldDisposition,
    val probability: BigDecimal?,
    val probabilityUnavailableReason: String?,
    val conflict: Boolean?,
    val suspicionReasons: List<String>,
    val correctionReason: String,
    val recommendation: ReviewRecommendation?,
    val retailer: RetailerEvidence,
    val price: PriceEvidence,
    val alternatives: List<ReviewAlternative>,
)

internal data class ReviewSpan(val tokenId: String, val start: Int, val end: Int, val text: String)
internal data class ReviewSourceReference(
    val kind: String,
    val id: String,
    val observed: String?,
    val tokenIds: List<String>,
    val spans: List<ReviewSpan>,
    val resource: String?,
)
internal data class RetailerReference(val resource: String, val entryId: String)
internal data class RetailerEvidence(val status: String, val id: String?, val refs: List<RetailerReference>, val reason: String)
internal data class PriceEvidence(
    val status: String,
    val reason: String,
    val observed: String?,
    val basis: String?,
    val low: String?,
    val high: String?,
    val rule: String?,
    val resource: String?,
    val entryIds: List<String>,
    val tokenIds: List<String>,
)
internal data class PantryIdentity(
    val entryId: String,
    val identity: String,
    val category: String?,
    val referenceUnit: String?,
    val resource: String,
)
internal data class PantryMapping(
    val rowId: String,
    val descriptionFieldId: String,
    val status: String,
    val selection: PantryIdentity?,
    val candidates: List<PantryIdentity>,
)

internal fun <T> List<T>.immutableReviewList(): List<T> = Collections.unmodifiableList(ArrayList(this))
