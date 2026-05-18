package com.timetracker.health

import com.google.gson.annotations.SerializedName

data class IngestRecord(
    @SerializedName("record_type") val recordType: String,
    @SerializedName("external_id") val externalId: String,
    @SerializedName("started_at") val startedAt: String? = null,
    @SerializedName("ended_at") val endedAt: String? = null,
    @SerializedName("local_date") val localDate: String? = null,
    @SerializedName("step_count") val stepCount: Int? = null,
    val payload: Map<String, Any?> = emptyMap(),
)

data class IngestBatch(
    @SerializedName("synced_at") val syncedAt: String,
    @SerializedName("device_id") val deviceId: String,
    val records: List<IngestRecord>,
)
