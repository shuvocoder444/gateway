package com.mfsgateway.smsforwarder;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.work.Constraints;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.WorkManager;

public class MainActivity extends Activity {
    private static final int SMS_PERMISSION_REQUEST = 41;
    private EditText endpointInput;
    private EditText tokenInput;
    private TextView statusText;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        buildScreen();
        loadSettings();
        requestSmsPermission();
    }

    private void buildScreen() {
        int pad = (int) (20 * getResources().getDisplayMetrics().density);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, pad, pad, pad);
        root.setBackgroundColor(0xFFF5F7FB);

        TextView title = new TextView(this);
        title.setText("MFS SMS Forwarder");
        title.setTextSize(24);
        title.setTextColor(0xFF152238);
        root.addView(title, matchWrap());

        TextView help = new TextView(this);
        help.setText("Only payment SMS containing an amount and TrxID are forwarded. Configure your gateway and device token below.");
        help.setTextSize(15);
        help.setPadding(0, pad / 2, 0, pad);
        root.addView(help, matchWrap());

        endpointInput = field("Gateway URL (e.g. https://pay.example.com)");
        endpointInput.setInputType( android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        root.addView(endpointInput, matchWrap());

        tokenInput = field("Device Token");
        tokenInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);
        root.addView(tokenInput, matchWrap());

        Button save = new Button(this);
        save.setText("Save settings");
        root.addView(save, matchWrap());
        save.setOnClickListener(v -> saveSettings());

        Button sync = new Button(this);
        sync.setText("Send test heartbeat");
        root.addView(sync, matchWrap());
        sync.setOnClickListener(v -> {
            saveSettings();
            enqueueSync();
            setStatus("Queued a connection check. It will send when internet is available.");
        });

        statusText = new TextView(this);
        statusText.setTextSize(14);
        statusText.setPadding(0, pad, 0, 0);
        root.addView(statusText, matchWrap());

        setContentView(root);
    }

    private EditText field(String hint) {
        EditText input = new EditText(this);
        input.setHint(hint);
        input.setSingleLine(true);
        input.setPadding(24, 12, 24, 12);
        return input;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private void loadSettings() {
        android.content.SharedPreferences prefs = getSharedPreferences(SmsReceiver.PREFS, MODE_PRIVATE);
        endpointInput.setText(prefs.getString(SmsReceiver.ENDPOINT, ""));
        tokenInput.setText(prefs.getString(SmsReceiver.TOKEN, ""));
        String last = prefs.getString(SmsReceiver.LAST_STATUS, "Not configured yet.");
        statusText.setText(last);
    }

    private void saveSettings() {
        String base = endpointInput.getText().toString().trim().replaceAll("/+$", "");
        String token = tokenInput.getText().toString().trim();
        if (base.isEmpty() || token.isEmpty()) {
            setStatus("Enter the gateway URL and the device token.");
            return;
        }
        if (!base.startsWith("https://") && !base.startsWith("http://")) {
            setStatus("Gateway URL must start with https:// (or http:// on a trusted local network).");
            return;
        }
        getSharedPreferences(SmsReceiver.PREFS, MODE_PRIVATE).edit()
                .putString(SmsReceiver.ENDPOINT, base + "/api/v1/device/sync-sms/")
                .putString(SmsReceiver.TOKEN, token)
                .apply();
        setStatus("Settings saved. SMS permission: " + (hasSmsPermission() ? "granted" : "not granted"));
    }

    private void requestSmsPermission() {
        if (!hasSmsPermission()) requestPermissions(new String[]{Manifest.permission.RECEIVE_SMS}, SMS_PERMISSION_REQUEST);
    }

    private boolean hasSmsPermission() {
        return checkSelfPermission(Manifest.permission.RECEIVE_SMS) == PackageManager.PERMISSION_GRANTED;
    }

    private void enqueueSync() {
        Constraints constraints = new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build();
        OneTimeWorkRequest work = new OneTimeWorkRequest.Builder(SyncWorker.class).setConstraints(constraints).build();
        WorkManager.getInstance(this).enqueueUniqueWork("mfs-sms-sync", ExistingWorkPolicy.KEEP, work);
    }

    private void setStatus(String message) {
        statusText.setText(message);
        getSharedPreferences(SmsReceiver.PREFS, MODE_PRIVATE).edit().putString(SmsReceiver.LAST_STATUS, message).apply();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (statusText != null) {
            statusText.setText(getSharedPreferences(SmsReceiver.PREFS, MODE_PRIVATE)
                    .getString(SmsReceiver.LAST_STATUS, "Not configured yet."));
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == SMS_PERMISSION_REQUEST) {
            setStatus(results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED
                    ? "SMS permission granted. Save your device token to start forwarding payment SMS."
                    : "SMS permission denied. The app cannot receive payment SMS without permission.");
        }
    }
}
