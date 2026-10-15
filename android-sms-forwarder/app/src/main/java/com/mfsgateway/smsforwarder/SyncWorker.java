package com.mfsgateway.smsforwarder;

import android.content.Context;
import android.content.SharedPreferences;
import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;

public class SyncWorker extends Worker {
    public SyncWorker(@NonNull Context context, @NonNull WorkerParameters params) { super(context, params); }

    @NonNull @Override public Result doWork() {
        Context context = getApplicationContext();
        SharedPreferences prefs = context.getSharedPreferences(SmsReceiver.PREFS, Context.MODE_PRIVATE);
        String endpoint = prefs.getString(SmsReceiver.ENDPOINT, "");
        String token = prefs.getString(SmsReceiver.TOKEN, "");
        if (endpoint.isEmpty() || token.isEmpty()) return Result.failure();

        List<JSONObject> batch = SmsQueueDb.get(context).firstBatch(40);
        if (batch.isEmpty()) {
            try {
                JSONObject heartbeat = new JSONObject();
                int battery = batteryLevel(context);
                if (battery >= 0) heartbeat.put("battery_percentage", battery);
                post(endpoint, token, heartbeat);
                prefs.edit().putString(SmsReceiver.LAST_STATUS, "Gateway connection is working. No queued SMS.").apply();
                return Result.success();
            } catch (Exception error) {
                prefs.edit().putString(SmsReceiver.LAST_STATUS, "Connection check failed; will retry when network is available.").apply();
                return Result.retry();
            }
        }

        JSONArray messages = new JSONArray();
        for (JSONObject row : batch) {
            JSONObject message = new JSONObject();
            try {
                message.put("sender", row.getString("sender"));
                message.put("trx_id", row.getString("trx_id"));
                message.put("amount", row.getString("amount"));
                message.put("raw_sms", row.getString("raw_sms"));
                messages.put(message);
            } catch (Exception ignored) { }
        }
        try {
            JSONObject payload = new JSONObject();
            payload.put("battery_percentage", batteryLevel(context));
            payload.put("messages", messages);
            JSONObject response = post(endpoint, token, payload);
            JSONArray synced = response.optJSONArray("synced_trx_ids");
            JSONArray duplicates = response.optJSONArray("duplicate_trx_ids");
            if (synced == null) synced = new JSONArray();
            if (duplicates == null) duplicates = new JSONArray();
            if (synced.length() + duplicates.length() != batch.size()) {
                prefs.edit().putString(SmsReceiver.LAST_STATUS, "Gateway returned item errors; queued SMS retained for review/retry.").apply();
                return Result.retry();
            }
            for (JSONObject row : batch) SmsQueueDb.get(context).delete(row.getLong("id"));
            prefs.edit().putString(SmsReceiver.LAST_STATUS, "Synced " + synced.length() + " payment SMS; duplicates ignored: " + duplicates.length() + ".").apply();
            return SmsQueueDb.get(context).size() > 0 ? Result.retry() : Result.success();
        } catch (Exception error) {
            prefs.edit().putString(SmsReceiver.LAST_STATUS, "SMS saved locally; delivery failed and will retry.").apply();
            return Result.retry();
        }
    }

    private JSONObject post(String endpoint, String token, JSONObject payload) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(endpoint).openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(15000);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setRequestProperty("X-DEVICE-TOKEN", token);
        byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
        try (OutputStream output = connection.getOutputStream()) { output.write(body); }
        int code = connection.getResponseCode();
        java.io.InputStream stream = code >= 200 && code < 300 ? connection.getInputStream() : connection.getErrorStream();
        String response = "";
        if (stream != null) {
            java.io.ByteArrayOutputStream bytes = new java.io.ByteArrayOutputStream();
            byte[] buffer = new byte[2048]; int read;
            while ((read = stream.read(buffer)) != -1) bytes.write(buffer, 0, read);
            response = bytes.toString("UTF-8"); stream.close();
        }
        connection.disconnect();
        if (code < 200 || code >= 300) throw new java.io.IOException("Gateway HTTP " + code + ": " + response);
        return response.isEmpty() ? new JSONObject() : new JSONObject(response);
    }

    private int batteryLevel(Context context) {
        android.content.Intent battery = context.registerReceiver(null, new android.content.IntentFilter(android.content.Intent.ACTION_BATTERY_CHANGED));
        if (battery == null) return -1;
        int level = battery.getIntExtra(android.os.BatteryManager.EXTRA_LEVEL, -1);
        int scale = battery.getIntExtra(android.os.BatteryManager.EXTRA_SCALE, -1);
        return level >= 0 && scale > 0 ? Math.round(level * 100f / scale) : -1;
    }
}
