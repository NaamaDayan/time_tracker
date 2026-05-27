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

class ActivityWatchSyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val prefs = Prefs(applicationContext)
        if (prefs.backendUrl.isBlank() || prefs.apiKey.isBlank()) {
            return@withContext Result.failure()
        }

        val sync = ActivityWatchSync(awBaseUrl = prefs.awBaseUrl.ifBlank { null })
        val records = sync.collectRecords(sinceEpochMs = prefs.awLastSyncEpochMs).getOrElse {
            return@withContext Result.retry()
        }
        if (records.isEmpty()) {
            return@withContext Result.success()
        }

        val batch = IngestBatch(
            syncedAt = Instant.now().toString(),
            deviceId = prefs.deviceId(applicationContext),
            records = records,
        )

        val client = IngestClient(prefs.backendUrl, prefs.apiKey)
        client.postActivityWatchBatch(batch).fold(
            onSuccess = {
                prefs.awLastSyncEpochMs = System.currentTimeMillis()
                Result.success()
            },
            onFailure = { Result.retry() },
        )
    }

    companion object {
        private const val WORK_NAME = "activitywatch_sync"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<ActivityWatchSyncWorker>(12, TimeUnit.HOURS)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }
    }
}
