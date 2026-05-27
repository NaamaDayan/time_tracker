package com.timetracker.health.location

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingClient
import com.google.android.gms.location.GeofencingRequest
import com.google.android.gms.location.LocationServices

class GeofenceManager(private val context: Context) {
    private val client: GeofencingClient = LocationServices.getGeofencingClient(context)

    fun registerZones(zones: List<GeofenceZone>, onComplete: (Result<Unit>) -> Unit) {
        if (zones.isEmpty()) {
            onComplete(Result.success(Unit))
            return
        }
        val geofences = zones.map { zone ->
            Geofence.Builder()
                .setRequestId(zone.name)
                .setCircularRegion(zone.lat, zone.lon, zone.radiusM)
                .setExpirationDuration(Geofence.NEVER_EXPIRE)
                .setTransitionTypes(Geofence.GEOFENCE_TRANSITION_ENTER or Geofence.GEOFENCE_TRANSITION_EXIT)
                .build()
        }
        val request = GeofencingRequest.Builder()
            .setInitialTrigger(GeofencingRequest.INITIAL_TRIGGER_ENTER)
            .addGeofences(geofences)
            .build()
        client.addGeofences(request, pendingIntent(context))
            .addOnCompleteListener { task ->
                if (task.isSuccessful) {
                    onComplete(Result.success(Unit))
                } else {
                    onComplete(Result.failure(task.exception ?: RuntimeException("Geofence register failed")))
                }
            }
    }

    fun removeAll(onComplete: (Result<Unit>) -> Unit = {}) {
        client.removeGeofences(pendingIntent(context))
            .addOnCompleteListener { task ->
                if (task.isSuccessful) onComplete(Result.success(Unit))
                else onComplete(Result.failure(task.exception ?: RuntimeException("Geofence remove failed")))
            }
    }

    companion object {
        private const val REQUEST_CODE = 9001

        fun pendingIntent(context: Context): PendingIntent {
            val intent = Intent(context, GeofenceBroadcastReceiver::class.java)
            return PendingIntent.getBroadcast(
                context,
                REQUEST_CODE,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
            )
        }
    }
}
