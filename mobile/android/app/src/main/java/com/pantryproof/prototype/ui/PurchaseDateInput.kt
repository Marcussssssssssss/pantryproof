package com.pantryproof.prototype.ui

import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.widget.EditText
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.format.ResolverStyle
import java.util.Locale

/** Keeps formatted input at the view boundary. Receipt validators still receive ISO dates. */
internal object PurchaseDateInput {
    private val format = DateTimeFormatter.ofPattern("dd-MM-uuuu", Locale.ROOT).withResolverStyle(ResolverStyle.STRICT)
    private val complete = Regex("[0-9]{2}-[0-9]{2}-[0-9]{4}")
    private val iso = Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}")

    fun display(date: LocalDate): String = date.format(format)

    fun display(value: String): String = if (iso.matches(value)) {
        // Preserve draft digits even for an invalid ISO value saved by an older UI.
        value.substring(8) + "-" + value.substring(5, 7) + "-" + value.substring(0, 4)
    } else value

    fun parse(value: String): LocalDate? =
        if (complete.matches(value)) runCatching { LocalDate.parse(value, format) }.getOrNull() else null

    fun draftValue(value: String): String = parse(value)?.toString() ?: value

    data class Edit(val text: String, val cursor: Int)

    fun edit(before: String, start: Int, end: Int, inserted: String, previousCursor: Int): Edit {
        fun digits(text: String) = text.filter { it in '0'..'9' }
        val current = digits(before)
        var from = digits(before.substring(0, start)).length
        var to = digits(before.substring(0, end)).length
        if (inserted.isEmpty() && end == start + 1 && before[start] == '-') {
            if (previousCursor == end && from > 0) from--
            if (previousCursor == start && to < current.length) to++
        }
        val replacement = if (start == 0 && end == before.length) display(inserted) else inserted
        val accepted = digits(replacement).take((8 - current.length + to - from).coerceAtLeast(0))
        if (from == to && accepted.isEmpty() && start == end) {
            return Edit(before, start)
        }
        val next = current.replaceRange(from, to, accepted)
        val formatted = next.chunked(2).take(2).joinToString("-") +
            if (next.length > 4) "-" + next.substring(4) else ""
        val digitPosition = from + accepted.length
        val cursor = digitPosition + (if (digitPosition > 2) 1 else 0) + (if (digitPosition > 4) 1 else 0)
        return Edit(formatted, cursor.coerceAtMost(formatted.length))
    }

    fun install(field: EditText) {
        // Keep the text key listener so formatted clipboard text and separators remain editable.
        field.setRawInputType(InputType.TYPE_CLASS_NUMBER)
        field.setSingleLine(true)
        field.addTextChangedListener(object : TextWatcher {
            private var updating = false
            private var before = ""
            private var oldCursor = -1
            private var result: Edit? = null

            override fun beforeTextChanged(text: CharSequence, start: Int, count: Int, after: Int) {
                if (!updating) {
                    before = text.toString()
                    oldCursor = if (field.selectionStart == field.selectionEnd) field.selectionStart else -1
                }
            }

            override fun onTextChanged(text: CharSequence, start: Int, beforeCount: Int, count: Int) {
                if (!updating) result = edit(before, start, start + beforeCount,
                    text.subSequence(start, start + count).toString(), oldCursor)
            }

            override fun afterTextChanged(text: Editable) {
                if (updating) return
                val next = result ?: return
                result = null
                if (next.text != text.toString()) {
                    updating = true
                    try {
                        text.replace(0, text.length, next.text)
                        field.setSelection(next.cursor)
                    } finally {
                        updating = false
                    }
                }
            }
        })
    }
}
