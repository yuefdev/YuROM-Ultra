// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.tests;

import android.app.UiAutomation;
import android.os.Bundle;
import android.os.HandlerThread;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.zip.ZipFile;
import org.json.JSONArray;
import org.json.JSONObject;

/** Root app_process acceptance runner driving the real Settings preference widgets. */
public final class NativeSettingsProbe {
    private static UiAutomation ui;
    private static Path output;
    private static JSONArray catalogue;
    private static final JSONObject results=new JSONObject();
    private static byte[] command(String... args)throws Exception{
        Process p=new ProcessBuilder(args).redirectErrorStream(true).start();
        ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buffer=new byte[8192];int n;
        try(InputStream in=p.getInputStream()){while((n=in.read(buffer))!=-1)out.write(buffer,0,n);}
        if(p.waitFor()!=0)throw new IllegalStateException(new String(out.toByteArray(),StandardCharsets.UTF_8));
        return out.toByteArray();
    }
    private static String shell(String text)throws Exception{return new String(command("sh","-c",text),StandardCharsets.UTF_8).trim();}
    private static void pause(long ms)throws Exception{Thread.sleep(ms);}
    private static String read(JSONObject f)throws Exception{return shell("settings get "+f.optString("namespace","global")+" "+f.getString("key"));}
    private static void restore(JSONObject f,String value)throws Exception{
        shell("settings "+("null".equals(value)?"delete ":"put ")+f.optString("namespace","global")+" "+f.getString("key")
                +("null".equals(value)?"":" '"+value.replace("'","'\\''")+"'"));
    }
    private static AccessibilityNodeInfo root()throws Exception{
        for(int i=0;i<20;i++){AccessibilityNodeInfo node=ui.getRootInActiveWindow();if(node!=null)return node;pause(100);}
        throw new IllegalStateException("No active accessibility window");
    }
    private static AccessibilityNodeInfo exact(AccessibilityNodeInfo node,String text){
        if(text.contentEquals(node.getText()==null?"":node.getText()))return node;
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i);if(child!=null){AccessibilityNodeInfo found=exact(child,text);if(found!=null)return found;}}
        return null;
    }
    private static AccessibilityNodeInfo kind(AccessibilityNodeInfo node,String type){
        if(type.contentEquals(node.getClassName()==null?"":node.getClassName()))return node;
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i);if(child!=null){AccessibilityNodeInfo found=kind(child,type);if(found!=null)return found;}}
        return null;
    }
    private static AccessibilityNodeInfo scroller(AccessibilityNodeInfo node){
        if(node.isScrollable())return node;
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo child=node.getChild(i);if(child!=null){AccessibilityNodeInfo found=scroller(child);if(found!=null)return found;}}
        return null;
    }
    private static AccessibilityNodeInfo find(String label)throws Exception{
        long deadline=android.os.SystemClock.uptimeMillis()+10000;
        do{
            for(int direction:new int[]{AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD,AccessibilityNodeInfo.ACTION_SCROLL_FORWARD}){
                for(int i=0;i<16;i++){
                    AccessibilityNodeInfo tree=root(),found=exact(tree,label);if(found!=null)return found;
                    AccessibilityNodeInfo scroll=scroller(tree);if(scroll==null || !scroll.performAction(direction))break;pause(120);
                }
            }
            pause(100);
        }while(android.os.SystemClock.uptimeMillis()<deadline);
        throw new IllegalStateException("Preference not visible: "+label);
    }
    private static void click(AccessibilityNodeInfo node)throws Exception{
        while(node!=null && !node.isClickable())node=node.getParent();
        if(node==null || !node.isEnabled() || !node.performAction(AccessibilityNodeInfo.ACTION_CLICK))throw new IllegalStateException("Control is not clickable");
        pause(180);
    }
    private static void back()throws Exception{ui.performGlobalAction(1);pause(180);}
    private static void open(String section)throws Exception{
        shell("input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard; cmd statusbar collapse; am force-stop com.android.settings; am start -W -n com.android.settings/.SubSettings --es :settings:show_fragment com.android.settings.artisan.ArtisanSettings");
        pause(350);click(find(section));find(section);
    }
    private static void expect(JSONObject f,String expected)throws Exception{
        for(int i=0;i<20;i++){if(expected.equals(read(f)))return;pause(80);}
        throw new AssertionError(f.getString("key")+": expected "+expected+", found "+read(f));
    }
    private static void edit(JSONObject f,String value,boolean valid)throws Exception{
        String before=read(f);click(find(f.getString("label")));
        AccessibilityNodeInfo input=kind(root(),"android.widget.EditText");if(input==null)throw new AssertionError("Editor not shown");
        Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);
        if(!input.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args))throw new AssertionError("Text could not be set");
        click(find("Kaydet"));
        if(valid){expect(f,value);if(exact(root(),"İşlem uygulanamadı")!=null)throw new AssertionError("Valid value rejected");}
        else{if(exact(root(),"İşlem uygulanamadı")==null)throw new AssertionError("Invalid value accepted");expect(f,before);click(find("Tamam"));}
    }
    private static void audioOutput(JSONArray checks)throws Exception{
        if(Looper.myLooper()==null)Looper.prepareMainLooper();
        Class<?> threadType=Class.forName("android.app.ActivityThread"),strategyType=Class.forName("android.media.audiopolicy.AudioProductStrategy");
        android.content.Context context=(android.content.Context)threadType.getMethod("getSystemContext").invoke(threadType.getMethod("systemMain").invoke(null));
        android.media.AudioManager audio=context.getSystemService(android.media.AudioManager.class);
        android.media.AudioAttributes attributes=new android.media.AudioAttributes.Builder().setUsage(android.media.AudioAttributes.USAGE_MEDIA).build();
        Object strategy=strategyType.getMethod("getAudioProductStrategyForAudioAttributes",android.media.AudioAttributes.class,boolean.class).invoke(null,attributes,false);
        java.lang.reflect.Method get=android.media.AudioManager.class.getMethod("getPreferredDevicesForStrategy",strategyType);
        List<?> original=new ArrayList<>((List<?>)get.invoke(audio,strategy));
        try{
            find("Medya ses çıkışı");find("Otomatik (sistem)");find("Telefon hoparlörü");find("Yenile");
            click(find("Telefon hoparlörü"));boolean selected=false;
            for(int i=0;i<30;i++){
                List<?> preferred=(List<?>)get.invoke(audio,strategy);
                if(preferred.size()==1&&(Integer)preferred.get(0).getClass().getMethod("getType").invoke(preferred.get(0))==2){selected=true;break;}
                pause(100);
            }
            if(!selected)throw new AssertionError("Settings UI did not set the real media strategy preference");
            find("Şu an medya: Telefon hoparlörü");checks.put("real Settings UID selected speaker in native media strategy");
            click(find("Otomatik (sistem)"));boolean cleared=false;
            for(int i=0;i<30;i++){if(((List<?>)get.invoke(audio,strategy)).isEmpty()){cleared=true;break;}pause(100);}
            if(!cleared)throw new AssertionError("Automatic did not remove the native media preference");
            find("Şu an medya: Telefon hoparlörü");click(find("Kapat"));checks.put("automatic removed preference; actual output displayed");
        }finally{
            if(original.isEmpty())android.media.AudioManager.class.getMethod("removePreferredDeviceForStrategy",strategyType).invoke(audio,strategy);
            else android.media.AudioManager.class.getMethod("setPreferredDevicesForStrategy",strategyType,List.class).invoke(audio,strategy,original);
        }
    }
    private static void feature(JSONObject f)throws Exception{
        String key=f.getString("key"),type=f.getString("type"),original=read(f);JSONArray checks=new JSONArray();
        try{
            if("bool".equals(type)){
                for(int i=0;i<2;i++){String before=read(f),effective="null".equals(before)?f.optString("default","0"):before;
                    click(find(f.getString("label")));String after="1".equals(effective)?"0":"1";expect(f,after);checks.put(after);}
            }else if("choice".equals(type)){
                JSONObject choices=f.getJSONObject("choices");java.util.Iterator<String> keys=choices.keys();
                while(keys.hasNext()){String value=keys.next();click(find(f.getString("label")));click(find(choices.getString(value)));expect(f,value);checks.put(value);}
            }else if("number".equals(type)||"decimal".equals(type)){
                for(String name:new String[]{"min","max"}){String value=f.get(name).toString();edit(f,value,true);checks.put(value);}
                edit(f,Double.toString(f.getDouble("min")-1),false);edit(f,Double.toString(f.getDouble("max")+1),false);checks.put("out-of-range rejected");
                if("number".equals(type)){edit(f,"0.5",false);checks.put("fraction rejected");}
            }else if("packages".equals(type)){
                click(find(f.getString("label")));find("Kaydet");back();checks.put("installed-app picker opens and cancels");
            }else if("profiles".equals(type)){
                edit(f,"{\"com.artisanrom.control.probe\":{\"MODEL\":\"ArtisanAcceptanceModel\"}}",true);
                edit(f,"{}",true);edit(f,"{\"invalid\":{}}",false);checks.put("valid profiles saved; malformed profile rejected");
            }else if("colour".equals(type)){
                edit(f,"#23ABCD",true);edit(f,"",true);edit(f,"not-a-colour",false);checks.put("valid/empty colours saved; invalid rejected");
            }else if("text".equals(type)){
                edit(f,"icon_blacklist".equals(key)?"alarm_clock,nfc":"",true);checks.put("text saved");
            }else if("action".equals(type)){
                click(find(f.getString("label")));
                if("power".equals(f.getString("action"))){for(String mode:new String[]{"Yeniden başlat","Recovery","Download modu","Kapat"})find(mode);back();checks.put("all power choices visible; execution requires separate device-mode test");}
                else if("performance".equals(f.getString("action"))){find("Canlı cihaz bilgileri");find("Tamam");back();checks.put("live broker response displayed");}
                else if("audio_output".equals(f.getString("action"))){audioOutput(checks);}
                else if("restart_home".equals(f.getString("action"))){pause(700);checks.put("launcher restart requested");}
                else{back();checks.put("action opens and cancels");}
            }
            results.put(key,new JSONObject().put("ui","pass").put("checks",checks));
        }catch(Throwable t){results.put(key,new JSONObject().put("ui","fail").put("error",t.toString()).put("checks",checks));throw t;}
        finally{if(!"action".equals(type))restore(f,original);Files.write(output,results.toString(2).getBytes(StandardCharsets.UTF_8));}
    }
    public static void main(String[] args)throws Exception{
        Thread.setDefaultUncaughtExceptionHandler((thread,failure)->{failure.printStackTrace(System.err);System.exit(1);});
        if(args.length<2||args.length>3)throw new IllegalArgumentException("Usage: NativeSettingsProbe <section|all> <device-result.json> [key,...]");
        output=Paths.get(args[1]);if(Files.exists(output))throw new IllegalArgumentException("Result must be new");
        try(ZipFile apk=new ZipFile("/system/priv-app/SecSettings/SecSettings.apk")){
            catalogue=new JSONArray(new String(apk.getInputStream(apk.getEntry("assets/artisan/features.json")).readAllBytes(),StandardCharsets.UTF_8));
        }
        HandlerThread thread=new HandlerThread("artisan-native-acceptance");thread.start();
        Class<?> connection=Class.forName("android.app.UiAutomationConnection"),contract=Class.forName("android.app.IUiAutomationConnection");
        ui=(UiAutomation)UiAutomation.class.getConstructor(Looper.class,contract).newInstance(thread.getLooper(),connection.getConstructor().newInstance());
        UiAutomation.class.getMethod("connect",int.class).invoke(ui,UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        JSONObject timeout=new JSONObject().put("namespace","system").put("key","screen_off_timeout");String oldTimeout=read(timeout);
        try{
            restore(timeout,"600000");String current=null;
            for(int i=0;i<catalogue.length();i++){
                JSONObject f=catalogue.getJSONObject(i);String section=f.getString("section");
                if(!"all".equals(args[0])&&!section.equals(args[0]))continue;
                if(args.length==3&&!java.util.Arrays.asList(args[2].split(",")).contains(f.getString("key")))continue;
                if(!section.equals(current)){open(section);current=section;}
                System.out.println("RUN "+f.getString("key"));feature(f);System.out.println("PASS "+f.getString("key"));
            }
        }finally{restore(timeout,oldTimeout);UiAutomation.class.getMethod("disconnect").invoke(ui);thread.quitSafely();}
        System.exit(0);
    }
}
