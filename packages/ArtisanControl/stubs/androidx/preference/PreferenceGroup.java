// SPDX-License-Identifier: GPL-3.0-or-later
package androidx.preference;
public class PreferenceGroup extends Preference {
    public PreferenceGroup(android.content.Context context,android.util.AttributeSet attrs){super(context,attrs);}
    public boolean addPreference(Preference preference){return false;}
    public final Preference findPreference(CharSequence key){return null;}
}
