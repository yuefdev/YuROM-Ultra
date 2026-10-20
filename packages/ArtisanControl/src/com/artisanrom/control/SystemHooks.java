// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import android.app.KeyguardManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.media.AudioManager;
import android.os.Binder;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.view.KeyEvent;
import java.util.HashMap;

/** System-server features. The original policy remains the default. */
public final class SystemHooks {
    private static Context context;
    private static boolean installed;
    private static final Handler handler = new Handler(Looper.getMainLooper());
    private static final HashMap<Integer, Press> presses = new HashMap<>();
    private SystemHooks() {}

    private static Context context(Object owner) {
        try { return (Context)Config.field(owner, "mContext"); }
        catch (Throwable t) { return context != null ? context : Config.context(); }
    }

    public static void install(Object policy) {
        Context c = context(policy);
        if (c == null || installed) return;
        context = c; Config.attach(c); installed = true;
        c.registerReceiver(new BroadcastReceiver() {
            @Override public void onReceive(Context receiverContext, Intent intent) {
                String command = intent.getStringExtra("command");
                try {
                    String[] packages = receiverContext.getPackageManager().getPackagesForUid(getSentFromUid());
                    boolean authorised = false;
                    if (packages != null) for (String pkg : packages) authorised |= Config.SETTINGS.equals(pkg);
                    if (!authorised) return;
                    PowerManager power = receiverContext.getSystemService(PowerManager.class);
                    if ("reboot".equals(command)) power.reboot(null);
                    else if ("recovery".equals(command)) power.reboot("recovery");
                    else if ("download".equals(command)) power.reboot("download");
                    else if ("shutdown".equals(command)) Config.invoke(power, "shutdown",
                            new Class<?>[]{boolean.class, String.class, boolean.class}, false, "userrequested", false);
                    else if ("restart_home".equals(command)) {
                        Intent home = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME);
                        android.content.pm.ResolveInfo resolved = receiverContext.getPackageManager().resolveActivity(home, 0);
                        if (resolved == null || resolved.activityInfo == null) return;
                        String pkg = resolved.activityInfo.packageName;
                        if ("android".equals(pkg) || Config.PACKAGE.equals(pkg)) return;
                        Object manager = receiverContext.getSystemService(android.app.ActivityManager.class);
                        Config.invoke(manager, "forceStopPackage", new Class<?>[]{String.class}, pkg);
                        receiverContext.startActivity(home.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                    }
                } catch (Throwable t) { Config.failure("command " + command, t); }
            }
        }, new IntentFilter(Config.COMMAND), "android.permission.WRITE_SECURE_SETTINGS", handler, Context.RECEIVER_EXPORTED);
    }

    /** -1 delegates to the OEM's normal secure-window policy. */
    public static int secureWindow(Object window) {
        if (!Config.enabled()) return -1;
        try {
            Object attrs = Config.field(window, "mAttrs");
            String pkg = (String)Config.field(attrs, "packageName");
            if (pkg == null || "android".equals(pkg) || "com.android.systemui".equals(pkg)) return -1;
            return Config.on("ac_secure_capture_all") || Config.member("ac_secure_capture_apps", pkg) ? 0 : -1;
        } catch (Throwable t) { Config.failure("secure-window policy", t); return -1; }
    }

    public static boolean quietCapture(Object service) {
        if (!Config.enabled() || Binder.getCallingUid() < 10000) return false;
        if (Config.on("ac_capture_detection_all")) return true;
        try {
            Context c = context(service);
            String[] pkgs = c.getPackageManager().getPackagesForUid(Binder.getCallingUid());
            if (pkgs != null) for (String pkg : pkgs)
                if (Config.member("ac_capture_detection_apps", pkg)) return true;
        } catch (Throwable t) { Config.failure("capture callback policy", t); }
        return false;
    }

    public static android.net.Uri notificationSound(android.net.Uri original) {
        if(original==null || !Config.enabled() || !"0".equals(Config.get("ac_notification_sound_screen_on","1")))return original;
        Context c=context!=null?context:Config.context();
        return c!=null && c.getSystemService(PowerManager.class).isInteractive()?null:original;
    }

    private static final class Press implements Runnable {
        final AudioManager audio; final int code; final int media; boolean longPress; boolean cancelled;
        Press(AudioManager a, int c, int m) { audio = a; code = c; media = m; }
        public synchronized void run() {
            if(cancelled)return;
            longPress = true;
            long now = SystemClock.uptimeMillis();
            audio.dispatchMediaKeyEvent(new KeyEvent(now, now, KeyEvent.ACTION_DOWN, media, 0));
            audio.dispatchMediaKeyEvent(new KeyEvent(now, now, KeyEvent.ACTION_UP, media, 0));
        }
    }

    public static boolean music(Object policy, KeyEvent event) {
        int code = event.getKeyCode();
        if (code != KeyEvent.KEYCODE_VOLUME_UP && code != KeyEvent.KEYCODE_VOLUME_DOWN) return false;
        Context c = context(policy);
        if (c == null) return false;
        AudioManager audio = c.getSystemService(AudioManager.class);
        PowerManager power = c.getSystemService(PowerManager.class);
        if (audio == null || power == null || audio.getMode() != AudioManager.MODE_NORMAL) return false;
        Press existing = presses.get(code);
        if (event.getAction() == KeyEvent.ACTION_UP && existing != null) {
            presses.remove(code); handler.removeCallbacks(existing);
            synchronized(existing){
                existing.cancelled=true;
                if (!existing.longPress && !event.isCanceled()) audio.adjustStreamVolume(AudioManager.STREAM_MUSIC,
                        code == KeyEvent.KEYCODE_VOLUME_UP ? AudioManager.ADJUST_RAISE : AudioManager.ADJUST_LOWER, 0);
            }
            return true;
        }
        if (!Config.on("ac_volume_music") || power.isInteractive() || !audio.isMusicActive()) return false;
        if (event.getAction() == KeyEvent.ACTION_DOWN) {
            if (existing == null) {
                int media = Config.integer(code == KeyEvent.KEYCODE_VOLUME_UP ? "ac_volume_up_action" : "ac_volume_down_action",
                        code == KeyEvent.KEYCODE_VOLUME_UP ? KeyEvent.KEYCODE_MEDIA_NEXT : KeyEvent.KEYCODE_MEDIA_PREVIOUS, 85, 87 + 1);
                Press press = new Press(audio, code, media); presses.put(code, press);
                handler.postDelayed(press, Config.integer("ac_volume_hold_ms", 600, 300, 1500));
            }
            return true;
        }
        return false;
    }

    public static boolean powerMenu(Object policy) {
        if (!Config.on("ac_power_menu")) return false;
        Context c = context(policy);
        if (c == null) return false;
        try {
            android.os.Bundle arguments=new android.os.Bundle();arguments.putBoolean("power_menu",true);
            Intent intent = new Intent().setClassName(Config.SETTINGS, "com.android.settings.SubSettings")
                    .putExtra(":settings:show_fragment",Config.SETTINGS_FRAGMENT)
                    .putExtra(":settings:show_fragment_args",arguments)
                    .putExtra(":settings:show_fragment_title",Config.BRAND).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            c.startActivity(intent); return true;
        } catch (Throwable t) { Config.failure("power menu", t); return false; }
    }
}
