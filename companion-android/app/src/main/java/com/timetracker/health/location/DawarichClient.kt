package com.timetracker.health.location

import com.google.gson.Gson
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

class DawarichClient(
    private val baseUrl: String,
    private val apiKey: String,
) {
    private val gson = Gson()
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()

    fun postPoints(points: List<BufferedPoint>): Result<Int> {
        if (points.isEmpty()) return Result.success(0)
        val url = "${baseUrl.trimEnd('/')}/api/v1/owntracks/points?api_key=$apiKey"
        val payload = points.map { p ->
            mapOf(
                "_type" to "location",
                "lat" to p.lat,
                "lon" to p.lon,
                "tst" to p.timestampSec,
                "acc" to p.accuracy,
            )
        }
        val body = gson.toJson(payload).toRequestBody(JSON)
        val request = Request.Builder()
            .url(url)
            .post(body)
            .build()
        return runCatching {
            client.newCall(request).execute().use { response ->
                val text = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw IllegalStateException("Dawarich HTTP ${response.code}: $text")
                }
                points.size
            }
        }
    }

    companion object {
        private val JSON = "application/json; charset=utf-8".toMediaType()
    }
}
