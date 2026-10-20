// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import android.app.KeyguardManager;
import android.app.Notification;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.os.BatteryManager;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.net.TrafficStats;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.TextView;
import android.widget.FrameLayout;
import java.util.Locale;

/** SystemUI integration, using native windows and stopping all drawing off-screen. */
public final class UiHooks {
    private static Runtime runtime;
    private static boolean recentsHidden;
    private static final java.util.WeakHashMap<View,Float> bars=new java.util.WeakHashMap<>();
    private static java.lang.ref.WeakReference<Object> privacyController=new java.lang.ref.WeakReference<>(null);
    private UiHooks() {}

    public static void install(Context context) {
        if (runtime != null) return;
        Config.attach(context);
        runtime = new Runtime(context);
        runtime.start();
    }

    public static void privacyController(Object controller) { privacyController=new java.lang.ref.WeakReference<>(controller); }
    public static java.util.List<?> privacyItems(java.util.List<?> original) {
        if(!Config.on("ac_hide_privacy") || original==null)return original;
        try{
            java.util.ArrayList<Object> filtered=new java.util.ArrayList<>();
            for(Object item:original){
                String type=String.valueOf(Config.field(item,"privacyType"));
                if(!"TYPE_MICROPHONE".equals(type) && !"TYPE_CAMERA".equals(type))filtered.add(item);
            }
            return filtered;
        }catch(Throwable t){Config.failure("privacy indicators",t);return original;}
    }

    public static boolean allowRemoteInput(int user) {
        Context c=Config.context();
        if(c==null || !Config.enabled() || user!=android.os.Process.myUid()/100000)return false;
        try{
            if(android.provider.Settings.Secure.getInt(c.getContentResolver(),"lock_screen_allow_remote_input",0)!=1)return false;
            android.app.admin.DevicePolicyManager policy=c.getSystemService(android.app.admin.DevicePolicyManager.class);
            int disabled=policy==null?0:policy.getKeyguardDisabledFeatures(null);
            return (disabled & (android.app.admin.DevicePolicyManager.KEYGUARD_DISABLE_SECURE_NOTIFICATIONS
                    |android.app.admin.DevicePolicyManager.KEYGUARD_DISABLE_UNREDACTED_NOTIFICATIONS))==0;
        }catch(Throwable t){Config.failure("lockscreen reply",t);return false;}
    }

    public static void fingerprint(Object controller, Object source) {
        if (!Config.on("ac_fingerprint_vibration") || !"FINGERPRINT".equals(String.valueOf(source))) return;
        Context c = Config.context();
        if (c == null || !c.getSystemService(KeyguardManager.class).isKeyguardLocked()) return;
        Vibrator vibrator = c.getSystemService(Vibrator.class);
        if (vibrator != null && vibrator.hasVibrator()) vibrator.vibrate(VibrationEffect.createOneShot(
                Config.integer("ac_fingerprint_ms", 25, 10, 100), VibrationEffect.DEFAULT_AMPLITUDE));
    }

    public static void notificationRow(View row) {
        if (!Config.on("ac_expand_first_notification")) return;
        row.post(() -> {
            try {
                if (!(row.getParent() instanceof ViewGroup)) return;
                ViewGroup parent = (ViewGroup)row.getParent();
                for (int i = 0; i < parent.getChildCount(); i++) {
                    View other = parent.getChildAt(i);
                    if (other.getVisibility() != View.GONE && row.getClass().isInstance(other)) {
                        if (other == row) Config.invoke(row, "setUserExpanded",
                                new Class<?>[]{boolean.class, boolean.class}, true, true);
                        return;
                    }
                }
            } catch (Throwable t) { Config.failure("first notification", t); }
        });
    }

    public static CharSequence clock(CharSequence original) {
        if (!Config.enabled() || original == null) return original;
        String format = Config.get("ac_clock_format", "");
        if (format.isEmpty()) return original;
        if (!format.equals("HH:mm:ss") && !format.equals("dd MMM HH:mm") && !format.equals("HH:mm")) return original;
        return new java.text.SimpleDateFormat(format, Locale.getDefault()).format(new java.util.Date());
    }

    public static String charging(String original) {
        if (!Config.on("ac_charge_info") || runtime == null) return original;
        return original + "\n" + runtime.batteryText();
    }

    public static Object callDecision(Object entry, Object original) {
        int style=Config.integer("ac_call_style",0,0,2);
        if(!Config.enabled() || style==0 || !(original instanceof Enum))return original;
        try {
            android.service.notification.StatusBarNotification sbn=(android.service.notification.StatusBarNotification)Config.field(entry,"mSbn");
            Notification notification=sbn.getNotification();
            if(!Notification.CATEGORY_CALL.equals(notification.category)||notification.fullScreenIntent==null)return original;
            String decision=((Enum<?>)original).name();String replacement=null;
            if(style==1 && (decision.equals("NO_FSI_EXPECTED_TO_HUN")||decision.equals("NO_FSI_EXPECTED_TO_BRIEF")
                    ||decision.equals("NO_FSI_NO_HUN_OR_KEYGUARD")))replacement="FSI_KEYGUARD_SHOWING";
            if(style==2 && (decision.equals("FSI_DEVICE_NOT_INTERACTIVE")||decision.equals("FSI_DEVICE_DREAMING")
                    ||decision.equals("FSI_KEYGUARD_SHOWING")||decision.equals("FSI_KEYGUARD_OCCLUDED")||decision.equals("FSI_LOCKED_SHADE")))
                replacement="NO_FSI_EXPECTED_TO_HUN";
            return replacement==null?original:Config.field(original.getClass(),replacement);
        }catch(Throwable t){Config.failure("incoming call style",t);return original;}
    }

    public static void statusBar(View root) {
        if(!(root instanceof ViewGroup))return;
        bars.put(root,null);
        TextView clock=findClock(root);
        TextView network=new TextView(root.getContext());network.setTextSize(9);network.setGravity(Gravity.CENTER_VERTICAL);
        network.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        if(root instanceof FrameLayout)((FrameLayout)root).addView(network,new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,ViewGroup.LayoutParams.MATCH_PARENT,Gravity.LEFT));
        else ((ViewGroup)root).addView(network);
        final float originalSize=clock==null?0:clock.getTextSize();
        final android.content.res.ColorStateList originalColour=clock==null?null:clock.getTextColors();
        root.post(new Runnable(){
            long lastRx=TrafficStats.getTotalRxBytes(),lastTx=TrafficStats.getTotalTxBytes(),lastTime=SystemClock.elapsedRealtime();
            boolean formatted=false,coloured=false,sized=false;
            public void run(){
                if(!root.isAttachedToWindow())return;
                try{
                    boolean awake=root.getContext().getSystemService(PowerManager.class).isInteractive();
                    updateBar(root);
                    if(clock!=null){
                        boolean enabled=Config.enabled();
                        String format=enabled?Config.get("ac_clock_format",""):"";
                        if(!format.isEmpty()){clock.setText(UiHooks.clock(clock.getText()));formatted=true;}
                        else if(formatted){formatted=false;try{Config.invoke(clock,"updateClock",new Class<?>[0]);}catch(Exception ignored){}}
                        int size=enabled?Config.integer("ac_clock_size",0,0,22):0;
                        if(size>0){clock.setTextSize(size);sized=true;}else if(sized){clock.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX,originalSize);sized=false;}
                        String colour=enabled?Config.get("ac_clock_colour",""):"";
                        if(colour.matches("#[0-9A-Fa-f]{6}")){clock.setTextColor(Color.parseColor(colour));coloured=true;}
                        else if(coloured){clock.setTextColor(originalColour);coloured=false;}
                    }
                    boolean show=Config.on("ac_network_speed")&&awake&&root.isShown();network.setVisibility(show?View.VISIBLE:View.GONE);
                    long now=SystemClock.elapsedRealtime(),rx=TrafficStats.getTotalRxBytes(),tx=TrafficStats.getTotalTxBytes();
                    if(show){
                        float scale=root.getResources().getDisplayMetrics().density;
                        network.setX(Config.integer("ac_network_left",190,0,220)*scale);
                        network.setTextColor(clock==null?Color.WHITE:clock.getCurrentTextColor());
                        double delta=Math.max(1,now-lastTime)/1000.0;
                        network.setText(String.format(Locale.getDefault(),"↑ %.0f  ↓ %.0f KB/s",Math.max(0,tx-lastTx)/1024.0/delta,Math.max(0,rx-lastRx)/1024.0/delta));
                    }
                    lastRx=rx;lastTx=tx;lastTime=now;root.postDelayed(this,awake?1000:5000);
                }catch(Throwable t){Config.failure("status bar",t);}
            }
        });
    }
    private static void updateBar(View root){
        try{
            Float normal=bars.get(root);
            if(recentsHidden&&Config.on("ac_recents_hide_status")){
                if(normal==null)bars.put(root,((Number)Config.invoke(root,"getTransitionAlpha",new Class<?>[0])).floatValue());
                Config.invoke(root,"setTransitionAlpha",new Class<?>[]{float.class},0f);
            }else if(normal!=null){
                Config.invoke(root,"setTransitionAlpha",new Class<?>[]{float.class},normal);bars.put(root,null);
            }
        }catch(Throwable t){Config.failure("recents status visibility",t);}
    }
    private static TextView findClock(View root){
        if(root instanceof TextView && root.getClass().getSimpleName().contains("Clock"))return (TextView)root;
        if(root instanceof ViewGroup)for(int i=0;i<((ViewGroup)root).getChildCount();i++){
            TextView found=findClock(((ViewGroup)root).getChildAt(i));if(found!=null)return found;
        }
        return null;
    }

    private static final class Runtime {
        final Context c; final Handler handler = new Handler(Looper.getMainLooper());
        final WindowManager windows; final PowerManager power; final KeyguardManager keyguard;
        TextView info; ChargeArt art; Intent battery; long connectedAt; boolean plugged;
        Runtime(Context context) {
            c = context; windows = c.getSystemService(WindowManager.class);
            power = c.getSystemService(PowerManager.class); keyguard = c.getSystemService(KeyguardManager.class);
        }
        int dp(int v) { return Math.round(c.getResources().getDisplayMetrics().density * v); }
        void start() {
            IntentFilter filter = new IntentFilter(Intent.ACTION_BATTERY_CHANGED);
            filter.addAction(Intent.ACTION_SCREEN_ON); filter.addAction(Intent.ACTION_SCREEN_OFF);
            filter.addAction(Intent.ACTION_USER_PRESENT);filter.addAction(Config.PACKAGE+".RECENTS");
            c.registerReceiver(new BroadcastReceiver() {
                public void onReceive(Context context, Intent intent) {
                    if((Config.PACKAGE+".RECENTS").equals(intent.getAction())){
                        String[] packages=c.getPackageManager().getPackagesForUid(getSentFromUid());boolean allowed=false;
                        if(packages!=null)for(String pkg:packages)allowed|="com.sec.android.app.launcher".equals(pkg);
                        android.util.Log.d("ArtisanControl","Recents display: authorised="+allowed+", bars="+bars.size()+", hidden="+intent.getBooleanExtra("shown",false));
                        if(!allowed)return;
                        recentsHidden=intent.getBooleanExtra("shown",false);updateBars();return;
                    }
                    if(Intent.ACTION_SCREEN_OFF.equals(intent.getAction())){recentsHidden=false;updateBars();}
                    if (Intent.ACTION_BATTERY_CHANGED.equals(intent.getAction())) {
                        battery = intent;
                        boolean next = intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) != 0;
                        if (next && !plugged) connectedAt = SystemClock.elapsedRealtime();
                        plugged = next;
                    }
                    handler.removeCallbacks(tick); handler.post(tick);
                }
            }, filter,Context.RECEIVER_EXPORTED);
            c.getContentResolver().registerContentObserver(android.provider.Settings.Global.CONTENT_URI, true,
                new android.database.ContentObserver(handler) {
                    public void onChange(boolean self, android.net.Uri uri) {
                        if (uri != null && uri.getLastPathSegment() != null
                                && uri.getLastPathSegment().startsWith("ac_")) {
                            handler.removeCallbacks(tick); handler.postDelayed(tick, 550);
                            String key=uri.getLastPathSegment();
                            if("ac_hide_privacy".equals(key)||"ac_enabled".equals(key))handler.postDelayed(()->{
                                Object controller=privacyController.get();
                                if(controller!=null)try{Config.invoke(controller,"update$4$1",new Class<?>[0]);}
                                catch(Throwable t){Config.failure("privacy indicator refresh",t);}
                            },550);
                        }
                    }
                });
            handler.post(tick);
        }
        void updateBars(){for(View bar:bars.keySet())updateBar(bar);}
        String batteryText() {
            Intent state = c.registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
            if (state == null) state = battery;
            if (state == null) return "";
            float volts = state.getIntExtra(BatteryManager.EXTRA_VOLTAGE, 0) / 1000f;
            float temperature = state.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) / 10f;
            int raw = c.getSystemService(BatteryManager.class).getIntProperty(BatteryManager.BATTERY_PROPERTY_CURRENT_NOW);
            boolean valid = raw != Integer.MIN_VALUE && Math.abs((long)raw) < 20000000;
            float amps = valid ? Math.abs(raw / 1000000f) : 0;
            String values = valid ? String.format(Locale.getDefault(), "%.1f W · %.2f V · %.0f mA · %.1f °C",
                    volts * amps, volts, amps * 1000, temperature)
                    : String.format(Locale.getDefault(), "%.2f V · %.1f °C", volts, temperature);
            return "Batarya · " + values;
        }
        void add(View view, int height, int gravity, int y) {
            WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                    WindowManager.LayoutParams.MATCH_PARENT, height, 2006,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                    | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED,
                    android.graphics.PixelFormat.TRANSLUCENT);
            params.gravity = gravity; params.y = y; params.setTitle("ArtisanControl charging");
            windows.addView(view, params);
        }
        void remove(View view) {
            if (view != null) try { windows.removeView(view); } catch (RuntimeException ignored) {}
        }
        final Runnable tick = new Runnable() {
            public void run() {
                try {
                    updateBars();
                    boolean awake = power.isInteractive();
                    boolean visible = Config.enabled() && plugged && awake && keyguard.isKeyguardLocked();
                    if (visible && Config.on("ac_charge_info")) {
                        int bottom=dp(Config.integer("ac_charge_bottom", 175, 80, 500));
                        if (info == null) {
                            info = new TextView(c); info.setTextSize(13); info.setTextColor(Color.WHITE);
                            info.setGravity(Gravity.CENTER); info.setShadowLayer(6, 0, 2, Color.BLACK);
                            add(info, dp(44), Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL, bottom);
                        } else {
                            WindowManager.LayoutParams params=(WindowManager.LayoutParams)info.getLayoutParams();
                            if(params.y!=bottom){params.y=bottom;windows.updateViewLayout(info,params);}
                        }
                        info.setText(batteryText());
                    } else { remove(info); info = null; }
                    int style = Config.integer("ac_charge_animation", 0, 0, 2);
                    long expires=connectedAt+Config.integer("ac_charge_animation_seconds", 6, 2, 15)*1000L;
                    boolean animate = visible && style != 0 && SystemClock.elapsedRealtime()<expires;
                    if (animate) {
                        if (art == null) { art = new ChargeArt(c); add(art, WindowManager.LayoutParams.MATCH_PARENT, Gravity.TOP, 0); }
                        art.style = style; art.invalidate();
                    } else { remove(art); art = null; }
                    if (awake && plugged) {
                        long delay=Config.integer("ac_charge_interval", 2000, 500, 30000);
                        if(animate)delay=Math.min(delay,Math.max(1,expires-SystemClock.elapsedRealtime()));
                        handler.postDelayed(this,delay);
                    }
                } catch (Throwable t) {
                    remove(info); remove(art); info = null; art = null;
                    Config.failure("charging display", t);
                }
            }
        };
    }

    private static final class ChargeArt extends View {
        final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG); final Path path = new Path(); int style;
        final long start = SystemClock.uptimeMillis();
        ChargeArt(Context c) { super(c); }
        protected void onDraw(Canvas canvas) {
            float seconds = (SystemClock.uptimeMillis() - start) / 1000f;
            float w = getWidth(), h = getHeight();
            paint.setColor(0xff7be9d0); paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(3);
            if (style == 1) {
                for (int i = 0; i < 4; i++) {
                    float progress = (seconds * 0.35f + i / 4f) % 1f;
                    paint.setAlpha((int)((1f - progress) * 130));
                    canvas.drawCircle(w / 2, h * 0.73f, w * 0.6f * progress, paint);
                }
            } else {
                for (int line = 0; line < 3; line++) {
                    path.reset(); paint.setAlpha(70 + line * 30);
                    for (int x = 0; x <= w; x += 8) {
                        float y = h * 0.79f + (float)Math.sin(x / w * Math.PI * 3 + seconds * 2 + line) * 38 + line * 15;
                        if (x == 0) path.moveTo(x, y); else path.lineTo(x, y);
                    }
                    canvas.drawPath(path, paint);
                }
            }
            if (isAttachedToWindow()) postInvalidateDelayed(33);
        }
    }
}
