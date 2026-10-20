// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import android.os.Build;
import android.system.Os;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.Arrays;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.HttpsURLConnection;
import org.json.JSONArray;
import org.json.JSONObject;

/** Explicit opt-in daily health summaries and previewed reports; no hardware IDs or raw logs. */
public final class RootBrokerTelemetry {
    private static final Path DIRECTORY=Paths.get("/data/system/artisan-control"),STATE=DIRECTORY.resolve("telemetry.json");
    private static final Path CONFIG=Paths.get("/system/etc/artisan-telemetry.json");
    private boolean loaded,enabled;
    private String installation="",endpoint="",build="",error="";
    private long lastSent,lastAttempt;
    private JSONObject pendingReport;
    private String pendingCategory;
    private long previewTime;
    private static final java.util.List<String> CATEGORIES=Arrays.asList("boot","camera","fingerprint","audio","dex","battery","performance","display","other");
    private static byte[] read(InputStream input,int limit)throws Exception{
        ByteArrayOutputStream output=new ByteArrayOutputStream();byte[] buffer=new byte[4096];int n;
        while((n=input.read(buffer))!=-1){if(output.size()+n>limit)throw new IllegalArgumentException("Yanıt sınırı aşıldı");output.write(buffer,0,n);}return output.toByteArray();
    }
    private static JSONObject document(Path path)throws Exception{
        try(InputStream input=Files.newInputStream(path)){return new JSONObject(new String(read(input,16384),StandardCharsets.UTF_8));}
    }
    private void load()throws Exception{
        if(loaded)return;
        if(Files.isRegularFile(CONFIG)){
            JSONObject config=document(CONFIG);build=config.getString("build");endpoint=config.getString("endpoint");
            if(config.optInt("schema")!=1||!build.matches("v[0-9]{1,4}(?:[._-][A-Za-z0-9]+){0,4}"))throw new IllegalStateException("Telemetri sürüm ayarı geçersiz");
            if(!endpoint.isEmpty()){
                URI uri=new URI(endpoint);
                if(!"https".equals(uri.getScheme())||uri.getHost()==null||!uri.getHost().matches("[A-Za-z0-9.-]+\\.[A-Za-z]{2,}")||uri.getUserInfo()!=null||uri.getQuery()!=null||uri.getFragment()!=null
                        ||uri.getPort()!=-1||!(uri.getPath().isEmpty()||"/".equals(uri.getPath())))throw new IllegalStateException("Telemetri için HTTPS sunucu kökü gerekli");
                endpoint="https://"+uri.getHost();
            }
        }
        if(Files.isRegularFile(STATE)){
            JSONObject state=document(STATE);enabled=state.optBoolean("enabled",false);installation=state.optString("installation","");lastSent=state.optLong("last_sent",0);
            if(!installation.isEmpty()&&!installation.matches("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"))throw new IllegalStateException("Kurulum kodu geçersiz");
        }
        loaded=true;
    }
    private void save()throws Exception{
        Files.createDirectories(DIRECTORY);Os.chmod(DIRECTORY.toString(),0700);Path temporary=Files.createTempFile(DIRECTORY,"telemetry-",".new");
        try{
            Files.write(temporary,new JSONObject().put("enabled",enabled).put("installation",installation).put("last_sent",lastSent).toString().getBytes(StandardCharsets.UTF_8));Os.chmod(temporary.toString(),0600);
            try(java.nio.channels.FileChannel file=java.nio.channels.FileChannel.open(temporary,java.nio.file.StandardOpenOption.WRITE)){file.force(true);}
            Files.move(temporary,STATE,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
        }finally{Files.deleteIfExists(temporary);}
    }
    private String mode(){
        try{String value=document(DIRECTORY.resolve("performance.json")).optString("mode");if(Arrays.asList("rom","stock","auto","oc").contains(value))return value;}
        catch(Exception ignored){}return "unknown";
    }
    private JSONArray crashes()throws Exception{
        Process process=new ProcessBuilder("logcat","-b","crash","-d","-t","600","-v","brief").redirectErrorStream(true).start();
        java.util.List<RootBrokerCrashSummary.Summary> summaries;
        try(InputStream input=process.getInputStream()){summaries=RootBrokerCrashSummary.parse(input);}
        finally{if(!process.waitFor(5,TimeUnit.SECONDS))process.destroyForcibly();}
        if(process.exitValue()!=0)throw new IllegalStateException("Çökme özeti okunamadı");
        JSONArray result=new JSONArray();for(RootBrokerCrashSummary.Summary summary:summaries)
            result.put(new JSONObject().put("signature",summary.signature).put("component",summary.component).put("exception",summary.exception).put("frames",new JSONArray(summary.frames)));
        return result;
    }
    private JSONObject payload(String category)throws Exception{
        if(!enabled||endpoint.isEmpty()||installation.isEmpty())throw new IllegalStateException("Önce isteğe bağlı istatistik paylaşımını aç");
        if(category!=null&&!CATEGORIES.contains(category))throw new IllegalArgumentException("Geçersiz sorun türü");
        if(!Arrays.asList("SM-G970F","SM-G973F","SM-G975F").contains(Build.MODEL))throw new IllegalStateException("Desteklenmeyen cihaz");
        return new JSONObject().put("schema",1).put("installation",installation).put("model",Build.MODEL).put("build",build).put("oc_mode",mode()).put("crashes",crashes()).put("report",category==null?JSONObject.NULL:category);
    }
    private void post(String route,JSONObject payload)throws Exception{
        byte[] bytes=payload.toString().getBytes(StandardCharsets.UTF_8);if(bytes.length>8192)throw new IllegalArgumentException("Rapor boyutu sınırı aşıldı");
        HttpsURLConnection connection=(HttpsURLConnection)new URL(endpoint+route).openConnection();
        try{
            connection.setConnectTimeout(8000);connection.setReadTimeout(8000);connection.setInstanceFollowRedirects(false);connection.setRequestMethod("POST");connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type","application/json");connection.setRequestProperty("User-Agent","YuROM-Ultra-Telemetry/1");connection.setFixedLengthStreamingMode(bytes.length);
            try(OutputStream output=connection.getOutputStream()){output.write(bytes);}
            if(connection.getResponseCode()!=200)throw new IllegalStateException("Telemetri sunucusu isteği kabul etmedi");
            JSONObject reply;try(InputStream input=connection.getInputStream()){reply=new JSONObject(new String(read(input,2048),StandardCharsets.UTF_8));}
            if(!reply.optBoolean("/v1/forget".equals(route)?"deleted":"accepted"))throw new IllegalStateException("Sunucu onayı eksik");
        }finally{connection.disconnect();}
    }
    public synchronized byte[] status()throws Exception{
        load();return new JSONObject().put("enabled",enabled).put("configured",!endpoint.isEmpty()).put("endpoint",endpoint).put("last_sent",lastSent).put("error",error).toString().getBytes(StandardCharsets.UTF_8);
    }
    public synchronized byte[] configure(byte[] bytes)throws Exception{
        load();JSONObject config=new JSONObject(new String(bytes,StandardCharsets.UTF_8));
        if(config.length()!=1||!(config.get("enabled") instanceof Boolean))throw new IllegalArgumentException("Geçersiz telemetri tercihi");
        boolean requested=config.getBoolean("enabled");if(requested&&endpoint.isEmpty())throw new IllegalStateException("Bu derlemede Cloudflare adresi henüz ayarlı değil");
        boolean previous=enabled;String oldId=installation;
        enabled=requested;if(requested&&installation.isEmpty())installation=UUID.randomUUID().toString();
        pendingReport=null;
        try{save();}catch(Exception e){enabled=previous;installation=oldId;throw e;}
        return status();
    }
    public synchronized byte[] preview(String category)throws Exception{
        load();pendingReport=payload(category);pendingCategory=category;previewTime=android.os.SystemClock.elapsedRealtime();return pendingReport.toString(2).getBytes(StandardCharsets.UTF_8);
    }
    public synchronized byte[] send(String category)throws Exception{
        load();JSONObject event;
        if(category==null)event=payload(null);
        else{
            if(!enabled||pendingReport==null||!category.equals(pendingCategory)||android.os.SystemClock.elapsedRealtime()-previewTime>300000)
                throw new IllegalStateException("Göndermeden önce raporu yeniden incele");
            event=pendingReport;
        }
        lastAttempt=android.os.SystemClock.elapsedRealtime();post("/v1/event",event);pendingReport=null;lastSent=System.currentTimeMillis();save();error="";return status();
    }
    public synchronized byte[] forget()throws Exception{
        load();enabled=false;pendingReport=null;save();if(!installation.isEmpty()){
            if(endpoint.isEmpty())throw new IllegalStateException("Sunucu adresi ayarlı değil");
            post("/v1/forget",new JSONObject().put("installation",installation));
        }
        installation="";lastSent=0;save();return status();
    }
    private synchronized void tick(){
        try{
            load();long now=System.currentTimeMillis(),elapsed=android.os.SystemClock.elapsedRealtime();
            if(enabled&&!endpoint.isEmpty()&&(lastSent==0||now-lastSent>=86400000L||now<lastSent)&&elapsed-lastAttempt>=3600000L)send(null);
        }catch(Exception e){lastAttempt=android.os.SystemClock.elapsedRealtime();error="Gönderim tamamlanamadı; daha sonra yeniden denenecek";}
    }
    public void start(){Thread thread=new Thread(()->{for(;;){tick();try{Thread.sleep(60000);}catch(InterruptedException e){return;}}},"artisan-telemetry");thread.setDaemon(true);thread.start();}
}
