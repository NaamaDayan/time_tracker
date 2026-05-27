package com.timetracker.health

import android.content.Intent
import android.os.Bundle
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import com.google.android.material.checkbox.MaterialCheckBox
import com.google.android.material.textfield.TextInputEditText
import android.util.Log
import androidx.core.content.ContextCompat
import com.timetracker.health.location.LocationPermissionHelper
import com.timetracker.health.location.LocationTrackingService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant

class MainActivity : AppCompatActivity() {
    private lateinit var prefs: Prefs
    private lateinit var reader: SamsungHealthReader

    private lateinit var backendUrl: TextInputEditText
    private lateinit var apiKey: TextInputEditText
    private lateinit var awBaseUrl: TextInputEditText
    private lateinit var dawarichBaseUrl: TextInputEditText
    private lateinit var dawarichApiKey: TextInputEditText
    private lateinit var dawarichUploadOnCellular: MaterialCheckBox
    private lateinit var statusText: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val toolbar = findViewById<MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)

        reader = SamsungHealthReader(this)
        prefs = Prefs(this)

        backendUrl = findViewById(R.id.backendUrl)
        apiKey = findViewById(R.id.apiKey)
        awBaseUrl = findViewById(R.id.awBaseUrl)
        dawarichBaseUrl = findViewById(R.id.dawarichBaseUrl)
        dawarichApiKey = findViewById(R.id.dawarichApiKey)
        dawarichUploadOnCellular = findViewById(R.id.dawarichUploadOnCellular)
        statusText = findViewById(R.id.statusText)

        if (prefs.backendUrl.isNotBlank()) {
            backendUrl.setText(prefs.backendUrl)
        }
        if (prefs.apiKey.isNotBlank()) {
            apiKey.setText(prefs.apiKey)
        }
        if (prefs.awBaseUrl.isNotBlank()) {
            awBaseUrl.setText(prefs.awBaseUrl)
        } else {
            awBaseUrl.setText(ActivityWatchClient.DEFAULT_BASE_URL)
        }
        if (prefs.dawarichBaseUrl.isNotBlank()) {
            dawarichBaseUrl.setText(prefs.dawarichBaseUrl)
        }
        if (prefs.dawarichApiKey.isNotBlank()) {
            dawarichApiKey.setText(prefs.dawarichApiKey)
        }
        dawarichUploadOnCellular.isChecked = prefs.dawarichUploadOnCellular

        findViewById<MaterialButton>(R.id.saveSettings).setOnClickListener {
            prefs.backendUrl = backendUrl.text?.toString().orEmpty()
            prefs.apiKey = apiKey.text?.toString().orEmpty()
            prefs.awBaseUrl = awBaseUrl.text?.toString().orEmpty()
            prefs.dawarichBaseUrl = dawarichBaseUrl.text?.toString().orEmpty()
            prefs.dawarichApiKey = dawarichApiKey.text?.toString().orEmpty()
            prefs.dawarichUploadOnCellular = dawarichUploadOnCellular.isChecked
            HealthSyncWorker.schedule(this)
            ActivityWatchSyncWorker.schedule(this)
            toast("Settings saved")
        }

        findViewById<MaterialButton>(R.id.connectHealth).setOnClickListener {
            connectSamsungHealth()
        }

        findViewById<MaterialButton>(R.id.syncNow).setOnClickListener {
            syncNow()
        }

        findViewById<MaterialButton>(R.id.openActivityWatch).setOnClickListener {
            openActivityWatchApp()
        }

        findViewById<MaterialButton>(R.id.syncActivityWatch).setOnClickListener {
            syncActivityWatch()
        }

        findViewById<MaterialButton>(R.id.locationPermissions).setOnClickListener {
            requestLocationPermissions()
        }

        findViewById<MaterialButton>(R.id.batteryOptimization).setOnClickListener {
            LocationPermissionHelper.openBatteryOptimizationSettings(this)
        }

        findViewById<MaterialButton>(R.id.startLocation).setOnClickListener {
            startLocationTracking()
        }
    }

    private fun requestLocationPermissions() {
        if (!LocationPermissionHelper.hasFineLocation(this)) {
            LocationPermissionHelper.requestFineLocation(this)
            return
        }
        if (!LocationPermissionHelper.hasBackgroundLocation(this)) {
            LocationPermissionHelper.requestBackgroundLocation(this)
            return
        }
        if (!LocationPermissionHelper.hasActivityRecognition(this)) {
            LocationPermissionHelper.requestActivityRecognition(this)
            return
        }
        if (!LocationPermissionHelper.hasPostNotifications(this)) {
            LocationPermissionHelper.requestPostNotifications(this)
            return
        }
        toast("Location permissions already granted")
    }

    private fun startLocationTracking() {
        prefs.backendUrl = backendUrl.text?.toString().orEmpty()
        prefs.apiKey = apiKey.text?.toString().orEmpty()
        prefs.dawarichBaseUrl = dawarichBaseUrl.text?.toString().orEmpty()
        prefs.dawarichApiKey = dawarichApiKey.text?.toString().orEmpty()

        if (!LocationPermissionHelper.hasAllForLocationTracking(this)) {
            toast("Grant all location permissions first (including Notifications on Android 13+)")
            requestLocationPermissions()
            return
        }

        prefs.locationTrackingEnabled = true
        try {
            ContextCompat.startForegroundService(
                this,
                Intent(this, LocationTrackingService::class.java),
            )
            setStatus(
                "Location tracking started.\n" +
                    "Geofences active; GPS polls every 5 min while moving.\n" +
                    "Disable battery optimization for reliable Samsung delivery.",
            )
        } catch (e: Exception) {
            Log.e("MainActivity", "Failed to start location service", e)
            prefs.locationTrackingEnabled = false
            setStatus("Could not start location tracking: ${e.message}")
            toast("Start failed: ${e.message}")
        }
    }

    private fun openActivityWatchApp() {
        val intent = packageManager.getLaunchIntentForPackage(ActivityWatchClient.AW_PACKAGE)
        if (intent != null) {
            startActivity(intent)
            setStatus("Opened Activity Watch. Wait a few seconds, then tap Sync Activity Watch.")
        } else {
            toast("Install Activity Watch from Play Store first")
        }
    }

    private fun connectSamsungHealth() {
        lifecycleScope.launch {
            setStatus("Connecting to Samsung Health…")
            try {
                withContext(Dispatchers.Main) {
                    reader.connect().getOrThrow()
                    when (val result = reader.ensurePermissions()) {
                        PermissionResult.Granted ->
                            setStatus(
                                "Samsung Health connected.\n" +
                                    "Permissions granted for Sleep, Exercise, and Steps.",
                            )

                        is PermissionResult.Denied ->
                            setStatus(result.message)

                        is PermissionResult.NeedsResolution -> {
                            reader.resolveIfNeeded(result)
                            setStatus(
                                "Samsung Health needs setup (update app, accept terms, or " +
                                    "enable Developer Mode). Complete the dialog, then tap Connect again.",
                            )
                        }

                        is PermissionResult.Error ->
                            setStatus("Connect failed: ${result.message}")
                    }
                }
            } catch (e: Exception) {
                if (reader.resolveIfNeeded(e)) {
                    setStatus("Complete the Samsung Health dialog, then tap Connect again.")
                } else {
                    setStatus("Connect failed: ${e.message}")
                }
            }
        }
    }

    private fun syncNow() {
        val url = backendUrl.text?.toString().orEmpty().ifBlank { prefs.backendUrl }
        val key = apiKey.text?.toString().orEmpty().ifBlank { prefs.apiKey }
        if (url.isBlank() || key.isBlank()) {
            toast("Set backend URL and API key first")
            return
        }
        prefs.backendUrl = url
        prefs.apiKey = key

        lifecycleScope.launch {
            setStatus("Checking Samsung Health permissions…")
            try {
                val records = withContext(Dispatchers.Main) {
                    reader.connect().getOrThrow()
                    when (val perm = reader.ensurePermissions()) {
                        PermissionResult.Granted -> { /* ok */ }
                        is PermissionResult.Denied ->
                            throw IllegalStateException(perm.message)
                        is PermissionResult.NeedsResolution -> {
                            reader.resolveIfNeeded(perm)
                            throw IllegalStateException(
                                "Samsung Health needs setup. Tap Connect and complete the dialog.",
                            )
                        }
                        is PermissionResult.Error ->
                            throw IllegalStateException(perm.message)
                    }
                    setStatus("Reading Samsung Health data…")
                    reader.collectRecords(daysBack = 14)
                }

                val batch = IngestBatch(
                    syncedAt = Instant.now().toString(),
                    deviceId = prefs.deviceId(this@MainActivity),
                    records = records,
                )
                setStatus("Uploading ${records.size} records…")
                val response = withContext(Dispatchers.IO) {
                    IngestClient(url, key).postBatch(batch).getOrThrow()
                }
                prefs.lastSyncEpochMs = System.currentTimeMillis()
                val sleepN = records.count { it.recordType == "sleep_session" }
                val exerciseN = records.count { it.recordType == "exercise_session" }
                val stepsN = records.count { it.recordType == "daily_steps" }
                setStatus(
                    "Synced ${records.size} records " +
                        "($sleepN sleep, $exerciseN exercise, $stepsN step-days).\n" +
                        "Reload the web calendar to see new blocks.\n$response",
                )
            } catch (e: Exception) {
                if (reader.resolveIfNeeded(e)) {
                    setStatus("Complete the Samsung Health dialog, then try again.")
                } else {
                    setStatus(
                        e.message?.takeIf { it.isNotBlank() }
                            ?: "Sync failed. Tap Connect Samsung Health first.",
                    )
                }
            }
        }
    }

    private fun syncActivityWatch() {
        val url = backendUrl.text?.toString().orEmpty().ifBlank { prefs.backendUrl }
        val key = apiKey.text?.toString().orEmpty().ifBlank { prefs.apiKey }
        if (url.isBlank() || key.isBlank()) {
            toast("Set backend URL and API key first")
            return
        }
        prefs.backendUrl = url
        prefs.apiKey = key

        val awUrl = awBaseUrl.text?.toString().orEmpty().ifBlank { prefs.awBaseUrl }
        prefs.awBaseUrl = awUrl

        lifecycleScope.launch {
            setStatus(
                "Connecting to Activity Watch on this phone…\n" +
                    "Tip: open Activity Watch first if this fails.",
            )
            try {
                val records = withContext(Dispatchers.IO) {
                    ActivityWatchSync(awBaseUrl = awUrl.ifBlank { null })
                        .collectRecords(sinceEpochMs = prefs.awLastSyncEpochMs, daysBack = 14)
                        .getOrThrow()
                }

                val batch = IngestBatch(
                    syncedAt = Instant.now().toString(),
                    deviceId = prefs.deviceId(this@MainActivity),
                    records = records,
                )
                setStatus("Uploading ${records.size} app sessions…")
                val response = withContext(Dispatchers.IO) {
                    IngestClient(url, key).postActivityWatchBatch(batch).getOrThrow()
                }
                prefs.awLastSyncEpochMs = System.currentTimeMillis()
                setStatus(
                    "Activity Watch: synced ${records.size} app sessions.\n" +
                        "Reload the web app calendar / pie / net views.\n$response",
                )
            } catch (e: Exception) {
                setStatus(
                    e.message?.takeIf { it.isNotBlank() }
                        ?: "Activity Watch sync failed. Is the AW app running?",
                )
            }
        }
    }

    private fun setStatus(msg: String) {
        statusText.text = msg
    }

    private fun toast(msg: String) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
    }
}
