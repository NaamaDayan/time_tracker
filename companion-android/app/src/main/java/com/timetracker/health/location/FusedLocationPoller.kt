package com.timetracker.health.location

import android.annotation.SuppressLint
import android.content.Context
import android.os.Looper
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority

class FusedLocationPoller(
    private val context: Context,
    private val onPoint: (BufferedPoint) -> Unit,
) {
    private val fused = LocationServices.getFusedLocationProviderClient(context)
    private val buffer = LocationPointBuffer(context)
    private var running = false

    private val callback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            val loc = result.lastLocation ?: return
            val point = BufferedPoint(
                lat = loc.latitude,
                lon = loc.longitude,
                accuracy = loc.accuracy,
                timestampSec = loc.time / 1000,
            )
            buffer.append(point)
            onPoint(point)
        }
    }

    @SuppressLint("MissingPermission")
    fun start() {
        if (running) return
        running = true
        val request = LocationRequest.Builder(Priority.PRIORITY_BALANCED_POWER_ACCURACY, 300_000L)
            .setMinUpdateIntervalMillis(300_000L)
            .setMaxUpdateDelayMillis(300_000L)
            .build()
        fused.requestLocationUpdates(request, callback, Looper.getMainLooper())
    }

    fun stop() {
        if (!running) return
        running = false
        fused.removeLocationUpdates(callback)
    }

    fun pendingPoints(): List<BufferedPoint> = buffer.load()

    fun clearPending() = buffer.clear()
}
