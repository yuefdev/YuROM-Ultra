// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control.probe;
import android.app.Service;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Intent;
import android.os.IBinder;
import android.os.Handler;
import android.os.Looper;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.hardware.display.VirtualDisplay;
import android.hardware.display.DisplayManager;
import android.media.ImageReader;
import android.graphics.PixelFormat;

/** Creates a transient projection surface without storing any captured frame. */
public final class ProjectionProbe extends Service {
    private MediaProjection projection;
    private VirtualDisplay display;
    private ImageReader images;
    public IBinder onBind(Intent intent){return null;}
    public int onStartCommand(Intent intent,int flags,int id){
        NotificationManager manager=getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("projection","Artisan projection probe",NotificationManager.IMPORTANCE_LOW));
        startForeground(91,new Notification.Builder(this,"projection").setSmallIcon(android.R.drawable.ic_menu_view).setContentTitle("Artisan projection probe").build());
        projection=getSystemService(MediaProjectionManager.class).getMediaProjection(intent.getIntExtra("result_code",0),intent.getParcelableExtra("result_data",Intent.class));
        projection.registerCallback(new MediaProjection.Callback(){public void onStop(){stopSelf();}},new Handler(Looper.getMainLooper()));
        images=ImageReader.newInstance(320,640,PixelFormat.RGBA_8888,2);
        images.setOnImageAvailableListener(reader->{try(android.media.Image image=reader.acquireLatestImage()){}},new Handler(Looper.getMainLooper()));
        display=projection.createVirtualDisplay("Artisan test projection",320,640,160,DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,images.getSurface(),null,null);
        return START_NOT_STICKY;
    }
    public void onDestroy(){if(display!=null)display.release();if(images!=null)images.close();if(projection!=null)projection.stop();super.onDestroy();}
}
