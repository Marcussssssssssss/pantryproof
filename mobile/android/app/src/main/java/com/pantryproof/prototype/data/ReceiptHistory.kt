package com.pantryproof.prototype.data

import java.math.BigDecimal
import java.security.MessageDigest
import java.time.LocalDate
import java.time.YearMonth
import org.json.JSONArray
import org.json.JSONObject

internal enum class ReceiptConfirmationMode { INVENTORY_ONLY, INVENTORY_AND_RECEIPT }

internal data class PurchasedRow(
    val id: String,
    val description: String,
    val quantity: BigDecimal,
    val inventoryUnit: InventoryUnit?,
    val included: Boolean,
    val unitPrice: BigDecimal?,
    val unitPriceAbsence: String?,
    val lineTotal: BigDecimal,
) {
    fun json() = JSONObject().put("id", id).put("description", description).put("quantity", quantity.toPlainString())
        .put("inventoryUnit", inventoryUnit?.code ?: JSONObject.NULL).put("included", included)
        .put("unitPrice", unitPrice?.toPlainString() ?: JSONObject.NULL)
        .put("unitPriceAbsence", unitPriceAbsence ?: JSONObject.NULL).put("lineTotal", lineTotal.toPlainString())
}

internal data class PurchaseRecord(
    val confirmationId: String,
    val store: String,
    val date: LocalDate,
    val total: BigDecimal,
    val rows: List<PurchasedRow>,
    val evidenceFile: String? = null,
    val originalFile: String? = null,
    val fieldAudit: List<ApprovedField> = emptyList(),
) {
    fun json() = JSONObject().put("confirmationId", confirmationId).put("store", store).put("date", date.toString())
        .put("total", total.toPlainString()).put("rows", JSONArray(rows.map(PurchasedRow::json)))
        .put("evidence", evidenceFile ?: JSONObject.NULL).put("original", originalFile ?: JSONObject.NULL)
        .put("fieldAudit", JSONArray(fieldAudit.map(ApprovedField::json)))

    companion object {
        fun read(j: JSONObject): PurchaseRecord = PurchaseRecord(
            j.getString("confirmationId"), j.getString("store"), LocalDate.parse(j.getString("date")),
            j.getString("total").toBigDecimal(), j.getJSONArray("rows").objects().map {
                PurchasedRow(it.getString("id"), it.getString("description"), it.getString("quantity").toBigDecimal(),
                    it.textOrNull("inventoryUnit")?.let { unit -> requireNotNull(InventoryUnit.fromCode(unit)) },
                    it.getBoolean("included"), it.textOrNull("unitPrice")?.toBigDecimal(), it.textOrNull("unitPriceAbsence"),
                    it.getString("lineTotal").toBigDecimal())
            },
            j.textOrNull("evidence"), j.textOrNull("original"), j.getJSONArray("fieldAudit").objects().map(ApprovedField::read),
        )
    }
}

internal data class ReceiptConfirmation(
    val identity: String,
    val legacyIdentity: String,
    val mode: ReceiptConfirmationMode,
    val stock: List<InventoryItem>,
    val decisions: List<Pair<String, Boolean>>,
    val fieldAudit: List<ApprovedField>,
    val history: PurchaseRecord?,
    val keepOriginal: Boolean,
    val incompleteAcknowledged: Boolean,
    val evidenceDigest: String,
) {
    fun fingerprint(): String {
        val payload = JSONObject()
            .put("identity", identity)
            .put("mode", mode.name)
            .put("stock", JSONArray(stock.map {
                JSONObject().put("id", it.id).put("description", it.name)
                    .put("quantity", it.quantity.toPlainString()).put("unit", it.unit.code)
            }))
            .put("decisions", JSONArray(decisions.map { (row, included) -> JSONArray(listOf(row, included)) }))
            .put("approvals", JSONArray(fieldAudit.map(ApprovedField::json)))
            .put("history", history?.json() ?: JSONObject.NULL)
            .put("keepOriginal", keepOriginal)
            .put("incompleteAcknowledged", incompleteAcknowledged)
            .put("evidenceDigest", evidenceDigest)
        return sha256(payload.toString().encodeToByteArray())
    }
}

internal data class ApprovedField(
    val id: String,
    val state: String,
    val source: String?,
    val candidateId: String?,
    val value: String?,
    val absenceReason: String?,
) {
    fun json() = JSONObject().put("id", id).put("state", state).put("source", source ?: JSONObject.NULL)
        .put("candidateId", candidateId ?: JSONObject.NULL).put("value", value ?: JSONObject.NULL)
        .put("absenceReason", absenceReason ?: JSONObject.NULL)
        .put("actorSource", if (state == "UNREVIEWED") "BACKEND" else "USER")

    companion object {
        fun read(j: JSONObject) = ApprovedField(j.getString("id"), j.getString("state"), j.textOrNull("source"),
            j.textOrNull("candidateId"), j.textOrNull("value"), j.textOrNull("absenceReason"))
    }
}

internal data class ReceiptHistoryMonth(val month: YearMonth, val purchases: List<PurchaseRecord>) {
    val spending: BigDecimal get() = purchases.fold(BigDecimal("0.00")) { sum, receipt -> sum + receipt.total }
}

internal fun receiptHistoryMonths(records: List<PurchaseRecord>, query: String): List<ReceiptHistoryMonth> {
    val needle = query.trim()
    val sorted = records.asReversed().sortedByDescending { it.date }
    return sorted.filter { purchase ->
        purchase.store.contains(needle, ignoreCase = true) ||
            purchase.rows.any { it.description.contains(needle, ignoreCase = true) }
    }.groupBy { YearMonth.from(it.date) }.map { (month, purchases) -> ReceiptHistoryMonth(month, purchases) }
}

internal fun confirmationDigest(vararg components: String): String =
    sha256(components.joinToString("\u0000").encodeToByteArray())

internal fun sha256(bytes: ByteArray): String =
    MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

internal fun JSONArray.objects(): List<JSONObject> = List(length(), ::getJSONObject)
internal fun JSONObject.textOrNull(key: String): String? = if (get(key) === JSONObject.NULL) null else get(key) as String
