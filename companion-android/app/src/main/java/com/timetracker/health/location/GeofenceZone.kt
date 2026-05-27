package com.timetracker.health.location

data class GeofenceZone(
    val name: String,
    val lat: Double,
    val lon: Double,
    val radiusM: Float,
)
