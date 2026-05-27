package com.timetracker.health.location

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import com.google.android.gms.location.ActivityRecognition
import com.google.android.gms.location.ActivityRecognitionClient
import com.google.android.gms.location.DetectedActivity

class ActivityRecognitionController(
    private val context: Context,
    private val onMotionChanged: (MotionState) -> Unit,
) {
    private val client: ActivityRecognitionClient =
        ActivityRecognition.getClient(context)

    fun start() {
        client.requestActivityUpdates(60_000L, pendingIntent())
    }

    fun stop() {
        client.removeActivityUpdates(pendingIntent())
    }

    private fun pendingIntent(): PendingIntent {
        val intent = Intent(context, ActivityRecognitionReceiver::class.java)
        return PendingIntent.getBroadcast(
            context,
            9002,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
        )
    }

    companion object {
        fun motionFromActivities(activities: List<DetectedActivity>): MotionState {
            val top = activities.maxByOrNull { it.confidence } ?: return MotionState.STILL
            return when (top.type) {
                DetectedActivity.IN_VEHICLE,
                DetectedActivity.ON_BICYCLE,
                DetectedActivity.WALKING,
                DetectedActivity.RUNNING,
                -> MotionState.MOVING
                else -> MotionState.STILL
            }
        }
    }
}
