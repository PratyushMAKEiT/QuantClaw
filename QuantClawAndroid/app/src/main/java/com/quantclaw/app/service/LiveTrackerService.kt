package com.quantclaw.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import android.widget.RemoteViews
import androidx.core.app.NotificationCompat
import androidx.core.graphics.createBitmap
import androidx.core.graphics.toColorInt
import com.quantclaw.app.MainActivity
import com.quantclaw.app.R
import com.quantclaw.app.network.ApiService
import com.quantclaw.app.network.PositionModel
import com.quantclaw.app.network.StatusResponse
import com.quantclaw.app.utils.IconManager
import com.quantclaw.app.utils.MediaHapticsController
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.Locale

class LiveTrackerService : Service() {

    private val serviceJob = SupervisorJob()
    private val serviceScope = CoroutineScope(Dispatchers.IO + serviceJob)
    private var pollJob: Job? = null

    private lateinit var apiService: ApiService
    private lateinit var serverUrl: String
    private lateinit var token: String

    private var previousArmedState: Boolean? = null
    private var previousPositions: Set<String> = emptySet()
    private var previousLogsCount = 0

    private val notificationId = 771

    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action
        if (action == ACTION_TOGGLE_ARM) {
            toggleArmBackground()
            return START_STICKY
        } else if (action == ACTION_FLATTEN) {
            flattenBackground()
            return START_STICKY
        }

        serverUrl = ApiService.normalizeUrl(intent?.getStringExtra("server_url") ?: "")
        token = intent?.getStringExtra("token") ?: ""

        if (serverUrl.isNotEmpty()) {
            apiService = ApiService.getClient(serverUrl)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                startForeground(
                    notificationId,
                    buildDefaultNotification(),
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
                )
            } else {
                startForeground(notificationId, buildDefaultNotification())
            }
            startPolling()
        } else {
            stopSelf()
        }

        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        pollJob?.cancel()
        serviceJob.cancel()
    }

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = serviceScope.launch {
            while (true) {
                try {
                    val status = apiService.getStatus(token)
                    handleStatusUpdate(status)
                } catch (e: Exception) {
                    Log.e("LiveTrackerService", "Polling status error: $e")
                }
                delay(2000)
            }
        }
    }

    private fun handleStatusUpdate(status: StatusResponse) {
        val context = applicationContext

        // 1. Send local broadcast to update MainActivity UI
        val broadcastIntent = Intent(ACTION_STATUS_UPDATE).apply {
            val gson = com.google.gson.Gson()
            setPackage(packageName)
            putExtra("armed", status.armed ?: false)
            putExtra("connected", status.connected ?: false)
            putExtra("status", status.status ?: "UNKNOWN")
            putExtra("regime", status.regime ?: "NONE")
            putExtra("session_pnl", status.sessionPnL ?: 0.0)
            putExtra("total_trades", status.totalTrades ?: 0)
            putExtra("status_message", status.statusMessage ?: "")
            putExtra("thinking_status", status.thinkingStatus ?: "")
            putExtra("decision_score", status.decisionScore ?: 100.0)
            putExtra("decision_status", status.decisionStatus ?: "Going smooth")
            putExtra("active_profile", status.activeProfile ?: "AUTO")
            putExtra("news_sentiment", status.newsSentiment ?: 0.0)
            putExtra("high_impact_macro", status.highImpactMacro ?: false)
            putExtra("balance", status.balance ?: 0.0)
            putExtra("equity", status.equity ?: 0.0)
            putExtra("floating_pnl", status.floatingPnL ?: 0.0)
            putExtra("today_pnl", status.todayPnL ?: 0.0)
            putExtra("login", status.login ?: 0L)
            putExtra("server", status.server ?: "")
            putExtra("positions_json", gson.toJson(status.positions ?: emptyList<PositionModel>()))
            putExtra("logs_json", gson.toJson(status.logs ?: emptyList<String>()))
        }
        val isArmedVal = status.armed ?: false
        Log.d("LiveTrackerService", "Sending status update broadcast. Armed: $isArmedVal")
        sendBroadcast(broadcastIntent)

        // 2. Handle Arm/Disarm Sound + Vibrations + Icon Swap
        if (previousArmedState != status.armed) {
            if (previousArmedState != null) {
                MediaHapticsController.triggerVibration(context, MediaHapticsController.PATTERN_ARM_TOGGLE)
                if (isArmedVal) {
                    MediaHapticsController.playSound(context, "arm_on")
                } else {
                    MediaHapticsController.playSound(context, "arm_off")
                }
            }
            IconManager.setArmedIcon(context, isArmed = isArmedVal)
        }
        previousArmedState = status.armed

        // 3. Handle Webhook Signal Alerts from Logs
        val logsList = status.logs ?: emptyList()
        if (logsList.size > previousLogsCount) {
            val newLogs = logsList.drop(previousLogsCount)
            for (log in newLogs) {
                if (log.contains("[Signal]") || log.contains("signal", ignoreCase = true)) {
                    MediaHapticsController.triggerVibration(context, MediaHapticsController.PATTERN_WEBHOOK)
                    MediaHapticsController.playSound(context, "ping_webhook")
                    break
                }
            }
        }
        previousLogsCount = logsList.size

        // 4. Handle Position Execution Sound + Vibrations
        val positionsList = status.positions ?: emptyList()
        val currentPositionIds = positionsList.asSequence().map { "${it.symbol ?: ""}_${it.side ?: ""}" }.toSet()
        val addedPositions = currentPositionIds - previousPositions
        if (addedPositions.isNotEmpty()) {
            // A new trade was executed by the bot
            MediaHapticsController.triggerVibration(context, MediaHapticsController.PATTERN_EXECUTION)
            MediaHapticsController.playSound(context, "ping_executed")
        }
        previousPositions = currentPositionIds

        // 5. Update Foreground Ongoing Live Notification with Progress Bar
        updateForegroundNotification(status)
    }

    private fun toggleArmBackground() {
        if (!::apiService.isInitialized) return
        serviceScope.launch {
            try {
                val target = !(previousArmedState ?: false)
                apiService.toggleArm(target, token)
            } catch (e: Exception) {
                Log.e("LiveTrackerService", "Failed to toggle arm from notification: $e")
            }
        }
    }

    private fun flattenBackground() {
        if (!::apiService.isInitialized) return
        serviceScope.launch {
            try {
                apiService.flattenAll(token)
            } catch (e: Exception) {
                Log.e("LiveTrackerService", "Failed to flatten from notification: $e")
            }
        }
    }

    private fun updateForegroundNotification(status: StatusResponse) {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        val positions = status.positions ?: emptyList()

        val packageName = packageName
        val notifLayout = RemoteViews(packageName, R.layout.notification_live_trade).apply {
            // Bind Arm Toggle / Flatten buttons
            val toggleIntent = Intent(this@LiveTrackerService, LiveTrackerService::class.java).apply {
                action = ACTION_TOGGLE_ARM
            }
            val togglePending = PendingIntent.getService(
                this@LiveTrackerService, 1, toggleIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            setOnClickPendingIntent(R.id.notifBtnToggleArm, togglePending)

            val flattenIntent = Intent(this@LiveTrackerService, LiveTrackerService::class.java).apply {
                action = ACTION_FLATTEN
            }
            val flattenPending = PendingIntent.getService(
                this@LiveTrackerService, 2, flattenIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            setOnClickPendingIntent(R.id.notifBtnFlatten, flattenPending)

            // Dynamic text for ARM button
            val isArmedVal = status.armed ?: false
            setTextViewText(R.id.notifBtnToggleArm, if (isArmedVal) "DISARM" else "ARM")

            // Bind session statistics
            val sessionPnL = status.sessionPnL ?: 0.0
            setTextViewText(R.id.notifSessionPnL, String.format(Locale.US, "PnL: %s$%.2f", if (sessionPnL >= 0) "+" else "", sessionPnL))
            setTextColor(R.id.notifSessionPnL, (if (sessionPnL >= 0) "#34d399" else "#f87171").toColorInt())

            setTextViewText(R.id.notifTotalTrades, "Trades: ${status.totalTrades ?: 0}")
            setTextViewText(R.id.notifRegime, "Regime: ${status.regime ?: "BETA"}")

            val statusMsg = (status.thinkingStatus?.ifEmpty { status.statusMessage } ?: status.statusMessage) ?: ""
            setTextViewText(R.id.notifStatusMessage, statusMsg)

            if (positions.isEmpty()) {
                setViewVisibility(R.id.notifEmptyText, android.view.View.VISIBLE)
                setViewVisibility(R.id.notifPositionsContainer, android.view.View.GONE)
            } else {
                setViewVisibility(R.id.notifEmptyText, android.view.View.GONE)
                setViewVisibility(R.id.notifPositionsContainer, android.view.View.VISIBLE)

                // Render Position 1
                if (positions.isNotEmpty()) {
                    setViewVisibility(R.id.notifPos1, android.view.View.VISIBLE)
                    bindNotifPosition(this, positions[0], 1)
                } else {
                    setViewVisibility(R.id.notifPos1, android.view.View.GONE)
                }

                // Render Position 2
                if (positions.size >= 2) {
                    setViewVisibility(R.id.notifPos2, android.view.View.VISIBLE)
                    bindNotifPosition(this, positions[1], 2)
                } else {
                    setViewVisibility(R.id.notifPos2, android.view.View.GONE)
                }

                // Render Position 3
                if (positions.size >= 3) {
                    setViewVisibility(R.id.notifPos3, android.view.View.VISIBLE)
                    bindNotifPosition(this, positions[2], 3)
                } else {
                    setViewVisibility(R.id.notifPos3, android.view.View.GONE)
                }
            }
        }

        val intent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        // Custom big notification builder
        val transparentBitmap = createBitmap(1, 1, android.graphics.Bitmap.Config.ARGB_8888)
        val isArmedVal = status.armed ?: false
        val notification = NotificationCompat.Builder(this, CHANNEL_LIVE_ID)
            .setSmallIcon(if (isArmedVal) R.drawable.ic_launcher_armed else R.drawable.ic_launcher_disarmed)
            .setLargeIcon(transparentBitmap)
            .setCustomContentView(notifLayout)
            .setCustomBigContentView(notifLayout)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

        manager.notify(notificationId, notification)
    }

    private fun bindNotifPosition(views: RemoteViews, pos: PositionModel, index: Int) {
        val sideStr = pos.side?.uppercase(Locale.ROOT) ?: ""
        val isLong = (sideStr == "LONG") || (sideStr == "BUY")
        val entry = pos.entryPrice ?: 0.0
        val mark = pos.markPrice ?: 0.0
        val sl = pos.currentSlPrice ?: (if (isLong) entry * 0.99 else entry * 1.01)
        val tp = pos.currentTpPrice ?: (if (isLong) entry * 1.01 else entry * 0.99)
        val bias = pos.liveBiasScore ?: 0.0

        val symbolId = when (index) {
            1 -> R.id.notifSymbol1
            2 -> R.id.notifSymbol2
            else -> R.id.notifSymbol3
        }
        val sideId = when (index) {
            1 -> R.id.notifSide1
            2 -> R.id.notifSide2
            else -> R.id.notifSide3
        }
        val biasId = when (index) {
            1 -> R.id.notifBias1
            2 -> R.id.notifBias2
            else -> R.id.notifBias3
        }
        val pnlId = when (index) {
            1 -> R.id.notifPnL1
            2 -> R.id.notifPnL2
            else -> R.id.notifPnL3
        }
        val slId = when (index) {
            1 -> R.id.notifSL1
            2 -> R.id.notifSL2
            else -> R.id.notifSL3
        }
        val markId = when (index) {
            1 -> R.id.notifMark1
            2 -> R.id.notifMark2
            else -> R.id.notifMark3
        }
        val tpId = when (index) {
            1 -> R.id.notifTP1
            2 -> R.id.notifTP2
            else -> R.id.notifTP3
        }
        val progressId = when (index) {
            1 -> R.id.notifProgressBar1
            2 -> R.id.notifProgressBar2
            else -> R.id.notifProgressBar3
        }

        views.setTextViewText(symbolId, pos.symbol ?: "")
        views.setTextViewText(sideId, if (isLong) "LONG" else "SHORT")
        views.setTextColor(sideId, (if (isLong) "#34d399" else "#f87171").toColorInt())
        
        views.setTextViewText(biasId, String.format(Locale.US, "BIAS: %s%.2f", if (bias >= 0) "+" else "", bias))
        views.setTextColor(
            biasId,
            (when {
                bias > 0.1 -> "#34d399"
                bias < -0.1 -> "#f87171"
                else -> "#94a3b8"
            }).toColorInt(),
        )

        val usdVal = pos.unrealizedPnLUsd ?: 0.0
        val pnlVal = pos.unrealizedPnL ?: 0.0
        val pnlSign = if (pnlVal >= 0) "+" else ""
        val usdSign = if (usdVal >= 0) "+" else ""
        views.setTextViewText(pnlId, String.format(Locale.US, "%s%.2f%% (%s$%.2f)", pnlSign, pnlVal, usdSign, usdVal))
        views.setTextColor(pnlId, (if (pnlVal >= 0) "#34d399" else "#f87171").toColorInt())

        views.setTextViewText(slId, String.format(Locale.US, "SL: $%.1f", sl))
        views.setTextViewText(markId, String.format(Locale.US, "Mark: $%.1f", mark))
        views.setTextViewText(tpId, String.format(Locale.US, "TP: $%.1f", tp))

        val progress = if (isLong) {
            if (tp > sl) (((mark - sl) / (tp - sl)) * 100).toInt() else 50
        } else {
            if (sl > tp) (((sl - mark) / (sl - tp)) * 100).toInt() else 50
        }
        views.setProgressBar(progressId, 100, progress.coerceIn(0, 100), false)
    }

    private fun buildDefaultNotification(): Notification {
        val intent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val transparentBitmap = createBitmap(1, 1, android.graphics.Bitmap.Config.ARGB_8888)
        return NotificationCompat.Builder(this, CHANNEL_LIVE_ID)
            .setContentTitle("QuantClaw Active")
            .setContentText("Awaiting market sweeps & AI signals...")
            .setSmallIcon(R.drawable.ic_launcher_disarmed)
            .setLargeIcon(transparentBitmap)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()
    }

    private fun createNotificationChannels() {
        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager

        val liveChannel = NotificationChannel(
            CHANNEL_LIVE_ID,
            "Live Activity Status",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Ongoing notification displaying active trade statistics and progress bar."
            setShowBadge(false)
        }
        manager.createNotificationChannel(liveChannel)
    }

    companion object {
        const val CHANNEL_LIVE_ID = "quantclaw_live_channel"
        const val ACTION_STATUS_UPDATE = "com.quantclaw.app.ACTION_STATUS_UPDATE"
        const val ACTION_TOGGLE_ARM = "com.quantclaw.app.ACTION_TOGGLE_ARM"
        const val ACTION_FLATTEN = "com.quantclaw.app.ACTION_FLATTEN"
    }
}
