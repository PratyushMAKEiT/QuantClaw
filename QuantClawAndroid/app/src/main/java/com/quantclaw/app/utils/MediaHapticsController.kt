package com.quantclaw.app.utils

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.net.Uri
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import androidx.core.net.toUri

object MediaHapticsController {
    private const val TAG = "MediaHapticsController"

    // Vibration Patterns
    val PATTERN_WEBHOOK = longArrayOf(0, 80)
    val PATTERN_EXECUTION = longArrayOf(0, 200, 100, 200)
    val PATTERN_ARM_TOGGLE = longArrayOf(0, 60, 40, 60)

    // Trigger device vibration
    fun triggerVibration(context: Context, pattern: LongArray) {
        try {
            val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vibratorManager = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
                vibratorManager.defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
            }

            vibrator.vibrate(VibrationEffect.createWaveform(pattern, -1))
        } catch (e: Exception) {
            Log.e(TAG, "Vibration failed: $e")
        }
    }

    // Play raw audio resource or fallback to system notification tone
    fun playSound(context: Context, soundName: String) {
        try {
            val resId = context.resources.getIdentifier(soundName, "raw", context.packageName)
            val soundUri: Uri = if (resId != 0) {
                "android.resource://${context.packageName}/$resId".toUri()
            } else {
                // Fallback to default system notification sound
                RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
            }

            MediaPlayer().apply {
                setDataSource(context, soundUri)
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                        .build(),
                )
                prepare()
                start()
                setOnCompletionListener {
                    it.release()
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to play sound $soundName: $e")
        }
    }
}
