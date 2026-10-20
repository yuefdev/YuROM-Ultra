// SPDX-License-Identifier: GPL-3.0-or-later
package com.android.settings;
public abstract class SettingsPreferenceFragment extends androidx.preference.PreferenceFragmentCompat {
    public SettingsPreferenceFragment(){}
    public abstract int getMetricsCategory();
    public void onCreatePreferences(android.os.Bundle state,String key){}
    public void onResume(){}
    public void onDestroy(){}
    public void setPreferenceScreen(androidx.preference.PreferenceScreen screen){}
}
