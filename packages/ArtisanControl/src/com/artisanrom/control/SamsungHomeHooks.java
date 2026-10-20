// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import android.content.Context;
import android.graphics.Point;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import java.lang.reflect.Method;

/** One UI Honeyspace adapter. Other launchers can use the same ac_* contract. */
public final class SamsungHomeHooks {
    private SamsungHomeHooks() {}
    public static boolean active() { return Config.on("ac_home_enabled"); }
    public static boolean bool(boolean original, String key) {
        return active() ? "1".equals(Config.get(key,"ac_recents_labels".equals(key)?"1":"0")) : original;
    }
    public static int integer(int original, String key) {
        if (!active()) return original;
        int fallback="ac_recents_layout".equals(key)?0:"ac_gesture_sensitivity".equals(key)?50:-1;
        int value = Config.integer(key, fallback, -1, 1000);
        return value < 0 ? original : value;
    }
    public static float number(float original, String key) {
        if (!active()) return original;
        float value = Config.number(key, -1, -1, 1000);
        return value < 0 ? original : value;
    }
    public static Point grid(Point original, String key) {
        if (!active()) return original;
        String[] value = Config.get(key, "").split("x");
        if (value.length != 2) return original;
        try {
            int x = Integer.parseInt(value[0]), y = Integer.parseInt(value[1]);
            return x >= 4 && x <= 7 && y >= 4 && y <= 9 ? new Point(x,y) : original;
        } catch (NumberFormatException e) { return original; }
    }
    public static Object flow(Object original, String key) {
        int axis = key.indexOf("_grid_");
        String setting = axis < 0 ? key : key.substring(0, axis + 5);
        if (!active() || Config.get(setting, "").isEmpty()) return original;
        if ("ac_dock_count".equals(key) && Config.integer(key, -1, -1, 9) < 4) return original;
        try {
            Object current = Config.invoke(original, "getValue", new Class<?>[0]);
            Object value;
            if (axis >= 0) {
                Point grid = grid(new Point(0,0), setting);
                int selected = key.endsWith("_x") ? grid.x : grid.y;
                if (selected == 0) return original;
                value = selected;
            } else value = Integer.valueOf(Config.integer(key, ((Number)current).intValue(), 4, 9));
            ClassLoader loader = original.getClass().getClassLoader();
            Class<?> helper = Class.forName("kotlinx.coroutines.flow.StateFlowKt", true, loader);
            return helper.getMethod("MutableStateFlow", Object.class).invoke(null, value);
        } catch (Throwable t) { Config.failure("launcher preference " + key, t); return original; }
    }
    public static android.graphics.PointF scales(android.graphics.PointF original) {
        if(!active() || original==null)return original;
        int x=Config.integer("ac_recents_scale_x",-1,-1,100),y=Config.integer("ac_recents_scale_y",-1,-1,100);
        return x<0&&y<0?original:new android.graphics.PointF(x<0?original.x:x/100f,y<0?original.y:y/100f);
    }
    public static float top(float original){
        int value=Config.integer("ac_recents_top",-1,-1,80);
        return active() && value>=0?value/100f:original;
    }
    public static long duration(long original) {
        return active() ? (long)(original * Config.number("ac_home_animation_scale", 1, 0.2f, 2)) : original;
    }
    public static android.view.animation.Interpolator bounce(android.view.animation.Interpolator original) {
        return active() && Config.on("ac_home_bounce") ? new android.view.animation.OvershootInterpolator(0.7f) : original;
    }
    public static void decorate(View root) {
        if (!active() || root == null) return;
        if (root instanceof TextView && Config.on("ac_folder_title_centre")) {
            String cls = root.getClass().getName();
            if (cls.contains("Folder") && cls.contains("Title")) root.post(()->{
                ((TextView)root).setGravity(android.view.Gravity.CENTER);
                root.setTextAlignment(View.TEXT_ALIGNMENT_CENTER);
            });
        }
        if (root instanceof ViewGroup) for (int i=0;i<((ViewGroup)root).getChildCount();i++)
            decorate(((ViewGroup)root).getChildAt(i));
    }
    public static int clearVisibility(int original){return active()&&Config.on("ac_recents_hide_clear")?View.GONE:original;}
    public static void task(View root){
        if(!active() || !Config.on("ac_recents_transparent"))return;
        root.setBackgroundColor(android.graphics.Color.TRANSPARENT);
    }
    public static void scenePaints(Object scene){
        if(!active() || !Config.on("ac_recents_transparent"))return;
        try{
            Object paints=Config.field(scene,"backgroundPaints");
            if(paints instanceof java.util.List)for(Object item:(java.util.List<?>)paints)
                if(item instanceof android.graphics.Paint)((android.graphics.Paint)item).setAlpha(0);
        }catch(Throwable t){Config.failure("recents background",t);}
    }
    public static void recents(Object pot,boolean shown){
        try{
            Context context=Config.context();
            if(context!=null)context.sendBroadcast(new android.content.Intent(Config.PACKAGE+".RECENTS")
                    .setPackage("com.android.systemui").putExtra("shown",shown&&active()&&Config.on("ac_recents_hide_status")),null,
                    android.app.BroadcastOptions.makeBasic().setShareIdentityEnabled(true).toBundle());
        }catch(Throwable t){Config.failure("recents status bar",t);}
    }
    public static void recentsView(View view,boolean visible){
        view.post(()->recents(null,visible&&view.isShown()));
    }
}
