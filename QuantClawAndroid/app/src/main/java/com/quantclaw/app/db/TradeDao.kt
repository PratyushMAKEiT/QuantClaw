package com.quantclaw.app.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface TradeDao {
    @Query("SELECT * FROM completed_trades ORDER BY timestamp DESC")
    suspend fun getAllTrades(): List<TradeEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTrades(trades: List<TradeEntity>)

    @Query("DELETE FROM completed_trades")
    suspend fun deleteAllTrades()
}
