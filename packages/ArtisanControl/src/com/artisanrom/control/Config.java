// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import android.content.Context;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.Log;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.HashMap;
import org.json.JSONObject;

/** Shared, OEM-independent settings contract. No vendor code is linked here. */
public final class Config {
    public static final String BRAND = "YuROM Ultra";
    public static final String GITHUB = "https://github.com/yuefdev";
    public static final String PACKAGE = "com.artisanrom.control";
    public static final String SETTINGS = "com.android.settings";
    public static final String SETTINGS_FRAGMENT = "com.android.settings.artisan.ArtisanSettings";
    public static final String COMMAND = PACKAGE + ".COMMAND";
    public static final String PERMISSION = PACKAGE + ".permission.CONTROL";
    public static final int VERSION = 1;
    private static volatile Context application;
    private static final HashMap<String, String> cache = new HashMap<>();
    private static long cachedAt;
    private static final HashMap<String, Boolean> logged = new HashMap<>();

    private Config() {}

    public static Context context() {
        Context c = application;
        if (c != null) return c;
        try {
            Class<?> thread = Class.forName("android.app.ActivityThread");
            c = (Context) thread.getMethod("currentApplication").invoke(null);
            if (c == null) {
                Object instance = thread.getMethod("currentActivityThread").invoke(null);
                if (instance != null) c = (Context) thread.getMethod("getSystemContext").invoke(instance);
            }
            if (c != null) application = c;
        } catch (Throwable t) { /* Early zygote: keep original behaviour until a context exists. */ }
        return c;
    }

    public static void attach(Context context) {
        if (context != null) application = context.getApplicationContext() != null
                ? context.getApplicationContext() : context;
    }

    public static synchronized String get(Context c, String key, String fallback) {
        if (c == null) return fallback;
        long now = SystemClock.elapsedRealtime();
        if (now - cachedAt > 500) { cache.clear(); cachedAt = now; }
        if (!cache.containsKey(key)) {
            try { cache.put(key, Settings.Global.getString(c.getContentResolver(), key)); }
            catch (Throwable t) { return fallback; }
        }
        String value = cache.get(key);
        return value == null ? fallback : value;
    }

    public static String get(String key, String fallback) { return get(context(), key, fallback); }
    public static boolean enabled() { return !"0".equals(get("ac_enabled", "1")); }
    public static boolean on(String key) { return enabled() && "1".equals(get(key, "0")); }
    public static int integer(String key, int fallback, int min, int max) {
        try { return Math.max(min, Math.min(max, Integer.parseInt(get(key, "" + fallback)))); }
        catch (RuntimeException e) { return fallback; }
    }
    public static float number(String key, float fallback, float min, float max) {
        try {
            float v = Float.parseFloat(get(key, "" + fallback));
            return Float.isFinite(v) ? Math.max(min, Math.min(max, v)) : fallback;
        } catch (RuntimeException e) { return fallback; }
    }
    public static boolean member(String listKey, String name) {
        if (name == null || name.isEmpty() || !enabled()) return false;
        for (String item : get(listKey, "").split(",")) if (name.equals(item.trim())) return true;
        return false;
    }
    public static JSONObject object(String key) {
        try { return new JSONObject(get(key, "{}")); }
        catch (Exception e) { return new JSONObject(); }
    }
    public static Object field(Object owner, String name) throws Exception {
        Class<?> type = owner instanceof Class ? (Class<?>) owner : owner.getClass();
        for (Class<?> current = type; current != null; current = current.getSuperclass()) {
            try {
                Field f = current.getDeclaredField(name); f.setAccessible(true);
                return f.get(owner instanceof Class ? null : owner);
            } catch (NoSuchFieldException e) { /* Try its superclass. */ }
        }
        throw new NoSuchFieldException(type.getName() + "." + name);
    }
    public static Object invoke(Object owner, String name, Class<?>[] types, Object... args) throws Exception {
        for (Class<?> c = owner.getClass(); c != null; c = c.getSuperclass()) {
            try {
                Method m = c.getDeclaredMethod(name, types); m.setAccessible(true);
                return m.invoke(owner, args);
            } catch (NoSuchMethodException e) { /* Try its superclass. */ }
        }
        throw new NoSuchMethodException(name);
    }
    public static synchronized void failure(String operation, Throwable error) {
        if (logged.put(operation, true) == null) Log.w("ArtisanControl", operation, error);
    }
}
