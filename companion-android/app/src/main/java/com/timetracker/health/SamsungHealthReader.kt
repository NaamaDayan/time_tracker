package com.timetracker.health

import android.app.Activity
import android.content.Context
import android.util.Log
import com.samsung.android.sdk.health.data.HealthDataService
import com.samsung.android.sdk.health.data.HealthDataStore
import com.samsung.android.sdk.health.data.data.AggregatedData
import com.samsung.android.sdk.health.data.data.HealthDataPoint
import com.samsung.android.sdk.health.data.error.HealthDataException
import com.samsung.android.sdk.health.data.error.ResolvablePlatformException
import com.samsung.android.sdk.health.data.permission.AccessType
import com.samsung.android.sdk.health.data.permission.Permission
import com.samsung.android.sdk.health.data.request.DataType
import com.samsung.android.sdk.health.data.request.DataTypes
import com.samsung.android.sdk.health.data.request.LocalDateFilter
import com.samsung.android.sdk.health.data.request.LocalTimeFilter
import com.samsung.android.sdk.health.data.request.LocalTimeGroup
import com.samsung.android.sdk.health.data.request.LocalTimeGroupUnit
import com.samsung.android.sdk.health.data.request.Ordering
import com.samsung.android.sdk.health.data.response.DataResponse
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * Reads sleep, exercise, and daily steps from Samsung Health Data SDK.
 *
 * Permission UI must run on the main thread with a live [Activity].
 */
class SamsungHealthReader private constructor(
    private val appContext: Context,
    private val uiActivity: Activity?,
) {
    /** Use from screens — can show Samsung Health permission UI. */
    constructor(activity: Activity) : this(activity.applicationContext, activity)

    /** Background sync only — cannot request permissions (use after manual Connect). */
    constructor(appContext: Context) : this(appContext.applicationContext, null)

    private var store: HealthDataStore? = null

    fun connect(): Result<HealthDataStore> = runCatching {
        HealthDataService.getStore(appContext).also { store = it }
    }

    /**
     * Shows Samsung Health permission UI if needed. Call from [androidx.lifecycle.lifecycleScope]
     * on the main thread (e.g. `withContext(Dispatchers.Main)`).
     */
    suspend fun ensurePermissions(): PermissionResult {
        val activity = uiActivity
            ?: return PermissionResult.Error(
                "Open the app and tap Connect Samsung Health to grant permissions.",
            )

        val healthDataStore = store ?: connect().getOrElse { e ->
            return PermissionResult.Error("Could not connect to Samsung Health: ${e.message}")
        }

        val permSet = permissionSet()
        return try {
            var granted = healthDataStore.getGrantedPermissions(permSet)
            if (granted.containsAll(permSet)) {
                return PermissionResult.Granted
            }

            Log.i(TAG, "Requesting Samsung Health permissions (sleep, exercise, steps)…")
            granted = healthDataStore.requestPermissions(permSet, activity)

            if (granted.containsAll(permSet)) {
                PermissionResult.Granted
            } else {
                val missing = permSet - granted
                PermissionResult.Denied(
                    "Not all permissions were granted. Missing: ${missing.describe()}. " +
                        "Tap Connect again and allow Sleep, Exercise, and Steps in Samsung Health.",
                )
            }
        } catch (e: HealthDataException) {
            Log.e(TAG, "Permission error", e)
            if (e is ResolvablePlatformException && e.hasResolution) {
                PermissionResult.NeedsResolution(e)
            } else {
                PermissionResult.Error(e.message ?: "Samsung Health permission error")
            }
        }
    }

    suspend fun hasPermissions(): Boolean {
        val healthDataStore = store ?: connect().getOrNull() ?: return false
        return try {
            val permSet = permissionSet()
            healthDataStore.getGrantedPermissions(permSet).containsAll(permSet)
        } catch (e: Exception) {
            Log.w(TAG, "hasPermissions failed: ${e.message}")
            false
        }
    }

    private fun Set<Permission>.describe(): String =
        joinToString { it.toString() }

    private fun permissionSet() = setOf(
        Permission.of(DataTypes.SLEEP, AccessType.READ),
        Permission.of(DataTypes.EXERCISE, AccessType.READ),
        Permission.of(DataTypes.STEPS, AccessType.READ),
    )

    suspend fun collectRecords(daysBack: Int = 14): List<IngestRecord> {
        val healthDataStore = store ?: error("Samsung Health not connected")
        val records = mutableListOf<IngestRecord>()
        val end = LocalDateTime.now()
        val start = end.minusDays(daysBack.toLong())

        records.addAll(readSleepSessions(healthDataStore, start, end))
        records.addAll(readExerciseSessions(healthDataStore, start, end))
        records.addAll(readDailySteps(healthDataStore, daysBack))

        return records
    }

    private suspend fun readSleepSessions(
        store: HealthDataStore,
        start: LocalDateTime,
        end: LocalDateTime,
    ): List<IngestRecord> {
        val cutoff = start.atZone(java.time.ZoneId.systemDefault()).toInstant()
        val out = mutableListOf<IngestRecord>()

        // Samsung docs: sleep reads use limit + ordering, NOT LocalTimeFilter (often returns 0 rows).
        try {
            val limit = minOf(100, maxOf(30, Duration.between(start, end).toDays().toInt() * 3))
            val request = DataTypes.SLEEP.readDataRequestBuilder
                .setOrdering(Ordering.DESC)
                .setLimit(limit)
                .build()
            val result = store.readData(request)
            Log.i(TAG, "readSleepSessions readData: ${result.dataList.size} points (limit=$limit)")
            for (point in result.dataList) {
                out.addAll(sleepRecordsFromPoint(point, cutoff))
            }
        } catch (e: Exception) {
            Log.w(TAG, "readSleepSessions readData failed: ${e.message}", e)
        }

        if (out.isEmpty()) {
            try {
                val fromDate = start.toLocalDate()
                val toDate = end.toLocalDate()
                val aggRequest = DataType.SleepType.TOTAL_DURATION.requestBuilder
                    .setLocalDateFilter(LocalDateFilter.of(fromDate, toDate))
                    .build()
                val aggResult = store.aggregateData(aggRequest)
                Log.i(TAG, "readSleepSessions aggregate: ${aggResult.dataList.size} nights")
                for (agg in aggResult.dataList) {
                    val startInstant = agg.startTime ?: continue
                    val endInstant = agg.endTime ?: continue
                    if (endInstant.isBefore(cutoff)) continue
                    val uid = "agg-${startInstant.toEpochMilli()}"
                    out.add(
                        IngestRecord(
                            recordType = "sleep_session",
                            externalId = "sleep:$uid",
                            startedAt = startInstant.toString(),
                            endedAt = endInstant.toString(),
                            payload = mapOf(
                                "duration_min" to Duration.between(startInstant, endInstant).toMinutes(),
                                "source" to "aggregate_total_duration",
                            ),
                        ),
                    )
                }
            } catch (e: Exception) {
                Log.w(TAG, "readSleepSessions aggregate failed: ${e.message}", e)
            }
        }

        val deduped = out.distinctBy { it.externalId }
        Log.i(TAG, "readSleepSessions: ${deduped.size} sleep records")
        return deduped
    }

    private fun sleepRecordsFromPoint(point: HealthDataPoint, cutoff: Instant): List<IngestRecord> {
        val records = mutableListOf<IngestRecord>()
        val sessions = point.getValue(DataType.SleepType.SESSIONS)
        if (!sessions.isNullOrEmpty()) {
            for (session in sessions) {
                val startInstant = session.startTime ?: continue
                val endInstant = session.endTime ?: continue
                if (endInstant.isBefore(cutoff)) continue
                val uid = "${point.uid}-${startInstant.toEpochMilli()}"
                records.add(
                    IngestRecord(
                        recordType = "sleep_session",
                        externalId = "sleep:$uid",
                        startedAt = startInstant.toString(),
                        endedAt = endInstant.toString(),
                        payload = mapOf(
                            "duration_min" to session.duration?.toMinutes(),
                            "sdk_uid" to point.uid,
                        ),
                    ),
                )
            }
            return records
        }

        val bed = point.startTime
        val wake = point.endTime
        if (bed != null && wake != null && !wake.isBefore(cutoff)) {
            val durationMin = point.getValue(DataType.SleepType.DURATION)?.toMinutes()
                ?: Duration.between(bed, wake).toMinutes()
            records.add(
                IngestRecord(
                    recordType = "sleep_session",
                    externalId = "sleep:${point.uid}",
                    startedAt = bed.toString(),
                    endedAt = wake.toString(),
                    payload = mapOf(
                        "duration_min" to durationMin,
                        "sdk_uid" to point.uid,
                    ),
                ),
            )
        }
        return records
    }

    private suspend fun readExerciseSessions(
        store: HealthDataStore,
        start: LocalDateTime,
        end: LocalDateTime,
    ): List<IngestRecord> {
        val request = DataTypes.EXERCISE.readDataRequestBuilder
            .setLocalTimeFilter(LocalTimeFilter.of(start, end))
            .build()

        val result = store.readData(request)
        val out = mutableListOf<IngestRecord>()

        for (point in result.dataList) {
            val sessions = point.getValue(DataType.ExerciseType.SESSIONS) ?: continue
            for ((index, session) in sessions.withIndex()) {
                val startInstant = session.startTime ?: continue
                val endInstant = session.endTime
                    ?: startInstant.plus(session.duration ?: Duration.ZERO)
                val typeName = session.exerciseType?.name ?: "UNKNOWN"
                val calories = session.calories
                val durationSec = session.duration?.seconds
                out.add(
                    IngestRecord(
                        recordType = "exercise_session",
                        externalId = "exercise:${point.uid}-$index",
                        startedAt = startInstant.toString(),
                        endedAt = endInstant.toString(),
                        payload = mapOf(
                            "exercise_type" to typeName,
                            "calories" to calories,
                            "duration_sec" to durationSec,
                        ),
                    ),
                )
            }
        }
        return out
    }

    private suspend fun readDailySteps(store: HealthDataStore, daysBack: Int): List<IngestRecord> {
        val out = mutableListOf<IngestRecord>()
        val today = LocalDate.now()

        for (offset in 0 until daysBack) {
            val day = today.minusDays(offset.toLong())
            val start = day.atStartOfDay()
            val end = day.plusDays(1).atStartOfDay().minusNanos(1)
            val request = DataType.StepsType.TOTAL.requestBuilder
                .setLocalTimeFilterWithGroup(
                    LocalTimeFilter.of(start, end),
                    LocalTimeGroup.of(LocalTimeGroupUnit.DAILY, 1),
                )
                .build()

            try {
                val result: DataResponse<AggregatedData<Long>> = store.aggregateData(request)
                val count = result.dataList.firstOrNull()?.value ?: continue
                if (count <= 0) continue
                out.add(
                    IngestRecord(
                        recordType = "daily_steps",
                        externalId = "steps:${day.format(DateTimeFormatter.ISO_LOCAL_DATE)}",
                        localDate = day.format(DateTimeFormatter.ISO_LOCAL_DATE),
                        stepCount = count.toInt(),
                        payload = mapOf("step_count" to count),
                    ),
                )
            } catch (e: Exception) {
                Log.w(TAG, "Steps read failed for $day: ${e.message}")
            }
        }
        return out
    }

    fun resolveIfNeeded(error: Throwable): Boolean {
        val activity = uiActivity ?: return false
        if (error is ResolvablePlatformException && error.hasResolution) {
            error.resolve(activity)
            return true
        }
        return false
    }

    fun resolveIfNeeded(result: PermissionResult.NeedsResolution): Boolean {
        val activity = uiActivity ?: return false
        if (result.exception.hasResolution) {
            result.exception.resolve(activity)
            return true
        }
        return false
    }

    companion object {
        private const val TAG = "SamsungHealthReader"
    }
}

sealed class PermissionResult {
    data object Granted : PermissionResult()
    data class Denied(val message: String) : PermissionResult()
    data class NeedsResolution(val exception: ResolvablePlatformException) : PermissionResult()
    data class Error(val message: String) : PermissionResult()
}
