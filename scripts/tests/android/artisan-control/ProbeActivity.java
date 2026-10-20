// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control.probe;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.RemoteInput;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.WindowManager;
import android.widget.TextView;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import org.json.JSONObject;

/** Own-app secure surface and observable framework regression fixture. */
public final class ProbeActivity extends Activity {
    private final JSONObject result=new JSONObject();
    private android.media.MediaPlayer player;
    private android.media.session.MediaSession session;
    private android.media.AudioRecord microphone;
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        if(getIntent().getBooleanExtra("secure",true))getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        TextView view=new TextView(this);view.setBackgroundColor(0xffffc44b);view.setTextColor(0xff121621);
        view.setGravity(android.view.Gravity.CENTER);view.setTextSize(24);view.setText("ARTISAN\nSECURE CAPTURE PROBE");setContentView(view);
        try{
            result.put("model",Build.MODEL);
            result.put("manufacturer",Build.MANUFACTURER);result.put("brand",Build.BRAND);result.put("device",Build.DEVICE);
            result.put("product",Build.PRODUCT);result.put("fingerprint",Build.FINGERPRINT);
            result.put("call_launch",getIntent().getBooleanExtra("call_launch",false));
            result.put("ringer_mode",getSystemService(android.media.AudioManager.class).getRingerMode());
            result.put("developer",Settings.Global.getInt(getContentResolver(),"development_settings_enabled",-1));
            result.put("adb",Settings.Global.getInt(getContentResolver(),"adb_enabled",-1));
            boolean found;
            String target=getIntent().getStringExtra("target_package");if(target==null)target="com.android.settings";
            final String selected=target;result.put("target_package",target);
            try{getPackageManager().getPackageInfo(target,0);found=true;}catch(android.content.pm.PackageManager.NameNotFoundException e){found=false;}
            result.put("control_package_visible",found);
            result.put("control_listed",getPackageManager().getInstalledPackages(0).stream().anyMatch(p->p.packageName.equals(selected)));
            int uid=getIntent().getIntExtra("control_uid",-1);
            if(uid<0)uid=getPackageManager().getApplicationInfo(target,0).uid;
            result.put("control_uid",uid);
            String[] packages=getPackageManager().getPackagesForUid(uid);
            result.put("control_uid_listed",packages!=null&&java.util.Arrays.asList(packages).contains(selected));
            Intent launcher=new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER).setPackage(target);
            result.put("control_resolved",getPackageManager().queryIntentActivities(launcher,0).stream()
                    .anyMatch(p->p.activityInfo!=null&&p.activityInfo.packageName.equals(selected)));
            result.put("control_resolved_flags",getPackageManager().queryIntentActivities(launcher,android.content.pm.PackageManager.ResolveInfoFlags.of(0)).stream()
                    .anyMatch(p->p.activityInfo!=null&&p.activityInfo.packageName.equals(selected)));
            registerScreenCaptureCallback(getMainExecutor(),()->{
                try{result.put("capture_count",result.optInt("capture_count",0)+1);save();}catch(Exception e){throw new RuntimeException(e);}
            });
            result.put("capture_registered",true);
            int recording=getWindowManager().addScreenRecordingCallback(getMainExecutor(),value->{
                try{result.put("recording_callback",value);save();}catch(Exception e){throw new RuntimeException(e);}
            });
            result.put("recording_initial",recording);
            launcherModels();
            if(getIntent().getBooleanExtra("notification",false))notification(this,false);
            if(getIntent().getBooleanExtra("call",false))notification(this,true);
            if(getIntent().getBooleanExtra("media",false))media();
            if(getIntent().getBooleanExtra("projection",false))startActivityForResult(getSystemService(android.media.projection.MediaProjectionManager.class).createScreenCaptureIntent(),91);
            if(getIntent().getBooleanExtra("microphone",false)){
                int size=android.media.AudioRecord.getMinBufferSize(8000,android.media.AudioFormat.CHANNEL_IN_MONO,android.media.AudioFormat.ENCODING_PCM_16BIT);
                microphone=new android.media.AudioRecord(android.media.MediaRecorder.AudioSource.MIC,8000,
                        android.media.AudioFormat.CHANNEL_IN_MONO,android.media.AudioFormat.ENCODING_PCM_16BIT,Math.max(16000,size));
                microphone.startRecording();result.put("microphone_active",microphone.getRecordingState()==android.media.AudioRecord.RECORDSTATE_RECORDING);
            }
            save();
        }catch(Exception e){try{result.put("error",e.toString());save();}catch(Exception ignored){}}
    }
    private void save()throws Exception{Files.write(new java.io.File(getFilesDir(),"result.json").toPath(),result.toString(2).getBytes(StandardCharsets.UTF_8));}
    private void launcherModels(){
        try{
            android.content.pm.ApplicationInfo launcher=getPackageManager().getApplicationInfo("com.sec.android.app.launcher",0);
            ClassLoader loader=new dalvik.system.PathClassLoader(launcher.sourceDir,getClassLoader());
            Class<?> grid=loader.loadClass("com.honeyspace.sdk.source.HomeUpDataSource$WorkspaceGrid");
            Object instance=grid.getConstructor(android.graphics.Point.class).newInstance(new android.graphics.Point(4,5));
            android.graphics.Point selected=(android.graphics.Point)grid.getMethod("getGrid").invoke(instance);
            result.put("home_grid",selected.x+"x"+selected.y);
            Class<?> apps=loader.loadClass("com.honeyspace.sdk.source.HomeUpDataSource$ApplistGrid");
            Object appGrid=apps.getConstructor(android.graphics.Point.class).newInstance(new android.graphics.Point(4,6));
            android.graphics.Point appSelected=(android.graphics.Point)apps.getMethod("getGrid").invoke(appGrid);
            result.put("apps_grid",appSelected.x+"x"+appSelected.y);
            Class<?> task=loader.loadClass("com.honeyspace.sdk.source.HomeUpDataSource$TaskChangerData");
            Object model=task.getConstructor().newInstance();
            result.put("recents_enabled",task.getMethod("getEnabled").invoke(model));
            result.put("recents_layout",task.getMethod("getLayoutType").invoke(model));
            java.io.File requests=new java.io.File(getFilesDir(),"home-requests.json");
            if(getIntent().getBooleanExtra("home_details",false)&&requests.isFile()){
                org.json.JSONArray selectedMethods=new org.json.JSONArray(new String(Files.readAllBytes(requests.toPath()),StandardCharsets.UTF_8));
                JSONObject details=new JSONObject();
                for(int i=0;i<selectedMethods.length();i++){
                    JSONObject request=selectedMethods.getJSONObject(i);
                    String name=request.getString("class"),method=request.getString("method");
                    if(!name.startsWith("com.honeyspace.sdk.source.HomeUpDataSource$"))throw new IllegalArgumentException("Unexpected fixture model");
                    Class<?> type=loader.loadClass(name);Object target;
                    try{target=type.getConstructor().newInstance();}
                    catch(NoSuchMethodException e){target=type.getConstructor(android.graphics.Point.class).newInstance(new android.graphics.Point(4,5));}
                    Object value=type.getMethod(method).invoke(target);
                    if(value instanceof android.graphics.Point){android.graphics.Point point=(android.graphics.Point)value;value=point.x+"x"+point.y;}
                    details.put(request.getString("key"),value);
                }
                result.put("home_details",details);
            }
        }catch(Throwable t){try{result.put("launcher_error",t.toString());}catch(Exception ignored){}}
    }
    private static void notification(Context context,boolean call){
        NotificationManager manager=context.getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("regression","Artisan regression",NotificationManager.IMPORTANCE_HIGH));
        PendingIntent reply=PendingIntent.getBroadcast(context,1,new Intent(context,Reply.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_MUTABLE);
        Notification.Builder builder=new Notification.Builder(context,"regression").setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(call?"Artisan test call":"Artisan test notification").setContentText("Own-app regression fixture")
                .setStyle(new Notification.BigTextStyle().bigText("Expanded own-app notification. Inline reply exercises the lock-screen reply path."))
                .addAction(new Notification.Action.Builder(null,"Yanıtla",reply).addRemoteInput(new RemoteInput.Builder("text").setLabel("Test yanıtı").build()).build());
        if(call){PendingIntent full=PendingIntent.getActivity(context,2,new Intent(context,ProbeActivity.class).putExtra("call_launch",true).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
            builder.setCategory(Notification.CATEGORY_CALL).setFullScreenIntent(full,true);}
        manager.notify(call?2:1,builder.build());
    }
    private void media()throws Exception{
        java.nio.ByteBuffer wave=java.nio.ByteBuffer.allocate(16044).order(java.nio.ByteOrder.LITTLE_ENDIAN);
        wave.put("RIFF".getBytes(StandardCharsets.US_ASCII)).putInt(16036).put("WAVEfmt ".getBytes(StandardCharsets.US_ASCII))
                .putInt(16).putShort((short)1).putShort((short)1).putInt(8000).putInt(16000).putShort((short)2).putShort((short)16)
                .put("data".getBytes(StandardCharsets.US_ASCII)).putInt(16000);
        java.io.File file=new java.io.File(getFilesDir(),"silence.wav");Files.write(file.toPath(),wave.array());
        session=new android.media.session.MediaSession(this,"Artisan regression");
        session.setCallback(new android.media.session.MediaSession.Callback(){
            public boolean onMediaButtonEvent(Intent intent){
                android.view.KeyEvent key=intent.getParcelableExtra(Intent.EXTRA_KEY_EVENT,android.view.KeyEvent.class);
                if(key!=null && key.getAction()==android.view.KeyEvent.ACTION_DOWN)try{result.put("media_key",key.getKeyCode());save();}catch(Exception e){throw new RuntimeException(e);}
                return true;
            }
        });
        session.setPlaybackState(new android.media.session.PlaybackState.Builder().setActions(android.media.session.PlaybackState.ACTION_SKIP_TO_NEXT
                |android.media.session.PlaybackState.ACTION_SKIP_TO_PREVIOUS|android.media.session.PlaybackState.ACTION_PLAY_PAUSE|android.media.session.PlaybackState.ACTION_STOP)
                .setState(android.media.session.PlaybackState.STATE_PLAYING,0,1).build());session.setActive(true);
        player=new android.media.MediaPlayer();player.setDataSource(file.getAbsolutePath());player.setLooping(true);player.prepare();player.start();
    }
    @Override public void onDestroy(){if(player!=null)player.release();if(session!=null)session.release();if(microphone!=null){microphone.stop();microphone.release();}super.onDestroy();}
    @Override public void onActivityResult(int request,int code,Intent data){
        super.onActivityResult(request,code,data);
        if(request==91&&code==RESULT_OK&&data!=null)startForegroundService(new Intent(this,ProjectionProbe.class).putExtra("result_code",code).putExtra("result_data",data));
    }
    public static final class Reply extends BroadcastReceiver{
        public void onReceive(Context c,Intent intent){try{Files.write(new java.io.File(c.getFilesDir(),"reply-received").toPath(),new byte[]{1});}catch(Exception e){throw new RuntimeException(e);}}
    }
    public static final class Emitter extends BroadcastReceiver{
        public void onReceive(Context c,Intent intent){
            if(intent.hasExtra("ringer_mode")){c.getSystemService(android.media.AudioManager.class).setRingerMode(intent.getIntExtra("ringer_mode",2));return;}
            if(intent.getBooleanExtra("stop_projection",false)){c.stopService(new Intent(c,ProjectionProbe.class));return;}
            if(intent.getBooleanExtra("cancel",false)){c.getSystemService(NotificationManager.class).cancelAll();return;}notification(c,intent.getBooleanExtra("call",false));
        }
    }
}
