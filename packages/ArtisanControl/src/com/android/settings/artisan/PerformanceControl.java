// SPDX-License-Identifier: GPL-3.0-or-later
package com.android.settings.artisan;

import android.app.AlertDialog;
import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import org.json.JSONObject;

/** Native Settings control surface; all tuning is performed by the fixed-operation broker. */
final class PerformanceControl {
    private static final String[] MODES={"rom","auto","oc","stock"};
    private static final String[] LABELS={"ROM profili (mevcut ayarlar)","Akıllı otomatik","OC (ısıl korumalı)","Stok sınırlar / undervolt kapalı"};
    private final Context context;
    private final ExecutorService worker;
    private final Handler main=new Handler(Looper.getMainLooper());
    private String mode="rom";
    private int margin=3;
    private boolean dirty,busy;
    PerformanceControl(Context context,ExecutorService worker){this.context=context;this.worker=worker;}
    private int dp(int value){return Math.round(value*context.getResources().getDisplayMetrics().density);}
    AlertDialog show(){
        LinearLayout panel=new LinearLayout(context);panel.setOrientation(LinearLayout.VERTICAL);panel.setPadding(dp(20),dp(8),dp(20),0);
        TextView status=new TextView(context);status.setText("Kernel ve sensörler kontrol ediliyor…");panel.addView(status);
        Button advanced=new Button(context);advanced.setText("Gelişmiş ayarlar");panel.addView(advanced);
        Button stock=new Button(context);stock.setText("Akıllı OC’yi kapat · stok sınırlara dön");panel.addView(stock);
        LinearLayout details=new LinearLayout(context);details.setOrientation(LinearLayout.VERTICAL);details.setVisibility(View.GONE);panel.addView(details);
        ListView modes=new ListView(context);modes.setChoiceMode(ListView.CHOICE_MODE_SINGLE);
        modes.setAdapter(new ArrayAdapter<>(context,android.R.layout.simple_list_item_single_choice,LABELS));details.addView(modes,new LinearLayout.LayoutParams(-1,dp(212)));
        Button voltage=new Button(context);voltage.setText("Undervolt üst sınırı: −%3");details.addView(voltage);
        Button selectedApply=new Button(context);selectedApply.setText("Seçili profili uygula");details.addView(selectedApply);
        TextView hint=new TextView(context);hint.setText("Tek dokunuşla otomatik ayar. Küçük cihaz-içi model sıcaklık/yük tepkisini öğrenir. En çok 3,016 GHz CPU, 806 MHz GPU ve −%3 marj; termal korumalar korunur.");
        hint.setPadding(0,dp(8),0,dp(8));panel.addView(hint);
        AlertDialog dialog=new AlertDialog.Builder(context).setTitle("Akıllı OC ve undervolt").setView(panel).setPositiveButton("Akıllı ayarla",null).setNegativeButton("Kapat",null).create();
        advanced.setOnClickListener(view->details.setVisibility(details.getVisibility()==View.GONE?View.VISIBLE:View.GONE));
        java.util.function.Consumer<JSONObject> display=value->{
            if(!dialog.isShowing())return;
            boolean available=value.optBoolean("available");
            if(!dirty){mode=value.optString("mode","rom");margin=value.optInt("undervolt",3);modes.setItemChecked(Arrays.asList(MODES).indexOf(mode),true);}
            voltage.setText("Undervolt üst sınırı: −%"+margin);voltage.setEnabled(available&&!busy);
            modes.setEnabled(available&&!busy);dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(available&&!busy);
            selectedApply.setEnabled(available&&!busy);stock.setEnabled(available&&!busy);
            JSONObject actual=value.optJSONObject("actual");
            String text=value.optString("reason");
            if(actual!=null)text+=String.format(Locale.ROOT,"\nCPU üst sınırı: %.3f GHz · GPU: %d MHz\nCPU: %.1f °C · Pil: %.1f °C / %%%d\nYük: %%%d · Voltaj marjı: %d / %d / %d / %d%%",
                    actual.optInt("big")/1000000.0,actual.optInt("gpu")/1000,value.optInt("cpu_temp")/1000.0,value.optInt("battery_temp")/10.0,value.optInt("capacity"),value.optInt("load"),
                    actual.optInt("lit_uv"),actual.optInt("mid_uv"),actual.optInt("big_uv"),actual.optInt("gpu_uv"));
            if(value.optBoolean("health_pending"))text+="\n60 saniyelik uygulama kontrolü sürüyor";
            text+="\nCihaz-içi model: "+(value.optBoolean("model_ready")?"etkin":"cihazı tanıyor")+" ("+value.optInt("model_samples")+" örnek)";
            if(value.optBoolean("model_ready"))text+=String.format(Locale.ROOT,"\n30 sn ısı tahmini: %.1f °C",value.optInt("forecast_cpu_temp")/1000.0);
            if(!value.optString("error").isEmpty())text+="\n"+value.optString("error");status.setText(text);
        };
        Runnable refresh=new Runnable(){public void run(){
            if(!dialog.isShowing()||worker.isShutdown())return;
            if(!busy){busy=true;worker.execute(()->{try{JSONObject result=new JSONObject(new String(ArtisanSettings.broker("performance-control",null),StandardCharsets.UTF_8));main.post(()->{busy=false;display.accept(result);});}
                catch(Exception e){main.post(()->{busy=false;if(dialog.isShowing()){status.setText(e.getMessage());dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(false);}});}});}
            main.postDelayed(this,5000);
        }};
        modes.setOnItemClickListener((parent,view,position,id)->{mode=MODES[position];dirty=true;});
        voltage.setOnClickListener(view->new AlertDialog.Builder(context).setTitle("En yüksek undervolt marjı").setSingleChoiceItems(new String[]{"Kapalı (%0)","−%1","−%2","−%3"},margin,
                (choice,index)->{margin=index;dirty=true;voltage.setText("Undervolt üst sınırı: −%"+margin);choice.dismiss();}).setNegativeButton("İptal",null).show());
        dialog.setOnDismissListener(ignored->main.removeCallbacks(refresh));dialog.show();dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(false);
        java.util.function.BiConsumer<String,Integer> apply=(selected,selectedMargin)->{
            if(busy||worker.isShutdown())return;busy=true;modes.setEnabled(false);voltage.setEnabled(false);selectedApply.setEnabled(false);stock.setEnabled(false);dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(false);
            worker.execute(()->{try{
                byte[] config=new JSONObject().put("mode",selected).put("undervolt",selectedMargin).toString().getBytes(StandardCharsets.UTF_8);
                JSONObject result=new JSONObject(new String(ArtisanSettings.broker("performance-config",config),StandardCharsets.UTF_8));main.post(()->{dirty=false;busy=false;display.accept(result);});
            }catch(Exception e){main.post(()->{busy=false;if(dialog.isShowing()){status.setText("Profil uygulanamadı: "+e.getMessage());dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(true);selectedApply.setEnabled(true);stock.setEnabled(true);modes.setEnabled(true);voltage.setEnabled(true);}});}});
        };
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view->apply.accept("auto",margin));
        stock.setOnClickListener(view->apply.accept("stock",0));selectedApply.setOnClickListener(view->apply.accept(mode,margin));refresh.run();return dialog;
    }
}
