// SPDX-License-Identifier: GPL-3.0-or-later
package androidx.fragment.app;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
public class Fragment {
    public Fragment() {}
    public final FragmentActivity getActivity(){return null;}
    public Context getContext(){return null;}
    public final Bundle getArguments(){return null;}
    public void onCreate(Bundle state){}
    public void onResume(){}
    public void onDestroy(){}
    public void onActivityResult(int request,int result,Intent data){}
    public void startActivityForResult(Intent intent,int request){}
}
