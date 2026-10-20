// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Exercises the actual controller policy and write transaction without Android or device sysfs. */
public final class PerformancePolicyProbe {
    private static int checks;
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);checks++;}
    private static RootBrokerPerformancePolicy.Decision decide(String mode,int cpu,int battery,int capacity,int load,boolean charging,boolean previous){
        return RootBrokerPerformancePolicy.decide(mode,3,cpu,battery,capacity,load,charging,previous);
    }
    private static final class Nodes implements RootBrokerPerformancePolicy.Nodes {
        Map<String,Integer> values=new LinkedHashMap<>(decide("stock",50000,300,80,20,false,false).values());
        final List<String> writes=new ArrayList<>();int failWrite,ignoreWrite,bigCeiling;boolean failRead;
        public int read(String key)throws Exception{if(failRead)throw new Exception("missing node");return values.get(key);}
        public void write(String key,int value)throws Exception{writes.add(key+"="+value);if(writes.size()==failWrite)throw new Exception("write rejected");if(writes.size()!=ignoreWrite)values.put(key,"big".equals(key)&&bigCeiling>0?Math.min(value,bigCeiling):value);}
    }
    public static void main(String[] args)throws Exception{
        check(decide("rom",50000,300,80,90,false,false)==null,"Default mode must not tune nodes");
        check(decide("auto",50000,300,80,80,false,false).boost,"Cool high load should boost");
        check(decide("auto",50000,300,80,80,false,false).undervolt==3,"Cool boost should respect selected UV ceiling");
        check(!decide("auto",50000,300,80,20,false,true).boost,"Idle should release boost");
        check(decide("auto",71000,395,80,45,false,true).boost,"Hysteresis should hold a permitted boost");
        check(!decide("auto",72000,300,80,80,false,true).boost,"Warm CPU should release boost");
        check(!decide("oc",50000,380,80,80,true,false).boost,"Charging battery should reduce boost");
        check(!decide("oc",50000,300,15,80,false,false).boost,"Low battery should disable boost");
        check(decide("oc",50000,300,15,80,true,false).boost,"External power may permit a cool boost");
        check(decide("oc",65000,300,80,80,false,false).undervolt==0,"Warm boost must not add UV");
        check(!decide("oc",78000,300,80,80,false,false).boost,"CPU heat guard");
        check(!decide("oc",50000,420,80,80,false,false).boost,"Battery heat guard");
        check(!decide("auto",-1,300,80,80,false,false).boost,"Invalid sensor must not boost");
        for(String mode:new String[]{"auto","oc","stock"})for(int cpu:new int[]{-1,0,64999,65000,69999,70000,71999,72000,77999,78000,120001})
            for(int battery:new int[]{-1,300,369,370,379,380,389,390,419,420,701})for(int charge:new int[]{0,1}){
                RootBrokerPerformancePolicy.Decision d=decide(mode,cpu,battery,30,80,charge==1,true);
                check(d.undervolt>=0&&d.undervolt<=3,"Margin bounds");
                check(d.values().get("big")<=3016000&&d.values().get("gpu")<=806000,"Clock bounds");
            }
        for(int margin:new int[]{-1,4})try{RootBrokerPerformancePolicy.validate("auto",margin);throw new AssertionError("Invalid UV accepted");}catch(IllegalArgumentException expected){checks++;}
        try{RootBrokerPerformancePolicy.validate("shell",0);throw new AssertionError("Invalid mode accepted");}catch(IllegalArgumentException expected){checks++;}
        Nodes normal=new Nodes();Map<String,Integer> boosted=decide("oc",50000,300,80,80,false,false).values();
        RootBrokerPerformancePolicy.apply(normal,boosted);check(normal.values.equals(boosted),"Apply/readback");
        int firstNegative=normal.writes.indexOf("lit_uv=-3"),lastClock=normal.writes.indexOf("gpu=806000");
        check(firstNegative>lastClock,"Negative margins must follow clock programming");
        for(boolean rejectReadback:new boolean[]{false,true}){
            Nodes failing=new Nodes();Map<String,Integer> before=new LinkedHashMap<>(failing.values);
            if(rejectReadback)failing.ignoreWrite=6;else failing.failWrite=3;
            try{RootBrokerPerformancePolicy.apply(failing,boosted);throw new AssertionError("Failure accepted");}catch(Exception expected){checks++;}
            check(failing.values.equals(before),"Failed write/readback must restore every node");
        }
        Nodes missing=new Nodes();missing.failRead=true;
        try{RootBrokerPerformancePolicy.apply(missing,boosted);throw new AssertionError("Missing sensor accepted");}catch(Exception expected){checks++;}
        check(missing.writes.isEmpty(),"Preflight failure must not write");
        RootBrokerPerformancePolicy.apply(normal,decide("stock",50000,300,80,80,false,false).values());
        check(normal.values.get("big")==2730000&&normal.values.get("gpu")==650000&&normal.values.get("big_uv")==0,"Stock restoration");
        Nodes thermallyLimited=new Nodes();thermallyLimited.bigCeiling=2340000;
        RootBrokerPerformancePolicy.apply(thermallyLimited,boosted);
        check(thermallyLimited.values.get("big")==2340000,"A Samsung thermal cap must be retained and accepted");
        RootBrokerPerformancePolicy.apply(thermallyLimited,decide("stock",50000,300,80,80,false,false).values());
        check(thermallyLimited.values.get("big")==2340000&&thermallyLimited.values.get("big_uv")==0,"Stock selection must respect thermal caps while removing UV");
        RootBrokerPerformanceLearner warm=new RootBrokerPerformanceLearner(),cool=new RootBrokerPerformanceLearner();
        check(!warm.ready()&&!warm.veto(65000,80,false),"Untrained model must not make learned decisions");
        for(int i=0;i<1000;i++){double[] sample={1,0.5,0.8,0,1};warm.learn(sample,1);cool.learn(sample,-1);}
        check(warm.ready()&&warm.veto(65000,80,false),"Model must learn a heating trajectory");
        check(!cool.veto(65000,80,false),"Cooling evidence must change the forecast");
        check(warm.forecast(65000,80,false,true)>cool.forecast(65000,80,false,true),"Different device evidence must change predictions");
        RootBrokerPerformanceLearner restored=new RootBrokerPerformanceLearner();restored.restore(warm.weights(),warm.samples(),warm.errorSquared());
        check(restored.forecast(65000,80,false,true)==warm.forecast(65000,80,false,true),"Model persistence");
        RootBrokerPerformanceLearner timing=new RootBrokerPerformanceLearner();timing.observe(60000,80,false,true,10000);timing.observe(61000,80,false,true,15000);
        check(timing.samples()==1,"Sensor observations must train the model");timing.observe(61500,80,false,true,15001);check(timing.samples()==1,"UI refresh must not train short intervals");
        try{restored.restore(new double[]{Double.NaN,0,0,0,0},1,1);throw new AssertionError("Invalid model accepted");}catch(IllegalArgumentException expected){checks++;}
        check(restored.forecast(65000,80,false,true)==warm.forecast(65000,80,false,true),"Invalid persisted weights must not replace the model");
        System.out.println("PASS: "+checks+" adaptive policy, learned thermal prediction, clock/UV boundary and transactional rollback checks");
    }
}
