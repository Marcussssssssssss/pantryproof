package com.pantryproof.prototype.contract.review

import com.pantryproof.prototype.contract.v1.PresentationItemRow

internal class ReviewEvidenceReader(tokens: List<ReviewToken>) {
    private val tokensById = tokens.associateBy { it.id }

    fun tokenIds(j: ReviewJson): List<String> = j.unique { value ->
        value.alias().also { value.require(it in tokensById, REVIEW_REFERENCE, "unknown OCR token") }
    }

    fun sourceReference(j: ReviewJson): ReviewSourceReference {
        j.obj("sourceKind", "reference", "observedValue", "sourceTokenIds", "characterSpans", "resourceReference")
        val kind = j["sourceKind"].enum("SOURCE_TOKEN_OR_NEIGHBOUR", "GENERIC_NORMALIZATION", "RETAILER_MAPPING", "PANTRY_TERMINOLOGY")
        val id = j["reference"].opaque()
        val observed = j["observedValue"].nullable(ReviewJson::nonblank)
        val ids = tokenIds(j["sourceTokenIds"])
        val spans = j["characterSpans"].array().map { span ->
            span.obj("tokenId", "start", "end", "text")
            val tokenId = span["tokenId"].alias()
            span["tokenId"].require(tokenId in ids, REVIEW_REFERENCE)
            val start = span["start"].integer()
            val end = span["end"].integer()
            val source = tokensById.getValue(tokenId).text
            val length = source.codePointCount(0, source.length)
            span["start"].require(start in 0 until length, REVIEW_REFERENCE)
            span["end"].require(end in start + 1..length, REVIEW_REFERENCE)
            val text = span["text"].string()
            span["text"].require(source.substring(source.offsetByCodePoints(0, start), source.offsetByCodePoints(0, end)) == text,
                REVIEW_REFERENCE, "span differs from OCR source")
            ReviewSpan(tokenId, start, end, text)
        }.immutableReviewList()
        val resource = j["resourceReference"].nullable(ReviewJson::resource)
        j["resourceReference"].require((resource != null) == (kind in setOf("RETAILER_MAPPING", "PANTRY_TERMINOLOGY")), REVIEW_STATE)
        return ReviewSourceReference(kind, id, observed, ids, spans, resource)
    }

    fun retailer(j: ReviewJson): RetailerEvidence {
        j.obj("status", "retailerId", "sourceReferences", "reason")
        val status = j["status"].enum("SUPPORTED", "UNAVAILABLE", "NOT_APPLICABLE")
        val id = j["retailerId"].nullable(ReviewJson::opaque)
        val refs = j["sourceReferences"].array().map {
            it.obj("resourceReference", "entryId")
            RetailerReference(it["resourceReference"].resource(), it["entryId"].opaque())
        }.immutableReviewList()
        j["sourceReferences"].require(refs.isNotEmpty() == (status == "SUPPORTED"), REVIEW_STATE)
        j["retailerId"].require((status != "SUPPORTED" || id != null) && (status != "NOT_APPLICABLE" || id == null), REVIEW_STATE)
        return RetailerEvidence(status, id, refs, j["reason"].reason())
    }

    fun price(j: ReviewJson): PriceEvidence {
        j.obj("status", "reason", "observedUnitPriceMyr", "priceBasis", "bandLowMyr", "bandHighMyr", "ruleId",
            "resourceReference", "entryIds", "sourceTokenIds")
        val status = j["status"].enum("PRICE_SUPPORTED", "PRICE_CONFLICT", "PRICE_UNAVAILABLE", "PRICE_INCONCLUSIVE", "NOT_APPLICABLE")
        val reason = j["reason"].reason()
        val observed = j["observedUnitPriceMyr"].nullable(::money)
        val basis = j["priceBasis"].nullable { it.enum("EACH", "KG", "G", "LB", "OZ") }
        val low = j["bandLowMyr"].nullable(::money)
        val high = j["bandHighMyr"].nullable(::money)
        val rule = j["ruleId"].nullable(ReviewJson::opaque)
        val resource = j["resourceReference"].nullable(ReviewJson::resource)
        val entries = j["entryIds"].unique(ReviewJson::opaque)
        val ids = tokenIds(j["sourceTokenIds"])
        j["bandHighMyr"].require((low == null) == (high == null), REVIEW_STATE)
        if (low != null && high != null) {
            j["bandHighMyr"].require(low.toBigDecimal() <= high.toBigDecimal(), REVIEW_STATE)
            j["entryIds"].require(entries.size == 1, REVIEW_STATE)
        }
        when (status) {
            "PRICE_SUPPORTED", "PRICE_CONFLICT" -> {
                j["observedUnitPriceMyr"].require(observed != null, REVIEW_STATE)
                j["priceBasis"].require(basis != null, REVIEW_STATE)
                j["bandLowMyr"].require(low != null, REVIEW_STATE)
                j["ruleId"].require(rule != null, REVIEW_STATE)
                j["resourceReference"].require(resource != null, REVIEW_STATE)
                j["sourceTokenIds"].require(ids.isNotEmpty(), REVIEW_REFERENCE)
            }
            "PRICE_UNAVAILABLE", "NOT_APPLICABLE" -> {
                j["observedUnitPriceMyr"].require(observed == null, REVIEW_STATE)
                j["bandLowMyr"].require(low == null, REVIEW_STATE)
                if (status == "NOT_APPLICABLE") {
                    j["priceBasis"].require(basis == null, REVIEW_STATE)
                    j["ruleId"].require(rule == null, REVIEW_STATE)
                    j["resourceReference"].require(resource == null, REVIEW_STATE)
                    j["entryIds"].require(entries.isEmpty(), REVIEW_STATE)
                    j["sourceTokenIds"].require(ids.isEmpty(), REVIEW_STATE)
                }
            }
        }
        return PriceEvidence(status, reason, observed, basis, low, high, rule, resource, entries, ids)
    }

    private fun money(j: ReviewJson): String = j.string().also { j.require(REVIEW_MONEY.matches(it)) }
}

internal val REVIEW_MONEY = Regex("(0|[1-9][0-9]*)\\.[0-9]{2}")
internal val REVIEW_QUANTITY = Regex("(0|[1-9][0-9]*)(?:\\.[0-9]{1,3})?")
internal val REVIEW_DATE = Regex("(?!0000)[0-9]{4}-[0-9]{2}-[0-9]{2}")

internal fun readPantryMapping(j: ReviewJson, row: PresentationItemRow): PantryMapping {
    j.obj("rowId", "descriptionFieldId", "mappingStatus", "selectedIdentity", "candidateIdentities")
    val rowId = j["rowId"].alias()
    j["rowId"].require(rowId == row.rowId, REVIEW_REFERENCE)
    val fieldId = j["descriptionFieldId"].alias()
    j["descriptionFieldId"].require(fieldId == row.fields.first().fieldId, REVIEW_REFERENCE)
    val status = j["mappingStatus"].enum("MAPPED", "AMBIGUOUS", "UNRESOLVED", "RESOURCE_UNAVAILABLE")
    val selected = j["selectedIdentity"].nullable(::readPantryIdentity)
    val seen = hashSetOf<String>()
    val candidates = j["candidateIdentities"].array().map {
        readPantryIdentity(it).also { candidate -> it["pantryIdentity"].require(seen.add(candidate.identity), REVIEW_REFERENCE) }
    }.immutableReviewList()
    j["selectedIdentity"].require((selected != null) == (status == "MAPPED"), REVIEW_STATE)
    j["candidateIdentities"].require(when (status) {
        "MAPPED" -> candidates.size == 1
        "AMBIGUOUS" -> candidates.size >= 2
        else -> candidates.isEmpty()
    }, REVIEW_STATE)
    if (selected != null) j["selectedIdentity"].require(selected == candidates.single(), REVIEW_REFERENCE)
    if (row.fields.first().presentationValue == null) {
        j["mappingStatus"].require(status == "UNRESOLVED" || status == "RESOURCE_UNAVAILABLE", REVIEW_STATE)
    }
    return PantryMapping(rowId, fieldId, status, selected, candidates)
}

private fun readPantryIdentity(j: ReviewJson): PantryIdentity {
    j.obj("entryId", "pantryIdentity", "pantryCategory", "referenceUnit", "resourceReference")
    return PantryIdentity(j["entryId"].opaque(), j["pantryIdentity"].opaque(),
        j["pantryCategory"].nullable(ReviewJson::safeDetail), j["referenceUnit"].nullable(ReviewJson::safeDetail),
        j["resourceReference"].resource())
}
