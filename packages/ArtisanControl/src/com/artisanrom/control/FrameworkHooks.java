// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import android.content.ContentResolver;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Build;
import android.os.Process;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONObject;

/** Hooks in the public framework. Changes apply only to explicitly selected apps. */
public final class FrameworkHooks {
    private FrameworkHooks() {}

    public static boolean hideDeveloper(ContentResolver resolver, String key) {
        if (!"development_settings_enabled".equals(key) && !"adb_enabled".equals(key)
                && !"adb_wifi_enabled".equals(key)) return false;
        if (Process.myUid() < 10000) return false;
        try {
            String pkg = (String) Config.invoke(resolver, "getPackageName", new Class<?>[0]);
            return !Config.PACKAGE.equals(pkg) && !Config.SETTINGS.equals(pkg) && Config.member("ac_hide_developer_apps", pkg);
        } catch (Throwable t) { Config.failure("developer visibility", t); return false; }
    }

    private static boolean filtered(Context c) {
        return c != null && Process.myUid() >= 10000 && !Config.PACKAGE.equals(c.getPackageName()) && !Config.SETTINGS.equals(c.getPackageName())
                && Config.member("ac_filter_apps", c.getPackageName());
    }

    public static void checkPackage(Context c, String name) throws PackageManager.NameNotFoundException {
        if (filtered(c) && !c.getPackageName().equals(name) && Config.member("ac_hidden_packages", name))
            throw new PackageManager.NameNotFoundException(name);
    }

    public static List<?> packages(Context c, List<?> original) {
        if (original == null || !filtered(c)) return original;
        ArrayList<Object> result = new ArrayList<>();
        for (Object item : original) {
            String name = null;
            if (item instanceof PackageInfo) name = ((PackageInfo)item).packageName;
            else if (item instanceof ApplicationInfo) name = ((ApplicationInfo)item).packageName;
            else if (item instanceof ResolveInfo && ((ResolveInfo)item).activityInfo != null)
                name = ((ResolveInfo)item).activityInfo.packageName;
            else if (item instanceof ResolveInfo && ((ResolveInfo)item).serviceInfo != null)
                name = ((ResolveInfo)item).serviceInfo.packageName;
            if (name == null || name.equals(c.getPackageName()) || !Config.member("ac_hidden_packages", name))
                result.add(item);
        }
        return result;
    }
    public static String[] packagesForUid(Context c,String[] original){
        if(original==null || !filtered(c))return original;
        ArrayList<String> result=new ArrayList<>();
        for(String pkg:original)if(pkg.equals(c.getPackageName())||!Config.member("ac_hidden_packages",pkg))result.add(pkg);
        return result.isEmpty()?null:result.toArray(new String[0]);
    }

    public static void application(Context c) {
        Config.attach(c);
        if (!Config.enabled() || c == null || Process.myUid() < 10000) return;
        String pkg = c.getPackageName();
        if (Config.PACKAGE.equals(pkg)) return;
        JSONObject profiles = Config.object("ac_device_profiles");
        JSONObject profile = profiles.optJSONObject(pkg);
        if (profile == null) return;
        for (String key : new String[]{"MODEL", "MANUFACTURER", "BRAND", "DEVICE", "PRODUCT", "FINGERPRINT"}) {
            String value = profile.optString(key, "");
            if (value.isEmpty() || value.length() > 512) continue;
            try {
                Field field = Build.class.getDeclaredField(key); field.setAccessible(true);
                field.set(null, value);
            } catch (Throwable t) { Config.failure("device profile " + key, t); }
        }
    }
}
