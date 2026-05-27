package com.timetracker.health.location

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

data class BufferedPoint(
    val lat: Double,
    val lon: Double,
    val accuracy: Float,
    val timestampSec: Long,
)

class LocationPointBuffer(context: Context) {
    private val prefs = context.getSharedPreferences("time_tracker_location", Context.MODE_PRIVATE)
    private val gson = Gson()

    fun append(point: BufferedPoint) {
        val list = load().toMutableList()
        list.add(point)
        prefs.edit().putString(KEY_POINTS, gson.toJson(list)).apply()
    }

    fun load(): List<BufferedPoint> {
        val json = prefs.getString(KEY_POINTS, null) ?: return emptyList()
        val type = object : TypeToken<List<BufferedPoint>>() {}.type
        return gson.fromJson(json, type) ?: emptyList()
    }

    fun clear() {
        prefs.edit().remove(KEY_POINTS).apply()
    }

    fun size(): Int = load().size

    companion object {
        private const val KEY_POINTS = "pending_points"
    }
}
