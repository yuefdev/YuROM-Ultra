// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import android.app.Activity;
import android.os.Bundle;
import android.provider.Settings;
import android.view.WindowManager;
import android.widget.TextView;

/** A synthetic secure window and settings readout; contains no user data. */
public final class ProbeActivity extends Activity {
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        TextView view=new TextView(this);view.setTextSize(22);view.setPadding(32,120,32,32);
        view.setText("ARTISAN SECURE WINDOW\nFLAG_SECURE = true\nDeveloper = "+Settings.Global.getInt(getContentResolver(),"development_settings_enabled",-1)+"\nADB = "+Settings.Global.getInt(getContentResolver(),"adb_enabled",-1)+"\nModel = "+android.os.Build.MODEL);
        setContentView(view);
    }
}
