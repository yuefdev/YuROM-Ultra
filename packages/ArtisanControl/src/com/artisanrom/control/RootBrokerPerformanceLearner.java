// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

/** Small on-device online regression model. Learning may only veto an otherwise permitted boost. */
public final class RootBrokerPerformanceLearner {
    private final double[] weights=new double[5];
    private int count;
    private double errorSquared=4;
    private long previousTime;
    private int previousTemperature;
    private double[] previousFeatures;
    private static double[] features(int temperature,int load,boolean charging,boolean boost){
        return new double[]{1,(temperature-50000)/30000.0,load/100.0,charging?1:0,boost?1:0};
    }
    private double prediction(double[] features){double value=0;for(int i=0;i<weights.length;i++)value+=weights[i]*features[i];return Math.max(-5,Math.min(5,value));}
    void learn(double[] features,double observedDelta){
        double error=observedDelta-prediction(features),norm=1;
        for(double value:features)norm+=value*value;
        errorSquared=Math.max(0.04,Math.min(25,errorSquared*0.97+Math.min(25,error*error)*0.03));
        for(int i=0;i<weights.length;i++)weights[i]=Math.max(-5,Math.min(5,weights[i]*0.9999+0.08*Math.max(-3,Math.min(3,error))*features[i]/norm));
        if(count<1000000)count++;
    }
    public void observe(int temperature,int load,boolean charging,boolean boost,long now){
        if(temperature<0||temperature>110000||load<0||load>100){previousFeatures=null;return;}
        long interval=now-previousTime;
        if(previousFeatures!=null&&interval>=2500&&interval<=15000){
            double delta=(temperature-previousTemperature)*5.0/interval;
            if(Math.abs(delta)<=10)learn(previousFeatures,delta);
        }
        // UI refreshes must not turn tiny timing differences into training samples.
        if(previousFeatures==null||interval>=2500){previousFeatures=features(temperature,load,charging,boost);previousTemperature=temperature;previousTime=now;}
    }
    public int samples(){return count;}
    public boolean ready(){return count>=36;}
    public int forecast(int temperature,int load,boolean charging,boolean boost){
        double rise=Math.max(0,prediction(features(temperature,load,charging,boost)));
        return (int)Math.min(120000,temperature+1000*(6*rise+2*Math.sqrt(errorSquared)));
    }
    public boolean veto(int temperature,int load,boolean charging){return ready()&&forecast(temperature,load,charging,true)>=70000;}
    public double[] weights(){return weights.clone();}
    public double errorSquared(){return errorSquared;}
    public void restore(double[] saved,int samples,double error){
        if(saved.length!=weights.length||samples<0||samples>1000000||!Double.isFinite(error)||error<0.04||error>25)throw new IllegalArgumentException("Geçersiz yerel model");
        for(double value:saved)if(!Double.isFinite(value)||Math.abs(value)>5)throw new IllegalArgumentException("Geçersiz yerel model ağırlığı");
        System.arraycopy(saved,0,weights,0,weights.length);count=samples;errorSquared=error;
    }
}
