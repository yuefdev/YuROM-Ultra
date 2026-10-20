// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import android.content.Context;
import android.content.ComponentName;
import android.content.pm.ApplicationInfo;
import android.content.pm.LauncherActivityInfo;
import android.content.res.Resources;
import android.graphics.drawable.Drawable;
import android.util.Xml;
import java.io.InputStream;
import java.util.HashMap;
import org.xmlpull.v1.XmlPullParser;

/** Standard appfilter.xml icon packs; no icon-pack APK is modified. */
public final class IconHooks {
    private static String loaded = "";
    private static Resources resources;
    private static final HashMap<String,String> icons = new HashMap<>();
    private IconHooks() {}
    public static synchronized Drawable icon(Context c, String pkg, int id, ApplicationInfo info, Drawable original) {
        if (!SamsungHomeHooks.active() || c == null || !"com.sec.android.app.launcher".equals(c.getPackageName())
                || info == null || id != info.icon || pkg == null) return original;
        return replacement(c,pkg,null,original);
    }
    public static synchronized Drawable activity(LauncherActivityInfo item,Drawable original,boolean badged) {
        Context c=Config.context();
        if(!SamsungHomeHooks.active() || c==null || !"com.sec.android.app.launcher".equals(c.getPackageName()))return original;
        Drawable selected=replacement(c,item.getComponentName().getPackageName(),item.getComponentName().flattenToString(),original);
        return selected==original || !badged ? selected : c.getPackageManager().getUserBadgedIcon(selected,item.getUser());
    }
    public static synchronized Drawable component(Context c,ComponentName component,Drawable original) {
        if(!SamsungHomeHooks.active() || c==null || !"com.sec.android.app.launcher".equals(c.getPackageName()) || component==null)return original;
        return replacement(c,component.getPackageName(),component.flattenToString(),original);
    }
    public static synchronized Drawable application(Context c,String pkg,Drawable original) {
        if(!SamsungHomeHooks.active() || c==null || !"com.sec.android.app.launcher".equals(c.getPackageName()) || pkg==null)return original;
        return replacement(c,pkg,null,original);
    }
    private static Drawable replacement(Context c,String pkg,String componentName,Drawable original) {
        String pack = Config.get("ac_icon_pack", "");
        if (pack.isEmpty() || pack.equals(pkg)) return original;
        try {
            if (!pack.equals(loaded)) {
                icons.clear(); resources = c.getPackageManager().getResourcesForApplication(pack);
                InputStream input=null;android.content.res.XmlResourceParser resourceXml=null;
                try {
                    XmlPullParser xml;
                    try {input=resources.getAssets().open("appfilter.xml");xml=Xml.newPullParser();xml.setInput(input,"UTF-8");}
                    catch(java.io.FileNotFoundException missing){
                        int resource=resources.getIdentifier("appfilter","xml",pack);
                        if(resource==0)throw missing;
                        resourceXml=resources.getXml(resource);xml=resourceXml;
                    }
                    for (int event=xml.getEventType();event!=XmlPullParser.END_DOCUMENT;event=xml.next()) {
                        if (event != XmlPullParser.START_TAG || !"item".equals(xml.getName())) continue;
                        String component = xml.getAttributeValue(null,"component");
                        String drawable = xml.getAttributeValue(null,"drawable");
                        if (component == null || drawable == null) continue;
                        int begin=component.indexOf('{'), end=component.lastIndexOf('}');
                        if (begin < 0 || end <= begin)continue;
                        ComponentName parsed=ComponentName.unflattenFromString(component.substring(begin+1,end));
                        if(parsed==null)continue;
                        icons.put(parsed.flattenToString(),drawable);
                        icons.putIfAbsent(parsed.getPackageName(),drawable);
                    }
                }finally{if(input!=null)input.close();if(resourceXml!=null)resourceXml.close();}
                loaded=pack;
            }
            String name=componentName==null?null:icons.get(componentName);
            if(name==null)name=icons.get(pkg);
            int replacement = name == null ? 0 : resources.getIdentifier(name,"drawable",pack);
            return replacement == 0 ? original : resources.getDrawable(replacement,null);
        } catch (Throwable t) { Config.failure("icon pack " + pack,t); return original; }
    }
}
