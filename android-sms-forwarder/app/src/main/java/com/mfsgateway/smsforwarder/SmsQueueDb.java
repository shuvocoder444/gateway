package com.mfsgateway.smsforwarder;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.content.ContentValues;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;

public class SmsQueueDb extends SQLiteOpenHelper {
    private static final String DB_NAME = "forward_queue.db";
    private static SmsQueueDb instance;

    public static synchronized SmsQueueDb get(Context context) {
        if (instance == null) instance = new SmsQueueDb(context.getApplicationContext());
        return instance;
    }

    private SmsQueueDb(Context context) { super(context, DB_NAME, null, 1); }

    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE sms_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, trx_id TEXT, amount TEXT, raw_sms TEXT, battery INTEGER)");
    }

    @Override public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) { }

    public synchronized void insert(String sender, String trxId, String amount, String rawSms, int battery) {
        ContentValues values = new ContentValues();
        values.put("sender", sender); values.put("trx_id", trxId); values.put("amount", amount);
        values.put("raw_sms", rawSms); values.put("battery", battery);
        getWritableDatabase().insert("sms_queue", null, values);
    }

    public synchronized List<JSONObject> firstBatch(int limit) {
        List<JSONObject> rows = new ArrayList<>();
        try (Cursor cursor = getReadableDatabase().rawQuery("SELECT id,sender,trx_id,amount,raw_sms,battery FROM sms_queue ORDER BY id LIMIT ?", new String[]{String.valueOf(limit)})) {
            while (cursor.moveToNext()) {
                JSONObject row = new JSONObject();
                row.put("id", cursor.getLong(0)); row.put("sender", cursor.getString(1));
                row.put("trx_id", cursor.getString(2)); row.put("amount", cursor.getString(3));
                row.put("raw_sms", cursor.getString(4)); row.put("battery_percentage", cursor.getInt(5));
                rows.add(row);
            }
        } catch (Exception ignored) { }
        return rows;
    }

    public synchronized void delete(long id) { getWritableDatabase().delete("sms_queue", "id=?", new String[]{String.valueOf(id)}); }
    public synchronized int size() {
        try (Cursor c = getReadableDatabase().rawQuery("SELECT COUNT(*) FROM sms_queue", null)) { return c.moveToFirst() ? c.getInt(0) : 0; }
    }
}
