package com.quantclaw.app.network

import android.os.Parcelable
import com.google.gson.annotations.SerializedName
import kotlinx.parcelize.Parcelize
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query
import java.util.concurrent.TimeUnit

// ------------------------------------------------------------------------------
// RESPONSE DATA MODELS
// ------------------------------------------------------------------------------

@Parcelize
data class StatusResponse(
    val armed: Boolean?,
    val connected: Boolean?,
    val status: String?,
    @SerializedName("status_message") val statusMessage: String?,
    val regime: String?,
    @SerializedName("active_profile") val activeProfile: String?,
    @SerializedName("news_sentiment") val newsSentiment: Double?,
    @SerializedName("high_impact_macro") val highImpactMacro: Boolean?,
    @SerializedName("top_headlines") val topHeadlines: List<String>?,
    val positions: List<PositionModel>?,
    val logs: List<String>?,
    val balance: Double?,
    val equity: Double?,
    @SerializedName("floating_pnl") val floatingPnL: Double?,
    @SerializedName("today_pnl") val todayPnL: Double?,
    val login: Long?,
    val server: String?,
    @SerializedName("session_pnl") val sessionPnL: Double?,
    @SerializedName("total_trades") val totalTrades: Int?,
    @SerializedName("thinking_status") val thinkingStatus: String?,
    @SerializedName("decision_score") val decisionScore: Double?,
    @SerializedName("decision_status") val decisionStatus: String?,
) : Parcelable

@Parcelize
data class SettingsModel(
    @SerializedName("mt5_login") val mt5Login: Long?,
    @SerializedName("mt5_password") val mt5Password: String?,
    @SerializedName("mt5_server") val mt5Server: String?,
    @SerializedName("mt5_path") val mt5Path: String?,
    @SerializedName("mt5_magic_number") val mt5MagicNumber: Long?,
    val armed: Boolean?,
    @SerializedName("enable_autonomous_trading") val enableAutonomousTrading: Boolean?,
    @SerializedName("trade_sizing_mode") val tradeSizingMode: String?,
    @SerializedName("risk_per_trade_pct") val riskPerTradePct: Double?,
    @SerializedName("trade_symbols") val tradeSymbols: String?,
    @SerializedName("symbol_quantities") val symbolQuantities: Map<String, Double>?,
    @SerializedName("max_spread_points") val maxSpreadPoints: Double?,
    @SerializedName("strategy_smc_enabled") val strategySmcEnabled: Boolean?,
    @SerializedName("strategy_occ_r5_enabled") val strategyOccR5Enabled: Boolean?,
    @SerializedName("strategy_eyes_sme_enabled") val strategyEyesSmeEnabled: Boolean?,
    @SerializedName("strategy_mean_rev_enabled") val strategyMeanRevEnabled: Boolean?,
    @SerializedName("strategy_quant_way_enabled") val strategyQuantWayEnabled: Boolean?,
    @SerializedName("enable_ml_brain") val enableMlBrain: Boolean?,
    @SerializedName("ml_brain_min_execute_score") val mlBrainMinExecuteScore: Double?,
    @SerializedName("ml_brain_confluence_bonus") val mlBrainConfluenceBonus: Double?,
    @SerializedName("daily_max_loss_pct") val dailyMaxLossPct: Double?,
    @SerializedName("weekly_profit_target_pct") val weeklyProfitTargetPct: Double?,
    @SerializedName("max_concurrent_positions") val maxConcurrentPositions: Int?,
    @SerializedName("enable_partial_take_profit") val enablePartialTakeProfit: Boolean?,
    @SerializedName("enable_breakeven_trigger") val enableBreakevenTrigger: Boolean?,
    @SerializedName("enable_trailing_stop") val enableTrailingStop: Boolean?,
) : Parcelable

@Parcelize
data class PositionModel(
    val ticket: Long?,
    val symbol: String?,
    val side: String?,
    val type: String?,
    val size: Double?,
    val volume: Double?,
    @SerializedName("open_price") val openPrice: Double?,
    @SerializedName("entry_price") val entryPrice: Double?,
    @SerializedName("current_price") val currentPrice: Double?,
    @SerializedName("mark_price") val markPrice: Double?,
    val sl: Double?,
    @SerializedName("current_sl_price") val currentSlPrice: Double?,
    val tp: Double?,
    @SerializedName("current_tp_price") val currentTpPrice: Double?,
    val profit: Double?,
    @SerializedName("unrealized_pnl") val unrealizedPnL: Double?,
    @SerializedName("unrealized_pnl_usd") val unrealizedPnLUsd: Double?,
    val regime: String?,
    @SerializedName("live_bias_score") val liveBiasScore: Double?,
) : Parcelable

@Parcelize
data class TradeModel(
    val id: String?,
    val status: String?,
    @SerializedName("entry_price") val entryPrice: Double?,
    val quantity: Double?,
    @SerializedName("received_at") val receivedAt: Double?,
    @SerializedName("executed_at") val executedAt: Double?,
    @SerializedName("closed_at") val closedAt: Double?,
    @SerializedName("realized_pnl") val realizedPnL: Double?,
    @SerializedName("trading_fee_usd") val tradingFeeUsd: Double?,
    @SerializedName("delta_india_total_cost_usd") val deltaIndiaTotalCostUsd: Double?,
    @SerializedName("net_pnl_usd") val netPnLUsd: Double?,
    val signal: SignalModel?,
    val decision: DecisionModel?
) : Parcelable

@Parcelize
data class SignalModel(
    val symbol: String?,
    val action: String?
) : Parcelable

@Parcelize
data class DecisionModel(
    val regime: String?,
    val confidence: Int?,
    val reasoning: String?
) : Parcelable


data class ToggleArmResponse(
    val armed: Boolean
)

data class FlattenResponse(
    val message: String
)

data class SetProfileResponse(
    val success: Boolean,
    @SerializedName("profile_override") val profileOverride: String
)

data class ActionResponse(
    val success: Boolean?,
    val message: String?,
    val error: String?
)

// ------------------------------------------------------------------------------
// RETROFIT API INTERFACE
// ------------------------------------------------------------------------------

interface ApiService {

    @GET("api/status")
    suspend fun getStatus(
        @Query("token") token: String
    ): StatusResponse

    @GET("api/trades")
    suspend fun getTrades(
        @Query("token") token: String
    ): List<TradeModel>

    @GET("api/v4/settings")
    suspend fun getSettings(
        @Query("token") token: String
    ): SettingsModel

    @POST("api/v4/settings")
    suspend fun updateSettings(
        @retrofit2.http.Body settings: Map<String, @JvmSuppressWildcards Any>,
        @Query("token") token: String
    ): ActionResponse

    @POST("api/mt5/connect")
    suspend fun connectMT5(
        @retrofit2.http.Body credentials: Map<String, @JvmSuppressWildcards Any>,
        @Query("token") token: String
    ): ActionResponse

    @POST("api/toggle-arm")
    suspend fun toggleArm(
        @Query("armed") armed: Boolean,
        @Query("token") token: String
    ): ToggleArmResponse

    @POST("api/flatten")
    suspend fun flattenAll(
        @Query("token") token: String
    ): FlattenResponse

    @POST("api/set-profile")
    suspend fun setProfile(
        @Query("profile") profile: String,
        @Query("token") token: String
    ): SetProfileResponse

    @POST("api/close-position")
    suspend fun closePosition(
        @Query("ticket") ticket: Long,
        @Query("token") token: String
    ): ActionResponse

    @POST("api/mt5/breakeven")
    suspend fun breakevenPosition(
        @Query("ticket") ticket: Long,
        @Query("token") token: String
    ): ActionResponse

    companion object {
        fun normalizeUrl(rawUrl: String): String {
            var url = rawUrl.trim()
            if (url.isEmpty()) return url

            // 1. Auto-prepend scheme if missing
            if (!url.startsWith("http://", ignoreCase = true) && !url.startsWith("https://", ignoreCase = true)) {
                url = if (url.startsWith("localhost", ignoreCase = true) || 
                          url.startsWith("127.0.0.1") || 
                          url.startsWith("10.") || 
                          url.startsWith("192.168.")) {
                    "http://$url"
                } else {
                    "https://$url"
                }
            }

            // 2. If it's a domain with control.dilulabs.space and doesn't contain lasthopepanel, append lasthopepanel
            if (url.contains("control.dilulabs.space", ignoreCase = true) && !url.contains("lasthopepanel", ignoreCase = true)) {
                url = if (url.endsWith("/")) "${url}lasthopepanel" else "$url/lasthopepanel"
            }

            // 3. Ensure trailing slash for Retrofit baseUrl
            if (!url.endsWith("/")) {
                url = "$url/"
            }
            return url
        }

        fun getClient(baseUrl: String): ApiService {
            val logging = HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BODY
            }

            val httpClient = OkHttpClient.Builder()
                .addInterceptor(logging)
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(15, TimeUnit.SECONDS)
                .build()

            val normalizedUrl = normalizeUrl(baseUrl)
            val gson = com.google.gson.GsonBuilder()
                .setLenient()
                .create()

            return Retrofit.Builder()
                .baseUrl(normalizedUrl)
                .addConverterFactory(GsonConverterFactory.create(gson))
                .client(httpClient)
                .build()
                .create(ApiService::class.java)
        }
    }
}
