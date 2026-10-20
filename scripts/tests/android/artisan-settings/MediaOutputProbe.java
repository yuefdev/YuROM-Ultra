// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.tests;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioDeviceInfo;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioTrack;
import android.os.Looper;
import com.android.settings.artisan.MediaOutput;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import org.json.JSONArray;
import org.json.JSONObject;

/** Executes the installed Settings implementation and an actual silent media track. */
public final class MediaOutputProbe {
    private static boolean same(AudioDeviceInfo a,AudioDeviceInfo b){return a==b||a!=null&&b!=null&&a.getType()==b.getType()&&a.getAddress().equals(b.getAddress());}
    private static JSONObject describe(MediaOutput.State state)throws Exception{
        JSONArray devices=new JSONArray();for(AudioDeviceInfo device:state.outputs)devices.put(new JSONObject().put("id",device.getId()).put("type",device.getType()).put("label",MediaOutput.label(device)));
        return new JSONObject().put("selected",state.selected).put("actual",state.actual()).put("devices",devices);
    }
    public static void main(String[] args)throws Exception{
        Thread.setDefaultUncaughtExceptionHandler((thread,error)->{error.printStackTrace();System.exit(1);});
        if(args.length<1||args.length>2)throw new IllegalArgumentException("Usage: MediaOutputProbe RESULT [CONNECTED_DEVICE_ID]");
        Looper.prepareMainLooper();Class<?> at=Class.forName("android.app.ActivityThread");
        Context context=(Context)at.getMethod("getSystemContext").invoke(at.getMethod("systemMain").invoke(null));
        MediaOutput output=new MediaOutput(context);AudioManager audio=output.manager();MediaOutput.State initial=output.snapshot();
        if(initial.selected<0)throw new IllegalStateException("Preserve the existing multi-device preference; test requires automatic or one connected output");
        AudioDeviceInfo restore=initial.selected==0?null:initial.outputs.get(initial.selected-1),target=null,invalid=null;
        for(AudioDeviceInfo device:audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS)){
            if((args.length==2&&device.getId()==Integer.parseInt(args[1]))||(args.length==1&&device.getType()==AudioDeviceInfo.TYPE_BUILTIN_SPEAKER))target=device;
            if(device.getType()==AudioDeviceInfo.TYPE_BUILTIN_EARPIECE)invalid=device;
        }
        if(target==null)throw new IllegalStateException("Requested physical output is not connected");
        int mode=audio.getMode();AudioDeviceInfo communication=audio.getCommunicationDevice();
        JSONObject result=new JSONObject().put("initial",describe(initial));AudioTrack track=null;
        try{
            MediaOutput.State selected=output.select(target);result.put("selected",describe(selected));
            int minimum=AudioTrack.getMinBufferSize(48000,AudioFormat.CHANNEL_OUT_STEREO,AudioFormat.ENCODING_PCM_16BIT);
            track=new AudioTrack.Builder().setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).build())
                    .setAudioFormat(new AudioFormat.Builder().setSampleRate(48000).setChannelMask(AudioFormat.CHANNEL_OUT_STEREO).setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
                    .setBufferSizeInBytes(Math.max(minimum*2,8192)).setTransferMode(AudioTrack.MODE_STREAM).build();
            track.play();byte[] silence=new byte[4096];
            for(int i=0;i<20;i++)if(track.write(silence,0,silence.length)<0)throw new AssertionError("PCM write failed");
            if(!same(track.getRoutedDevice(),target))throw new AssertionError("Active media track did not use the selected device");
            result.put("active_track_device_id",track.getRoutedDevice().getId()).put("active_track_route_verified",true);
            if(invalid!=null){
                try{output.select(invalid);throw new AssertionError("Call-only earpiece was accepted for media");}
                catch(IllegalStateException expected){result.put("non_media_output_rejected",true);}
                if(output.snapshot().selected!=selected.selected)throw new AssertionError("Rejected selection changed the preference");
            }
            result.put("automatic",describe(output.select(null)));
            if(audio.getMode()!=mode||!same(audio.getCommunicationDevice(),communication))throw new AssertionError("Call routing changed");
            result.put("call_route_unchanged",true).put("status","pass");
        }finally{
            if(track!=null){track.stop();track.release();}
            result.put("restored",describe(output.select(restore)));
            Files.write(Paths.get(args[0]),result.toString(2).getBytes(StandardCharsets.UTF_8));
        }
        System.out.println(result);System.exit(0);
    }
}
