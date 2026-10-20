// SPDX-License-Identifier: GPL-3.0-or-later
package com.artisanrom.control;

import java.util.List;

/** Actual parser regression: private messages/paths and third-party processes are excluded. */
public final class TelemetryPrivacyProbe {
    private static void check(boolean value){if(!value)throw new AssertionError("Telemetry privacy regression");}
    public static void main(String[] args)throws Exception{
        String crash="E/AndroidRuntime( 1234): FATAL EXCEPTION: main\n"+
            "E/AndroidRuntime( 1234): Process: com.android.settings, PID: 1234\n"+
            "E/AndroidRuntime( 1234): java.lang.RuntimeException: user@example.test +905551234567\n"+
            "E/AndroidRuntime( 1234): at android.app.ActivityThread.main(ActivityThread.java:99)\n"+
            "E/AndroidRuntime( 1234): Caused by: java.lang.IllegalStateException: /data/user/0/private\n"+
            "E/AndroidRuntime( 1234): at com.android.settings.Foo.load(Foo.java:42)\n";
        List<RootBrokerCrashSummary.Summary> summaries=RootBrokerCrashSummary.parse(crash+crash);
        check(summaries.size()==1);RootBrokerCrashSummary.Summary summary=summaries.get(0);
        check(summary.exception.equals("java.lang.IllegalStateException"));check(summary.component.equals("com.android.settings"));
        check(summary.frames.size()==1&&summary.frames.get(0).equals("com.android.settings.Foo.load"));check(summary.signature.matches("[0-9a-f]{64}"));
        String output=summary.component+summary.exception+summary.frames+summary.signature;
        for(String privateValue:new String[]{"@","+90555","/data/","Foo.java","1234"})check(!output.contains(privateValue));
        check(RootBrokerCrashSummary.parse(crash.replace("com.android.settings,","com.private.bank," )).isEmpty());
        check(RootBrokerCrashSummary.parse(crash.replace("com.android.settings,","com.samsung.android.smartsuggestions:moneta,")).size()==1);
        check(RootBrokerCrashSummary.parse("FATAL EXCEPTION: main\nProcess: com.android.settings, PID: 1\nsecret text\n").isEmpty());
        check(RootBrokerCrashSummary.parse(crash.replace("at com.android.settings.Foo.load(Foo.java:42)","at /private/path(user@example.test)")).get(0).frames.isEmpty());
        byte[] large=new byte[900000];java.util.Arrays.fill(large,(byte)'x');byte[] suffix=("\n"+crash).getBytes(java.nio.charset.StandardCharsets.UTF_8);
        System.arraycopy(suffix,0,large,large.length-suffix.length,suffix.length);
        List<RootBrokerCrashSummary.Summary> bounded=RootBrokerCrashSummary.parse(new java.io.ByteArrayInputStream(large));
        check(bounded.size()==1&&bounded.get(0).signature.equals(summary.signature));
        System.out.println("PASS: crash summary allowlist, nested causes, deduplication, subprocesses and private message/path exclusion");
    }
}
