package com.quantclaw.app.utils

import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import android.util.Log

object IconManager {
    private const val TAG = "IconManager"

    fun setArmedIcon(context: Context, isArmed: Boolean) {
        try {
            val pm = context.packageManager
            val packageName = context.packageName

            val disarmedName = ComponentName(context, "$packageName.MainActivityDisarmed")
            val armedName = ComponentName(context, "$packageName.MainActivityArmed")

            if (isArmed) {
                // Enable Armed (Green Icon)
                pm.setComponentEnabledSetting(
                    armedName,
                    PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
                    PackageManager.DONT_KILL_APP,
                )
                // Disable Disarmed (Red Icon)
                pm.setComponentEnabledSetting(
                    disarmedName,
                    PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
                    PackageManager.DONT_KILL_APP
                )
                Log.d(TAG, "Dynamic App Icon swapped to ARMED (Green)")
            } else {
                // Enable Disarmed (Red Icon)
                pm.setComponentEnabledSetting(
                    disarmedName,
                    PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
                    PackageManager.DONT_KILL_APP,
                )
                // Disable Armed (Green Icon)
                pm.setComponentEnabledSetting(
                    armedName,
                    PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
                    PackageManager.DONT_KILL_APP
                )
                Log.d(TAG, "Dynamic App Icon swapped to DISARMED (Red)")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to toggle dynamic app icons: $e")
        }
    }
}
