package com.mfsgateway.smsforwarder;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.BatteryManager;
import android.provider.Telephony;
import android.telephony.SmsMessage;
import androidx.work.Constraints;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.WorkManager;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SmsReceiver extends BroadcastReceiver {
    public static final String PREFS = "mfs_forwarder";
    public static final String ENDPOINT = "endpoint";
    public static final String TOKEN = "device_token";
    public static final String LAST_STATUS = "last_status";
    private static final Pattern TRX = Pattern.compile("(?i)\\b(?:trx\\s*id|transaction\\s*id|trxid)\\s*[:#\\-]?\\s*([A-Z0-9]{5,32})\\b");
    private static final Pattern AMOUNT = Pattern.compile("(?i)\\b(?:tk|taka|bdt)\\s*[:.]?\\s*([0-9][0-9,]*(?:\\.[0-9]{1,2})?)");

    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Telephony.Sms.Intents.SMS_RECEIVED_ACTION.equals(intent.getAction())) return;
        SmsMessage[] messages = Telephony.Sms.Intents.getMessagesFromIntent(intent);
        if (messages == null || messages.length == 0) return;
        StringBuilder body = new StringBuilder();
        String sender = messages[0].getOriginatingAddress();
        for (SmsMessage message : messages) body.append(message.getMessageBody());
        String raw = body.toString();

        Matcher trx = TRX.matcher(raw);
        Matcher amount = AMOUNT.matcher(raw);
        if (!trx.find() || !amount.find() || !looksLikeReceipt(raw)) return;

        String numericAmount = amount.group(1).replace(",", "");
        try {
            if (new java.math.BigDecimal(numericAmount).signum() <= 0) return;
        } catch (NumberFormatException invalidAmount) {
            return;
        }

        android.content.SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (prefs.getString(ENDPOINT, "").isEmpty() || prefs.getString(TOKEN, "").isEmpty()) {
            prefs.edit().putString(LAST_STATUS, "Payment SMS received, but gateway URL/device token is not configured.").apply();
            return;
        }

        int battery = -1;
        Intent batteryIntent = context.registerReceiver(null, new android.content.IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        if (batteryIntent != null) {
            int level = batteryIntent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
            int scale = batteryIntent.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
            if (level >= 0 && scale > 0) battery = Math.round(level * 100f / scale);
        }
        SmsQueueDb.get(context).insert(sender == null ? "Unknown" : sender, trx.group(1).toUpperCase(), numericAmount, raw, battery);

        Constraints constraints = new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build();
        OneTimeWorkRequest work = new OneTimeWorkRequest.Builder(SyncWorker.class).setConstraints(constraints).build();
        WorkManager.getInstance(context).enqueueUniqueWork("mfs-sms-sync", ExistingWorkPolicy.APPEND_OR_REPLACE, work);
        prefs.edit().putString(LAST_STATUS, "Payment SMS queued for secure delivery.").apply();
    }

    private boolean looksLikeReceipt(String message) {
        String lower = message.toLowerCase(java.util.Locale.ROOT);
        return lower.contains("received") || lower.contains("credited")
                || lower.contains("cash in") || lower.contains("cash-in");
    }
}
