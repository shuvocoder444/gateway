# MFS SMS Forwarder (Android App)

Native Android application designed to forward bKash, Nagad, Rocket, and Cellfin payment SMS directly to your MFS Payment Gateway.

---

## 📱 Features

1. **Automatic SMS Interception**:
   - Listens in the background for incoming SMS (`android.provider.Telephony.SMS_RECEIVED`).
   - Automatically detects receipts (keywords: `received`, `credited`, `cash in`, `cash-in`).
   - Extracts Transaction ID (`TrxID`) and Payment Amount using RegEx.

2. **Offline-First & Resilience**:
   - Uses local SQLite database (`SmsQueueDb`) to store messages safely if the device is temporarily offline.
   - Syncs automatically via Android `WorkManager` as soon as internet connectivity returns.

3. **Secure API Sync**:
   - Posts data to `/api/v1/device/sync-sms/` using `X-DEVICE-TOKEN` authentication.
   - Reports battery percentage and periodic heartbeats to the Master Dashboard.

---

## 🛠️ How to Build the APK

### Method 1: Using Android Studio (Recommended)
1. Install [Android Studio](https://developer.android.com/studio) if not already installed.
2. Open Android Studio and choose **Open an Existing Project**.
3. Select the folder: `e:\payment gateway\android-sms-forwarder`.
4. Allow Gradle to sync dependencies (`androidx.work:work-runtime`).
5. In the top menu, go to:
   **Build** > **Build Bundle(s) / APK(s)** > **Build APK(s)**.
6. Once completed, click **locate** to get the generated `app-debug.apk`.
7. Transfer the `.apk` to your Android phone (via USB cable, Google Drive, WhatsApp, or Telegram) and tap to install.

### Method 2: Command Line (if Android SDK / Gradle is installed)
```bash
cd android-sms-forwarder
gradle assembleDebug
# Generated APK will be in:
# app/build/outputs/apk/debug/app-debug.apk
```

---

## ⚙️ Configuration & Setup on Phone

1. **Install APK**: Install the APK on your Android phone where the MFS SIM cards (bKash/Nagad/Rocket) are inserted.
2. **Grant Permissions**:
   - Open the app and allow **SMS Read/Receive permissions**.
   - Ensure Battery Optimization is set to **Don't optimize / Unrestricted** (so Android doesn't kill background sync).
3. **Connect to Gateway**:
   - Go to your Master Admin: `http://<your-server-ip>:8000/admin-dashboard/` -> **Android Bridge Nodes**.
   - Create a new Bridge Device (e.g., `Shop SIM 1`) and copy the **Device Token**.
   - In the Android app:
     - **Gateway URL**: `http://<your-server-ip>:8000` (or your domain e.g., `https://pay.yourdomain.com`)
     - **Device Token**: Paste your copied token.
   - Click **Save settings**.
4. **Test Connection**:
   - Tap **Send test heartbeat** in the app.
   - Check your Master Admin dashboard: the device status will turn **Online** with battery percentage!
