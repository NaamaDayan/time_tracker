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
        private const val KEY_DEVICE_ID = "device_id"
    }
}
