package com.timetracker.health.location

import com.google.gson.Gson
import com.timetracker.health.IngestClient
import com.timetracker.health.Prefs
import java.time.Instant

data class GeofenceEventPayload(
    val zone_name: String,
    val transition: String,
    val lat: Double,
    val lon: Double,
    val timestamp: String,
)

object GeofenceEventUploader {
    private val gson = Gson()

    fun upload(
        prefs: Prefs,
        zoneName: String,
        transition: String,
        lat: Double,
        lon: Double,
        timestampMs: Long = System.currentTimeMillis(),
    ): Result<String> {
        val backend = prefs.backendUrl
        val key = prefs.apiKey
        if (backend.isBlank() || key.isBlank()) {
            return Result.failure(IllegalStateException("Backend URL and API key required"))
        }
        val payload = GeofenceEventPayload(
            zone_name = zoneName,
            transition = transition,
            lat = lat,
            lon = lon,
            timestamp = Instant.ofEpochMilli(timestampMs).toString(),
        )
        return IngestClient(backend, key).postGeofenceEvent(gson.toJson(payload))
    }
}
