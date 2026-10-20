// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import android.os.Build;
import android.system.Os;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.LinkedHashMap;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONObject;

/** UID-checked broker backend; clients select a mode, never paths, clocks or shell commands. */
public final class RootBrokerPerformance {
    private static final Path DIRECTORY=Paths.get("/data/system/artisan-control");
    private static final Path CONFIG=DIRECTORY.resolve("performance.json"),PENDING=DIRECTORY.resolve("performance-pending");
    private static final Path PROFILE=Paths.get("/vendor/etc/s10-performance-control.json");
    private static final Path MODEL=DIRECTORY.resolve("performance-model.json");
    private static final Map<String,String> PATHS=new LinkedHashMap<>();
    static{
        for(int i=0;i<3;i++)PATHS.put(RootBrokerPerformancePolicy.KEYS[i],"/sys/devices/system/cpu/cpufreq/policy"+new int[]{0,4,6}[i]+"/scaling_max_freq");
        PATHS.put("gpu","/sys/kernel/gpu/gpu_max_clock");
        String[] domains={"lit","mid","big","g3d"};
        for(int i=0;i<4;i++)PATHS.put(RootBrokerPerformancePolicy.KEYS[i+4],"/sys/power/percent_margin/"+domains[i]+"_margin_percent");
    }
    private final RootBrokerPerformancePolicy.Nodes nodes=new RootBrokerPerformancePolicy.Nodes(){
        public int read(String key)throws Exception{return integer(PATHS.get(key));}
        public void write(String key,int value)throws Exception{Files.write(Paths.get(PATHS.get(key)),Integer.toString(value).getBytes(StandardCharsets.US_ASCII));}
    };
    private String mode="rom",reason="ROM profili",error="";
    private int undervolt=3,cpuTemp,batteryTemp,capacity,load;
    private boolean available,blocked,boost,charging,loaded,ownsNodes;
    private long previousTotal,previousIdle,healthUntil;
    private Map<String,Integer> initial,lastApplied;
    private final RootBrokerPerformanceLearner learner=new RootBrokerPerformanceLearner();
    private String expectedBoot="";
    private int savedSamples;
    private boolean bootControlStarted;
    private static String text(String path)throws Exception{return new String(Files.readAllBytes(Paths.get(path)),StandardCharsets.UTF_8).trim();}
    private static int integer(String path)throws Exception{return Integer.parseInt(text(path));}
    private static String property(String key)throws Exception{
        Process p=new ProcessBuilder("getprop",key).start();byte[] data=new byte[4096];int n=p.getInputStream().read(data);
        if(p.waitFor()!=0)throw new IllegalStateException("Sistem özelliği okunamadı");return n<0?"":new String(data,0,n,StandardCharsets.UTF_8).trim();
    }
    private static String hash(Path path)throws Exception{
        MessageDigest digest=MessageDigest.getInstance("SHA-256");byte[] buffer=new byte[65536];int n;
        try(InputStream input=Files.newInputStream(path)){while((n=input.read(buffer))!=-1)digest.update(buffer,0,n);}
        StringBuilder result=new StringBuilder();for(byte b:digest.digest())result.append(String.format("%02x",b&255));return result.toString();
    }
    private void ready()throws Exception{
        if(available)return;
        if(!Files.isRegularFile(PROFILE))throw new IllegalStateException("Bu ROM’da eşleşen OC kontrol profili yok");
        JSONObject profile=new JSONObject(text(PROFILE.toString()));
        if(profile.optInt("schema")!=1||profile.optInt("maximum_undervolt_percent")!=3||!Build.MODEL.equals(profile.optString("model"))||!profile.optString("boot_sha256").matches("[0-9a-f]{64}"))
            throw new IllegalStateException("OC profili cihazla eşleşmiyor");
        if(!"applied".equals(property("vendor.s10.performance.state")))throw new IllegalStateException("ROM performans açılış kontrolü bekleniyor");
        if(!hash(Paths.get("/dev/block/platform/13d60000.ufs/by-name/boot")).equals(profile.getString("boot_sha256")))
            throw new IllegalStateException("OC için doğrulanmış kernel gerekli");
        initial=RootBrokerPerformancePolicy.snapshot(nodes);
        for(int i=4;i<RootBrokerPerformancePolicy.KEYS.length;i++)if(initial.get(RootBrokerPerformancePolicy.KEYS[i])>0||initial.get(RootBrokerPerformancePolicy.KEYS[i])< -3)
            throw new IllegalStateException("Kernel voltaj marjı ROM aralığının dışında");
        // Saved adaptive modes boot at stock caps. The explicit ROM choice must
        // still restore the reviewed ROM profile rather than those startup caps.
        initial=new RootBrokerPerformancePolicy.Decision(true,3,"ROM profili").values();
        expectedBoot=profile.getString("boot_sha256");
        try{
            if(Files.isRegularFile(MODEL)){
                JSONObject saved=new JSONObject(text(MODEL.toString()));
                if(expectedBoot.equals(saved.optString("boot_sha256"))&&Build.MODEL.equals(saved.optString("model"))){
                    JSONArray values=saved.getJSONArray("weights");double[] weights=new double[values.length()];for(int i=0;i<weights.length;i++)weights[i]=values.getDouble(i);
                    learner.restore(weights,saved.getInt("samples"),saved.getDouble("error_squared"));savedSamples=learner.samples();
                }
            }
        }catch(Exception ignored){/* Invalid learning data starts a fresh bounded model. */}
        available=true;
    }
    private void writeJson(Path destination,JSONObject document)throws Exception{
        Files.createDirectories(DIRECTORY);Os.chmod(DIRECTORY.toString(),0700);
        Path stage=Files.createTempFile(DIRECTORY,"performance-",".new");
        try{
            Files.write(stage,document.toString().getBytes(StandardCharsets.UTF_8));Os.chmod(stage.toString(),0600);
            try(java.nio.channels.FileChannel file=java.nio.channels.FileChannel.open(stage,java.nio.file.StandardOpenOption.WRITE)){file.force(true);}
            Files.move(stage,destination,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
        }finally{Files.deleteIfExists(stage);}
    }
    private void save()throws Exception{writeJson(CONFIG,new JSONObject().put("mode",mode).put("undervolt",undervolt));}
    private void beginHealthWindow()throws Exception{
        Files.createDirectories(DIRECTORY);Os.chmod(DIRECTORY.toString(),0700);Files.write(PENDING,new byte[]{1});Os.chmod(PENDING.toString(),0600);
        try(java.nio.channels.FileChannel file=java.nio.channels.FileChannel.open(PENDING,java.nio.file.StandardOpenOption.WRITE)){file.force(true);}
        healthUntil=android.os.SystemClock.elapsedRealtime()+60000;
    }
    private void load()throws Exception{
        if(loaded)return;
        if(Files.isRegularFile(CONFIG)){
            JSONObject config=new JSONObject(text(CONFIG.toString()));mode=config.getString("mode");undervolt=config.getInt("undervolt");RootBrokerPerformancePolicy.validate(mode,undervolt);
        }
        if(Files.exists(PENDING)){mode="stock";undervolt=0;reason="Önceki uygulama tamamlanmadı; stok sınırlar seçildi";save();}
        loaded=true;
    }
    private void sample()throws Exception{
        cpuTemp=Math.max(integer("/sys/class/thermal/thermal_zone0/temp"),Math.max(integer("/sys/class/thermal/thermal_zone1/temp"),integer("/sys/class/thermal/thermal_zone3/temp")));
        batteryTemp=integer("/sys/class/power_supply/battery/temp");capacity=integer("/sys/class/power_supply/battery/capacity");
        charging="Charging".equals(text("/sys/class/power_supply/battery/status"));
        String[] fields=text("/proc/stat").split("\n",2)[0].trim().split("\\s+");long total=0;
        for(int i=1;i<=8;i++)total+=Long.parseLong(fields[i]);long idle=Long.parseLong(fields[4])+Long.parseLong(fields[5]);
        long delta=total-previousTotal;load=previousTotal==0||delta<=0?0:(int)Math.max(0,Math.min(100,100-100*(idle-previousIdle)/delta));previousTotal=total;previousIdle=idle;
        boolean active=nodes.read("big")>2730000||nodes.read("gpu")>650000;
        learner.observe(cpuTemp,load,charging,active,android.os.SystemClock.elapsedRealtime());
        if(learner.samples()-savedSamples>=60)try{
            JSONArray weights=new JSONArray();for(double value:learner.weights())weights.put(value);
            writeJson(MODEL,new JSONObject().put("schema",1).put("model",Build.MODEL).put("boot_sha256",expectedBoot).put("weights",weights).put("samples",learner.samples()).put("error_squared",learner.errorSquared()));
            savedSamples=learner.samples();
        }catch(Exception ignored){/* Learning persistence must not interrupt thermal protection. */}
    }
    private void apply()throws Exception{
        if("rom".equals(mode)){
            if(ownsNodes)RootBrokerPerformancePolicy.apply(nodes,initial);
            ownsNodes=false;boost=false;lastApplied=null;reason="ROM profili";healthUntil=0;Files.deleteIfExists(PENDING);
            try{sample();}catch(Exception e){reason+="; sensör okunamadı";}
            return;
        }
        sample();RootBrokerPerformancePolicy.Decision decision=RootBrokerPerformancePolicy.decide(mode,undervolt,cpuTemp,batteryTemp,capacity,load,charging,boost);
        if(decision.boost&&learner.veto(cpuTemp,load,charging))decision=new RootBrokerPerformancePolicy.Decision(false,0,"Cihaz-içi model ısınma öngörüyor");
        Map<String,Integer> values=decision.values();
        if(!values.equals(lastApplied)){RootBrokerPerformancePolicy.apply(nodes,values);lastApplied=values;ownsNodes=true;}
        boost=decision.boost;reason=decision.reason;
        if("stock".equals(mode)&&healthUntil==0)Files.deleteIfExists(PENDING);
        if(healthUntil>0&&android.os.SystemClock.elapsedRealtime()>=healthUntil){Files.deleteIfExists(PENDING);healthUntil=0;}
    }
    private synchronized void tick(){
        if(blocked)return;
        try{load();ready();if(!bootControlStarted){if("auto".equals(mode)||"oc".equals(mode))beginHealthWindow();bootControlStarted=true;}apply();error="";}
        catch(Exception e){
            error=String.valueOf(e.getMessage());
            if(available){
                blocked=true;mode="stock";undervolt=0;boost=false;lastApplied=null;reason="Hata sonrası stok sınırlar";
                try{RootBrokerPerformancePolicy.apply(nodes,new RootBrokerPerformancePolicy.Decision(false,0,"Kontrol durduruldu").values());save();Files.deleteIfExists(PENDING);}
                catch(Exception rollback){error+="; geri yükleme: "+rollback.getMessage();}
            }
        }
    }
    public void start(){Thread worker=new Thread(()->{for(;;){tick();try{Thread.sleep(5000);}catch(InterruptedException e){return;}}},"artisan-oc");worker.setDaemon(true);worker.start();}
    public synchronized byte[] configure(byte[] bytes)throws Exception{
        if(bytes.length>1024)throw new IllegalArgumentException("OC isteği çok büyük");
        JSONObject config=new JSONObject(new String(bytes,StandardCharsets.UTF_8));
        if(config.length()!=2||!(config.get("mode") instanceof String)||!(config.get("undervolt") instanceof Integer))throw new IllegalArgumentException("Geçersiz OC isteği");
        String requested=config.getString("mode");int margin=config.getInt("undervolt");RootBrokerPerformancePolicy.validate(requested,margin);load();ready();
        String oldMode=mode;int oldMargin=undervolt;Map<String,Integer> previous=RootBrokerPerformancePolicy.snapshot(nodes),previousApplied=lastApplied;boolean previousOwnership=ownsNodes;
        try{
            beginHealthWindow();bootControlStarted=true;
            mode=requested;undervolt=margin;blocked=false;apply();save();error="";
        }catch(Exception e){
            mode=oldMode;undervolt=oldMargin;lastApplied=previousApplied;ownsNodes=previousOwnership;blocked=true;healthUntil=0;error=String.valueOf(e.getMessage());
            try{RootBrokerPerformancePolicy.apply(nodes,previous);Files.deleteIfExists(PENDING);}catch(Exception rollback){e.addSuppressed(rollback);error+="; geri yükleme: "+rollback.getMessage();}
            throw e;
        }
        return status();
    }
    public synchronized byte[] status()throws Exception{
        JSONObject result=new JSONObject().put("available",available).put("mode",mode).put("undervolt",undervolt).put("reason",reason).put("error",error).put("blocked",blocked)
                .put("cpu_temp",cpuTemp).put("battery_temp",batteryTemp).put("capacity",capacity).put("load",load).put("charging",charging).put("boost",boost).put("health_pending",healthUntil>0);
        result.put("model_samples",learner.samples()).put("model_ready",learner.ready()).put("forecast_cpu_temp",learner.forecast(cpuTemp,load,charging,boost));
        if(available){JSONObject actual=new JSONObject();for(String key:RootBrokerPerformancePolicy.KEYS)actual.put(key,nodes.read(key));result.put("actual",actual);}
        return result.toString().getBytes(StandardCharsets.UTF_8);
    }
}
