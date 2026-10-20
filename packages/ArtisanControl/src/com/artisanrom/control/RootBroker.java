// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import android.net.LocalServerSocket;
import android.net.LocalSocket;
import android.os.Build;
import android.system.Os;
import android.system.StructStat;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.File;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;
import org.json.JSONObject;

/** Small root broker: peer-UID checked, fixed operations, no arbitrary shell protocol. */
public final class RootBroker {
    public static final String SOCKET = "artisan-control-v1";
    public static final int LIMIT = 64 * 1024 * 1024;
    private static final Path BACKUPS = Paths.get("/data/system/artisan-control");
    private static final String[] SCOPES = {"databases", "shared_prefs", "files"};
    private static final RootBrokerPerformance PERFORMANCE=new RootBrokerPerformance();
    private static final RootBrokerTelemetry TELEMETRY=new RootBrokerTelemetry();
    private RootBroker() {}

    private static byte[] execute(String... command) throws Exception {
        Process process = new ProcessBuilder(command).redirectErrorStream(true).start();
        byte[] output = read(process.getInputStream(), 1024 * 1024);
        if (process.waitFor() != 0) throw new IllegalStateException(new String(output, StandardCharsets.UTF_8));
        return output;
    }
    private static byte[] read(InputStream input, int max) throws Exception {
        ByteArrayOutputStream result = new ByteArrayOutputStream(); byte[] buffer = new byte[8192]; int n;
        while ((n = input.read(buffer)) != -1) {
            if (result.size() + n > max) throw new IllegalArgumentException("Dosya boyutu sınırı aşıldı");
            result.write(buffer,0,n);
        }
        return result.toByteArray();
    }
    private static int appUid() throws Exception {
        String output = new String(execute("cmd","package","list","packages","-U",Config.SETTINGS), StandardCharsets.UTF_8);
        Matcher match = Pattern.compile("(?m)^package:com\\.android\\.settings uid:(\\d+)\\s*$").matcher(output);
        if (!match.find()) throw new SecurityException("Settings package is not installed");
        return Integer.parseInt(match.group(1));
    }
    private static String homePackage() throws Exception {
        String resolved=new String(execute("cmd","package","resolve-activity","--brief","-a","android.intent.action.MAIN","-c","android.intent.category.HOME"),StandardCharsets.UTF_8);
        Matcher match=Pattern.compile("(?m)^([A-Za-z][A-Za-z0-9_]*(?:\\.[A-Za-z0-9_]+)+)/[^\\s]+\\s*$").matcher(resolved);
        if(!match.find() || "android".equals(match.group(1)))throw new IllegalStateException("Önce varsayılan başlatıcıyı seç");
        return match.group(1);
    }
    private static String homeHash(String home) throws Exception {
        String path = new String(execute("pm","path",home), StandardCharsets.UTF_8).trim();
        if (!path.startsWith("package:") || path.contains("\n")) throw new IllegalStateException("Unsupported split launcher");
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (InputStream in=Files.newInputStream(Paths.get(path.substring(8)))) {
            byte[] buffer=new byte[65536];int n;while((n=in.read(buffer))!=-1)hash.update(buffer,0,n);
        }
        StringBuilder hex=new StringBuilder();for(byte b:hash.digest())hex.append(String.format("%02x",b&255));return hex.toString();
    }
    private static void homeStart() throws Exception {
        execute("am","start","-a","android.intent.action.MAIN","-c","android.intent.category.HOME");
    }
    private static byte[] exportHome() throws Exception {
        String home=homePackage();Path data=Paths.get("/data/user/0/"+home);
        execute("am","force-stop",home);
        try {
            JSONObject manifest=new JSONObject().put("schema",1).put("package",home).put("apk_sha256",homeHash(home))
                    .put("android_sdk",Build.VERSION.SDK_INT);
            ByteArrayOutputStream result=new ByteArrayOutputStream();
            long total=0;int count=0;
            try(ZipOutputStream zip=new ZipOutputStream(result)) {
                zip.putNextEntry(new ZipEntry("artisan-launcher.json"));
                zip.write(manifest.toString().getBytes(StandardCharsets.UTF_8));zip.closeEntry();
                for(String scope:SCOPES) {
                    Path start=data.resolve(scope); if(!Files.isDirectory(start))continue;
                    try(java.util.stream.Stream<Path> files=Files.walk(start)) {
                        for(Path path:(Iterable<Path>)files::iterator) {
                            if(Files.isSymbolicLink(path))throw new IllegalArgumentException("Symbolic launcher file");
                            if(!Files.isRegularFile(path))continue;
                            total+=Files.size(path);
                            if(total>LIMIT || ++count>20000)throw new IllegalArgumentException("Launcher archive is too large");
                            zip.putNextEntry(new ZipEntry(data.relativize(path).toString()));
                            Files.copy(path,zip);zip.closeEntry();
                            if(result.size()>LIMIT)throw new IllegalArgumentException("Launcher archive is too large");
                        }
                    }
                }
            }
            return result.toByteArray();
        } finally { homeStart(); }
    }
    private static void importHome(byte[] bytes) throws Exception {
        String home=homePackage();Path dataDirectory=Paths.get("/data/user/0/"+home);
        Files.createDirectories(BACKUPS); Os.chmod(BACKUPS.toString(),0700);
        // Stage under the launcher's own CE encryption policy; cross-policy renames fail on FBE.
        Path stage=Files.createTempDirectory(dataDirectory,".artisan-restore-");
        JSONObject manifest=null; Set<String> names=new HashSet<>(); long total=0;
        try(ZipInputStream zip=new ZipInputStream(new ByteArrayInputStream(bytes))) {
            ZipEntry entry;
            while((entry=zip.getNextEntry())!=null) {
                String name=entry.getName();
                if(name.equals("artisan-launcher.json")) {
                    if(manifest!=null)throw new IllegalArgumentException("Duplicate manifest");
                    manifest=new JSONObject(new String(read(zip,16384),StandardCharsets.UTF_8));continue;
                }
                if(entry.isDirectory() || !names.add(name) || names.size()>20000)
                    throw new IllegalArgumentException("Invalid archive entry");
                boolean allowed=false;for(String scope:SCOPES)allowed|=name.startsWith(scope+"/");
                Path destination=stage.resolve(name).normalize();
                if(!allowed || !destination.startsWith(stage) || name.contains("\\") || name.startsWith("/"))
                    throw new IllegalArgumentException("Invalid archive path");
                byte[] data=read(zip,(int)Math.min(LIMIT-total,LIMIT)); total+=data.length;
                Files.createDirectories(destination.getParent());Files.write(destination,data);
            }
        } catch(Exception e) { removeTree(stage); throw e; }
        if(manifest==null || manifest.optInt("schema")!=1 || !home.equals(manifest.optString("package"))
                || !homeHash(home).equals(manifest.optString("apk_sha256")) || names.isEmpty()) {
            removeTree(stage); throw new IllegalArgumentException("Yedek bu başlatıcı sürümüyle eşleşmiyor");
        }
        StructStat owner=Os.stat(dataDirectory.toString());
        try(java.util.stream.Stream<Path> paths=Files.walk(stage)) {
            for(Path path:(Iterable<Path>)paths::iterator) {
                Os.chown(path.toString(),owner.st_uid,owner.st_gid);Os.chmod(path.toString(),Files.isDirectory(path)?0770:0660);
            }
        }
        Path previous=Files.createTempDirectory(dataDirectory,".artisan-previous-");
        execute("am","force-stop",home);
        Set<String> moved=new HashSet<>(), installed=new HashSet<>();
        try {
            for(String scope:SCOPES) {
                if(!Files.isDirectory(stage.resolve(scope)))continue;
                if(Files.exists(dataDirectory.resolve(scope))){Files.move(dataDirectory.resolve(scope),previous.resolve(scope));moved.add(scope);}
                Files.move(stage.resolve(scope),dataDirectory.resolve(scope));installed.add(scope);
            }
            execute("restorecon","-RF",dataDirectory.toString());
        } catch(Exception e) {
            for(String scope:installed)removeTree(dataDirectory.resolve(scope));
            for(String scope:moved)Files.move(previous.resolve(scope),dataDirectory.resolve(scope));
            execute("restorecon","-RF",dataDirectory.toString());throw e;
        } finally { removeTree(stage);homeStart(); }
    }
    private static void removeTree(Path path) throws Exception {
        if(!Files.exists(path))return;
        try(java.util.stream.Stream<Path> paths=Files.walk(path)) {
            for(Path file:(Iterable<Path>)paths.sorted(java.util.Comparator.reverseOrder())::iterator)Files.delete(file);
        }
    }
    private static byte[] performance() throws Exception {
        JSONObject values=new JSONObject().put("sdk",Build.VERSION.SDK_INT).put("model",Build.MODEL);
        for(String file:new String[]{"/sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq",
                "/sys/devices/system/cpu/cpufreq/policy4/scaling_cur_freq","/sys/devices/system/cpu/cpufreq/policy6/scaling_cur_freq",
                "/sys/kernel/gpu/gpu_clock","/sys/class/power_supply/battery/temp","/sys/class/power_supply/battery/voltage_now",
                "/sys/class/power_supply/battery/current_now"}) {
            Path path=Paths.get(file);if(Files.isReadable(path))values.put(file,new String(Files.readAllBytes(path),StandardCharsets.UTF_8).trim());
        }
        values.put("performance_state",new String(execute("getprop","vendor.s10.performance.state"),StandardCharsets.UTF_8).trim());
        return values.toString(2).getBytes(StandardCharsets.UTF_8);
    }
    private static byte[] nativeSettings() throws Exception {
        JSONObject values=new JSONObject();
        for(String key:new String[]{"lock_screen_show_only_unseen_notifications","lock_screen_allow_remote_input",
                "notification_history_enabled","show_notification_category_setting","icon_blacklist","clock_seconds"}) {
            String value=new String(execute("settings","get","secure",key),StandardCharsets.UTF_8).trim();
            values.put("secure:"+key,"null".equals(value)?JSONObject.NULL:value);
        }
        String timeout=new String(execute("settings","get","system","screen_off_timeout"),StandardCharsets.UTF_8).trim();
        values.put("system:screen_off_timeout","null".equals(timeout)?JSONObject.NULL:timeout);
        return values.toString().getBytes(StandardCharsets.UTF_8);
    }
    private static void restartHome() throws Exception {
        String home=homePackage();execute("am","force-stop",home);
        if("com.sec.android.app.launcher".equals(home)) {
            String pack=new String(execute("settings","get","global","ac_icon_pack"),StandardCharsets.UTF_8).trim();
            Path current=BACKUPS.resolve("icon-pack");
            String previous=Files.isRegularFile(current)?new String(Files.readAllBytes(current),StandardCharsets.UTF_8):"null";
            if(!pack.equals(previous)) {
                Path icons=Files.createTempDirectory(Paths.get("/data/user/0/"+home),".artisan-icons-");
                for(String name:new String[]{"Icon.db","Icon.db-shm","Icon.db-wal","FolderIcon.db","FolderIcon.db-shm","FolderIcon.db-wal"}) {
                    Path file=Paths.get("/data/user/0/"+home+"/databases/"+name);
                    if(Files.isRegularFile(file))Files.move(file,icons.resolve(name));
                }
                Files.createDirectories(BACKUPS);Files.write(current,pack.getBytes(StandardCharsets.UTF_8));
            }
        }
        homeStart();
    }
    public static void main(String[] args) throws Exception {
        if(Os.getuid()!=0)throw new SecurityException("Root broker requires uid 0");
        try(LocalServerSocket server=new LocalServerSocket(SOCKET)) {
            PERFORMANCE.start();
            TELEMETRY.start();
            for(;;)try(LocalSocket socket=server.accept()) {
                socket.setSoTimeout(30000);
                int uid=socket.getPeerCredentials().getUid();
                if(uid!=0 && uid!=2000 && uid!=appUid())continue;
                DataInputStream input=new DataInputStream(socket.getInputStream());
                DataOutputStream output=new DataOutputStream(socket.getOutputStream());
                try {
                    String command=input.readUTF();byte[] result;
                    if("ping".equals(command))result="ArtisanControl/1".getBytes(StandardCharsets.UTF_8);
                    else if("launcher-export".equals(command))result=exportHome();
                    else if("launcher-import".equals(command)) {
                        int size=input.readInt();if(size<1 || size>LIMIT)throw new IllegalArgumentException("Invalid archive size");
                        byte[] bytes=new byte[size];input.readFully(bytes);importHome(bytes);result=new byte[0];
                    } else if("restart-home".equals(command)) {restartHome();result=new byte[0];}
                    else if("performance".equals(command))result=performance();
                    else if("performance-control".equals(command))result=PERFORMANCE.status();
                    else if("performance-config".equals(command)){
                        int size=input.readInt();if(size<1||size>1024)throw new IllegalArgumentException("Invalid OC config size");
                        byte[] bytes=new byte[size];input.readFully(bytes);result=PERFORMANCE.configure(bytes);
                    }
                    else if("telemetry-status".equals(command))result=TELEMETRY.status();
                    else if("telemetry-forget".equals(command))result=TELEMETRY.forget();
                    else if("telemetry-config".equals(command)||"telemetry-preview".equals(command)||"telemetry-report".equals(command)){
                        int size=input.readInt();if(size<1||size>256)throw new IllegalArgumentException("Invalid telemetry request size");
                        byte[] bytes=new byte[size];input.readFully(bytes);
                        if("telemetry-config".equals(command))result=TELEMETRY.configure(bytes);
                        else{String category=new String(bytes,StandardCharsets.UTF_8);result="telemetry-preview".equals(command)?TELEMETRY.preview(category):TELEMETRY.send(category);}
                    }
                    else if("native-settings".equals(command))result=nativeSettings();
                    else if("reboot".equals(command)||"recovery".equals(command)||"download".equals(command)) {
                        output.writeBoolean(true);output.writeInt(0);output.flush();
                        execute("svc","power","reboot","reboot".equals(command)?"":command);continue;
                    } else if("shutdown".equals(command)) {
                        output.writeBoolean(true);output.writeInt(0);output.flush();execute("svc","power","shutdown");continue;
                    } else throw new IllegalArgumentException("Unknown command");
                    output.writeBoolean(true);output.writeInt(result.length);output.write(result);output.flush();
                } catch(Throwable t) {
                    byte[] message=String.valueOf(t.getMessage()).getBytes(StandardCharsets.UTF_8);
                    output.writeBoolean(false);output.writeInt(message.length);output.write(message);output.flush();
                    Config.failure("root broker",t);
                }
            } catch(Throwable t) {Config.failure("root client",t);}
        }
    }
}
