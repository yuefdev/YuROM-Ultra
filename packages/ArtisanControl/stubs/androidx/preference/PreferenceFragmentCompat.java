// SPDX-License-Identifier: GPL-3.0-or-later
package androidx.preference;
public abstract class PreferenceFragmentCompat extends androidx.fragment.app.Fragment {
    public PreferenceFragmentCompat(){}
    public PreferenceManager getPreferenceManager(){return null;}
    public PreferenceScreen getPreferenceScreen(){return null;}
    public void setPreferenceScreen(PreferenceScreen screen){}
    public abstract void onCreatePreferences(android.os.Bundle state,String key);
}
