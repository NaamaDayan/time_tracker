package com.timetracker.health.location

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.timetracker.health.Prefs

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val prefs = Prefs(context)
        if (!prefs.locationTrackingEnabled) return
        val serviceIntent = Intent(context, LocationTrackingService::class.java)
        context.startForegroundService(serviceIntent)
    }
}
