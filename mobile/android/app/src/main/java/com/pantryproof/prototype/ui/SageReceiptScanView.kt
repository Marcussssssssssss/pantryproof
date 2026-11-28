package com.pantryproof.prototype.ui

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.view.View
import com.pantryproof.prototype.R

/** Decorative indicator whose lifetime is the attached active-state view. */
internal class SageReceiptScanView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val paper = RectF()
    private var fraction = 0.5f
    private var animation: ValueAnimator? = null

    init {
        minimumHeight = (context.resources.displayMetrics.density * 120).toInt()
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        updateAnimation()
    }

    override fun onWindowVisibilityChanged(visibility: Int) {
        super.onWindowVisibilityChanged(visibility)
        updateAnimation()
    }

    override fun onDetachedFromWindow() {
        stopAnimation()
        super.onDetachedFromWindow()
    }

    private fun updateAnimation() {
        if (!isAttachedToWindow || windowVisibility != VISIBLE || !ValueAnimator.areAnimatorsEnabled()) {
            stopAnimation()
        } else if (animation == null) {
            animation = ValueAnimator.ofFloat(0f, 1f).apply {
                duration = 1800L
                repeatMode = ValueAnimator.REVERSE
                repeatCount = ValueAnimator.INFINITE
                addUpdateListener {
                    fraction = it.animatedValue as Float
                    invalidate()
                }
                start()
            }
        }
    }

    private fun stopAnimation() {
        animation?.cancel()
        animation = null
        fraction = 0.5f
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val size = height.toFloat()
        if (size == 0f) return
        paint.color = context.getColor(R.color.pantry_surface_container)
        canvas.drawRoundRect(0f, 0f, width.toFloat(), size, size / 10, size / 10, paint)
        val halfWidth = minOf(width * 0.3f, size * 0.29f)
        paper.set(width / 2f - halfWidth, size * 0.13f, width / 2f + halfWidth, size * 0.87f)
        paint.color = context.getColor(R.color.pantry_surface_bright)
        canvas.drawRoundRect(paper, size / 30, size / 30, paint)
        paint.color = context.getColor(R.color.pantry_soft_sage)
        for (row in 1..3) {
            val y = paper.top + paper.height() * row / 4
            canvas.drawRect(paper.left + halfWidth / 3, y, paper.right - halfWidth / 3, y + size / 55, paint)
        }
        paint.color = context.getColor(R.color.pantry_primary)
        val y = paper.top + paper.height() * fraction
        canvas.drawRect(paper.left - halfWidth / 4, y, paper.right + halfWidth / 4, y + size / 45, paint)
    }
}
