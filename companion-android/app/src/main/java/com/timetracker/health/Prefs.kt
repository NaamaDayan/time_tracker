package com.timetracker.health

import android.content.Context
import android.provider.Settings

class Prefs(context: Context) {
    private val prefs = context.getSharedPreferences("time_tracker_health", Context.MODE_PRIVATE)

    var backendUrl: String
        get() = prefs.getString(KEY_BACKEND, "") ?: ""
        set(value) = prefs.edit().putString(KEY_BACKEND, value.trimEnd('/')).apply()

    var apiKey: String
        get() = prefs.getString(KEY_API_KEY, "") ?: ""
        set(value) = prefs.edit().putString(KEY_API_KEY, value).apply()

    var lastSyncEpochMs: Long
        get() = prefs.getLong(KEY_LAST_SYNC, 0L)
        set(value) = prefs.edit().putLong(KEY_LAST_SYNC, value).apply()

    var awLastSyncEpochMs: Long
        get() = prefs.getLong(KEY_AW_LAST_SYNC, 0L)
        set(value) = prefs.edit().putLong(KEY_AW_LAST_SYNC, value).apply()

    /** Optional override; empty = try 127.0.0.1:5600 and localhost:5600 */
    var awBaseUrl: String
        get() = prefs.getString(KEY_AW_BASE_URL, "") ?: ""
        set(value) = prefs.edit().putString(KEY_AW_BASE_URL, value.trim().trimEnd('/')).apply()

    var dawarichBaseUrl: String
        get() = prefs.getString(KEY_DAWARICH_BASE, "") ?: ""
        set(value) = prefs.edit().putString(KEY_DAWARICH_BASE, value.trim().trimEnd('/')).apply()

    var dawarichApiKey: String
        get() = prefs.getString(KEY_DAWARICH_API_KEY, "") ?: ""
        set(value) = prefs.edit().putString(KEY_DAWARICH_API_KEY, value).apply()

    /** When true, GPS batches upload on cellular (e.g. via Tailscale). Default false saves mobile data. */
    var dawarichUploadOnCellular: Boolean
        get() = prefs.getBoolean(KEY_DAWARICH_CELLULAR, false)
        set(value) = prefs.edit().putBoolean(KEY_DAWARICH_CELLULAR, value).apply()

    var locationTrackingEnabled: Boolean
        get() = prefs.getBoolean(KEY_LOCATION_ENABLED, false)
        set(value) = prefs.edit().putBoolean(KEY_LOCATION_ENABLED, value).apply()

    var motionState: String
        get() = prefs.getString(KEY_MOTION_STATE, "STILL") ?: "STILL"
        set(value) = prefs.edit().putString(KEY_MOTION_STATE, value).apply()

    fun deviceId(context: Context): String {
        val saved = prefs.getString(KEY_DEVICE_ID, null)
        if (saved != null) return saved
        val id = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
            ?: "unknown-device"
        prefs.edit().putString(KEY_DEVICE_ID, id).apply()
        return id
    }

    companion object {
        private const val KEY_BACKEND = "backend_url"
        private const val KEY_API_KEY = "api_key"
        private const val KEY_LAST_SYNC = "last_sync_ms"
        private const val KEY_AW_LAST_SYNC = "aw_last_sync_ms"
        private const val KEY_AW_BASE_URL = "aw_base_url"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_DAWARICH_BASE = "dawarich_base_url"
        private const val KEY_DAWARICH_API_KEY = "dawarich_api_key"
        private const val KEY_DAWARICH_CELLULAR = "dawarich_upload_on_cellular"
        private const val KEY_LOCATION_ENABLED = "location_tracking_enabled"
        private const val KEY_MOTION_STATE = "motion_state"
    }
}
