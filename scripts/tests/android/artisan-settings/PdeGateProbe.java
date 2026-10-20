// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.tests;

import dalvik.system.PathClassLoader;
import org.json.JSONObject;

/** Exercise the installed provider's unsupported-platform init branch without attaching it to user data. */
public final class PdeGateProbe {
    public static void main(String[] args) throws Exception {
        Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
            error.printStackTrace(System.err);
            System.exit(2);
        });
        Class<?> feature = Class.forName("com.samsung.android.feature.SemFloatingFeature");
        Object instance = feature.getMethod("getInstance").invoke(null);
        boolean supported = (Boolean) feature.getMethod("getBoolean", String.class).invoke(instance,
                "SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_PERSONALIZED_DATA_CORE");
        if (supported) throw new IllegalStateException("This regression check requires the unsupported S10 platform");
        PathClassLoader loader = new PathClassLoader(
                "/system/priv-app/SamsungSmartSuggestions/SamsungSmartSuggestions.apk", PdeGateProbe.class.getClassLoader());
        Class<?> provider = Class.forName("com.samsung.android.moneta.search.provider.DataProvider", true, loader);
        Object unattached = provider.getConstructor().newInstance();
        Object result = provider.getMethod("init").invoke(unattached);
        if (!Boolean.FALSE.equals(result)) throw new IllegalStateException("Unsupported platform scheduled provider initialisation");
        System.out.println(new JSONObject().put("platform_supported", false).put("installed_search_init_returned_false", true)
                .put("provider_attached_to_context", false).put("component_state_changed", false).toString());
    }
}
