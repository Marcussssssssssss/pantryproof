package com.pantryproof.prototype.contract.review

import com.pantryproof.prototype.contract.v1.ReceiptPresentationIssueCodes as V1
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder.JsonArray
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder.JsonBoolean
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder.JsonNull
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder.JsonNumber
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder.JsonObject
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder.JsonString
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Decoder.JsonValue
import com.pantryproof.prototype.contract.v1.ReceiptPresentationV1Validator
import com.pantryproof.prototype.contract.v1.rejectPresentation
import java.math.BigDecimal

internal const val REVIEW_VALUE = "REJECT_INVALID_REVIEW_VALUE"
internal const val REVIEW_REFERENCE = "REJECT_INVALID_REVIEW_REFERENCE"
internal const val REVIEW_STATE = "REJECT_REVIEW_STATE"

internal class ReviewJson(val node: JsonValue, val path: String) {
    fun obj(vararg keys: String): ReviewJson {
        objectNode().requireExactMembers(path, keys.asList())
        return this
    }

    fun objectNode(): JsonObject = node as? JsonObject ?: invalid("object")
    operator fun get(key: String): ReviewJson = ReviewJson(
        objectNode().members[key] ?: rejectPresentation(V1.MISSING_MEMBER, path, "missing member '$key'"),
        "$path.$key",
    )
    fun array(): List<ReviewJson> = (node as? JsonArray ?: invalid("array")).values
        .mapIndexed { i, v -> ReviewJson(v, "$path[$i]") }

    fun string(): String = (node as? JsonString)?.value ?: invalid("string")
    fun boolean(): Boolean = (node as? JsonBoolean)?.value ?: invalid("boolean")
    fun number(): BigDecimal = (node as? JsonNumber)?.value ?: invalid("number")
    fun integer(): Int {
        val value = (node as? JsonNumber)?.takeIf { it.integerToken }?.value ?: invalid("integer")
        return try { value.intValueExact() } catch (_: ArithmeticException) { fail(REVIEW_VALUE, "integer outside bounds") }
    }

    fun <T> nullable(parse: (ReviewJson) -> T): T? = if (node === JsonNull) null else parse(this)
    fun textOrNull(): String? = nullable(ReviewJson::string)
    fun nonblank(): String = string().also { require(it.isNotBlank()) }
    fun reason(): String = nonblank().also {
        ReceiptPresentationV1Validator.requirePrivacySafeReason(it, path)
        if (!publicCode.matches(it)) fail(V1.UNSAFE_PROVENANCE, "expected a fixed public code")
    }
    fun safeDetail(): String = nonblank().also { ReceiptPresentationV1Validator.requirePrivacySafeReason(it, path) }
    fun alias(): String = ReceiptPresentationV1Validator.validateProtocolId(string(), path, REVIEW_VALUE)
    // Resource identifiers and opaque local keys can contain colons by contract.
    fun opaque(): String = nonblank().also {
        if (!opaqueKey.matches(it) || it.substringBefore(':').lowercase() in uriSchemes && ':' in it) {
            fail(V1.UNSAFE_PROVENANCE, "invalid opaque evidence identifier")
        }
        it.split(':').forEach { part ->
            ReceiptPresentationV1Validator.validateProtocolId(part, path, V1.UNSAFE_PROVENANCE)
        }
    }
    fun resource(): String = string().also {
        if (!resourcePin.matches(it)) fail(REVIEW_VALUE, "invalid pinned resource reference")
        it.substringBefore(':').split('@').forEach { part ->
            ReceiptPresentationV1Validator.requirePrivacySafeReason(part, path)
        }
    }
    fun finite(): BigDecimal = number().also { require(it.toDouble().isFinite()) }
    fun probability(): BigDecimal = finite().also { require(it >= BigDecimal.ZERO && it <= BigDecimal.ONE) }
    fun enum(vararg values: String): String = string().also { require(it in values) }
    inline fun <reified T : Enum<T>> enum(): T = string().let { value ->
        enumValues<T>().firstOrNull { it.name == value } ?: fail(REVIEW_VALUE, "unknown review state")
    }

    fun <T> unique(read: (ReviewJson) -> T): List<T> {
        val seen = hashSetOf<T>()
        return array().map { child ->
            read(child).also { child.require(seen.add(it)) }
        }.immutableReviewList()
    }

    fun require(valid: Boolean, code: String = REVIEW_VALUE, detail: String = "invalid review member") {
        if (!valid) fail(code, detail)
    }

    fun fail(code: String, detail: String): Nothing = rejectPresentation(code, path, detail)
    private fun invalid(type: String): Nothing = fail(V1.INVALID_JSON, "expected $type")

    private companion object {
        val publicCode = Regex("[A-Z][A-Z0-9_]{0,63}")
        val opaqueKey = Regex("[A-Za-z0-9][A-Za-z0-9._-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*)*")
        val uriSchemes = setOf("http", "https", "ftp", "file", "data", "content", "mailto", "s3")
        val resourcePin = Regex("[A-Za-z0-9][A-Za-z0-9._-]*@[A-Za-z0-9][A-Za-z0-9._-]*:sha256:[0-9a-f]{64}")
    }
}
