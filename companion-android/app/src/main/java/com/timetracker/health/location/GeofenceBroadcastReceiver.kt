package com.timetracker.health.location

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingEvent
import com.timetracker.health.Prefs
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class GeofenceBroadcastReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val event = GeofencingEvent.fromIntent(intent) ?: return
        if (event.hasError()) return

        val transition = when (event.geofenceTransition) {
            Geofence.GEOFENCE_TRANSITION_ENTER -> "ENTER"
            Geofence.GEOFENCE_TRANSITION_EXIT -> "EXIT"
            else -> return
        }

        val geofence = event.triggeringGeofences?.firstOrNull() ?: return
        val zoneName = geofence.requestId
        val location = event.triggeringLocation ?: return

        val prefs = Prefs(context)
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            GeofenceEventUploader.upload(
                prefs = prefs,
                zoneName = zoneName,
                transition = transition,
                lat = location.latitude,
                lon = location.longitude,
                timestampMs = location.time,
            )
            pending.finish()
        }
    }
}
