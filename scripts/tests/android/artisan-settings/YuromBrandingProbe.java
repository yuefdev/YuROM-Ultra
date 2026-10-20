// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.tests;

import android.app.UiAutomation;
import android.os.HandlerThread;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import org.json.JSONObject;

/** Check the real Settings preferences and their browser intents after a ROM boot. */
public final class YuromBrandingProbe {
    private static UiAutomation ui;
    private static String command(String command) throws Exception {
        Process process=new ProcessBuilder("sh","-c",command).redirectErrorStream(true).start();
        ByteArrayOutputStream output=new ByteArrayOutputStream();
        try(InputStream input=process.getInputStream()){
            byte[] buffer=new byte[8192];int count;while((count=input.read(buffer))!=-1)output.write(buffer,0,count);
        }
        byte[] bytes=output.toByteArray();
        if(process.waitFor()!=0)throw new IllegalStateException(new String(bytes,StandardCharsets.UTF_8));
        return new String(bytes,StandardCharsets.UTF_8).trim();
    }
    private static AccessibilityNodeInfo find(AccessibilityNodeInfo node,String text){
        if(node==null)return null;
        if(text.contentEquals(node.getText()==null?"":node.getText()))return node;
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo result=find(node.getChild(i),text);if(result!=null)return result;}
        return null;
    }
    private static AccessibilityNodeInfo waitFor(String text)throws Exception{
        for(int i=0;i<50;i++){AccessibilityNodeInfo node=find(ui.getRootInActiveWindow(),text);if(node!=null)return node;Thread.sleep(200);}
        throw new AssertionError("YuROM control not visible: "+text);
    }
    private static void open(String fragment)throws Exception{
        command("input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard; cmd statusbar collapse; am force-stop com.android.settings; am start -W -n com.android.settings/.SubSettings --es :settings:show_fragment "+fragment);
        Thread.sleep(500);
    }
    private static void github()throws Exception{
        AccessibilityNodeInfo node=waitFor("YuROM Ultra · GitHub");while(node!=null&&!node.isClickable())node=node.getParent();
        if(node==null||!node.performAction(AccessibilityNodeInfo.ACTION_CLICK))throw new AssertionError("GitHub preference not clickable");
        for(int i=0;i<30;i++){
            if(command("dumpsys activity activities").contains("https://github.com/yuefdev"))return;
            Thread.sleep(200);
        }
        throw new AssertionError("GitHub preference did not dispatch the exact HTTPS profile URI");
    }
    public static void main(String[] args)throws Exception{
        Thread.setDefaultUncaughtExceptionHandler((thread,error)->{error.printStackTrace(System.err);System.exit(1);});
        if(!"RUNNING_UNLOCKED".equals(command("am get-started-user-state 0")))throw new IllegalStateException("Unlock normally before testing");
        HandlerThread thread=new HandlerThread("yurom-ui-probe");thread.start();
        Class<?> contract=Class.forName("android.app.IUiAutomationConnection"),connection=Class.forName("android.app.UiAutomationConnection");
        ui=(UiAutomation)UiAutomation.class.getConstructor(android.os.Looper.class,contract).newInstance(thread.getLooper(),connection.getConstructor().newInstance());
        UiAutomation.class.getMethod("connect",int.class).invoke(ui,UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        JSONObject result=new JSONObject();String timeout=command("settings get system screen_off_timeout");
        try{
            command("settings put system screen_off_timeout 600000");
            open("com.android.settings.artisan.ArtisanSettings");waitFor("YuROM Ultra");github();result.put("controls_brand_and_github_intent",true);
            open("com.samsung.android.settings.deviceinfo.softwareinfo.SoftwareInfoSettings");waitFor("YuROM Ultra");github();result.put("software_info_brand_and_github_intent",true);
            result.put("github_profile","https://github.com/yuefdev");
        }finally{
            command("settings "+("null".equals(timeout)?"delete system screen_off_timeout":"put system screen_off_timeout "+timeout));
            Files.write(Paths.get(args[0]),result.toString(2).getBytes(StandardCharsets.UTF_8));
            UiAutomation.class.getMethod("disconnect").invoke(ui);thread.quitSafely();
        }
        System.out.println(result.toString());System.exit(0);
    }
}
