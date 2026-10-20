// SPDX-License-Identifier: GPL-3.0-or-later
package com.android.settings.artisan;

import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.media.AudioDeviceCallback;
import android.media.AudioDeviceInfo;
import android.os.Handler;
import android.os.Looper;
import android.net.LocalSocket;
import android.net.LocalSocketAddress;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.View;
import android.widget.EditText;
import android.widget.ArrayAdapter;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import androidx.preference.Preference;
import androidx.preference.PreferenceScreen;
import androidx.preference.SecPreference;
import androidx.preference.SecSwitchPreference;
import com.android.settings.SettingsPreferenceFragment;
import com.artisanrom.control.Config;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

/** Native Samsung Settings preferences; loaded by the Settings APK's own classloader. */
public final class ArtisanSettings extends SettingsPreferenceFragment {
    public static final String FRAGMENT="com.android.settings.artisan.ArtisanSettings";
    private static final int EXPORT=11, IMPORT=12, HOME_EXPORT=13, HOME_IMPORT=14;
    private static final int LIMIT=64*1024*1024;
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private JSONArray catalogue;
    private JSONObject adapter;
    private PreferenceScreen content;
    private String section;
    private boolean powerShown;
    private AlertDialog audioDialog;
    private AlertDialog performanceDialog;
    private AlertDialog telemetryDialog;

    @Override public int getMetricsCategory(){return 0;}
    public static void homepage(SettingsPreferenceFragment fragment){
        PreferenceScreen screen=fragment.getPreferenceScreen();
        if(screen==null || screen.findPreference("artisan_control")!=null)return;
        SecPreference entry=new SecPreference(fragment.getContext(),null);
        entry.setKey("artisan_control");entry.setTitle(Config.BRAND);
        entry.setSummary("Ekran, bildirim, başlatıcı ve sistem özelleştirmeleri");
        entry.setIcon(android.R.drawable.ic_menu_manage);entry.setFragment(FRAGMENT);
        Preference advanced=screen.findPreference("useful_feature");
        entry.setOrder(advanced==null?90:advanced.getOrder()+1);screen.addPreference(entry);
    }
    @Override public void onCreatePreferences(Bundle state,String key) {
        try {
            catalogue=new JSONArray(new String(read(getContext().getAssets().open("artisan/features.json"),1024*1024),StandardCharsets.UTF_8));
            adapter=new JSONObject(new String(read(getContext().getAssets().open("artisan/adapter.json"),65536),StandardCharsets.UTF_8));
            render(getArguments()==null?null:getArguments().getString("section"));
        } catch(Exception e){error(e);}
    }
    @Override public void onResume(){
        super.onResume();
        if(!powerShown && getArguments()!=null && getArguments().getBoolean("power_menu",false)){powerShown=true;power();}
    }
    private android.content.ContentResolver getContentResolver(){return getContext().getContentResolver();}
    private PackageManager getPackageManager(){return getContext().getPackageManager();}
    private SharedPreferences getSharedPreferences(String name,int mode){return getContext().getSharedPreferences("artisan_control_"+name,mode);}
    private void runOnUiThread(Runnable task){if(getActivity()!=null)getActivity().runOnUiThread(task);}
    private int dp(int n){return Math.round(n*getContext().getResources().getDisplayMetrics().density);}
    private void render(String selected) throws Exception {
        section=selected;getActivity().setTitle(selected==null?Config.BRAND:selected);
        content=getPreferenceManager().createPreferenceScreen(getContext());
        if(selected==null){
            Set<String> sections=new LinkedHashSet<>();
            for(int i=0;i<catalogue.length();i++)sections.add(catalogue.getJSONObject(i).getString("section"));
            for(String name:sections){
                Preference category=new SecPreference(getContext(),null);category.setKey("artisan_section_"+sectionsIndex(name));
                category.setTitle(name);category.setFragment(FRAGMENT);category.getExtras().putString("section",name);
                content.addPreference(category);
            }
            Preference github=new SecPreference(getContext(),null);
            github.setKey("yurom_github");github.setTitle("YuROM Ultra · GitHub");github.setSummary(Config.GITHUB);
            github.setOnPreferenceClickListener(view->{try{getActivity().startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(Config.GITHUB)));}
                catch(Exception error){error(error);}return true;});
            content.addPreference(github);
            setPreferenceScreen(content);
            return;
        }
        for(int i=0;i<catalogue.length();i++){
            JSONObject feature=catalogue.getJSONObject(i);if(!selected.equals(feature.getString("section")))continue;
            String key=feature.getString("key"),type=feature.getString("type");
            Preference preference;
            if("bool".equals(type)){
                SecSwitchPreference toggle=new SecSwitchPreference(getContext());toggle.setPersistent(false);
                toggle.setChecked("1".equals(value(feature)));
                toggle.setOnPreferenceChangeListener((view,checked)->save(feature,Boolean.TRUE.equals(checked)?"1":"0"));preference=toggle;
            }else{
                preference=new SecPreference(getContext(),null);
                preference.setOnPreferenceClickListener(view->{if("action".equals(type))action(feature.optString("action"));else edit(feature);return true;});
            }
            preference.setKey(key);preference.setTitle(feature.getString("label"));preference.setIconSpaceReserved(false);
            preference.setSummary("action".equals(type)||"bool".equals(type)?feature.optString("description",""):summary(feature));
            preference.setEnabled(supported(feature));content.addPreference(preference);
        }
        setPreferenceScreen(content);
    }
    private int sectionsIndex(String selected)throws Exception{
        Set<String> names=new LinkedHashSet<>();for(int i=0;i<catalogue.length();i++)names.add(catalogue.getJSONObject(i).getString("section"));
        return new ArrayList<>(names).indexOf(selected);
    }
    private boolean supported(JSONObject feature)throws Exception{
        if(feature.has("namespace")||"action".equals(feature.getString("type")))return true;
        JSONArray supported=adapter.getJSONArray("features");
        for(int i=0;i<supported.length();i++)if(feature.getString("key").equals(supported.getString(i)))return true;
        return false;
    }
    private String raw(JSONObject f)throws Exception{
        String key=f.getString("key"),space=f.optString("namespace","global");
        if("system".equals(space)||"secure".equals(space))return nativeValue(space,key);
        return Settings.Global.getString(getContentResolver(),key);
    }
    private String nativeValue(String space,String key)throws Exception{
        return "system".equals(space)?Settings.System.getString(getContentResolver(),key):Settings.Secure.getString(getContentResolver(),key);
    }
    private String value(JSONObject f)throws Exception{String v=raw(f);return v==null?f.optString("default",""):v;}
    private String summary(JSONObject f)throws Exception{
        String v=value(f);if("packages".equals(f.getString("type")))return v.isEmpty()?"Uygulama seçilmedi":v.split(",").length+" uygulama";
        if("profiles".equals(f.getString("type")))return new JSONObject(v).length()+" uygulama profili";
        return f.has("choices")?f.getJSONObject("choices").optString(v,v):v.isEmpty()?"Sistem varsayılanı":v;
    }
    private void write(JSONObject f,String value)throws Exception{
        String key=f.getString("key"),space=f.optString("namespace","global");boolean ok;
        if("system".equals(space))ok=Settings.System.putString(getContentResolver(),key,value);
        else if("secure".equals(space))ok=Settings.Secure.putString(getContentResolver(),key,value);
        else ok=Settings.Global.putString(getContentResolver(),key,value);
        if(!ok)throw new IllegalStateException("Ayar yazılamadı: "+key);
    }
    private boolean save(JSONObject f,String v){
        try{
            validate(f,v);
            String key=f.getString("key");
            remember(f);
            write(f,v);
            if("ac_clock_format".equals(key))Settings.Secure.putInt(getContentResolver(),"clock_seconds","HH:mm:ss".equals(v)?1:0);
            Preference preference=content.findPreference(key);
            if(preference!=null && !"bool".equals(f.getString("type")))preference.setSummary(summary(f));
            return true;
        }catch(Exception e){error(e);return false;}
    }
    private void remember(JSONObject f)throws Exception{
        SharedPreferences initial=getSharedPreferences("initial",Context.MODE_PRIVATE);String key=f.getString("key");
        if(!initial.contains(key)){String old=raw(f);initial.edit().putString(key,old==null?"\u0000":old).apply();}
        if("ac_clock_format".equals(key)&&!initial.contains("@clock_seconds")){
            String old=nativeValue("secure","clock_seconds");
            initial.edit().putString("@clock_seconds",old==null?"\u0000":old).apply();
        }
    }
    private void edit(JSONObject f){
        try{
            String type=f.getString("type");
            if("packages".equals(type)){packages(f);return;}
            if("choice".equals(type)){
                JSONObject choices=f.getJSONObject("choices");List<String> keys=new ArrayList<>();choices.keys().forEachRemaining(keys::add);
                String[] labels=new String[keys.size()];for(int i=0;i<labels.length;i++)labels[i]=choices.getString(keys.get(i));
                new AlertDialog.Builder(getContext()).setTitle(f.getString("label")).setSingleChoiceItems(labels,keys.indexOf(value(f)),
                    (dialog,which)->{save(f,keys.get(which));dialog.dismiss();}).setNegativeButton("İptal",null).show();return;
            }
            EditText input=new EditText(getContext());input.setText(value(f));input.setSelectAllOnFocus(true);input.setPadding(dp(18),dp(12),dp(18),dp(12));
            if("number".equals(type)||"decimal".equals(type))input.setInputType(InputType.TYPE_CLASS_NUMBER|InputType.TYPE_NUMBER_FLAG_SIGNED|InputType.TYPE_NUMBER_FLAG_DECIMAL);
            else if("profiles".equals(type)){input.setMinLines(8);input.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);}
            new AlertDialog.Builder(getContext()).setTitle(f.getString("label")).setView(input).setPositiveButton("Kaydet",(dialog,which)->save(f,input.getText().toString().trim()))
                    .setNegativeButton("İptal",null).show();
        }catch(Exception e){error(e);}
    }
    private void packages(JSONObject f){
        worker.execute(()->{try{
            List<ApplicationInfo> apps=new ArrayList<>(getPackageManager().getInstalledApplications(0));
            apps.removeIf(a->a.uid<10000||Config.PACKAGE.equals(a.packageName)||Config.SETTINGS.equals(a.packageName));
            apps.sort(Comparator.comparing(a->getPackageManager().getApplicationLabel(a).toString(),String.CASE_INSENSITIVE_ORDER));
            Set<String> chosen=new LinkedHashSet<>();Collections.addAll(chosen,value(f).split(","));chosen.remove("");
            String[] labels=new String[apps.size()];boolean[] checks=new boolean[apps.size()];
            for(int i=0;i<apps.size();i++){ApplicationInfo a=apps.get(i);labels[i]=getPackageManager().getApplicationLabel(a)+"\n"+a.packageName;checks[i]=chosen.contains(a.packageName);}
            runOnUiThread(()->new AlertDialog.Builder(getContext()).setTitle(f.optString("label")).setMultiChoiceItems(labels,checks,(dialog,which,checked)->{
                if(checked)chosen.add(apps.get(which).packageName);else chosen.remove(apps.get(which).packageName);
            }).setPositiveButton("Kaydet",(dialog,which)->save(f,String.join(",",chosen))).setNegativeButton("İptal",null).show());
        }catch(Exception e){runOnUiThread(()->error(e));}});
    }
    public static void validate(JSONObject f,String value)throws Exception{
        String type=f.getString("type");if(value.length()>60000)throw new IllegalArgumentException("Ayar çok uzun");
        if("bool".equals(type)&&!value.equals("0")&&!value.equals("1"))throw new IllegalArgumentException("Geçersiz anahtar değeri");
        if("choice".equals(type)&&!f.getJSONObject("choices").has(value))throw new IllegalArgumentException("Geçersiz seçenek");
        if("number".equals(type)||"decimal".equals(type)){
            double number=Double.parseDouble(value);if(!Double.isFinite(number)||number<f.getDouble("min")||number>f.getDouble("max")
                    ||("number".equals(type)&&number!=Math.rint(number)))throw new IllegalArgumentException("Değer belirtilen aralığın dışında");
            if("ac_dock_count".equals(f.getString("key"))&&number!=-1&&number<4)throw new IllegalArgumentException("Dock için 4–9 veya -1 seç");
        }
        if("colour".equals(type)&&!value.isEmpty()&&!value.matches("#[0-9a-fA-F]{6}"))throw new IllegalArgumentException("Renk biçimi: #RRGGBB");
        if("packages".equals(type)&&!value.isEmpty())for(String pkg:value.split(","))if(!pkg.matches("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+"))throw new IllegalArgumentException("Geçersiz paket adı");
        if("profiles".equals(type)){
            JSONObject profiles=new JSONObject(value);java.util.Iterator<String> names=profiles.keys();
            while(names.hasNext()){
                String pkg=names.next();if(!pkg.matches("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+"))throw new IllegalArgumentException("Geçersiz profil paketi");
                JSONObject profile=profiles.getJSONObject(pkg);java.util.Iterator<String> fields=profile.keys();
                while(fields.hasNext()){String name=fields.next();if(!java.util.Arrays.asList("MODEL","BRAND","MANUFACTURER","DEVICE","PRODUCT","FINGERPRINT").contains(name)
                        ||!(profile.get(name) instanceof String)||profile.getString(name).length()>512)throw new IllegalArgumentException("Geçersiz cihaz profili alanı: "+name);}
            }
        }
    }
    private void action(String name){
        try{
            switch(name){
                case "power":power();break;
                case "audio_output":audioOutput();break;
                case "overclock":performanceDialog=new PerformanceControl(getContext(),worker).show();break;
                case "telemetry":telemetryDialog=new TelemetryControl(getContext(),worker).show();break;
                case "launcher":getActivity().startActivity(new Intent(Settings.ACTION_HOME_SETTINGS));break;
                case "export":create(EXPORT,"yurom-control.json","application/json");break;
                case "import":open(IMPORT,"application/json");break;
                case "home_export":create(HOME_EXPORT,"yurom-launcher.zip","application/zip");break;
                case "home_import":new AlertDialog.Builder(getContext()).setMessage("Başlatıcının mevcut düzeni değişecek. Önce mevcut düzeni yedekle. Yalnız aynı başlatıcı sürümünün yedeği kabul edilir.")
                        .setPositiveButton("Yedeği seç",(d,w)->open(HOME_IMPORT,"application/zip")).setNegativeButton("İptal",null).show();break;
                case "restart_home":background("Başlatıcı yeniden açıldı",()->broker("restart-home",null));break;
                case "performance":worker.execute(()->{try{String result=new String(broker("performance",null),StandardCharsets.UTF_8);
                    runOnUiThread(()->new AlertDialog.Builder(getContext()).setTitle("Canlı cihaz bilgileri").setMessage(result).setPositiveButton("Tamam",null).show());}
                    catch(Exception e){runOnUiThread(()->error(e));}});break;
                case "reset":new AlertDialog.Builder(getContext()).setMessage("YuROM ayarları ilk değerlerine dönecek. Başlatıcı verileri silinmez.")
                        .setPositiveButton("Sıfırla",(d,w)->reset()).setNegativeButton("İptal",null).show();break;
            }
        }catch(Exception e){error(e);}
    }
    private void power(){
        String[] names={"Yeniden başlat","Recovery","Download modu","Kapat"};String[] commands={"reboot","recovery","download","shutdown"};
        new AlertDialog.Builder(getContext()).setTitle("Güç menüsü").setItems(names,(dialog,which)->new AlertDialog.Builder(getContext())
            .setMessage(names[which]+" işlemi şimdi uygulanacak.").setPositiveButton("Uygula",(d,w)->background("İşlem gönderildi",()->broker(commands[which],null)))
            .setNegativeButton("İptal",null).show()).setNegativeButton("İptal",null).show();
    }
    private void audioOutput()throws Exception{
        MediaOutput output=new MediaOutput(getContext());
        LinearLayout panel=new LinearLayout(getContext());panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(16),dp(8),dp(16),0);
        TextView status=new TextView(getContext());status.setText("Bağlı ses çıkışları okunuyor…");panel.addView(status);
        ListView choices=new ListView(getContext());choices.setChoiceMode(ListView.CHOICE_MODE_SINGLE);choices.setEnabled(false);
        panel.addView(choices,new LinearLayout.LayoutParams(-1,dp(260)));
        TextView hint=new TextView(getContext());hint.setText("TV/HDMI, USB ve Bluetooth yalnız sistem bağlı görüyorsa listelenir. Otomatik, özel medya tercihini kaldırır.");
        hint.setPadding(0,dp(8),0,dp(8));panel.addView(hint);
        AlertDialog dialog=new AlertDialog.Builder(getContext()).setTitle("Medya ses çıkışı").setView(panel)
                .setNegativeButton("Kapat",null).setNeutralButton("Yenile",null).create();audioDialog=dialog;
        MediaOutput.State[] current={null};
        java.util.function.Consumer<MediaOutput.State> show=state->{
            if(!dialog.isShowing())return;
            current[0]=state;List<String> labels=new ArrayList<>();labels.add("Otomatik (sistem)");
            for(AudioDeviceInfo device:state.outputs)labels.add(MediaOutput.label(device));
            choices.setAdapter(new ArrayAdapter<>(getContext(),android.R.layout.simple_list_item_single_choice,labels));
            choices.clearChoices();if(state.selected>=0)choices.setItemChecked(state.selected,true);
            status.setText("Şu an medya: "+state.actual());choices.setEnabled(true);
        };
        Runnable refresh=()->{if(worker.isShutdown())return;worker.execute(()->{try{MediaOutput.State state=output.snapshot();runOnUiThread(()->show.accept(state));}
            catch(Exception e){runOnUiThread(()->{if(dialog.isShowing()){status.setText("Ses çıkışları okunamadı");error(e);}});}});};
        choices.setOnItemClickListener((parent,view,position,id)->{
            MediaOutput.State state=current[0];if(state==null||position>state.outputs.size())return;
            AudioDeviceInfo target=position==0?null:state.outputs.get(position-1);choices.setEnabled(false);status.setText("Ses yönlendiriliyor…");
            worker.execute(()->{try{MediaOutput.State applied=output.select(target);runOnUiThread(()->show.accept(applied));}
                catch(Exception e){runOnUiThread(()->{if(dialog.isShowing()){error(e);refresh.run();}});}});
        });
        AudioDeviceCallback callback=new AudioDeviceCallback(){
            @Override public void onAudioDevicesAdded(AudioDeviceInfo[] devices){refresh.run();}
            @Override public void onAudioDevicesRemoved(AudioDeviceInfo[] devices){refresh.run();}
        };
        dialog.setOnDismissListener(ignored->{output.manager().unregisterAudioDeviceCallback(callback);if(audioDialog==dialog)audioDialog=null;});
        dialog.show();dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(ignored->refresh.run());
        output.manager().registerAudioDeviceCallback(callback,new Handler(Looper.getMainLooper()));refresh.run();
    }
    private interface Work{void run()throws Exception;}
    private void background(String done,Work work){worker.execute(()->{try{work.run();runOnUiThread(()->android.widget.Toast.makeText(getContext(),done,android.widget.Toast.LENGTH_LONG).show());}
        catch(Exception e){runOnUiThread(()->error(e));}});}
    private void create(int code,String name,String mime){startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType(mime).putExtra(Intent.EXTRA_TITLE,name),code);}
    private void open(int code,String mime){startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType(mime),code);}
    private JSONObject snapshot()throws Exception{
        JSONObject values=new JSONObject();for(int i=0;i<catalogue.length();i++){JSONObject f=catalogue.getJSONObject(i);if(!"action".equals(f.getString("type")))values.put(f.getString("key"),value(f));}
        return new JSONObject().put("schema",1).put("kind","artisan-control").put("values",values);
    }
    private void importSettings(JSONObject document)throws Exception{
        if(document.optInt("schema")!=1||!"artisan-control".equals(document.optString("kind")))throw new IllegalArgumentException("Geçersiz YuROM yedeği");
        JSONObject values=document.getJSONObject("values");LinkedHashMap<JSONObject,String> changes=new LinkedHashMap<>(),previous=new LinkedHashMap<>();
        for(int i=0;i<catalogue.length();i++){JSONObject f=catalogue.getJSONObject(i);String key=f.getString("key");
            if("action".equals(f.getString("type"))||!values.has(key)||!supported(f))continue;
            String value=values.getString(key);validate(f,value);changes.put(f,value);previous.put(f,raw(f));}
        try{for(java.util.Map.Entry<JSONObject,String> change:changes.entrySet()){remember(change.getKey());write(change.getKey(),change.getValue());}}
        catch(Exception e){for(java.util.Map.Entry<JSONObject,String> old:previous.entrySet())write(old.getKey(),old.getValue());throw e;}
        if(values.has("ac_clock_format"))Settings.Secure.putInt(getContentResolver(),"clock_seconds","HH:mm:ss".equals(values.getString("ac_clock_format"))?1:0);
    }
    private void reset(){try{
        SharedPreferences initial=getSharedPreferences("initial",Context.MODE_PRIVATE);
        for(int i=0;i<catalogue.length();i++){JSONObject f=catalogue.getJSONObject(i);String key=f.getString("key");if("action".equals(f.getString("type")))continue;
            String previous=initial.getString(key,null);if(previous!=null)write(f,"\u0000".equals(previous)?null:previous);else if(key.startsWith("ac_"))write(f,null);}
        String seconds=initial.getString("@clock_seconds",null);
        if(seconds!=null)Settings.Secure.putString(getContentResolver(),"clock_seconds","\u0000".equals(seconds)?null:seconds);
        initial.edit().clear().apply();render(section);
    }catch(Exception e){error(e);}}
    @Override public void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(result!=Activity.RESULT_OK||data==null||data.getData()==null)return;
        Uri uri=data.getData();background("İşlem tamamlandı",()->{
            if(request==EXPORT||request==HOME_EXPORT){byte[] bytes=request==EXPORT?snapshot().toString(2).getBytes(StandardCharsets.UTF_8):broker("launcher-export",null);
                try(OutputStream output=getContentResolver().openOutputStream(uri,"wt")){if(output==null)throw new IllegalStateException("Dosya açılamadı");output.write(bytes);}}
            else{byte[] bytes;try(InputStream input=getContentResolver().openInputStream(uri)){bytes=read(input,request==IMPORT?1024*1024:LIMIT);}
                if(request==IMPORT)importSettings(new JSONObject(new String(bytes,StandardCharsets.UTF_8)));else if(request==HOME_IMPORT)broker("launcher-import",bytes);}
            runOnUiThread(()->{try{render(section);}catch(Exception e){error(e);}});
        });
    }
    static byte[] broker(String command,byte[] payload)throws Exception{
        try(LocalSocket socket=new LocalSocket()){
            socket.connect(new LocalSocketAddress("artisan-control-v1"));socket.setSoTimeout(60000);
            DataOutputStream out=new DataOutputStream(socket.getOutputStream());DataInputStream in=new DataInputStream(socket.getInputStream());
            out.writeUTF(command);if(payload!=null){out.writeInt(payload.length);out.write(payload);}out.flush();
            boolean success=in.readBoolean();int size=in.readInt();if(size<0||size>LIMIT)throw new IllegalArgumentException("Geçersiz yanıt boyutu");
            byte[] bytes=new byte[size];in.readFully(bytes);if(!success)throw new IllegalStateException(new String(bytes,StandardCharsets.UTF_8));return bytes;
        }
    }
    private static byte[] read(InputStream input,int max)throws Exception{
        if(input==null)throw new IllegalArgumentException("Dosya açılamadı");ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buffer=new byte[8192];int n;
        while((n=input.read(buffer))!=-1){if(out.size()+n>max)throw new IllegalArgumentException("Dosya çok büyük");out.write(buffer,0,n);}return out.toByteArray();
    }
    private void error(Throwable e){runOnUiThread(()->{if(getContext()!=null)new AlertDialog.Builder(getContext()).setTitle("İşlem uygulanamadı").setMessage(e.getMessage()==null?e.toString():e.getMessage()).setPositiveButton("Tamam",null).show();});}
    @Override public void onDestroy(){if(audioDialog!=null)audioDialog.dismiss();if(performanceDialog!=null)performanceDialog.dismiss();if(telemetryDialog!=null)telemetryDialog.dismiss();worker.shutdown();super.onDestroy();}
}
