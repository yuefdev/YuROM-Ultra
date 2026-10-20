// SPDX-License-Identifier: GPL-3.0-or-later
package com.android.settings.artisan;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioDeviceInfo;
import android.media.AudioManager;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

/** Uses the system media strategy, rather than the unrelated speakerphone/call route. */
public final class MediaOutput {
    private final AudioManager audio;
    private final Object strategy;
    private final Class<?> strategyType, deviceType;
    private final AudioAttributes attributes=new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).build();

    public static final class State {
        public final List<AudioDeviceInfo> outputs, routed;
        public final int selected;
        private final List<?> preferred;
        State(List<AudioDeviceInfo> outputs,List<AudioDeviceInfo> routed,List<?> preferred,int selected){
            this.outputs=outputs;this.routed=routed;this.preferred=preferred;this.selected=selected;
        }
        public String actual(){
            List<String> names=new ArrayList<>();for(AudioDeviceInfo device:routed)names.add(label(device));
            return names.isEmpty()?"Yönlendirme bekleniyor":String.join(", ",names);
        }
    }

    public MediaOutput(Context context)throws Exception{
        audio=context.getSystemService(AudioManager.class);
        if(audio==null)throw new IllegalStateException("Ses hizmeti kullanılamıyor");
        strategyType=Class.forName("android.media.audiopolicy.AudioProductStrategy");
        deviceType=Class.forName("android.media.AudioDeviceAttributes");
        strategy=invoke(strategyType.getMethod("getAudioProductStrategyForAudioAttributes",AudioAttributes.class,boolean.class),null,attributes,false);
        if(strategy==null)throw new IllegalStateException("Medya ses stratejisi bulunamadı");
        int stream=(Integer)invoke(strategyType.getMethod("getLegacyStreamTypeForAudioAttributes",AudioAttributes.class),strategy,attributes);
        if(stream!=AudioManager.STREAM_MUSIC)throw new IllegalStateException("Beklenmeyen medya ses stratejisi");
    }
    public AudioManager manager(){return audio;}
    private static Object invoke(Method method,Object receiver,Object...args)throws Exception{
        try{return method.invoke(receiver,args);}catch(InvocationTargetException error){
            Throwable cause=error.getCause();if(cause instanceof Exception)throw (Exception)cause;throw error;
        }
    }
    private Object api(String method,Class<?>[] types,Object...args)throws Exception{
        return invoke(AudioManager.class.getMethod(method,types),audio,args);
    }
    private static boolean same(AudioDeviceInfo first,AudioDeviceInfo second){
        return first.getType()==second.getType()&&first.getAddress().equals(second.getAddress());
    }
    private boolean matches(Object preferred,AudioDeviceInfo device)throws Exception{
        return (Integer)invoke(deviceType.getMethod("getType"),preferred)==device.getType()
                &&device.getAddress().equals(invoke(deviceType.getMethod("getAddress"),preferred));
    }
    private static boolean selectable(AudioDeviceInfo device){
        if(!device.isSink())return false;
        switch(device.getType()){
            case AudioDeviceInfo.TYPE_BUILTIN_SPEAKER:case AudioDeviceInfo.TYPE_WIRED_HEADSET:
            case AudioDeviceInfo.TYPE_WIRED_HEADPHONES:case AudioDeviceInfo.TYPE_BLUETOOTH_A2DP:
            case AudioDeviceInfo.TYPE_HDMI:case AudioDeviceInfo.TYPE_HDMI_ARC:case AudioDeviceInfo.TYPE_HDMI_EARC:
            case AudioDeviceInfo.TYPE_USB_DEVICE:case AudioDeviceInfo.TYPE_USB_HEADSET:
            case AudioDeviceInfo.TYPE_LINE_ANALOG:case AudioDeviceInfo.TYPE_LINE_DIGITAL:
            case AudioDeviceInfo.TYPE_BLE_HEADSET:case AudioDeviceInfo.TYPE_BLE_SPEAKER:
            case AudioDeviceInfo.TYPE_BLE_BROADCAST:case AudioDeviceInfo.TYPE_HEARING_AID:return true;
            default:return false;
        }
    }
    public State snapshot()throws Exception{
        List<AudioDeviceInfo> outputs=new ArrayList<>();
        for(AudioDeviceInfo device:audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS))if(selectable(device))outputs.add(device);
        List<?> preferred=(List<?>)api("getPreferredDevicesForStrategy",new Class<?>[]{strategyType},strategy);
        List<AudioDeviceInfo> routed=new ArrayList<>();
        for(Object device:(List<?>)api("getAudioDevicesForAttributes",new Class<?>[]{AudioAttributes.class},attributes))routed.add((AudioDeviceInfo)device);
        int selected=preferred.isEmpty()?0:-1;
        if(preferred.size()==1)for(int i=0;i<outputs.size();i++)if(matches(preferred.get(0),outputs.get(i)))selected=i+1;
        return new State(outputs,routed,preferred,selected);
    }
    private boolean set(List<?> preferred)throws Exception{
        return preferred.isEmpty()?(Boolean)api("removePreferredDeviceForStrategy",new Class<?>[]{strategyType},strategy)
                :(Boolean)api("setPreferredDevicesForStrategy",new Class<?>[]{strategyType,List.class},strategy,preferred);
    }
    public State select(AudioDeviceInfo requested)throws Exception{
        State previous=snapshot();AudioDeviceInfo target=null;
        if(requested!=null){
            for(AudioDeviceInfo connected:previous.outputs)if(connected.getId()==requested.getId()&&same(connected,requested))target=connected;
            if(target==null)throw new IllegalStateException("Seçilen ses çıkışının bağlantısı kesildi. Listeyi yenile.");
        }else if(previous.preferred.isEmpty())return previous;
        List<Object> preferred=new ArrayList<>();
        if(target!=null)preferred.add(deviceType.getConstructor(AudioDeviceInfo.class).newInstance(target));
        if(!set(preferred))throw new IllegalStateException("Sistem ses çıkışı tercihini kabul etmedi");
        try{
            for(int attempt=0;attempt<20;attempt++){
                State current=snapshot();boolean verified=target==null?current.preferred.isEmpty():
                        current.preferred.size()==1&&matches(current.preferred.get(0),target);
                if(target!=null){boolean routed=false;for(AudioDeviceInfo device:current.routed)routed|=same(device,target);verified&=routed;}
                if(verified)return current;
                Thread.sleep(100);
            }
            throw new IllegalStateException("Seçim uygulandı ancak medya bu çıkışa yönlenmedi; önceki tercih geri yükleniyor.");
        }catch(Exception error){
            if(!set(previous.preferred))throw new IllegalStateException("Ses yönlendirmesi doğrulanamadı; Otomatik seçeneğiyle tercihi temizle.",error);
            throw error;
        }
    }
    public static String label(AudioDeviceInfo device){
        String type;
        switch(device.getType()){
            case AudioDeviceInfo.TYPE_BUILTIN_SPEAKER:return "Telefon hoparlörü";
            case AudioDeviceInfo.TYPE_HDMI:case AudioDeviceInfo.TYPE_HDMI_ARC:case AudioDeviceInfo.TYPE_HDMI_EARC:type="TV / HDMI / DisplayPort";break;
            case AudioDeviceInfo.TYPE_USB_DEVICE:case AudioDeviceInfo.TYPE_USB_HEADSET:type="USB ses";break;
            case AudioDeviceInfo.TYPE_BLUETOOTH_A2DP:case AudioDeviceInfo.TYPE_BLE_HEADSET:
            case AudioDeviceInfo.TYPE_BLE_SPEAKER:case AudioDeviceInfo.TYPE_BLE_BROADCAST:type="Bluetooth";break;
            case AudioDeviceInfo.TYPE_WIRED_HEADSET:case AudioDeviceInfo.TYPE_WIRED_HEADPHONES:type="Kablolu kulaklık";break;
            case AudioDeviceInfo.TYPE_HEARING_AID:type="İşitme cihazı";break;
            default:type="Ses çıkışı";
        }
        String name=String.valueOf(device.getProductName()).trim();
        return name.isEmpty()||name.matches("[0-9]+")||"null".equals(name)?type:type+" — "+name;
    }
}
