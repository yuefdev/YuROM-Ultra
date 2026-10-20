# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned One UI 9 / Honeyspace adapter. Original methods are always retained."""
from s10_ce_storage import CE_TOKENLESS_EDIT,VOLD_SHA256
H="Lcom/artisanrom/control/"
rules={name:[] for name in ("framework","services","systemui","home","settings")}
features={"ac_enabled"}


def hook(target,owner,method,before="",after="",keys=()):
    rules[target].append({"class":"L"+owner+";","method":method,"before":before,"after":after})
    features.update(keys)


for name in ("Global","Secure"):
    hook("framework","android/provider/Settings$"+name,
         "getStringForUser(Landroid/content/ContentResolver;Ljava/lang/String;I)Ljava/lang/String;",
         before=f"    invoke-static {{p0, p1}}, {H}FrameworkHooks;->hideDeveloper(Landroid/content/ContentResolver;Ljava/lang/String;)Z\n"
                "    move-result v0\n    if-eqz v0, :ac_delegate\n    const-string v0, \"0\"\n    return-object v0",
         keys=["ac_hide_developer_apps"])
for method,context in [("newApplication(Ljava/lang/Class;Landroid/content/Context;)Landroid/app/Application;","p1"),
                        ("newApplication(Ljava/lang/ClassLoader;Ljava/lang/String;Landroid/content/Context;)Landroid/app/Application;","p3")]:
    hook("framework","android/app/Instrumentation",method,
         after=f"    invoke-static {{{context}}}, {H}FrameworkHooks;->application(Landroid/content/Context;)V",keys=["ac_device_profiles"])
PM="android/app/ApplicationPackageManager"
for stem,flags in [("Applications","ApplicationInfoFlags"),("Packages","PackageInfoFlags")]:
    for descriptor in ["(I)Ljava/util/List;",f"(Landroid/content/pm/PackageManager${flags};)Ljava/util/List;"]:
        hook("framework",PM,"getInstalled"+stem+descriptor,
             after=f"    iget-object v1, p0, L{PM};->mContext:Landroid/app/ContextImpl;\n"
                   f"    invoke-static {{v1, v0}}, {H}FrameworkHooks;->packages(Landroid/content/Context;Ljava/util/List;)Ljava/util/List;\n    move-result-object v0",
             keys=["ac_filter_apps","ac_hidden_packages"])
for name,flags,returns in [("getPackageInfo","PackageInfoFlags","PackageInfo"),("getApplicationInfo","ApplicationInfoFlags","ApplicationInfo")]:
    for parameter in ["I",f"Landroid/content/pm/PackageManager${flags};"]:
        hook("framework",PM,f"{name}(Ljava/lang/String;{parameter})Landroid/content/pm/{returns};",
             before=f"    iget-object v1, p0, L{PM};->mContext:Landroid/app/ContextImpl;\n"
                    f"    invoke-static {{v1, p1}}, {H}FrameworkHooks;->checkPackage(Landroid/content/Context;Ljava/lang/String;)V")
for name in ("queryIntentActivities","queryIntentServices","queryBroadcastReceivers"):
    for flags in ("I","Landroid/content/pm/PackageManager$ResolveInfoFlags;"):
        hook("framework",PM,f"{name}(Landroid/content/Intent;{flags})Ljava/util/List;",
             after=f"    iget-object v1, p0, L{PM};->mContext:Landroid/app/ContextImpl;\n    invoke-static {{v1, v0}}, {H}FrameworkHooks;->packages(Landroid/content/Context;Ljava/util/List;)Ljava/util/List;\n    move-result-object v0")
hook("framework",PM,"getPackagesForUid(I)[Ljava/lang/String;",
     after=f"    iget-object v1, p0, L{PM};->mContext:Landroid/app/ContextImpl;\n    invoke-static {{v1, v0}}, {H}FrameworkHooks;->packagesForUid(Landroid/content/Context;[Ljava/lang/String;)[Ljava/lang/String;\n    move-result-object v0")
hook("framework",PM,"getDrawable(Ljava/lang/String;ILandroid/content/pm/ApplicationInfo;)Landroid/graphics/drawable/Drawable;",
     after=f"    iget-object v1, p0, L{PM};->mContext:Landroid/app/ContextImpl;\n"
           f"    invoke-static {{v1, p1, p2, p3, v0}}, {H}IconHooks;->icon(Landroid/content/Context;Ljava/lang/String;ILandroid/content/pm/ApplicationInfo;Landroid/graphics/drawable/Drawable;)Landroid/graphics/drawable/Drawable;\n    move-result-object v0",
      keys=["ac_icon_pack"])
for method,badged in [("getIcon",0),("getUnthemedIcon",0),("semGetBadgedIconForIconTray",1)]:
    hook("framework","android/content/pm/LauncherActivityInfo",method+"(I)Landroid/graphics/drawable/Drawable;",
         after=f"    const/4 v1, 0x{badged}\n    invoke-static {{p0, v0, v1}}, {H}IconHooks;->activity(Landroid/content/pm/LauncherActivityInfo;Landroid/graphics/drawable/Drawable;Z)Landroid/graphics/drawable/Drawable;\n    move-result-object v0",keys=["ac_icon_pack"])
hook("framework",PM,"semGetActivityIconForIconTray(Landroid/content/ComponentName;I)Landroid/graphics/drawable/Drawable;",
     after=f"    iget-object v1, p0, L{PM};->mContext:Landroid/app/ContextImpl;\n    invoke-static {{v1, p1, v0}}, {H}IconHooks;->component(Landroid/content/Context;Landroid/content/ComponentName;Landroid/graphics/drawable/Drawable;)Landroid/graphics/drawable/Drawable;\n    move-result-object v0")
for parameter in ("Ljava/lang/String;","Landroid/content/pm/ApplicationInfo;"):
    package="    move-object v2, p1" if parameter=="Ljava/lang/String;" else "    iget-object v2, p1, Landroid/content/pm/ApplicationInfo;->packageName:Ljava/lang/String;"
    hook("framework",PM,"semGetApplicationIconForIconTray("+parameter+"I)Landroid/graphics/drawable/Drawable;",
         after=f"    iget-object v1, p0, L{PM};->mContext:Landroid/app/ContextImpl;\n{package}\n    invoke-static {{v1, v2, v0}}, {H}IconHooks;->application(Landroid/content/Context;Ljava/lang/String;Landroid/graphics/drawable/Drawable;)Landroid/graphics/drawable/Drawable;\n    move-result-object v0")
hook("services","com/android/server/wm/WindowState","isSecureLocked()Z",
     before=f"    invoke-static {{p0}}, {H}SystemHooks;->secureWindow(Ljava/lang/Object;)I\n    move-result v0\n    if-ltz v0, :ac_delegate\n    return v0",
     keys=["ac_secure_capture_apps","ac_secure_capture_all"])
for owner,method,returns in [("ActivityTaskManagerService","registerScreenCaptureObserver(Landroid/os/IBinder;Landroid/app/IScreenCaptureObserver;)V","return-void"),
                             ("WindowManagerService","registerScreenRecordingCallback(Landroid/window/IScreenRecordingCallback;)Z","const/4 v0, 0x0\n    return v0")]:
    hook("services","com/android/server/wm/"+owner,method,
         before=f"    invoke-static {{p0}}, {H}SystemHooks;->quietCapture(Ljava/lang/Object;)Z\n    move-result v0\n    if-eqz v0, :ac_delegate\n    {returns}",
         keys=["ac_capture_detection_apps","ac_capture_detection_all"])
POLICY="com/android/server/policy/PhoneWindowManager"
hook("services",POLICY,"init(Landroid/content/Context;Lcom/android/server/wm/WindowManagerService;)V",
     after=f"    invoke-static {{p0}}, {H}SystemHooks;->install(Ljava/lang/Object;)V")
hook("services",POLICY,"interceptKeyBeforeQueueing(Landroid/view/KeyEvent;I)I",
     before=f"    invoke-static {{p0, p1}}, {H}SystemHooks;->music(Ljava/lang/Object;Landroid/view/KeyEvent;)Z\n    move-result v0\n    if-eqz v0, :ac_delegate\n    const/4 v0, 0x0\n    return v0",
     keys=["ac_volume_music","ac_volume_up_action","ac_volume_down_action","ac_volume_hold_ms"])
hook("services",POLICY,"powerLongPress(JLandroid/view/KeyEvent;)V",
     before=f"    invoke-static {{p0}}, {H}SystemHooks;->powerMenu(Ljava/lang/Object;)Z\n    move-result v0\n    if-eqz v0, :ac_delegate\n    return-void",keys=["ac_power_menu"])
hook("systemui","com/android/systemui/SystemUIService","onCreate()V",
     after=f"    invoke-static {{p0}}, {H}UiHooks;->install(Landroid/content/Context;)V",
     keys=["ac_charge_info","ac_charge_interval","ac_charge_bottom","ac_charge_animation","ac_charge_animation_seconds"])
hook("systemui","com/android/systemui/statusbar/phone/BiometricUnlockController",
     "onBiometricAuthenticated(ILandroid/hardware/biometrics/BiometricSourceType;Z)V",
     before=f"    invoke-static {{p0, p2}}, {H}UiHooks;->fingerprint(Ljava/lang/Object;Ljava/lang/Object;)V",
     keys=["ac_fingerprint_vibration","ac_fingerprint_ms"])
hook("systemui","com/android/systemui/statusbar/notification/row/ExpandableNotificationRow","onAttachedToWindow()V",
     after=f"    invoke-static {{p0}}, {H}UiHooks;->notificationRow(Landroid/view/View;)V",keys=["ac_expand_first_notification"])
hook("systemui","com/android/systemui/statusbar/policy/Clock","getSmallTime()Ljava/lang/CharSequence;",
     after=f"    invoke-static {{v0}}, {H}UiHooks;->clock(Ljava/lang/CharSequence;)Ljava/lang/CharSequence;\n    move-result-object v0",keys=["ac_clock_format"])
hook("systemui","com/android/systemui/statusbar/phone/PhoneStatusBarView","onFinishInflate()V",
     after=f"    invoke-static {{p0}}, {H}UiHooks;->statusBar(Landroid/view/View;)V",
     keys=["ac_clock_size","ac_clock_colour","ac_network_speed","ac_network_left"])
hook("systemui","com/android/systemui/statusbar/notification/interruption/FullScreenIntentDecisionProvider",
     "makeFullScreenIntentDecision(Lcom/android/systemui/statusbar/notification/collection/NotificationEntry;Z)Lcom/android/systemui/statusbar/notification/interruption/FullScreenIntentDecisionProvider$Decision;",
     after=f"    invoke-static {{p1, v0}}, {H}UiHooks;->callDecision(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;\n    move-result-object v0\n    check-cast v0, Lcom/android/systemui/statusbar/notification/interruption/FullScreenIntentDecisionProvider$Decision;",keys=["ac_call_style"])
hook("services","com/android/server/notification/NotificationRecord","getSound()Landroid/net/Uri;",
     after=f"    invoke-static {{v0}}, {H}SystemHooks;->notificationSound(Landroid/net/Uri;)Landroid/net/Uri;\n    move-result-object v0",keys=["ac_notification_sound_screen_on"])
hook("systemui","com/android/systemui/privacy/PrivacyItemController",
     "getPrivacyList$frameworks__base__packages__SystemUI__android_common__SystemUI_core()Ljava/util/List;",
     after=f"    invoke-static {{v0}}, {H}UiHooks;->privacyItems(Ljava/util/List;)Ljava/util/List;\n    move-result-object v0",keys=["ac_hide_privacy"])
hook("systemui","com/android/systemui/privacy/PrivacyItemController",
     "addCallback(Lcom/android/systemui/privacy/PrivacyItemController$Callback;)V",
     after=f"    invoke-static {{p0}}, {H}UiHooks;->privacyController(Ljava/lang/Object;)V")


def model(model,method,key,kind="bool"):
    returns={"bool":"Z","integer":"I","number":"F","grid":"Landroid/graphics/Point;"}[kind]
    result="-object" if kind=="grid" else ""
    hook("home","com/honeyspace/sdk/source/HomeUpDataSource$"+model,method+"()"+returns,
         after=f"    const-string v1, \"{key}\"\n    invoke-static {{v0, v1}}, {H}SamsungHomeHooks;->{kind}({returns}Ljava/lang/String;){returns}\n    move-result{result} v0",keys=[key,"ac_home_enabled"])


for modelname,method,key in [
    ("HomeUpFeature","getEnabled","ac_home_enabled"),
    ("HomeUpFeature","isV2PlugIn","ac_home_enabled"),
    ("HomeMasterData","getEnabled","ac_home_enabled"),
    ("HomePageLoopingData","getEnabled","ac_home_loop"),
    ("AppsPageLoopingData","getEnabled","ac_apps_loop"),
    ("IconViewData","getHideLabel","ac_hide_icon_labels"),
    ("TaskChangerData","getEnabled","ac_recents_enabled"),
    ("TaskChangerData","getCenterRunningApp","ac_recents_centre"),
    ("TaskChangerData","getMiniMode","ac_recents_mini"),
    ("TaskChangerData","getCircularList","ac_recents_loop"),
    ("TaskChangerData","getAppLabel","ac_recents_labels"),
    ("GestureSettingsData","getEnabled","ac_home_enabled"),
    ("GestureSettingsData","getHomeVibration","ac_home_vibration"),
    ("GestureSensitivityData","getGestureSensitivity","ac_gesture_sensitivity_enabled"),
    ("PopupFolderData","getEnabled","ac_popup_folder"),
    ("PopupFolderData","getFixedPosition","ac_folder_fixed"),
    ("PopupFolderData","getFlexibleSize","ac_folder_flexible"),
    ("PopupFolderData","getRemoveBlur","ac_folder_no_blur")]: model(modelname,method,key)
for modelname,method,key,kind in [
    ("WorkspaceGrid","getGrid","ac_home_grid","grid"),
    ("ApplistGrid","getGrid","ac_apps_grid","grid"),
    ("IconViewData","getSizeScale","ac_icon_scale","number"),
    ("TaskChangerData","getLayoutType","ac_recents_layout","integer"),
    ("GestureSensitivityData","getGestureSensitivitySize","ac_gesture_sensitivity","integer"),
    ("PopupFolderData","getSize","ac_folder_size","number")]: model(modelname,method,key,kind)
for method,key in [("getHotseatCount","ac_dock_count"),("getWorkspaceCellX","ac_home_grid_x"),("getWorkspaceCellY","ac_home_grid_y"),
                   ("getApplistCellX","ac_apps_grid_x"),("getApplistCellY","ac_apps_grid_y")]:
    hook("home","com/honeyspace/ui/common/preference/BasePreferenceDataSource",method+"()Lkotlinx/coroutines/flow/StateFlow;",
         after=f"    const-string v1, \"{key}\"\n    invoke-static {{v0, v1}}, {H}SamsungHomeHooks;->flow(Ljava/lang/Object;Ljava/lang/String;)Ljava/lang/Object;\n    move-result-object v0\n    check-cast v0, Lkotlinx/coroutines/flow/StateFlow;",keys=["ac_dock_count"])
for style in ("StackStyle","VerticalStyle","ListStyle","GridStyle","SlimStyle","TiltStackStyle"):
    owner="com/honeyspace/ui/common/taskChangerLayout/"+style
    hook("home",owner,"getSceneRadius(Landroid/content/res/Resources;)F",
         after=f"    const-string v1, \"ac_recents_radius\"\n    invoke-static {{v0, v1}}, {H}SamsungHomeHooks;->number(FLjava/lang/String;)F\n    move-result v0",keys=["ac_recents_radius"])
hook("home","com/honeyspace/ui/common/recentstyler/RecentStyler",
     "getSceneScale(Landroid/content/res/Resources;Lcom/honeyspace/ui/common/taskChangerLayout/LayoutInfo;Lcom/honeyspace/ui/common/taskChangerLayout/LayoutInfo;IF)Landroid/graphics/PointF;",
     after=f"    invoke-static {{v0}}, {H}SamsungHomeHooks;->scales(Landroid/graphics/PointF;)Landroid/graphics/PointF;\n    move-result-object v0",keys=["ac_recents_scale_x","ac_recents_scale_y"])
hook("home","com/honeyspace/ui/common/recentstyler/RecentStyler",
     "getSceneTop(Landroid/content/res/Resources;Lcom/honeyspace/ui/common/taskChangerLayout/LayoutStyle;IZZI)F",
     after=f"    invoke-static {{v0}}, {H}SamsungHomeHooks;->top(F)F\n    move-result v0",keys=["ac_recents_top"])
for owner,methods in [
    ("com/honeyspace/transition/data/open/HomeUpOpenParams",["getHomeDuration","getWallpaperDuration","getWindowAlphaDuration","getWindowPositionDuration","getTaskWindowAlphaDuration","getTaskWindowPositionDuration"]),
    ("com/honeyspace/transition/data/close/HomeUpCloseParams",["getContentDurationMs","getNoTargetWindowAlphaDurationMs","getWallpaperDurationMs","getWindowAlphaDurationMs","getWindowDurationMs"])]:
    for method in methods:
        hook("home",owner,method+"()J",after=f"    invoke-static {{v0, v1}}, {H}SamsungHomeHooks;->duration(J)J\n    move-result-wide v0",keys=["ac_home_animation_scale"])
hook("home","com/honeyspace/transition/data/close/HomeUpCloseParams","getPositionInterpolator()Landroid/view/animation/Interpolator;",
     after=f"    invoke-static {{v0}}, {H}SamsungHomeHooks;->bounce(Landroid/view/animation/Interpolator;)Landroid/view/animation/Interpolator;\n    move-result-object v0",keys=["ac_home_bounce"])
for method,shown in [("show(Lcom/honeyspace/sdk/HoneyState;ZLkotlin/jvm/functions/Function3;)V",1),("hide()V",0)]:
    hook("home","com/honeyspace/ui/honeypots/recentscreen/presentation/RecentscreenPot",method,
         after=f"    const/4 v1, 0x{shown}\n    invoke-static {{p0, v1}}, {H}SamsungHomeHooks;->recents(Ljava/lang/Object;Z)V",keys=["ac_recents_hide_status"])
hook("home","com/honeyspace/ui/honeypots/tasklist/presentation/TaskView","onFinishInflate()V",
     after=f"    invoke-static {{p0}}, {H}SamsungHomeHooks;->task(Landroid/view/View;)V",keys=["ac_recents_transparent"])
hook("home","com/honeyspace/common/taskscene/TaskSceneView","setScenePaintSet(Lcom/honeyspace/common/taskscene/paintpallet/ScenePaintSet;)V",
     after=f"    invoke-static {{p0}}, {H}SamsungHomeHooks;->scenePaints(Ljava/lang/Object;)V",keys=["ac_recents_transparent"])
hook("home","com/honeyspace/ui/honeypots/folder/presentation/open/OpenFolderTitle","onAttachedToWindow()V",
     after=f"    invoke-static {{p0}}, {H}SamsungHomeHooks;->decorate(Landroid/view/View;)V",keys=["ac_folder_title_centre"])
features.update(["ac_recents_hide_clear","ac_folder_title_centre"])
additions=[
    {"class":"Lcom/honeyspace/ui/honeypots/tasklist/presentation/CloseAllButton;","method":"setVisibility(I)V",
     "code":f".method public setVisibility(I)V\n    .locals 1\n    invoke-static {{p1}}, {H}SamsungHomeHooks;->clearVisibility(I)I\n    move-result p1\n    invoke-super {{p0, p1}}, Landroid/widget/Button;->setVisibility(I)V\n    return-void\n.end method"}
]
recents_class="Lcom/honeyspace/ui/honeypots/recentscreen/presentation/RecentsContainerView;"
additions.extend([
    {"class":recents_class,"method":"onVisibilityChanged(Landroid/view/View;I)V",
     "code":f".method protected onVisibilityChanged(Landroid/view/View;I)V\n    .locals 1\n    invoke-super {{p0, p1, p2}}, Landroid/widget/FrameLayout;->onVisibilityChanged(Landroid/view/View;I)V\n    const/4 v0, 0x0\n    if-nez p2, :ac_hidden\n    const/4 v0, 0x1\n    :ac_hidden\n    invoke-static {{p0, v0}}, {H}SamsungHomeHooks;->recentsView(Landroid/view/View;Z)V\n    return-void\n.end method"},
    {"class":recents_class,"method":"onDetachedFromWindow()V",
     "code":f".method protected onDetachedFromWindow()V\n    .locals 1\n    invoke-super {{p0}}, Landroid/widget/FrameLayout;->onDetachedFromWindow()V\n    const/4 v0, 0x0\n    invoke-static {{p0, v0}}, {H}SamsungHomeHooks;->recentsView(Landroid/view/View;Z)V\n    return-void\n.end method"}
])
hook("settings","com/android/settings/homepage/TopLevelSettings","onResume()V",
     after="    invoke-static {p0}, Lcom/android/settings/artisan/ArtisanSettings;->homepage(Lcom/android/settings/SettingsPreferenceFragment;)V")

ADAPTER={
    "id":"oneui9-s942b-zzh6-honeyspace",
    "required_files":{"bin/vold":VOLD_SHA256},
    "features":sorted(features),
    "targets":{
        "framework":{"path":"framework/framework.jar","sha256":"94fbadff654584636bf62bf7faaf8b4dd9f671ed39fcf6d25b9cc4849b9e3f7b","hooks":rules["framework"]},
        "services":{"path":"framework/services.jar","sha256":"05d52cec00855dd7e4e2d2f0c5fb4a1e3a51951736c905b22568a40aeadae37a","hooks":rules["services"],
                    "edits":[CE_TOKENLESS_EDIT,{"class":"Lcom/android/server/notification/NotificationAttentionHelper;","method":"buzzBeepBlinkLocked",
                              "find":"    iget-object v14, v2, Lcom/android/server/notification/NotificationRecord;->mSound:Landroid/net/Uri;",
                              "replace":"    iget-object v14, v2, Lcom/android/server/notification/NotificationRecord;->mSound:Landroid/net/Uri;\n"
                                        +f"    invoke-static/range {{v14 .. v14}}, {H}SystemHooks;->notificationSound(Landroid/net/Uri;)Landroid/net/Uri;\n    move-result-object v14"}]},
        "systemui":{"path":"system_ext/priv-app/SystemUI/SystemUI.apk","sha256":"cb3c137401885c60a2bb2ae6cc4543ac6719e4ba99d309451787afa53ddc44ef","hooks":rules["systemui"],
                    "edits":[{"class":"Lcom/android/systemui/statusbar/NotificationRemoteInputManager;","method":"activateRemoteInputOnExpanded",
                              "find":"    :goto_6f\n    iget-object v7, p0, Lcom/android/systemui/statusbar/NotificationRemoteInputManager;->mLockscreenUserManager:Lcom/android/systemui/statusbar/NotificationLockscreenUserManager;",
                              "replace":f"    :goto_6f\n    invoke-static/range {{v3 .. v3}}, {H}UiHooks;->allowRemoteInput(I)Z\n    move-result v8\n    if-nez v8, :cond_93\n    iget-object v7, p0, Lcom/android/systemui/statusbar/NotificationRemoteInputManager;->mLockscreenUserManager:Lcom/android/systemui/statusbar/NotificationLockscreenUserManager;"}],
                     },
        "home":{"path":"priv-app/TouchWizHome_2017/TouchWizHome_2017.apk","sha256":"1c452c83ef3a4b1fe9f520b62ba45c46d8d75286c85dfa4775a6d3568e07519d","hooks":rules["home"],"add_methods":additions}
        ,"settings":{"path":"priv-app/SecSettings/SecSettings.apk","sha256":"57792a331109cc889d8d2be0caa8d0d4e40ade53fc1e0c608e96c582b0d20b35","hooks":rules["settings"]}
    }
}
