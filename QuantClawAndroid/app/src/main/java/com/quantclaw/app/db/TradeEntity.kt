package com.quantclaw.app.db

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "completed_trades")
data class TradeEntity(
    @PrimaryKey val id: String,
    val timestamp: Long,
    val symbol: String,
    val side: String,
    val regime: String,
    val confidence: Int,
    val grossPnl: Double,
    val fee: Double,
    val indiaCost: Double,
    val netPnl: Double,
    val reasoning: String
)
