package com.timetracker.health

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.time.Instant
import java.util.concurrent.TimeUnit

class HealthSyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val prefs = Prefs(applicationContext)
        if (prefs.backendUrl.isBlank() || prefs.apiKey.isBlank()) {
            return@withContext Result.failure()
        }

        val reader = SamsungHealthReader(applicationContext)

        val connect = reader.connect()
        if (connect.isFailure || !reader.hasPermissions()) {
            return@withContext Result.retry()
        }

        val records = reader.collectRecords(daysBack = 7)
        if (records.isEmpty()) {
            return@withContext Result.success()
        }

        val batch = IngestBatch(
            syncedAt = Instant.now().toString(),
            deviceId = prefs.deviceId(applicationContext),
            records = records,
        )

        val client = IngestClient(prefs.backendUrl, prefs.apiKey)
        client.postBatch(batch).fold(
            onSuccess = {
                prefs.lastSyncEpochMs = System.currentTimeMillis()
                Result.success()
            },
            onFailure = { Result.retry() },
        )
    }

    companion object {
        private const val WORK_NAME = "samsung_health_sync"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<HealthSyncWorker>(12, TimeUnit.HOURS)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }
    }
}
