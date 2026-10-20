// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import android.app.*;
import android.os.*;
import android.provider.Settings;

public final class PowerActivity extends Activity {
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        String[] labels={"Yeniden başlat","Recovery","Download modu","Kapat"};
        String[] actions={"reboot","recovery","download","shutdown"};
        new AlertDialog.Builder(this).setTitle("Artisan güç menüsü").setItems(labels,(d,n)->{
            new AlertDialog.Builder(this).setMessage(labels[n]+"?").setPositiveButton("Uygula",(dialog,which)->{
                try{Settings.Global.putString(getContentResolver(),"artisan_command",SystemClock.elapsedRealtime()+":"+actions[n]);}finally{finish();}
            }).setNegativeButton("Vazgeç",(dialog,which)->finish()).setOnCancelListener(dialog->finish()).show();
        }).setOnCancelListener(d->finish()).setNegativeButton("Vazgeç",(d,n)->finish()).show();
    }
}
