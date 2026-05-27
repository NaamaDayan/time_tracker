package com.timetracker.health.location

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.google.android.gms.location.ActivityRecognitionResult
import com.timetracker.health.Prefs

class ActivityRecognitionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!ActivityRecognitionResult.hasResult(intent)) return
        val result = ActivityRecognitionResult.extractResult(intent) ?: return
        val motion = ActivityRecognitionController.motionFromActivities(result.probableActivities)
        val prefs = Prefs(context)
        val previous = prefs.motionState
        if (previous == motion.name) return
        prefs.motionState = motion.name
        val serviceIntent = Intent(context, LocationTrackingService::class.java)
            .setAction(LocationTrackingService.ACTION_MOTION_CHANGED)
            .putExtra(LocationTrackingService.EXTRA_MOTION, motion.name)
        context.startForegroundService(serviceIntent)
    }
}
