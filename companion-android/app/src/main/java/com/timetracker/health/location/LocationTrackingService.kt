package com.timetracker.health.location

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.timetracker.health.Prefs
import com.timetracker.health.R

class LocationTrackingService : Service() {
    private val logTag = "LocationTrackingService"

    private lateinit var prefs: Prefs
    private lateinit var geofenceManager: GeofenceManager
    private var fusedPoller: FusedLocationPoller? = null
    private var activityController: ActivityRecognitionController? = null
    private var lastMotionChangeMs = 0L

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        geofenceManager = GeofenceManager(this)
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = buildNotification("Location tracking active")
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION,
                )
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
        } catch (e: Exception) {
            Log.e(logTag, "startForeground failed", e)
            stopSelf()
            return START_NOT_STICKY
        }

        if (!hasLocationPermission()) {
            Log.e(logTag, "Missing location permission; stopping service")
            stopSelf()
            return START_NOT_STICKY
        }

        try {
            when (intent?.action) {
                ACTION_MOTION_CHANGED -> {
                    val motionName = intent.getStringExtra(EXTRA_MOTION) ?: MotionState.STILL.name
                    applyMotion(MotionState.valueOf(motionName))
                }
                else -> bootstrap()
            }
            DawarichUploadWorker.schedule(this)
        } catch (e: Exception) {
            Log.e(logTag, "bootstrap failed", e)
            stopSelf()
        }
        return START_STICKY
    }

    private fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(
            this,
            android.Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED

    private fun bootstrap() {
        val zones = GeofenceZoneLoader.load(this)
        geofenceManager.registerZones(zones) { result ->
            result.onFailure { Log.e(logTag, "Geofence register failed", it) }
        }
        activityController = ActivityRecognitionController(this) { motion ->
            applyMotionDebounced(motion)
        }.also { it.start() }
        applyMotion(
            runCatching { MotionState.valueOf(prefs.motionState) }.getOrDefault(MotionState.STILL),
        )
    }

    private fun applyMotionDebounced(motion: MotionState) {
        val now = System.currentTimeMillis()
        if (now - lastMotionChangeMs < 30_000) return
        lastMotionChangeMs = now
        prefs.motionState = motion.name
        applyMotion(motion)
    }

    private fun applyMotion(motion: MotionState) {
        when (motion) {
            MotionState.MOVING -> {
                if (fusedPoller == null) {
                    fusedPoller = FusedLocationPoller(this) { /* buffered */ }
                }
                fusedPoller?.start()
            }
            MotionState.STILL -> {
                fusedPoller?.stop()
                maybeUploadPoints()
            }
        }
        val nm = getSystemService(NotificationManager::class.java)
        nm.notify(NOTIFICATION_ID, buildNotification("Motion: ${motion.name}"))
    }

    private fun maybeUploadPoints() {
        val url = prefs.dawarichBaseUrl
        val key = prefs.dawarichApiKey
        if (url.isBlank() || key.isBlank()) return
        val poller = fusedPoller ?: return
        val points = poller.pendingPoints()
        if (points.isEmpty()) return
        DawarichClient(url, key).postPoints(points).onSuccess {
            poller.clearPending()
        }
    }

    override fun onDestroy() {
        fusedPoller?.stop()
        activityController?.stop()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Location tracking",
            NotificationManager.IMPORTANCE_LOW,
        )
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun buildNotification(text: String): Notification =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setOngoing(true)
            .build()

    companion object {
        const val ACTION_MOTION_CHANGED = "com.timetracker.health.MOTION_CHANGED"
        const val EXTRA_MOTION = "motion"
        private const val CHANNEL_ID = "location_tracking"
        private const val NOTIFICATION_ID = 42
    }
}
