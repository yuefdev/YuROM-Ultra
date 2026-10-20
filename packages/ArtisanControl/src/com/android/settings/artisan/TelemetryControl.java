// SPDX-License-Identifier: GPL-3.0-or-later
package com.android.settings.artisan;

import android.app.AlertDialog;
import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.nio.charset.StandardCharsets;
import java.text.DateFormat;
import java.util.Date;
import java.util.concurrent.ExecutorService;
import org.json.JSONObject;

/** Explicit participation and a structured problem report with a visible payload preview. */
final class TelemetryControl {
    private final Context context;
    private final ExecutorService worker;
    private final Handler main=new Handler(Looper.getMainLooper());
    private AlertDialog dialog,child;
    private TextView status;
    private Button toggle,report,forget;
    private boolean enabled,configured,busy;
    TelemetryControl(Context context,ExecutorService worker){this.context=context;this.worker=worker;}
    private interface Work{byte[] run()throws Exception;}
    private int dp(int value){return Math.round(value*context.getResources().getDisplayMetrics().density);}
    private void buttons(){toggle.setEnabled(!busy&&(!enabled?configured:true));report.setEnabled(!busy&&enabled&&configured);forget.setEnabled(!busy&&configured);}
    private void state(byte[] bytes)throws Exception{
        JSONObject result=new JSONObject(new String(bytes,StandardCharsets.UTF_8));enabled=result.optBoolean("enabled");configured=result.optBoolean("configured");
        toggle.setText(enabled?"Paylaşımı kapat":"İstatistik ve hata özeti paylaşımını aç");
        String text=enabled?"Paylaşım açık · günde en fazla bir otomatik gönderim":"Paylaşım kapalı";
        if(!configured)text+="\nBu derlemeye Cloudflare sunucu adresi henüz eklenmedi.";
        else text+="\nSunucu: "+result.optString("endpoint");
        if(result.optLong("last_sent")>0)text+="\nSon gönderim: "+DateFormat.getDateTimeInstance().format(new Date(result.optLong("last_sent")));
        if(!result.optString("error").isEmpty())text+="\n"+result.optString("error");status.setText(text);buttons();
    }
    private void request(Work work,java.util.function.Consumer<byte[]> success){
        if(busy||worker.isShutdown()||!dialog.isShowing())return;busy=true;buttons();
        worker.execute(()->{try{byte[] result=work.run();main.post(()->{busy=false;if(dialog.isShowing()){try{success.accept(result);}catch(Exception e){status.setText(e.getMessage());}buttons();}});}
            catch(Exception e){main.post(()->{busy=false;if(dialog.isShowing()){status.setText("İşlem tamamlanamadı: "+e.getMessage());buttons();}});}});
    }
    private void display(byte[] bytes){try{state(bytes);}catch(Exception e){status.setText(e.getMessage());}}
    AlertDialog show(){
        LinearLayout panel=new LinearLayout(context);panel.setOrientation(LinearLayout.VERTICAL);panel.setPadding(dp(20),dp(8),dp(20),dp(8));
        TextView info=new TextView(context);info.setText("Varsayılan olarak kapalıdır. Açarsan ROM sürümü, cihaz modeli, rastgele kurulum kodu, OC modu ve yalnız sistem uygulamalarının arındırılmış çökme özetleri Cloudflare’a gönderilir.\n\nIMEI, seri numarası, hesaplar, konum, mesajlar ve tam günlükler gönderilmez. Sunucudaki kayıtlar en fazla 90 gün tutulur. Kurulum sayısı paylaşımı açan cihazları kapsar.");panel.addView(info);
        status=new TextView(context);status.setPadding(0,dp(12),0,dp(8));status.setText("Tercih okunuyor…");panel.addView(status);
        toggle=new Button(context);toggle.setText("Paylaşımı aç");panel.addView(toggle);
        report=new Button(context);report.setText("Sorun bildir · önce raporu incele");panel.addView(report);
        forget=new Button(context);forget.setText("Paylaşımı kapat ve sunucudaki verilerimi sil");panel.addView(forget);
        dialog=new AlertDialog.Builder(context).setTitle("İstatistikler ve sorun bildirimi").setView(panel).setNegativeButton("Kapat",null).create();
        toggle.setOnClickListener(view->{final boolean requested=!enabled;request(()->ArtisanSettings.broker("telemetry-config",new JSONObject().put("enabled",requested).toString().getBytes(StandardCharsets.UTF_8)),this::display);});
        report.setOnClickListener(view->{
            String[] labels={"Açılış","Kamera","Parmak izi","Ses / HDMI","DeX","Pil","Performans / OC","Ekran","Diğer"};
            String[] categories={"boot","camera","fingerprint","audio","dex","battery","performance","display","other"};
            child=new AlertDialog.Builder(context).setTitle("Sorun türü").setItems(labels,(choice,index)->{
                byte[] category=categories[index].getBytes(StandardCharsets.UTF_8);
                request(()->ArtisanSettings.broker("telemetry-preview",category),bytes->{
                    child=new AlertDialog.Builder(context).setTitle("Gönderilecek rapor").setMessage(new String(bytes,StandardCharsets.UTF_8))
                        .setPositiveButton("Bu raporu gönder",(confirm,which)->request(()->ArtisanSettings.broker("telemetry-report",category),this::display)).setNegativeButton("İptal",null).show();
                });
            }).setNegativeButton("İptal",null).show();
        });
        forget.setOnClickListener(view->request(()->ArtisanSettings.broker("telemetry-forget",null),this::display));
        dialog.setOnDismissListener(ignored->{if(child!=null)child.dismiss();});dialog.show();request(()->ArtisanSettings.broker("telemetry-status",null),this::display);return dialog;
    }
}
