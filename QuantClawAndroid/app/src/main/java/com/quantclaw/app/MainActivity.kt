package com.quantclaw.app

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.tabs.TabLayout
import com.quantclaw.app.databinding.ActivityMainBinding
import com.quantclaw.app.databinding.ItemCompletedTradeBinding
import com.quantclaw.app.databinding.ItemPositionBinding
import com.quantclaw.app.db.AppDatabase
import com.quantclaw.app.db.TradeDao
import com.quantclaw.app.db.TradeEntity
import com.quantclaw.app.network.ApiService
import com.quantclaw.app.network.PositionModel
import com.quantclaw.app.network.SettingsModel
import com.quantclaw.app.network.StatusResponse
import com.quantclaw.app.service.LiveTrackerService
import com.quantclaw.app.utils.MediaHapticsController
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var sharedPrefs: SharedPreferences
    private lateinit var tradeDao: TradeDao

    private var serverUrl: String = ""
    private var token: String = ""
    private var isArmed: Boolean = false
    private var isSettingsLoaded: Boolean = false
    private var existingSettings: SettingsModel? = null

    private val activityScope = CoroutineScope(Dispatchers.Main)

    private val positionsAdapter = PositionsAdapter()
    private val tradesAdapter = TradesAdapter()

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { isGranted: Boolean ->
        if (!isGranted) {
            Toast.makeText(this, "Notifications are required for live tracking updates", Toast.LENGTH_LONG).show()
        }
    }

    // Dynamic broadcast receiver to capture LiveTrackerService data updates
    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            intent?.let {
                val armed = it.getBooleanExtra("armed", false)
                val connected = it.getBooleanExtra("connected", false)
                val regime = it.getStringExtra("regime") ?: "NONE"
                val sessionPnL = it.getDoubleExtra("session_pnl", 0.0)
                val status = it.getStringExtra("status") ?: "UNKNOWN"
                val statusMsg = it.getStringExtra("status_message") ?: ""
                val thinking = it.getStringExtra("thinking_status") ?: ""
                val decisionScore = it.getDoubleExtra("decision_score", 100.0)
                val decisionStatus = it.getStringExtra("decision_status") ?: "Going smooth"
                val activeProfile = it.getStringExtra("active_profile") ?: "AUTO"
                val newsSentiment = it.getDoubleExtra("news_sentiment", 0.0)
                val highImpactMacro = it.getBooleanExtra("high_impact_macro", false)
                val balance = it.getDoubleExtra("balance", 0.0)
                val equity = it.getDoubleExtra("equity", 0.0)
                val floatingPnL = it.getDoubleExtra("floating_pnl", 0.0)
                val todayPnL = it.getDoubleExtra("today_pnl", 0.0)
                val login = it.getLongExtra("login", 0L)
                val server = it.getStringExtra("server") ?: ""
                val positionsJson = it.getStringExtra("positions_json") ?: "[]"
                val logsJson = it.getStringExtra("logs_json") ?: "[]"

                var positionsList: List<PositionModel> = emptyList()
                try {
                    val type = object : com.google.gson.reflect.TypeToken<List<PositionModel>>() {}.type
                    positionsList = com.google.gson.Gson().fromJson(positionsJson, type) ?: emptyList()
                } catch (e: Exception) {
                    Log.e("MainActivity", "Error parsing broadcast positions: $e")
                }

                var logsList: List<String> = emptyList()
                try {
                    val type = object : com.google.gson.reflect.TypeToken<List<String>>() {}.type
                    logsList = com.google.gson.Gson().fromJson(logsJson, type) ?: emptyList()
                } catch (e: Exception) {
                    Log.e("MainActivity", "Error parsing broadcast logs: $e")
                }

                renderStatus(
                    armed = armed,
                    connected = connected,
                    regime = regime,
                    sessionPnL = sessionPnL,
                    statusMsg = statusMsg,
                    thinking = thinking,
                    decisionScore = decisionScore,
                    balance = balance,
                    equity = equity,
                    floatingPnL = floatingPnL,
                    todayPnL = todayPnL,
                    login = login,
                    server = server,
                    positions = positionsList,
                    logs = logsList
                )
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        sharedPrefs = getSharedPreferences("QuantClawPrefs", MODE_PRIVATE)
        tradeDao = AppDatabase.getDatabase(this).tradeDao()

        setupRecyclerViews()
        setupListeners()
        checkLoginState()
        checkNotificationPermission()
    }

    private fun checkNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        val filter = IntentFilter(LiveTrackerService.ACTION_STATUS_UPDATE)
        ContextCompat.registerReceiver(
            this,
            statusReceiver,
            filter,
            ContextCompat.RECEIVER_NOT_EXPORTED
        )
        if (serverUrl.isNotEmpty()) {
            fetchCurrentStatus()
            syncOfflineTrades()
            if (!isSettingsLoaded) {
                fetchBotSettings()
            }
        }
    }

    override fun onPause() {
        super.onPause()
        try {
            unregisterReceiver(statusReceiver)
        } catch (e: Exception) {
            Log.e("MainActivity", "Error unregistering receiver: $e")
        }
    }

    private fun checkLoginState() {
        val rawUrl = sharedPrefs.getString("server_url", "") ?: ""
        token = sharedPrefs.getString("token", "") ?: ""
        serverUrl = ApiService.normalizeUrl(rawUrl)

        if (serverUrl.isNotEmpty()) {
            showMainLayout()
            startLiveTrackerService()
            fetchCurrentStatus()
            fetchBotSettings()
        } else {
            showLoginOverlay()
        }
    }

    private fun showLoginOverlay() {
        binding.loginOverlay.visibility = View.VISIBLE
        binding.mainLayout.visibility = View.GONE
        binding.etServerUrl.setText(sharedPrefs.getString("server_url", "") ?: "")
        binding.etSecurityToken.setText(token)
    }

    private fun showMainLayout() {
        binding.loginOverlay.visibility = View.GONE
        binding.mainLayout.visibility = View.VISIBLE
    }

    private fun startLiveTrackerService() {
        if (serverUrl.isEmpty()) return
        val serviceIntent = Intent(this, LiveTrackerService::class.java).apply {
            putExtra("server_url", serverUrl)
            putExtra("token", token)
        }
        ContextCompat.startForegroundService(this, serviceIntent)
    }

    private fun setupRecyclerViews() {
        binding.positionsRecyclerView.apply {
            layoutManager = LinearLayoutManager(this@MainActivity)
            adapter = positionsAdapter
            isNestedScrollingEnabled = false
        }

        binding.tradesRecyclerView.apply {
            layoutManager = LinearLayoutManager(this@MainActivity)
            adapter = tradesAdapter
        }
    }

    private fun setupListeners() {
        // Login Connect Button
        binding.btnConnect.setOnClickListener {
            val rawUrl = binding.etServerUrl.text.toString().trim()
            val secToken = binding.etSecurityToken.text.toString().trim()

            if (rawUrl.isEmpty()) {
                Toast.makeText(this, "Please enter a valid Server URL", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            serverUrl = ApiService.normalizeUrl(rawUrl)
            token = secToken

            sharedPrefs.edit()
                .putString("server_url", serverUrl)
                .putString("token", token)
                .apply()

            showMainLayout()
            startLiveTrackerService()
            fetchCurrentStatus()
            fetchBotSettings()
        }

        // Arm / Disarm Bot Button
        binding.btnToggleArm.setOnClickListener {
            val newArmed = !isArmed
            MediaHapticsController.triggerVibration(this, MediaHapticsController.PATTERN_ARM_TOGGLE)
            activityScope.launch {
                try {
                    val client = ApiService.getClient(serverUrl)
                    withContext(Dispatchers.IO) {
                        client.toggleArm(newArmed, token)
                    }
                    isArmed = newArmed
                    binding.btnToggleArm.text = if (newArmed) "🔴 DISARM BOT" else "🟢 ARM BOT"
                    binding.btnToggleArm.backgroundTintList = ContextCompat.getColorStateList(
                        this@MainActivity,
                        if (newArmed) R.color.colorRed else R.color.colorGreen
                    )
                    Toast.makeText(this@MainActivity, if (newArmed) "Bot ARMED for live execution!" else "Bot DISARMED safely!", Toast.LENGTH_SHORT).show()
                    fetchCurrentStatus()
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Failed to toggle arm: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }

        // Flatten All Positions Button
        binding.btnFlatten.setOnClickListener {
            MediaHapticsController.triggerVibration(this, MediaHapticsController.PATTERN_ARM_TOGGLE)
            activityScope.launch {
                try {
                    val client = ApiService.getClient(serverUrl)
                    withContext(Dispatchers.IO) {
                        client.flattenAll(token)
                    }
                    Toast.makeText(this@MainActivity, "⚡ Emergency Flatten Sent! All open positions closing...", Toast.LENGTH_SHORT).show()
                    fetchCurrentStatus()
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Failed to flatten positions: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }

        // Clear Logs Button
        binding.btnClearLogs.setOnClickListener {
            binding.terminalLogText.text = "[SYSTEM] Log console cleared."
        }

        // Connect MT5 Button
        binding.btnConnectMt5.setOnClickListener {
            val loginStr = binding.etMt5Login.text.toString().trim()
            val password = binding.etMt5Password.text.toString().trim()
            val server = binding.etMt5Server.text.toString().trim()

            if (loginStr.isEmpty() || password.isEmpty()) {
                Toast.makeText(this, "Please enter MT5 Account Login and Password", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            val payload = mapOf<String, Any>(
                "login" to (loginStr.toLongOrNull() ?: 0L),
                "password" to password,
                "server" to server
            )

            binding.btnConnectMt5.text = "CONNECTING..."
            binding.btnConnectMt5.isEnabled = false

            activityScope.launch {
                try {
                    val client = ApiService.getClient(serverUrl)
                    val resp = withContext(Dispatchers.IO) {
                        client.connectMT5(payload, token)
                    }
                    if (resp.success == true) {
                        Toast.makeText(this@MainActivity, "✅ MT5 Terminal Connected Successfully!", Toast.LENGTH_LONG).show()
                    } else {
                        Toast.makeText(this@MainActivity, "⚠️ Connect Response: ${resp.message ?: resp.error}", Toast.LENGTH_LONG).show()
                    }
                    fetchCurrentStatus()
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Connection failed: ${e.message}", Toast.LENGTH_SHORT).show()
                } finally {
                    binding.btnConnectMt5.text = "CONNECT METATRADER 5"
                    binding.btnConnectMt5.isEnabled = true
                }
            }
        }

        // Save All Bot Settings Button
        binding.btnSaveSettings.setOnClickListener {
            saveBotSettings()
        }

        // Tab Navigation Listener
        binding.tabLayout.addOnTabSelectedListener(
            object : TabLayout.OnTabSelectedListener {
                override fun onTabSelected(tab: TabLayout.Tab?) {
                    when (tab?.position) {
                        0 -> {
                            binding.viewDashboard.visibility = View.VISIBLE
                            binding.viewControls.visibility = View.GONE
                            binding.viewJournal.visibility = View.GONE
                            binding.tvWorkspaceWebView.visibility = View.GONE
                            fetchCurrentStatus()
                        }
                        1 -> {
                            binding.viewDashboard.visibility = View.GONE
                            binding.viewControls.visibility = View.VISIBLE
                            binding.viewJournal.visibility = View.GONE
                            binding.tvWorkspaceWebView.visibility = View.GONE
                            fetchBotSettings()
                        }
                        2 -> {
                            binding.viewDashboard.visibility = View.GONE
                            binding.viewControls.visibility = View.GONE
                            binding.viewJournal.visibility = View.VISIBLE
                            binding.tvWorkspaceWebView.visibility = View.GONE
                            loadCachedTrades()
                            syncOfflineTrades()
                        }
                        3 -> {
                            binding.viewDashboard.visibility = View.GONE
                            binding.viewControls.visibility = View.GONE
                            binding.viewJournal.visibility = View.GONE
                            binding.tvWorkspaceWebView.visibility = View.VISIBLE
                            setupWebView()
                        }
                    }
                }
                override fun onTabUnselected(tab: TabLayout.Tab?) {}
                override fun onTabReselected(tab: TabLayout.Tab?) {}
            }
        )

        // Swipe to Refresh
        binding.swipeRefresh.setOnRefreshListener {
            fetchCurrentStatus()
            syncOfflineTrades()
            fetchBotSettings()
        }
    }

    private fun fetchCurrentStatus() {
        if (serverUrl.isEmpty()) return
        activityScope.launch {
            try {
                val client = ApiService.getClient(serverUrl)
                val status = withContext(Dispatchers.IO) { client.getStatus(token) }
                renderStatus(
                    armed = status.armed ?: false,
                    connected = status.connected ?: false,
                    regime = status.regime ?: "INSTITUTIONAL_SMC",
                    sessionPnL = status.sessionPnL ?: 0.0,
                    statusMsg = status.statusMessage ?: "",
                    thinking = status.thinkingStatus ?: "",
                    decisionScore = status.decisionScore ?: 100.0,
                    balance = status.balance ?: 0.0,
                    equity = status.equity ?: 0.0,
                    floatingPnL = status.floatingPnL ?: 0.0,
                    todayPnL = status.todayPnL ?: 0.0,
                    login = status.login ?: 0L,
                    server = status.server ?: "",
                    positions = status.positions ?: emptyList(),
                    logs = status.logs ?: emptyList()
                )
            } catch (e: Exception) {
                Log.e("MainActivity", "Failed to fetch status: $e")
            } finally {
                binding.swipeRefresh.isRefreshing = false
            }
        }
    }

    private fun renderStatus(
        armed: Boolean,
        connected: Boolean,
        regime: String,
        sessionPnL: Double,
        statusMsg: String,
        thinking: String,
        decisionScore: Double,
        balance: Double,
        equity: Double,
        floatingPnL: Double,
        todayPnL: Double,
        login: Long,
        server: String,
        positions: List<PositionModel>,
        logs: List<String>
    ) {
        isArmed = armed

        // 1. Arm / Disarm Button State
        binding.btnToggleArm.text = if (armed) "🔴 DISARM BOT" else "🟢 ARM BOT"
        binding.btnToggleArm.backgroundTintList = ContextCompat.getColorStateList(
            this,
            if (armed) R.color.colorRed else R.color.colorGreen
        )

        // 2. MT5 Header Connection Badge
        if (connected) {
            val loginDisplay = if (login > 0) "#$login" else ""
            val serverDisplay = if (server.isNotEmpty() && server != "--") server else "MT5 LIVE"
            binding.headerServerBadge.text = "🟢 $serverDisplay $loginDisplay"
            binding.headerServerBadge.setTextColor(ContextCompat.getColor(this, R.color.colorGreen))
            binding.headerServerBadge.background = ContextCompat.getDrawable(this, R.drawable.bg_badge_long)
        } else {
            binding.headerServerBadge.text = "🔴 MT5: DISCONNECTED"
            binding.headerServerBadge.setTextColor(ContextCompat.getColor(this, R.color.colorRed))
            binding.headerServerBadge.background = ContextCompat.getDrawable(this, R.drawable.bg_badge_neutral)
        }

        // 3. Quick Metrics Header
        binding.tvHeaderBalance.text = if (balance > 0) String.format(Locale.US, "$%.2f", balance) else "$0.00"
        binding.tvHeaderEquity.text = if (equity > 0) String.format(Locale.US, "$%.2f", equity) else "$0.00"

        binding.tvHeaderFloating.text = String.format(Locale.US, "%s$%.2f", if (floatingPnL >= 0) "+" else "", floatingPnL)
        binding.tvHeaderFloating.setTextColor(ContextCompat.getColor(this, if (floatingPnL >= 0) R.color.colorGreen else R.color.colorRed))

        val effTodayPnL = if (todayPnL != 0.0) todayPnL else sessionPnL
        binding.tvHeaderTodayPnL.text = String.format(Locale.US, "%s$%.2f", if (effTodayPnL >= 0) "+" else "", effTodayPnL)
        binding.tvHeaderTodayPnL.setTextColor(ContextCompat.getColor(this, if (effTodayPnL >= 0) R.color.colorGreen else R.color.colorRed))

        // 4. Decision & Regime HUD
        binding.regimeText.text = regime
        binding.decisionScoreText.text = String.format(Locale.US, "%.1f%%", decisionScore)
        binding.decisionScoreText.setTextColor(ContextCompat.getColor(this, if (decisionScore >= 70.0) R.color.colorGreen else R.color.colorOrange))

        val statusText = if (thinking.isNotEmpty()) thinking else if (statusMsg.isNotEmpty()) statusMsg else "24/7 Scanning Active"
        binding.engineStatusMessage.text = statusText

        // 5. Positions List
        binding.posCountBadge.text = "${positions.size} Active"
        positionsAdapter.updateList(positions)

        // 6. Terminal Logs
        if (logs.isNotEmpty()) {
            val sb = StringBuilder()
            for (log in logs.reversed()) {
                sb.append(log).append("\n")
            }
            binding.terminalLogText.text = sb.toString()
        }
    }

    private fun findSymbolQty(map: Map<String, Double>?, symbolPrefix: String, defaultVal: String): String {
        if (map == null || map.isEmpty()) return defaultVal
        val key = map.keys.find {
            it.equals(symbolPrefix, ignoreCase = true) ||
            it.startsWith(symbolPrefix, ignoreCase = true) ||
            symbolPrefix.startsWith(it, ignoreCase = true)
        }
        return key?.let { map[it]?.toString() } ?: defaultVal
    }

    private fun fetchBotSettings() {
        if (serverUrl.isEmpty()) return
        activityScope.launch {
            try {
                val client = ApiService.getClient(serverUrl)
                val settings = withContext(Dispatchers.IO) { client.getSettings(token) }
                existingSettings = settings

                // MetaTrader Credentials
                settings.mt5Login?.let { if (it > 0) binding.etMt5Login.setText(it.toString()) }
                settings.mt5Server?.let { binding.etMt5Server.setText(it) }

                // Autonomous & Strategies
                binding.swAutonomousTrading.isChecked = settings.enableAutonomousTrading ?: false
                binding.swStrategySMC.isChecked = settings.strategySmcEnabled ?: true
                binding.swStrategyOCC.isChecked = settings.strategyOccR5Enabled ?: true
                binding.swStrategyEyes.isChecked = settings.strategyEyesSmeEnabled ?: true
                binding.swStrategyMeanRev.isChecked = settings.strategyMeanRevEnabled ?: true
                binding.swStrategyQuantWay.isChecked = settings.strategyQuantWayEnabled ?: true

                // Lot Sizing with broker suffix matching (e.g. BTCUSD.P, XAUTUSD.P)
                val qMap = settings.symbolQuantities ?: emptyMap()
                binding.etQtyEurUsd.setText(findSymbolQty(qMap, "EURUSD", "0.10"))
                binding.etQtyGbpUsd.setText(findSymbolQty(qMap, "GBPUSD", "0.10"))
                binding.etQtyXauUsd.setText(findSymbolQty(qMap, "XAU", "0.05"))
                binding.etQtyBtcUsd.setText(findSymbolQty(qMap, "BTC", "0.01"))
                binding.etQtyUs30.setText(findSymbolQty(qMap, "US30", "0.10"))
                binding.etQtyNas100.setText(findSymbolQty(qMap, "NAS100", "0.10"))

                // Risk Settings
                settings.dailyMaxLossPct?.let { binding.etDailyMaxLoss.setText(it.toString()) }
                settings.weeklyProfitTargetPct?.let { binding.etWeeklyTarget.setText(it.toString()) }
                binding.swBreakevenTrigger.isChecked = settings.enableBreakevenTrigger ?: true
                binding.swPartialTP.isChecked = settings.enablePartialTakeProfit ?: true
                binding.swTrailingStop.isChecked = settings.enableTrailingStop ?: true

                isSettingsLoaded = true
            } catch (e: Exception) {
                Log.e("MainActivity", "Failed to fetch bot settings: $e")
            }
        }
    }

    private fun saveBotSettings() {
        val qtyMap = mutableMapOf<String, Double>()
        
        // Preserve broker symbol keys if existingSettings had exact suffixes
        val prevMap = existingSettings?.symbolQuantities ?: emptyMap()
        fun mapKey(prefix: String, fallback: String): String {
            return prevMap.keys.find { it.startsWith(prefix, ignoreCase = true) || prefix.startsWith(it, ignoreCase = true) } ?: fallback
        }

        binding.etQtyEurUsd.text.toString().toDoubleOrNull()?.let { qtyMap[mapKey("EURUSD", "EURUSD")] = it }
        binding.etQtyGbpUsd.text.toString().toDoubleOrNull()?.let { qtyMap[mapKey("GBPUSD", "GBPUSD")] = it }
        binding.etQtyXauUsd.text.toString().toDoubleOrNull()?.let { qtyMap[mapKey("XAU", "XAUUSD")] = it }
        binding.etQtyBtcUsd.text.toString().toDoubleOrNull()?.let { qtyMap[mapKey("BTC", "BTCUSD")] = it }
        binding.etQtyUs30.text.toString().toDoubleOrNull()?.let { qtyMap[mapKey("US30", "US30")] = it }
        binding.etQtyNas100.text.toString().toDoubleOrNull()?.let { qtyMap[mapKey("NAS100", "NAS100")] = it }

        val payload = mutableMapOf<String, Any>(
            "enable_autonomous_trading" to binding.swAutonomousTrading.isChecked,
            "strategy_smc_enabled" to binding.swStrategySMC.isChecked,
            "strategy_occ_r5_enabled" to binding.swStrategyOCC.isChecked,
            "strategy_eyes_sme_enabled" to binding.swStrategyEyes.isChecked,
            "strategy_mean_rev_enabled" to binding.swStrategyMeanRev.isChecked,
            "strategy_quant_way_enabled" to binding.swStrategyQuantWay.isChecked,
            "enable_breakeven_trigger" to binding.swBreakevenTrigger.isChecked,
            "enable_partial_take_profit" to binding.swPartialTP.isChecked,
            "enable_trailing_stop" to binding.swTrailingStop.isChecked,
            "symbol_quantities" to qtyMap
        )

        binding.etDailyMaxLoss.text.toString().toDoubleOrNull()?.let { payload["daily_max_loss_pct"] = it }
        binding.etWeeklyTarget.text.toString().toDoubleOrNull()?.let { payload["weekly_profit_target_pct"] = it }

        binding.btnSaveSettings.text = "SAVING SETTINGS..."
        binding.btnSaveSettings.isEnabled = false

        activityScope.launch {
            try {
                val client = ApiService.getClient(serverUrl)
                val resp = withContext(Dispatchers.IO) {
                    client.updateSettings(payload, token)
                }
                if (resp.success == true) {
                    Toast.makeText(this@MainActivity, "💾 Bot Settings Saved & Applied Live!", Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(this@MainActivity, "Response: ${resp.message ?: "Saved"}", Toast.LENGTH_SHORT).show()
                }
                fetchCurrentStatus()
            } catch (e: Exception) {
                Toast.makeText(this@MainActivity, "Save failed: ${e.message}", Toast.LENGTH_SHORT).show()
            } finally {
                binding.btnSaveSettings.text = "💾 SAVE ALL BOT SETTINGS"
                binding.btnSaveSettings.isEnabled = true
            }
        }
    }

    private fun loadCachedTrades() {
        activityScope.launch {
            val cached = withContext(Dispatchers.IO) { tradeDao.getAllTrades() }
            tradesAdapter.updateList(cached)
            calculateStats(cached)
        }
    }

    private fun syncOfflineTrades() {
        if (serverUrl.isEmpty()) return
        activityScope.launch {
            try {
                val client = ApiService.getClient(serverUrl)
                val remoteTrades = withContext(Dispatchers.IO) { client.getTrades(token) }

                val entities = remoteTrades.map {
                    val pnl = it.realizedPnL ?: 0.0
                    val fee = it.tradingFeeUsd ?: 0.0
                    val net = it.netPnLUsd ?: (pnl - fee)
                    val india = it.deltaIndiaTotalCostUsd ?: 0.0
                    val rawTs = it.closedAt ?: it.receivedAt ?: (System.currentTimeMillis() / 1000.0)

                    TradeEntity(
                        id = it.id ?: "QC-${(rawTs * 1000).toLong()}",
                        timestamp = rawTs.toLong(),
                        symbol = it.signal?.symbol ?: "UNKNOWN",
                        side = it.signal?.action ?: "UNKNOWN",
                        regime = it.decision?.regime ?: "BETA",
                        confidence = it.decision?.confidence ?: 0,
                        grossPnl = pnl,
                        fee = fee,
                        indiaCost = india,
                        netPnl = net,
                        reasoning = it.decision?.reasoning ?: "QuantClaw Trade Confluence"
                    )
                }

                withContext(Dispatchers.IO) {
                    tradeDao.deleteAllTrades()
                    tradeDao.insertTrades(entities)
                }

                loadCachedTrades()
            } catch (e: Exception) {
                Log.e("MainActivity", "Sync offline trades error: $e")
            }
        }
    }

    private fun calculateStats(trades: List<TradeEntity>) {
        if (trades.isEmpty()) {
            binding.statsPnl.text = "$0.00"
            binding.statsPnl.setTextColor(ContextCompat.getColor(this, R.color.colorTextSecondary))
            binding.statsWinRate.text = "0.0%"
            binding.statsProfitFactor.text = "1.00"
            binding.statsTotalTrades.text = "0"
            return
        }

        var cumulativeNetPnl = 0.0
        var wins = 0
        var grossProfit = 0.0
        var grossLoss = 0.0

        for (t in trades) {
            val net = t.netPnl
            cumulativeNetPnl += net
            if (net > 0) {
                wins++
                grossProfit += net
            } else if (net < 0) {
                grossLoss += abs(net)
            }
        }

        val totalTrades = trades.size
        val winRate = (wins.toDouble() / totalTrades) * 100.0
        val profitFactor = if (grossLoss > 0) grossProfit / grossLoss else if (grossProfit > 0) 99.9 else 1.00

        binding.statsPnl.text = String.format(Locale.US, "%s$%.2f", if (cumulativeNetPnl >= 0) "+" else "", cumulativeNetPnl)
        binding.statsPnl.setTextColor(ContextCompat.getColor(this, if (cumulativeNetPnl >= 0) R.color.colorGreen else R.color.colorRed))

        binding.statsWinRate.text = String.format(Locale.US, "%.1f%%", winRate)
        binding.statsProfitFactor.text = String.format(Locale.US, "%.2f", profitFactor)
        binding.statsTotalTrades.text = totalTrades.toString()
    }

    private fun setupWebView() {
        binding.tvWorkspaceWebView.apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.useWideViewPort = true
            settings.loadWithOverviewMode = true

            webViewClient = object : WebViewClient() {
                override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                    super.onReceivedError(view, request, error)
                    Log.e("MainActivity", "WebView error: ${error?.description}")
                }
            }

            webChromeClient = WebChromeClient()

            val normUrl = ApiService.normalizeUrl(serverUrl)
            val targetUrl = if (token.isNotEmpty()) {
                if (normUrl.contains("?")) "${normUrl}&token=$token" else "${normUrl}?token=$token"
            } else {
                normUrl
            }

            Log.i("MainActivity", "Loading Web Dashboard: $targetUrl")
            loadUrl(targetUrl)
        }
    }

    // --------------------------------------------------------------------------
    // RECYCLER VIEW ADAPTERS
    // --------------------------------------------------------------------------

    inner class PositionsAdapter : RecyclerView.Adapter<PositionsAdapter.PositionViewHolder>() {

        private val items = mutableListOf<PositionModel>()

        fun updateList(newItems: List<PositionModel>) {
            items.clear()
            items.addAll(newItems)
            notifyDataSetChanged()
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): PositionViewHolder {
            val binding = ItemPositionBinding.inflate(LayoutInflater.from(parent.context), parent, false)
            return PositionViewHolder(binding)
        }

        override fun onBindViewHolder(holder: PositionViewHolder, position: Int) {
            holder.bind(items[position])
        }

        override fun getItemCount(): Int = items.size

        inner class PositionViewHolder(private val itemBinding: ItemPositionBinding) :
            RecyclerView.ViewHolder(itemBinding.root) {

            fun bind(model: PositionModel) {
                val symbol = model.symbol ?: "UNKNOWN"
                val side = (model.side ?: model.type ?: "BUY").uppercase(Locale.US)
                val isBuy = side.contains("BUY") || side.contains("LONG")

                itemBinding.posSymbol.text = symbol
                itemBinding.posRegime.text = model.regime ?: "SMC"
                itemBinding.posBias.text = String.format(Locale.US, "LOTS: %.2f", model.volume ?: model.size ?: 0.10)

                itemBinding.posSide.text = if (isBuy) "BUY" else "SELL"
                itemBinding.posSide.background = ContextCompat.getDrawable(
                    itemView.context,
                    if (isBuy) R.drawable.bg_badge_long else R.drawable.bg_badge_neutral
                )
                itemBinding.posSide.setTextColor(
                    ContextCompat.getColor(
                        itemView.context,
                        if (isBuy) R.color.colorGreen else R.color.colorRed
                    )
                )

                val entry = model.entryPrice ?: model.openPrice ?: 0.0
                val mark = model.markPrice ?: model.currentPrice ?: 0.0
                itemBinding.posPrices.text = String.format(Locale.US, "$%.2f / $%.2f", entry, mark)

                val profit = model.profit ?: model.unrealizedPnLUsd ?: model.unrealizedPnL ?: 0.0
                itemBinding.posPnL.text = String.format(Locale.US, "%s$%.2f", if (profit >= 0) "+" else "", profit)
                itemBinding.posPnL.setTextColor(
                    ContextCompat.getColor(
                        itemView.context,
                        if (profit >= 0) R.color.colorGreen else R.color.colorRed
                    )
                )

                val sl = model.currentSlPrice ?: model.sl ?: 0.0
                val tp = model.currentTpPrice ?: model.tp ?: 0.0

                itemBinding.posSLText.text = if (sl > 0) String.format(Locale.US, "SL: $%.2f", sl) else "SL: NONE"
                itemBinding.posTPText.text = if (tp > 0) String.format(Locale.US, "TP: $%.2f", tp) else "TP: NONE"

                val progress = if (sl > 0 && tp > 0 && tp != sl && mark > 0) {
                    val totalDist = abs(tp - sl)
                    val currDist = abs(mark - sl)
                    ((currDist / totalDist) * 100).toInt().coerceIn(0, 100)
                } else {
                    50
                }
                itemBinding.posProgressBar.progress = progress

                val ticket = model.ticket ?: 0L

                // Close Position Click Handler
                itemBinding.btnPosClose.setOnClickListener {
                    if (ticket <= 0L) {
                        Toast.makeText(itemView.context, "Invalid Ticket ID", Toast.LENGTH_SHORT).show()
                        return@setOnClickListener
                    }
                    activityScope.launch {
                        try {
                            val client = ApiService.getClient(serverUrl)
                            val res = withContext(Dispatchers.IO) { client.closePosition(ticket, token) }
                            Toast.makeText(itemView.context, "Closed Position #$ticket: ${res.message ?: "Success"}", Toast.LENGTH_SHORT).show()
                            fetchCurrentStatus()
                        } catch (e: Exception) {
                            Toast.makeText(itemView.context, "Close failed: ${e.message}", Toast.LENGTH_SHORT).show()
                        }
                    }
                }

                // Breakeven Click Handler
                itemBinding.btnPosBreakeven.setOnClickListener {
                    if (ticket <= 0L) {
                        Toast.makeText(itemView.context, "Invalid Ticket ID", Toast.LENGTH_SHORT).show()
                        return@setOnClickListener
                    }
                    activityScope.launch {
                        try {
                            val client = ApiService.getClient(serverUrl)
                            val res = withContext(Dispatchers.IO) { client.breakevenPosition(ticket, token) }
                            Toast.makeText(itemView.context, "Breakeven Set for #$ticket: ${res.message ?: "Success"}", Toast.LENGTH_SHORT).show()
                            fetchCurrentStatus()
                        } catch (e: Exception) {
                            Toast.makeText(itemView.context, "Breakeven failed: ${e.message}", Toast.LENGTH_SHORT).show()
                        }
                    }
                }
            }
        }
    }

    inner class TradesAdapter : RecyclerView.Adapter<TradesAdapter.TradeViewHolder>() {

        private val items = mutableListOf<TradeEntity>()
        private val dateFormat = SimpleDateFormat("MM/dd HH:mm", Locale.US)

        fun updateList(newItems: List<TradeEntity>) {
            items.clear()
            items.addAll(newItems)
            notifyDataSetChanged()
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): TradeViewHolder {
            val binding = ItemCompletedTradeBinding.inflate(LayoutInflater.from(parent.context), parent, false)
            return TradeViewHolder(binding)
        }

        override fun onBindViewHolder(holder: TradeViewHolder, position: Int) {
            holder.bind(items[position])
        }

        override fun getItemCount(): Int = items.size

        inner class TradeViewHolder(private val itemBinding: ItemCompletedTradeBinding) :
            RecyclerView.ViewHolder(itemBinding.root) {

            fun bind(trade: TradeEntity) {
                itemBinding.tradeSymbol.text = trade.symbol
                val isBuy = trade.side.equals("BUY", ignoreCase = true) || trade.side.equals("LONG", ignoreCase = true)
                itemBinding.tradeSide.text = trade.side.uppercase(Locale.US)
                itemBinding.tradeSide.background = ContextCompat.getDrawable(
                    itemView.context,
                    if (isBuy) R.drawable.bg_badge_long else R.drawable.bg_badge_neutral
                )
                itemBinding.tradeSide.setTextColor(
                    ContextCompat.getColor(
                        itemView.context,
                        if (isBuy) R.color.colorGreen else R.color.colorRed
                    )
                )

                itemBinding.tradeDate.text = dateFormat.format(Date(trade.timestamp * 1000L))
                itemBinding.tradeGrossPnL.text = String.format(Locale.US, "%s$%.2f", if (trade.grossPnl >= 0) "+" else "", trade.grossPnl)
                itemBinding.tradeFee.text = String.format(Locale.US, "$%.2f", trade.fee)
                itemBinding.tradeIndiaCost.text = String.format(Locale.US, "$%.2f", trade.indiaCost)

                itemBinding.tradeNetPnL.text = String.format(Locale.US, "%s$%.2f", if (trade.netPnl >= 0) "+" else "", trade.netPnl)
                itemBinding.tradeNetPnL.setTextColor(
                    ContextCompat.getColor(
                        itemView.context,
                        if (trade.netPnl >= 0) R.color.colorGreen else R.color.colorRed
                    )
                )

                itemBinding.tradeReasoning.text = trade.reasoning
            }
        }
    }
}
