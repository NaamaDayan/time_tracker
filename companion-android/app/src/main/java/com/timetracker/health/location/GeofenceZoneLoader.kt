package com.timetracker.health.location

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

object GeofenceZoneLoader {
    private val gson = Gson()

    fun load(context: Context): List<GeofenceZone> {
        val json = context.assets.open("geofence_zones.json").bufferedReader().use { it.readText() }
        val type = object : TypeToken<List<Map<String, Any>>>() {}.type
        val raw: List<Map<String, Any>> = gson.fromJson(json, type) ?: emptyList()
        return raw.mapNotNull { row ->
            val name = row["name"]?.toString() ?: return@mapNotNull null
            val lat = (row["lat"] as? Number)?.toDouble() ?: return@mapNotNull null
            val lon = (row["lon"] as? Number)?.toDouble() ?: return@mapNotNull null
            val radius = (row["radius_m"] as? Number)?.toFloat() ?: 100f
            GeofenceZone(name, lat, lon, radius)
        }
    }
}
