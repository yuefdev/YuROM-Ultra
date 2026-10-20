// SPDX-License-Identifier: GPL-3.0-or-later
package androidx.preference;
import android.content.Context;
import android.os.Bundle;
public class Preference {
    public Preference(Context context){}
    public Preference(Context context,android.util.AttributeSet attrs){}
    public final Context getContext(){return null;}
    public final String getKey(){return null;}
    public final Bundle getExtras(){return null;}
    public int getOrder(){return 0;}
    public final void setKey(String key){}
    public void setTitle(CharSequence title){}
    public void setSummary(CharSequence summary){}
    public void setIcon(int resource){}
    public final void setIconSpaceReserved(boolean reserved){}
    public void setOrder(int order){}
    public final void setPersistent(boolean persistent){}
    public void setEnabled(boolean enabled){}
    public final void setFragment(String fragment){}
    public void setOnPreferenceChangeListener(OnPreferenceChangeListener listener){}
    public void setOnPreferenceClickListener(OnPreferenceClickListener listener){}
    public interface OnPreferenceChangeListener {boolean onPreferenceChange(Preference preference,Object value);}
    public interface OnPreferenceClickListener {boolean onPreferenceClick(Preference preference);}
}
