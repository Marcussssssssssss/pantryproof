package com.pantryproof.prototype.data

import com.pantryproof.prototype.contract.v1.PresentationConsumerContext
import com.pantryproof.prototype.contract.v1.PresentationConsumerMode
import java.nio.charset.StandardCharsets

internal object SyntheticReceiptPresentationPayload {
    const val REQUEST_ID = "request-android-demo-001"
    const val IMAGE_ID = "image-android-demo-001"

    val context = PresentationConsumerContext(
        REQUEST_ID,
        IMAGE_ID,
        PresentationConsumerMode.FIXTURE,
    )

    fun bytes(): ByteArray = JSON.toByteArray(StandardCharsets.UTF_8)

    private val JSON =
        """
        {
          "schemaName": "receipt-presentation",
          "schemaVersion": "1",
          "sourceContractVersion": "0",
          "requestId": "$REQUEST_ID",
          "imageId": "$IMAGE_ID",
          "source": {
            "type": "SYNTHETIC_FIXTURE",
            "provenance": {
              "sourceSystem": "ANDROID_SYNTHETIC_DEMO",
              "sourceReference": "m3f-demo-001",
              "contentSha256": null
            }
          },
          "outcome": {"status": "RESULT_AVAILABLE", "failure": null},
          "sourceEvidence": {
            "sourceProcessingStatus": "OCR_COMPLETED",
            "tokenIds": [
              "token-store", "token-date", "token-total",
              "token-milk-description", "token-milk-quantity", "token-milk-unit", "token-milk-total",
              "token-bread-description", "token-bread-quantity", "token-bread-unit", "token-bread-total",
              "token-bananas-description", "token-bananas-quantity", "token-bananas-total"
            ]
          },
          "sourceGate": {"gateResultId": "gate-android-demo-001", "decision": "SUFFICIENT", "reasons": []},
          "automaticExtraction": {
            "stage": "PRE_REVIEW_AUTOMATIC",
            "extractionStatus": "PARTIAL",
            "producer": {"producerId": "android-synthetic-demo", "producerVersion": "1.0"}
          },
          "receipt": {
            "receiptId": "receipt-android-demo-001",
            "currencyCode": "MYR",
            "receiptFields": [
              {
                "fieldId": "field-store", "role": "STORE_NAME", "status": "EXTRACTED",
                "originalAutomaticValue": "Demo Grocery Store (Synthetic)",
                "presentationValue": "Demo Grocery Store (Synthetic)", "absenceReason": null,
                "sourceTokenIds": ["token-store"], "nativeConfidence": 0.99
              },
              {
                "fieldId": "field-date", "role": "PURCHASE_DATE", "status": "EXTRACTED",
                "originalAutomaticValue": "2026-10-31", "presentationValue": "2026-10-31",
                "absenceReason": null, "sourceTokenIds": ["token-date"], "nativeConfidence": 0.99
              },
              {
                "fieldId": "field-total", "role": "RECEIPT_TOTAL", "status": "EXTRACTED",
                "originalAutomaticValue": "RM 23.00", "presentationValue": "23.00",
                "absenceReason": null, "sourceTokenIds": ["token-total"], "nativeConfidence": 0.99
              }
            ],
            "itemRows": [
              {
                "rowId": "demo-milk",
                "fields": [
                  {"fieldId": "milk-description", "role": "ITEM_DESCRIPTION", "status": "EXTRACTED", "originalAutomaticValue": "UHT Milk 1L", "presentationValue": "UHT Milk 1L", "absenceReason": null, "sourceTokenIds": ["token-milk-description"], "nativeConfidence": 0.99},
                  {"fieldId": "milk-quantity", "role": "QUANTITY", "status": "EXTRACTED", "originalAutomaticValue": "2", "presentationValue": "2", "absenceReason": null, "sourceTokenIds": ["token-milk-quantity"], "nativeConfidence": 0.99},
                  {"fieldId": "milk-unit", "role": "UNIT_PRICE", "status": "EXTRACTED", "originalAutomaticValue": "6.50", "presentationValue": "6.50", "absenceReason": null, "sourceTokenIds": ["token-milk-unit"], "nativeConfidence": 0.99},
                  {"fieldId": "milk-total", "role": "LINE_TOTAL", "status": "EXTRACTED", "originalAutomaticValue": "13.00", "presentationValue": "13.00", "absenceReason": null, "sourceTokenIds": ["token-milk-total"], "nativeConfidence": 0.99}
                ]
              },
              {
                "rowId": "demo-bread",
                "fields": [
                  {"fieldId": "bread-description", "role": "ITEM_DESCRIPTION", "status": "EXTRACTED", "originalAutomaticValue": "Wholemeal Bread", "presentationValue": "Wholemeal Bread", "absenceReason": null, "sourceTokenIds": ["token-bread-description"], "nativeConfidence": 0.99},
                  {"fieldId": "bread-quantity", "role": "QUANTITY", "status": "EXTRACTED", "originalAutomaticValue": "1", "presentationValue": "1", "absenceReason": null, "sourceTokenIds": ["token-bread-quantity"], "nativeConfidence": 0.99},
                  {"fieldId": "bread-unit", "role": "UNIT_PRICE", "status": "EXTRACTED", "originalAutomaticValue": "4.20", "presentationValue": "4.20", "absenceReason": null, "sourceTokenIds": ["token-bread-unit"], "nativeConfidence": 0.99},
                  {"fieldId": "bread-total", "role": "LINE_TOTAL", "status": "EXTRACTED", "originalAutomaticValue": "4.20", "presentationValue": "4.20", "absenceReason": null, "sourceTokenIds": ["token-bread-total"], "nativeConfidence": 0.99}
                ]
              },
              {
                "rowId": "demo-bananas",
                "fields": [
                  {"fieldId": "bananas-description", "role": "ITEM_DESCRIPTION", "status": "EXTRACTED", "originalAutomaticValue": "Bananas (bunch)", "presentationValue": "Bananas (bunch)", "absenceReason": null, "sourceTokenIds": ["token-bananas-description"], "nativeConfidence": 0.99},
                  {"fieldId": "bananas-quantity", "role": "QUANTITY", "status": "EXTRACTED", "originalAutomaticValue": "1", "presentationValue": "1", "absenceReason": null, "sourceTokenIds": ["token-bananas-quantity"], "nativeConfidence": 0.99},
                  {"fieldId": "bananas-unit", "role": "UNIT_PRICE", "status": "MISSING", "originalAutomaticValue": null, "presentationValue": null, "absenceReason": "NO_EXPLICIT_UNIT_PRICE_OBSERVED", "sourceTokenIds": [], "nativeConfidence": null},
                  {"fieldId": "bananas-total", "role": "LINE_TOTAL", "status": "EXTRACTED", "originalAutomaticValue": "5.80", "presentationValue": "5.80", "absenceReason": null, "sourceTokenIds": ["token-bananas-total"], "nativeConfidence": 0.99}
                ]
              }
            ]
          }
        }
        """.trimIndent()
}
