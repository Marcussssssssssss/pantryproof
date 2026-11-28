package com.pantryproof.prototype.contract.review

import com.pantryproof.prototype.contract.v1.PresentationField
import com.pantryproof.prototype.contract.v1.ReceiptFieldRole
import java.math.BigDecimal
import java.time.LocalDate
import java.time.format.DateTimeParseException

internal class ReviewFieldReader(private val evidence: ReviewEvidenceReader, private val readiness: ReviewReadiness) {
    private val candidates = hashSetOf<String>()

    fun read(j: ReviewJson, rowId: String?, field: PresentationField): ReviewField {
        j.obj("fieldId", "itemRowId", "role", "optionalWhenMissing", "originalB2", "selectedPreReview",
            "fieldDisposition", "automaticCommitPermitted", "calibratedProbability", "probabilityAvailable",
            "probabilityUnavailableReason", "unresolvedConflict", "suspicionReasons", "correctionReason",
            "developmentRecommendation", "retailerEvidence", "priceEvidence", "alternativeCandidates")
        j["fieldId"].require(j["fieldId"].alias() == field.fieldId, REVIEW_REFERENCE)
        j["itemRowId"].require(j["itemRowId"].nullable(ReviewJson::alias) == rowId, REVIEW_REFERENCE)
        j["role"].require(j["role"].string() == field.role.name, REVIEW_REFERENCE)
        j["optionalWhenMissing"].require(j["optionalWhenMissing"].boolean() == (field.role == ReceiptFieldRole.UNIT_PRICE), REVIEW_STATE)

        val original = original(j["originalB2"], field.role)
        val list = j["alternativeCandidates"].array()
        j["alternativeCandidates"].require(list.size <= 127)
        val alternatives = list.mapIndexed { index, value -> alternative(value, field.role, index + 1) }.immutableReviewList()
        val selected = selected(j["selectedPreReview"], original, alternatives, field)
        val alternative = alternatives.firstOrNull { it.value.id == selected.id }
        val recommendation = j["developmentRecommendation"].nullable {
            it.obj("recommendation", "recommendedCandidateId", "reason")
            val suggestion = it["recommendation"].enum("CORRECT", "RETAIN", "REVIEW_REQUIRED")
            val id = it["recommendedCandidateId"].alias()
            it["recommendedCandidateId"].require(id == original.value.id || alternatives.any { candidate -> candidate.value.id == id }, REVIEW_REFERENCE)
            ReviewRecommendation(suggestion, id, it["reason"].reason())
        }

        val disposition = j["fieldDisposition"].enum<FieldDisposition>()
        j["automaticCommitPermitted"].require(j["automaticCommitPermitted"].boolean() ==
            (disposition == FieldDisposition.AUTO_ACCEPTED), REVIEW_STATE)
        val probability = probability(j)
        val unavailable = j["probabilityUnavailableReason"].nullable(ReviewJson::reason)
        j["probabilityUnavailableReason"].require((probability == null) == (unavailable != null), REVIEW_STATE)
        val conflict = j["unresolvedConflict"].nullable(ReviewJson::boolean)
        val correction = j["correctionReason"].reason()
        verifyPolicy(j, original, selected, alternative, disposition, probability, unavailable, conflict, correction)
        val suspicion = j["suspicionReasons"].unique {
            it.enum("LOW_OCR_CONFIDENCE", "LOW_EXTRACTOR_CONFIDENCE", "MISSING_REQUIRED_CONTENT", "PARSE_TYPE_FAILURE",
                "LINE_ASSOCIATION_CONFLICT", "ARITHMETIC_CONTRADICTION")
        }
        return ReviewField(field.fieldId, rowId, field.role, original, selected, disposition, probability,
            unavailable, conflict, suspicion, correction, recommendation, evidence.retailer(j["retailerEvidence"]),
            evidence.price(j["priceEvidence"]), alternatives)
    }

    private fun original(j: ReviewJson, role: ReceiptFieldRole): ReviewOriginal {
        j.obj("c0CandidateId", "status", "value", "canonicalValue", "absenceReason", "sourceTokenIds", "nativeConfidence",
            "candidateStatus", "constraintReasons", "calibratedProbability", "probabilityAvailable")
        val candidate = readValue(j, candidateId(j["c0CandidateId"]))
        val confidence = j["nativeConfidence"].nullable(ReviewJson::finite)
        val status = j["candidateStatus"].enum<CandidateStatus>()
        j["candidateStatus"].require(status != CandidateStatus.REJECTED_PRICE_ONLY)
        if (candidate.status == "EXTRACTED") {
            j["value"].require(!candidate.raw.isNullOrBlank(), REVIEW_STATE)
            j["canonicalValue"].require(candidate.canonical == canonical(role, candidate.raw), REVIEW_STATE)
            j["absenceReason"].require(candidate.absenceReason == null, REVIEW_STATE)
            j["sourceTokenIds"].require(candidate.tokenIds.isNotEmpty(), REVIEW_REFERENCE)
        } else {
            j["value"].require(candidate.raw == null, REVIEW_STATE)
            j["canonicalValue"].require(candidate.canonical == null, REVIEW_STATE)
            j["absenceReason"].require(candidate.absenceReason != null, REVIEW_STATE)
            j["nativeConfidence"].require(confidence == null, REVIEW_STATE)
            j["candidateStatus"].require(status != CandidateStatus.SCORING_ELIGIBLE, REVIEW_STATE)
        }
        val constraints = constraints(j, status)
        return ReviewOriginal(candidate, status, candidateProbability(j, status), confidence, constraints)
    }

    private fun alternative(j: ReviewJson, role: ReceiptFieldRole, rank: Int): ReviewAlternative {
        j.obj("candidateId", "value", "canonicalValue", "candidateStatus", "constraintReasons", "replacementSupport",
            "preliminaryRank", "calibratedProbability", "probabilityAvailable", "sourceTokenIds", "sourceReferences",
            "retailerEvidence", "priceEvidence")
        val id = candidateId(j["candidateId"])
        val raw = j["value"].nonblank()
        val canonical = j["canonicalValue"].textOrNull()
        j["canonicalValue"].require(canonical == canonical(role, raw), REVIEW_STATE)
        val status = j["candidateStatus"].enum<CandidateStatus>()
        val constraints = constraints(j, status)
        val supports = j["replacementSupport"].unique {
            it.reason().also { code -> it.require(!code.startsWith("PRICE") && !code.startsWith("REFERENCE_PRICE")) }
        }
        j["replacementSupport"].require(status == CandidateStatus.SCORING_ELIGIBLE || supports.isEmpty(), REVIEW_STATE)
        j["preliminaryRank"].require(j["preliminaryRank"].integer() == rank)
        val refs = j["sourceReferences"].array().map(evidence::sourceReference).immutableReviewList()
        j["sourceReferences"].require(refs.isNotEmpty())
        val value = CandidateValue(id, "EXTRACTED", raw, canonical, null, evidence.tokenIds(j["sourceTokenIds"]))
        return ReviewAlternative(value, status, candidateProbability(j, status), constraints, supports, refs,
            evidence.retailer(j["retailerEvidence"]), evidence.price(j["priceEvidence"]))
    }

    private fun selected(
        j: ReviewJson,
        original: ReviewOriginal,
        alternatives: List<ReviewAlternative>,
        field: PresentationField,
    ): CandidateValue {
        j.obj("candidateId", "status", "value", "canonicalValue", "absenceReason", "sourceTokenIds", "changedFromC0")
        val id = j["candidateId"].alias()
        val changed = id != original.value.id
        val expected = if (!changed) original.value else {
            val match = alternatives.find { it.value.id == id } ?: j["candidateId"].fail(REVIEW_REFERENCE, "unknown field candidate")
            j["candidateId"].require(match.status == CandidateStatus.SCORING_ELIGIBLE &&
                match.replacementSupport.isNotEmpty() && match.value.tokenIds.isNotEmpty() && match.value.canonical != null, REVIEW_REFERENCE)
            match.value
        }
        val value = readValue(j, id)
        j["changedFromC0"].require(j["changedFromC0"].boolean() == changed, REVIEW_STATE)
        compareSelected(j, value, expected)
        compareSelected(j, value, CandidateValue(id, field.status.name, field.originalAutomaticValue,
            field.presentationValue, field.absenceReason, field.sourceTokenIds))
        return value
    }

    private fun compareSelected(j: ReviewJson, value: CandidateValue, expected: CandidateValue) {
        j["status"].require(value.status == expected.status, REVIEW_STATE)
        j["value"].require(value.raw == expected.raw, REVIEW_STATE)
        j["canonicalValue"].require(value.canonical == expected.canonical, REVIEW_STATE)
        j["absenceReason"].require(value.absenceReason == expected.absenceReason, REVIEW_STATE)
        j["sourceTokenIds"].require(value.tokenIds == expected.tokenIds, REVIEW_STATE)
    }

    private fun verifyPolicy(
        j: ReviewJson,
        original: ReviewOriginal,
        selected: CandidateValue,
        alternative: ReviewAlternative?,
        disposition: FieldDisposition,
        probability: BigDecimal?,
        unavailable: String?,
        conflict: Boolean?,
        correction: String,
    ) {
        if (readiness == ReviewReadiness.NOT_READY) {
            j["fieldDisposition"].require(disposition == FieldDisposition.UNVERIFIED_DRAFT, REVIEW_STATE)
            j["calibratedProbability"].require(probability == null, REVIEW_STATE)
            j["unresolvedConflict"].require(conflict == null, REVIEW_STATE)
            j["selectedPreReview"]["candidateId"].require(alternative == null, REVIEW_STATE)
            j["correctionReason"].require(correction == "EMPIRICAL_POLICY_UNAVAILABLE", REVIEW_STATE)
            return
        }
        j["fieldDisposition"].require(readiness == ReviewReadiness.POLICY_APPLIED && disposition != FieldDisposition.UNVERIFIED_DRAFT, REVIEW_STATE)
        val chosenProbability = if (alternative == null) original.probability else alternative.probability
        if (probability == null) {
            j["fieldDisposition"].require(disposition == FieldDisposition.REVIEW_REQUIRED, REVIEW_STATE)
            j["selectedPreReview"]["candidateId"].require(alternative == null, REVIEW_STATE)
        } else {
            j["calibratedProbability"].require(chosenProbability != null && probability.compareTo(chosenProbability) == 0, REVIEW_STATE)
        }
        if (alternative != null) j["originalB2"]["calibratedProbability"].require(original.probability != null, REVIEW_STATE)
        if (original.value.status == "MISSING") {
            j["probabilityUnavailableReason"].require(unavailable == "ORIGINAL_NOT_SCORING_ELIGIBLE", REVIEW_STATE)
        }
        if (disposition == FieldDisposition.AUTO_ACCEPTED) {
            j["fieldDisposition"].require(selected.status == "EXTRACTED" && selected.canonical != null &&
                (alternative != null || original.status == CandidateStatus.SCORING_ELIGIBLE) && conflict == false, REVIEW_STATE)
        }
    }

    private fun readValue(j: ReviewJson, id: String): CandidateValue = CandidateValue(id,
        j["status"].enum("EXTRACTED", "MISSING", "UNRESOLVED"), j["value"].textOrNull(),
        j["canonicalValue"].textOrNull(), j["absenceReason"].nullable(ReviewJson::safeDetail),
        evidence.tokenIds(j["sourceTokenIds"]))

    private fun candidateId(j: ReviewJson): String = j.alias().also {
        j.require(candidates.add(it), REVIEW_REFERENCE, "duplicate review candidate")
    }

    private fun constraints(j: ReviewJson, status: CandidateStatus): List<String> =
        j["constraintReasons"].unique(ReviewJson::reason).also {
            j["constraintReasons"].require(it.isNotEmpty() == (status == CandidateStatus.CONSTRAINT_REJECTED), REVIEW_STATE)
        }

    private fun probability(j: ReviewJson): BigDecimal? = j["calibratedProbability"].nullable(ReviewJson::probability).also {
        j["probabilityAvailable"].require(j["probabilityAvailable"].boolean() == (it != null), REVIEW_STATE)
    }

    private fun candidateProbability(j: ReviewJson, status: CandidateStatus): BigDecimal? = probability(j).also {
        j["calibratedProbability"].require(it == null || readiness == ReviewReadiness.POLICY_APPLIED &&
            status == CandidateStatus.SCORING_ELIGIBLE, REVIEW_STATE)
    }
}

private val sourceMoney = Regex("(?:(?i:RM|MYR)[ ]*)?((?:0|[1-9][0-9]*)|(?:[1-9][0-9]{0,2}(?:,[0-9]{3})+))\\.([0-9]{2})")

internal fun canonical(role: ReceiptFieldRole, raw: String?): String? {
    if (raw.isNullOrBlank()) return null
    return when (role) {
        ReceiptFieldRole.STORE_NAME, ReceiptFieldRole.ITEM_DESCRIPTION -> raw
        ReceiptFieldRole.PURCHASE_DATE -> raw.takeIf {
            REVIEW_DATE.matches(it) && try { LocalDate.parse(it); true } catch (_: DateTimeParseException) { false }
        }
        ReceiptFieldRole.QUANTITY -> raw.takeIf { REVIEW_QUANTITY.matches(it) && it.toBigDecimal().signum() > 0 }
        ReceiptFieldRole.UNIT_PRICE, ReceiptFieldRole.LINE_TOTAL, ReceiptFieldRole.RECEIPT_TOTAL ->
            sourceMoney.matchEntire(raw)?.destructured?.let { (whole, fraction) -> whole.replace(",", "") + "." + fraction }
    }
}
