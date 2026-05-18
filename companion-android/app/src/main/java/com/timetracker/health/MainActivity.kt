package com.timetracker.health

import android.os.Bundle
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant

class MainActivity : AppCompatActivity() {
    private lateinit var prefs: Prefs
    private lateinit var reader: SamsungHealthReader

    private lateinit var backendUrl: TextInputEditText
    private lateinit var apiKey: TextInputEditText
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
        statusText = findViewById(R.id.statusText)

        if (prefs.backendUrl.isNotBlank()) {
            backendUrl.setText(prefs.backendUrl)
        }
        if (prefs.apiKey.isNotBlank()) {
            apiKey.setText(prefs.apiKey)
        }

        findViewById<MaterialButton>(R.id.saveSettings).setOnClickListener {
            prefs.backendUrl = backendUrl.text?.toString().orEmpty()
            prefs.apiKey = apiKey.text?.toString().orEmpty()
            HealthSyncWorker.schedule(this)
            toast("Settings saved")
        }

        findViewById<MaterialButton>(R.id.connectHealth).setOnClickListener {
            connectSamsungHealth()
        }

        findViewById<MaterialButton>(R.id.syncNow).setOnClickListener {
            syncNow()
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

    private fun setStatus(msg: String) {
        statusText.text = msg
    }

    private fun toast(msg: String) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
    }
}
