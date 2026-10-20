/* SPDX-License-Identifier: GPL-3.0-or-later */
import java.lang.reflect.Method;
import android.os.Build;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import org.json.JSONObject;

/** Register typed, reversible display resources through the platform overlay API. */
public final class S10DisplayOverlay {
    public static void main(String[] args) throws Exception {
        JSONObject configuration = new JSONObject(new String(Files.readAllBytes(
                Paths.get("/system/etc/s10-display-defaults.json")), StandardCharsets.UTF_8));
        if (configuration.getInt("schema") != 1) throw new IllegalArgumentException("Unsupported display profile schema");
        JSONObject profile = configuration.getJSONObject("models").getJSONObject(Build.MODEL);
        String expectedDevice = profile.getString("device");
        if (!Build.DEVICE.equals(expectedDevice) && !Build.DEVICE.equals(expectedDevice.replace("lte", "")))
            throw new IllegalArgumentException("Display profile does not match the device");
        Class<?> overlayClass = Class.forName("android.content.om.FabricatedOverlay");
        Object overlay = overlayClass.getConstructor(String.class, String.class)
                .newInstance("S10DisplayGeometry", "android");
        overlayClass.getMethod("setOwningPackage", String.class).invoke(overlay, "android");
        overlayClass.getMethod("setResourceValue", String.class, int.class, String.class, String.class)
                .invoke(overlay, "android:string/config_mainBuiltInDisplayCutout", 3,
                        profile.getString("cutout"), null);
        // The donor's no-cutout indicator algorithm has no asymmetric right-camera
        // branch. Reserve the camera width in portrait through its existing inset.
        overlayClass.getMethod("setResourceValue", String.class, float.class, int.class, String.class)
                .invoke(overlay, "android:dimen/status_bar_indicator_corner_padding",
                        (float) profile.getInt("portrait_indicator_padding_dp"), 1, "port");
        Class<?> builderClass = Class.forName("android.content.om.OverlayManagerTransaction$Builder");
        Object builder = builderClass.getConstructor().newInstance();
        builderClass.getMethod("registerFabricatedOverlay", overlayClass).invoke(builder, overlay);
        Class<?> identifierClass = Class.forName("android.content.om.OverlayIdentifier");
        Object identifier = overlayClass.getMethod("getIdentifier").invoke(overlay);
        builderClass.getMethod("setEnabled", identifierClass, boolean.class, int.class)
                .invoke(builder, identifier, true, 0);
        Object transaction = builderClass.getMethod("build").invoke(builder);
        Class<?> binderClass = Class.forName("android.os.IBinder");
        Object binder = Class.forName("android.os.ServiceManager").getMethod("getService", String.class)
                .invoke(null, "overlay");
        Object manager = Class.forName("android.content.om.IOverlayManager$Stub")
                .getMethod("asInterface", binderClass).invoke(null, binder);
        Method commit = Class.forName("android.content.om.IOverlayManager")
                .getMethod("commit", Class.forName("android.content.om.OverlayManagerTransaction"));
        commit.invoke(manager, transaction);
        System.out.println("Enabled android:S10DisplayGeometry for " + Build.MODEL + " with typed portrait camera insets.");
    }
}
