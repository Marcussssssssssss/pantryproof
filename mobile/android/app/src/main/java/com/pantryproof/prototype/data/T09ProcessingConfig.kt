package com.pantryproof.prototype.data

/** Trusted, process-local enablement. The Activity separately checks the installed variant. */
internal object T09ProcessingConfig {
    const val HOST = "10.0.2.2"
    const val PORT = 8765
    private val bearerSyntax = Regex("[A-Za-z0-9._~+/\\-]+=*")
    private var pending: Session? = null

    fun isCapable(packageName: String) = packageName == "com.pantryproof.prototype.t09live"

    class Session internal constructor(val scheme: String, val host: String, val port: Int, credential: String) {
        init {
            require(scheme == "http" && host == HOST && port == PORT) { "Unapproved T09 development origin." }
            require(credential.length in 1..4096 && bearerSyntax.matches(credential)) { "Invalid Bearer credential." }
        }

        @Volatile
        private var token: String? = credential

        fun credential(): String? = token

        fun clear() { token = null }
    }

    @Synchronized
    fun configure(scheme: String, host: String, port: Int, bearer: String) {
        val next = Session(scheme, host, port, bearer)
        pending?.clear()
        pending = next
    }

    @Synchronized
    fun isConfigured(): Boolean = pending != null

    @Synchronized
    fun take(): Session? = pending.also { pending = null }

    @Synchronized
    fun clear() { take()?.clear() }
}
