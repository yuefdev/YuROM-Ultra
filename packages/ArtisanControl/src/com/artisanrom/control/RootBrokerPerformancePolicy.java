// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import java.util.LinkedHashMap;
import java.util.Map;

/** Local adaptive policy. Frequencies and voltage margins stay inside the reviewed kernel profile. */
public final class RootBrokerPerformancePolicy {
    public static final String[] KEYS={"lit","mid","big","gpu","lit_uv","mid_uv","big_uv","gpu_uv"};
    public interface Nodes { int read(String key)throws Exception; void write(String key,int value)throws Exception; }
    public static final class Decision {
        public final boolean boost;
        public final int undervolt;
        public final String reason;
        Decision(boolean boost,int undervolt,String reason){this.boost=boost;this.undervolt=undervolt;this.reason=reason;}
        public Map<String,Integer> values(){
            Map<String,Integer> values=new LinkedHashMap<>();
            int[] clocks=boost?new int[]{2106000,2400000,3016000,806000}:new int[]{1950000,2314000,2730000,650000};
            for(int i=0;i<KEYS.length;i++)values.put(KEYS[i],i<4?clocks[i]:-undervolt);
            return values;
        }
    }
    private RootBrokerPerformancePolicy(){}
    public static void validate(String mode,int undervolt){
        if(!("rom".equals(mode)||"stock".equals(mode)||"auto".equals(mode)||"oc".equals(mode)))throw new IllegalArgumentException("Geçersiz OC modu");
        if(undervolt<0||undervolt>3)throw new IllegalArgumentException("Undervolt sınırı %0–%3 olmalı");
    }
    public static Decision decide(String mode,int undervolt,int cpuMilliC,int batteryDeciC,int capacity,
                                  int load,boolean charging,boolean wasBoosting){
        validate(mode,undervolt);
        if("rom".equals(mode))return null;
        if(cpuMilliC<0||cpuMilliC>120000||batteryDeciC<0||batteryDeciC>700||capacity<0||capacity>100||load<0||load>100)
            return new Decision(false,0,"Sensör verisi geçersiz");
        if("stock".equals(mode))return new Decision(false,0,"Stok sınırlar");
        if(cpuMilliC>=78000||batteryDeciC>=420)return new Decision(false,0,"Isı koruması");
        if(capacity<=15&&!charging)return new Decision(false,0,"Düşük pil");
        // Charging and a warm battery reduce sustained boost, rather than defeating thermal protection.
        int batteryCeiling=charging?370:390;
        boolean cool=cpuMilliC<70000&&batteryDeciC<batteryCeiling;
        boolean hold=wasBoosting&&cpuMilliC<72000&&batteryDeciC<batteryCeiling+10&&load>=35;
        boolean boost="oc".equals(mode)?cool:(cool&&load>=65)||hold;
        int margin=boost&&cpuMilliC<65000&&batteryDeciC<370?undervolt:0;
        return new Decision(boost,margin,boost?"Yük için OC":"Dengeli / bekleme");
    }
    public static Map<String,Integer> snapshot(Nodes nodes)throws Exception{
        Map<String,Integer> result=new LinkedHashMap<>();
        for(String key:KEYS)result.put(key,nodes.read(key));
        return result;
    }
    private static void writeChecked(Nodes nodes,String key,int value)throws Exception{
        if(nodes.read(key)==value)return;
        nodes.write(key,value);
        int actual=nodes.read(key);
        boolean clock="lit".equals(key)||"mid".equals(key)||"big".equals(key)||"gpu".equals(key);
        // Samsung thermal/QoS may expose a lower effective maximum immediately.
        // Never require that protection to be bypassed to accept a bounded cap.
        if(actual!=value&&!(clock&&actual>0&&actual<value))throw new IllegalStateException("Kernel değeri doğrulanamadı: "+key);
    }
    private static void applyValues(Nodes nodes,Map<String,Integer> values)throws Exception{
        for(int i=4;i<KEYS.length;i++)writeChecked(nodes,KEYS[i],0);
        for(int i=0;i<4;i++)writeChecked(nodes,KEYS[i],values.get(KEYS[i]));
        for(int i=4;i<KEYS.length;i++)writeChecked(nodes,KEYS[i],values.get(KEYS[i]));
    }
    public static void apply(Nodes nodes,Map<String,Integer> values)throws Exception{
        if(!values.keySet().equals(new java.util.HashSet<>(java.util.Arrays.asList(KEYS))))throw new IllegalArgumentException("Eksik performans işlemi");
        Map<String,Integer> before=snapshot(nodes);
        try{applyValues(nodes,values);}
        catch(Exception failure){
            // Attempt every rollback node even if a disappearing device rejects another one.
            for(int i=4;i<KEYS.length;i++)try{writeChecked(nodes,KEYS[i],0);}catch(Exception e){failure.addSuppressed(e);}
            for(int i=0;i<KEYS.length;i++)try{writeChecked(nodes,KEYS[i],before.get(KEYS[i]));}catch(Exception e){failure.addSuppressed(e);}
            throw failure;
        }
    }
}
