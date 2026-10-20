// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import java.nio.charset.StandardCharsets;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Allowlisted crash classes/frames only. Exception messages, paths and arbitrary app names never leave this parser. */
public final class RootBrokerCrashSummary {
    private static final List<String> COMPONENTS=Arrays.asList("system_server","com.android.systemui","com.android.settings",
            "com.sec.android.app.camera","com.sec.android.app.launcher","com.samsung.android.smartsuggestions");
    private static final Pattern PROCESS=Pattern.compile("^Process: ([A-Za-z0-9_.]+)(?::[A-Za-z0-9_.]+)?, PID: [0-9]+$");
    private static final Pattern EXCEPTION=Pattern.compile("^(?:Caused by: )?([A-Za-z_$][A-Za-z0-9_.$]{0,159}(?:Exception|Error))(?::.*)?$");
    private static final Pattern FRAME=Pattern.compile("^at ([A-Za-z_$][A-Za-z0-9_.$]{0,199})\\([^)]*\\)$");
    public static final class Summary {
        public final String component,exception,signature;
        public final List<String> frames;
        Summary(String component,String exception,List<String> frames)throws Exception{
            this.component=component;this.exception=exception;this.frames=new ArrayList<>(frames);
            MessageDigest digest=MessageDigest.getInstance("SHA-256");byte[] hash=digest.digest((component+"\n"+exception+"\n"+String.join("\n",frames)).getBytes(StandardCharsets.UTF_8));
            StringBuilder hex=new StringBuilder();for(byte b:hash)hex.append(String.format("%02x",b&255));signature=hex.toString();
        }
    }
    private RootBrokerCrashSummary(){}
    private static void add(Map<String,Summary> summaries,String component,String exception,List<String> frames)throws Exception{
        if(component==null||exception==null||exception.length()>160||summaries.size()>=6)return;
        Summary summary=new Summary(component,exception,frames);summaries.put(summary.signature,summary);
    }
    public static List<Summary> parse(InputStream input)throws Exception{
        // A single Android log entry may contain a whole stack trace, so -t is
        // not a byte bound. Drain the process and retain only a bounded tail.
        byte[] tail=new byte[384*1024],buffer=new byte[8192];int position=0,size=0,n;
        while((n=input.read(buffer))!=-1){
            int first=Math.min(n,tail.length-position);System.arraycopy(buffer,0,tail,position,first);
            if(first<n)System.arraycopy(buffer,first,tail,0,n-first);
            position=(position+n)%tail.length;size=Math.min(tail.length,size+n);
        }
        byte[] bytes=new byte[size];int start=size==tail.length?position:0,first=Math.min(size,tail.length-start);
        System.arraycopy(tail,start,bytes,0,first);if(first<size)System.arraycopy(tail,0,bytes,first,size-first);
        return parse(new String(bytes,StandardCharsets.UTF_8));
    }
    public static List<Summary> parse(String log)throws Exception{
        Map<String,Summary> summaries=new LinkedHashMap<>();String component=null,exception=null;List<String> frames=new ArrayList<>();
        for(String line:log.split("\n")){
            String text=line.trim();int marker=text.indexOf("AndroidRuntime: ");if(marker>=0)text=text.substring(marker+16).trim();
            else text=text.replaceFirst("^[VDIWEF]/AndroidRuntime\\([^)]*\\):\\s*","");
            if(text.startsWith("FATAL EXCEPTION:")){add(summaries,component,exception,frames);component=null;exception=null;frames.clear();continue;}
            Matcher process=PROCESS.matcher(text);
            if(process.matches()){add(summaries,component,exception,frames);component=COMPONENTS.contains(process.group(1))?process.group(1):null;exception=null;frames.clear();continue;}
            if(component==null)continue;
            Matcher failure=EXCEPTION.matcher(text);
            if(failure.matches()){
                // A nested cause is more useful than the outer ActivityThread wrapper.
                exception=failure.group(1);frames.clear();continue;
            }
            Matcher frame=FRAME.matcher(text);if(exception!=null&&frames.size()<3&&frame.matches())frames.add(frame.group(1));
        }
        add(summaries,component,exception,frames);return new ArrayList<>(summaries.values());
    }
}
