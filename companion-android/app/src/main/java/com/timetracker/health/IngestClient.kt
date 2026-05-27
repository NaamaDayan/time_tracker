package com.timetracker.health

import com.google.gson.Gson
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

class IngestClient(
    private val backendUrl: String,
    private val apiKey: String,
) {
    private val gson = Gson()
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()

    fun postActivityWatchBatch(batch: IngestBatch): Result<String> =
        postBatch(batch, "/api/v1/integrations/activitywatch/ingest")

    fun postBatch(batch: IngestBatch): Result<String> =
        postBatch(batch, "/api/v1/integrations/samsung/ingest")

    fun postGeofenceEvent(jsonBody: String): Result<String> =
        postJson(jsonBody, "/api/v1/integrations/location/geofence")

    private fun postBatch(batch: IngestBatch, path: String): Result<String> {
        val body = gson.toJson(batch).toRequestBody(JSON)
        return postRaw(body, path)
    }

    private fun postJson(jsonBody: String, path: String): Result<String> {
        val body = jsonBody.toRequestBody(JSON)
        return postRaw(body, path)
    }

    private fun postRaw(body: okhttp3.RequestBody, path: String): Result<String> {
        val url = "${backendUrl.trimEnd('/')}$path"
        val request = Request.Builder()
            .url(url)
            .addHeader("X-API-Key", apiKey)
            .addHeader("Content-Type", "application/json")
            .post(body)
            .build()

        return runCatching {
            client.newCall(request).execute().use { response ->
                val text = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw IllegalStateException("HTTP ${response.code}: $text")
                }
                text
            }
        }
    }

    companion object {
        private val JSON = "application/json; charset=utf-8".toMediaType()
    }
}
