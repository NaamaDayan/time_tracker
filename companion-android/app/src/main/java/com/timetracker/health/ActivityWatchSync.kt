package com.timetracker.health

import java.time.Instant
import java.time.temporal.ChronoUnit

class ActivityWatchSync(
    awBaseUrl: String? = null,
    private val client: ActivityWatchClient = ActivityWatchClient(awBaseUrl),
) {
    fun collectRecords(
        sinceEpochMs: Long = 0L,
        daysBack: Int = 14,
    ): Result<List<IngestRecord>> = runCatching {
        if (!client.isReachableWithRetries()) {
            throw IllegalStateException(client.unreachableMessage())
        }

        val buckets = client.findAndroidBuckets()
        if (buckets.isEmpty()) {
            throw IllegalStateException(
                "No Android watcher buckets found. Open Activity Watch and grant Usage Access.",
            )
        }

        val end = Instant.now()
        val defaultStart = end.minus(daysBack.toLong(), ChronoUnit.DAYS)
        val start = if (sinceEpochMs > 0L) {
            val fromSync = Instant.ofEpochMilli(sinceEpochMs)
            if (fromSync.isBefore(defaultStart)) fromSync else defaultStart
        } else {
            defaultStart
        }
        val startIso = start.toString()
        val endIso = end.toString()

        val records = mutableListOf<IngestRecord>()
        for (bucketId in buckets) {
            val events = client.fetchEvents(bucketId, startIso, endIso)
            for (event in events) {
                if (event.duration < ActivityWatchClient.MIN_DURATION_SEC) continue
                val started = Instant.parse(event.timestamp)
                val ended = started.plusMillis((event.duration * 1000).toLong())

                val app = event.data["app"]?.toString()
                    ?: event.data["name"]?.toString()
                val packageName = event.data["package"]?.toString()

                val eventId = event.id?.toString()
                    ?: "${started.epochSecond}:${event.duration}:${packageName ?: app}"
                val externalId = "aw:$bucketId:$eventId"

                val payload = mutableMapOf<String, Any?>(
                    "app" to app,
                    "package" to packageName,
                    "bucket_id" to bucketId,
                    "aw_event_id" to event.id,
                    "duration_sec" to event.duration,
                    "data" to event.data,
                )

                records.add(
                    IngestRecord(
                        recordType = "app_session",
                        externalId = externalId,
                        startedAt = started.toString(),
                        endedAt = ended.toString(),
                        payload = payload,
                    ),
                )
            }
        }
        records
    }
}
