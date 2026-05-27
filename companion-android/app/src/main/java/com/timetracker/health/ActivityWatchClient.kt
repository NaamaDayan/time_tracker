package com.timetracker.health

import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.reflect.TypeToken
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

data class AwEvent(
    val id: Long?,
    val timestamp: String,
    val duration: Double,
    val data: Map<String, Any?> = emptyMap(),
)

class ActivityWatchClient(
    baseUrl: String? = null,
) {
    private val gson = Gson()
    private val client = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private val configuredBase: String? = baseUrl?.trim()?.trimEnd('/')?.takeIf { it.isNotBlank() }

    private var resolvedBase: String? = null
    var lastError: String? = null
        private set

    val activeBaseUrl: String?
        get() = resolvedBase ?: configuredBase

    fun isReachable(): Boolean = resolveBaseUrl() != null

    /**
     * Try several times — AW starts its embedded server when you open the AW app
     * (see net.activitywatch.android MainActivity.startServerTask).
     */
    fun isReachableWithRetries(
        attempts: Int = 6,
        delayMs: Long = 750,
    ): Boolean {
        repeat(attempts) { attempt ->
            if (resolveBaseUrl(force = attempt > 0) != null) return true
            if (attempt < attempts - 1) Thread.sleep(delayMs)
        }
        return false
    }

    fun findAndroidBuckets(): List<String> {
        val base = resolveBaseUrl() ?: return emptyList()
        val root = getJson("$base/api/0/buckets/") ?: return emptyList()
        return root.keySet().filter { id ->
            id.contains("android", ignoreCase = true) ||
                id.contains("aw-watcher", ignoreCase = true)
        }.sorted()
    }

    fun fetchEvents(
        bucketId: String,
        startIso: String,
        endIso: String? = null,
    ): List<AwEvent> {
        val base = resolveBaseUrl() ?: return emptyList()
        val encoded = java.net.URLEncoder.encode(bucketId, Charsets.UTF_8.name())
        var url = "$base/api/0/buckets/$encoded/events?start=$startIso"
        if (!endIso.isNullOrBlank()) {
            url += "&end=$endIso"
        }
        val body = getRaw(url) ?: return emptyList()
        return parseEvents(body)
    }

    fun unreachableMessage(): String {
        val tried = (listOfNotNull(configuredBase) + DEFAULT_CANDIDATES).distinct().joinToString(", ")
        val detail = lastError?.let { "\nLast error: $it" }.orEmpty()
        return "Activity Watch API not reachable ($tried).$detail\n\n" +
            "1. Open the Activity Watch app (net.activitywatch.android) and leave it running.\n" +
            "2. Complete onboarding and grant Usage Access.\n" +
            "3. In a browser on the phone, try: http://127.0.0.1:5600/api/0/info\n" +
            "4. Disable battery restrictions for Activity Watch, then sync again."
    }

    private fun resolveBaseUrl(force: Boolean = false): String? {
        if (!force && resolvedBase != null) return resolvedBase

        val candidates = buildList {
            configuredBase?.let { add(it) }
            addAll(DEFAULT_CANDIDATES)
        }.distinct()

        for (candidate in candidates) {
            val normalized = candidate.trimEnd('/')
            if (probe(normalized)) {
                resolvedBase = normalized
                return normalized
            }
        }
        resolvedBase = null
        return null
    }

    private fun probe(base: String): Boolean {
        // /api/0/info is lightweight; buckets confirms datastore is up.
        return getRaw("$base/api/0/info") != null || getJson("$base/api/0/buckets/") != null
    }

    private fun getJson(url: String): JsonObject? {
        val text = getRaw(url) ?: return null
        return runCatching { gson.fromJson(text, JsonObject::class.java) }.getOrNull()
    }

    private fun getRaw(url: String): String? {
        val hostHeader = hostForUrl(url)
        val request = Request.Builder()
            .url(url)
            .addHeader("Host", hostHeader)
            .get()
            .build()
        return runCatching {
            client.newCall(request).execute().use { response ->
                val text = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw IllegalStateException("HTTP ${response.code} for $url: $text")
                }
                text
            }
        }.onFailure { lastError = it.message ?: it.toString() }.getOrNull()
    }

    private fun hostForUrl(url: String): String {
        return runCatching {
            val uri = java.net.URI(url)
            val host = uri.host ?: "127.0.0.1"
            val port = if (uri.port > 0) ":${uri.port}" else ""
            host + port
        }.getOrDefault("127.0.0.1:5600")
    }

    private fun parseEvents(json: String): List<AwEvent> {
        val array = parseEventArray(json) ?: return emptyList()

        return array.mapNotNull { el ->
            if (!el.isJsonObject) return@mapNotNull null
            val obj = el.asJsonObject
            val ts = obj.get("timestamp")?.asString ?: return@mapNotNull null
            val duration = obj.get("duration")?.asDouble ?: 0.0
            val id = obj.get("id")?.let {
                if (it.isJsonNull) null else it.asLong
            }
            val dataEl = obj.getAsJsonObject("data")
            val data: Map<String, Any?> = if (dataEl != null) {
                @Suppress("UNCHECKED_CAST")
                gson.fromJson(dataEl, object : TypeToken<Map<String, Any?>>() {}.type)
                    ?: emptyMap()
            } else {
                emptyMap()
            }
            AwEvent(id = id, timestamp = ts, duration = duration, data = data)
        }
    }

    private fun parseEventArray(json: String): JsonArray? {
        val root: JsonElement = runCatching {
            gson.fromJson(json, JsonElement::class.java)
        }.getOrNull() ?: return null

        return when {
            root.isJsonArray -> root.asJsonArray
            root.isJsonObject && root.asJsonObject.has("events") -> {
                val events = root.asJsonObject.get("events")
                if (events != null && events.isJsonArray) events.asJsonArray else null
            }
            else -> null
        }
    }

    companion object {
        const val DEFAULT_BASE_URL = "http://127.0.0.1:5600"
        val DEFAULT_CANDIDATES = listOf(
            "http://127.0.0.1:5600",
            "http://localhost:5600",
        )
        const val MIN_DURATION_SEC = 1.0
        const val AW_PACKAGE = "net.activitywatch.android"
    }
}
