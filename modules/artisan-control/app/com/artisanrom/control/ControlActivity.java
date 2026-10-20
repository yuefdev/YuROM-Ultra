// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import android.app.*;
import android.content.*;
import android.content.pm.*;
import android.net.Uri;
import android.os.*;
import android.provider.Settings;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Portable settings client. Only advertised adapter capabilities can be changed. */
public final class ControlActivity extends Activity {
    private JSONArray features;
    private Set<String> capabilities = new HashSet<>();
    private LinearLayout body;
    private String category = "Uygulamalar";
    private static final int EXPORT = 10, IMPORT = 11;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        boolean dark = (getResources().getConfiguration().uiMode & 48) == 32;
        setTheme(dark ? android.R.style.Theme_DeviceDefault : android.R.style.Theme_DeviceDefault_Light);
        setTitle("Artisan Kontrol");
        try {
            features = new JSONObject(read(getAssets().open("features.json"))).getJSONArray("features");
            JSONArray caps = new JSONArray(Settings.Global.getString(getContentResolver(), "artisan_capabilities"));
            for (int i=0; i<caps.length(); i++) capabilities.add(caps.getString(i));
        } catch (Exception ignored) { if (features == null) features = new JSONArray(); }
        capabilities.add("native");
        render();
    }

    private static String read(InputStream input) throws IOException {
        try (InputStream in=input; ByteArrayOutputStream out=new ByteArrayOutputStream()) {
            byte[] b=new byte[4096]; int n;
            while ((n=in.read(b))!=-1) {
                if (out.size()+n > 262144) throw new IOException("Dosya çok büyük");
                out.write(b,0,n);
            }
            return new String(out.toByteArray(),StandardCharsets.UTF_8);
        }
    }

    private String value(JSONObject f) {
        String ns=f.optString("namespace","global"), key=f.optString("setting","artisan_"+f.optString("key"));
        String v="system".equals(ns)?Settings.System.getString(getContentResolver(),key):
            "secure".equals(ns)?Settings.Secure.getString(getContentResolver(),key):Settings.Global.getString(getContentResolver(),key);
        if (v==null) return f.optString("default");
        return f.optBoolean("inverted") ? ("1".equals(v)?"0":"1") : v;
    }

    private void put(JSONObject f, String value) throws Exception {
        validate(f,value);
        String key=f.optString("setting","artisan_"+f.getString("key")), ns=f.optString("namespace","global");
        String stored=f.optBoolean("inverted")?("1".equals(value)?"0":"1"):value;
        boolean ok="system".equals(ns)?Settings.System.putString(getContentResolver(),key,stored):
            "secure".equals(ns)?Settings.Secure.putString(getContentResolver(),key,stored):Settings.Global.putString(getContentResolver(),key,stored);
        if (!ok) throw new IOException("Ayar yazılamadı");
        if ("animation_scale".equals(f.getString("key")))
            for (String s:new String[]{"window_animation_scale","transition_animation_scale","animator_duration_scale"})
                Settings.Global.putString(getContentResolver(),s,value);
    }

    private static void validate(JSONObject f,String v) throws Exception {
        if (v.length()>32768) throw new IllegalArgumentException("Ayar çok uzun");
        String type=f.getString("type");
        if ("bool".equals(type) && !v.equals("0") && !v.equals("1")) throw new IllegalArgumentException("Geçersiz anahtar");
        if ("choice".equals(type)) {
            JSONArray a=f.getJSONArray("values"); boolean found=false;
            for(int i=0;i<a.length();i++) found|=v.equals(a.getString(i));
            if(!found) throw new IllegalArgumentException("Desteklenmeyen değer");
        }
        if ("apps".equals(type)) {
            JSONArray a=new JSONArray(v);
            for(int i=0;i<a.length();i++) if(!a.getString(i).matches("[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)+")) throw new IllegalArgumentException("Geçersiz paket adı");
        }
        if ("json".equals(type)) {
            JSONObject profiles=new JSONObject(v);
            for(Iterator<String> it=profiles.keys();it.hasNext();) {
                String pkg=it.next();
                if(!pkg.matches("[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)+"))throw new IllegalArgumentException("Geçersiz paket adı");
                JSONObject profile=profiles.getJSONObject(pkg);
                for(Iterator<String> fields=profile.keys();fields.hasNext();) {
                    String field=fields.next();
                    if(!Arrays.asList("MODEL","BRAND","MANUFACTURER","DEVICE","PRODUCT").contains(field) || !(profile.get(field) instanceof String)) throw new IllegalArgumentException("Geçersiz profil alanı: "+field);
                }
            }
        }
        if ("icon_pack".equals(f.getString("key")) && !v.isEmpty() && !v.matches("[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)+")) throw new IllegalArgumentException("Geçersiz simge paketi");
    }

    private void render() {
        LinearLayout page=new LinearLayout(this); page.setOrientation(1);
        TextView subtitle=new TextView(this); subtitle.setText("ROM'lar arası ortak ayarlar • v1"); subtitle.setPadding(24,16,24,16); page.addView(subtitle);
        Spinner categories=new Spinner(this); LinkedHashSet<String> names=new LinkedHashSet<>();
        for(int i=0;i<features.length();i++)names.add(features.optJSONObject(i).optString("category"));
        names.add("Araçlar"); List<String> list=new ArrayList<>(names);
        categories.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,list));
        categories.setSelection(Math.max(0,list.indexOf(category))); page.addView(categories);
        ScrollView scroll=new ScrollView(this);body=new LinearLayout(this);body.setOrientation(1);body.setPadding(24,8,24,32);scroll.addView(body);page.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        setContentView(page);
        categories.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(android.widget.AdapterView<?> p){}
            public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){category=list.get(pos);renderRows();}
        });
    }

    private void renderRows() {
        body.removeAllViews();
        if (checkSelfPermission("android.permission.WRITE_SECURE_SETTINGS")!=PackageManager.PERMISSION_GRANTED) {
            text("Yetki kurulmadı. ROM entegrasyonunu veya belgelenmiş ADB kurulumunu tamamlayın.");
        }
        if(category.equals("Araçlar")){tools();return;}
        for(int i=0;i<features.length();i++) {
            JSONObject f=features.optJSONObject(i);if(!category.equals(f.optString("category")))continue;
            boolean supported=capabilities.contains(f.optString("cap"));
            boolean permitted=checkSelfPermission("android.permission.WRITE_SECURE_SETTINGS")==PackageManager.PERMISSION_GRANTED;
            boolean enabled=supported&&permitted;
            String title=f.optString("title"), type=f.optString("type");
            if(type.equals("bool")) {
                Switch sw=new Switch(this);sw.setText(title);sw.setChecked(value(f).equals("1"));sw.setPadding(0,18,0,18);sw.setEnabled(enabled);body.addView(sw);
                sw.setOnCheckedChangeListener((b,checked)->{try{put(f,checked?"1":"0");}catch(Exception e){error(e);sw.setOnCheckedChangeListener(null);sw.setChecked(!checked);}});
            } else {
                Button button=new Button(this);String shown=value(f);
                if(type.equals("choice")){JSONArray a=f.optJSONArray("values"),l=f.optJSONArray("labels");for(int j=0;j<a.length();j++)if(a.optString(j).equals(shown)){shown=l.optString(j);break;}}
                if(type.equals("apps")) {try{shown=new JSONArray(shown).length()+" uygulama";}catch(Exception e){shown="0 uygulama";}}
                if(type.equals("json"))shown="Profilleri düzenle";
                button.setText(title+"\n"+shown);button.setAllCaps(false);button.setEnabled(enabled);body.addView(button);
                button.setOnClickListener(v->{try{edit(f);}catch(Exception e){error(e);}});
            }
            if(!supported)text("Bu ROM için bağlantı henüz kurulmadı.");
            else if(f.has("note"))text(f.optString("note"));
        }
    }

    private void edit(JSONObject f)throws Exception {
        String type=f.getString("type");
        if(type.equals("choice")) {
            JSONArray labels=f.getJSONArray("labels"),values=f.getJSONArray("values");String[] items=new String[labels.length()];int checked=-1;
            for(int i=0;i<items.length;i++){items[i]=labels.getString(i);if(values.getString(i).equals(value(f)))checked=i;}
            new AlertDialog.Builder(this).setTitle(f.getString("title")).setSingleChoiceItems(items,checked,(d,n)->{try{put(f,values.getString(n));d.dismiss();renderRows();}catch(Exception e){error(e);}}).setNegativeButton("Vazgeç",null).show();
        } else if(type.equals("apps")) {
            List<ApplicationInfo> apps=getPackageManager().getInstalledApplications(0);
            apps.sort(Comparator.comparing(a->getPackageManager().getApplicationLabel(a).toString(),String.CASE_INSENSITIVE_ORDER));
            Set<String> selected=new HashSet<>();JSONArray stored=new JSONArray(value(f));for(int i=0;i<stored.length();i++)selected.add(stored.getString(i));
            String[] labels=new String[apps.size()];boolean[] checked=new boolean[apps.size()];
            for(int i=0;i<apps.size();i++){ApplicationInfo a=apps.get(i);labels[i]=getPackageManager().getApplicationLabel(a)+"\n"+a.packageName;checked[i]=selected.contains(a.packageName);}
            new AlertDialog.Builder(this).setTitle(f.getString("title")).setMultiChoiceItems(labels,checked,(d,n,on)->{if(on)selected.add(apps.get(n).packageName);else selected.remove(apps.get(n).packageName);}).setPositiveButton("Kaydet",(d,n)->{try{put(f,new JSONArray(new TreeSet<>(selected)).toString());renderRows();}catch(Exception e){error(e);}}).setNegativeButton("Vazgeç",null).show();
        } else {
            EditText input=new EditText(this);input.setText(value(f));input.setMinLines(type.equals("json")?6:1);
            new AlertDialog.Builder(this).setTitle(f.getString("title")).setView(input).setPositiveButton("Kaydet",(d,n)->{try{put(f,input.getText().toString());renderRows();}catch(Exception e){error(e);}}).setNegativeButton("Vazgeç",null).show();
        }
    }

    private void text(String value){TextView t=new TextView(this);t.setText(value);t.setTextSize(13);t.setPadding(0,4,0,14);body.addView(t);}
    private void button(String label,Runnable action){Button b=new Button(this);b.setText(label);b.setAllCaps(false);body.addView(b);b.setOnClickListener(v->action.run());}
    private void tools(){
        button("Varsayılan başlatıcı",()->startActivity(new Intent(Settings.ACTION_HOME_SETTINGS)));
        button("Başlatıcıyı yeniden aç",()->command("restart_home"));
        button("Genişletilmiş güç menüsü",()->startActivity(new Intent(this,PowerActivity.class)));
        button("Tüm Artisan / başlatıcı ayarlarını dışa aktar",()->{Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE,"artisan-settings.json");startActivityForResult(i,EXPORT);});
        button("Artisan / başlatıcı ayarlarını içe aktar",()->startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE),IMPORT));
        text("Yedek yalnızca Artisan ayarlarını içerir. Ana ekrandaki simge/widget yerleşimi ve üçüncü taraf başlatıcı verileri içerilmez.");
        button("Performans durumu",()->{String state=property("vendor.s10.performance.state");new AlertDialog.Builder(this).setTitle("Performans").setMessage(Build.MODEL+"\nProfil: "+(state.isEmpty()?"Bu ROM tarafından bildirilmedi":state)+"\nBatarya: "+((BatteryManager)getSystemService(BATTERY_SERVICE)).getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)+"%").setPositiveButton("Tamam",null).show();});
        button("Artisan özelleştirmelerini varsayılana döndür",()->new AlertDialog.Builder(this).setMessage("Artisan ayarları sıfırlanacak. ROM'un diğer ayarları ve ana ekran yerleşimi korunur.").setPositiveButton("Sıfırla",(d,n)->{try{for(int j=0;j<features.length();j++){JSONObject f=features.getJSONObject(j);if(!f.has("setting"))Settings.Global.putString(getContentResolver(),"artisan_"+f.getString("key"),null);}command("restart_home");renderRows();}catch(Exception e){error(e);}}).setNegativeButton("Vazgeç",null).show());
        text("Çalışan bağlantılar: "+new TreeSet<>(capabilities));
    }

    static String property(String name){try{return (String)Class.forName("android.os.SystemProperties").getMethod("get",String.class).invoke(null,name);}catch(Exception e){return "";}}
    void command(String action){try{Settings.Global.putString(getContentResolver(),"artisan_command",SystemClock.elapsedRealtime()+":"+action);Toast.makeText(this,"İstek gönderildi",Toast.LENGTH_SHORT).show();}catch(Exception e){error(e);}}
    private void error(Exception e){new AlertDialog.Builder(this).setTitle("Uygulanamadı").setMessage(e.toString()).setPositiveButton("Tamam",null).show();}

    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);if(result!=RESULT_OK||data==null)return;
        try{
            Uri uri=data.getData();
            if(request==EXPORT){JSONObject values=new JSONObject();for(int i=0;i<features.length();i++){JSONObject f=features.getJSONObject(i);if(capabilities.contains(f.getString("cap")))values.put(f.getString("key"),value(f));}JSONObject backup=new JSONObject().put("schema",1).put("settings",values);try(OutputStream out=getContentResolver().openOutputStream(uri)){out.write(backup.toString(2).getBytes(StandardCharsets.UTF_8));}}
            if(request==IMPORT){JSONObject backup=new JSONObject(read(getContentResolver().openInputStream(uri)));if(backup.getInt("schema")!=1)throw new IllegalArgumentException("Desteklenmeyen yedek sürümü");JSONObject values=backup.getJSONObject("settings");List<JSONObject> selected=new ArrayList<>();for(int i=0;i<features.length();i++){JSONObject f=features.getJSONObject(i);if(values.has(f.getString("key"))&&capabilities.contains(f.getString("cap"))){validate(f,values.getString(f.getString("key")));selected.add(f);}}new AlertDialog.Builder(this).setMessage(selected.size()+" ayar uygulanacak.").setPositiveButton("İçe aktar",(d,n)->{Map<JSONObject,String> before=new LinkedHashMap<>();try{for(JSONObject f:selected){before.put(f,value(f));put(f,values.getString(f.getString("key")));}renderRows();}catch(Exception e){for(Map.Entry<JSONObject,String> old:before.entrySet())try{put(old.getKey(),old.getValue());}catch(Exception ignored){}error(e);}}).setNegativeButton("Vazgeç",null).show();}
            Toast.makeText(this,request==EXPORT?"Yedek kaydedildi":"Yedek okundu",Toast.LENGTH_SHORT).show();
        }catch(Exception e){error(e);}
    }
}
