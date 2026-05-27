package com.timetracker.health.location

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.timetracker.health.Prefs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

class DawarichUploadWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val prefs = Prefs(applicationContext)
        val url = prefs.dawarichBaseUrl
        val key = prefs.dawarichApiKey
        if (url.isBlank() || key.isBlank()) {
            return@withContext Result.success()
        }

        val buffer = LocationPointBuffer(applicationContext)
        val points = buffer.load()
        if (points.isEmpty()) {
            return@withContext Result.success()
        }

        if (!prefs.dawarichUploadOnCellular && !isOnWifi(applicationContext)) {
            return@withContext Result.success()
        }

        DawarichClient(url, key).postPoints(points).fold(
            onSuccess = {
                buffer.clear()
                Result.success()
            },
            onFailure = { Result.retry() },
        )
    }

    private fun isOnWifi(context: Context): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
    }

    companion object {
        private const val WORK_NAME = "dawarich_upload"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<DawarichUploadWorker>(15, TimeUnit.MINUTES)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }
    }
}
