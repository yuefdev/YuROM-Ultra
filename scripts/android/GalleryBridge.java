// SPDX-License-Identifier: GPL-3.0-or-later
package org.artisanrom.gallery;

import android.app.Activity;
import android.app.KeyguardManager;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ContentUris;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import android.util.Log;

/** Adapts the original S10 Camera's explicit Gallery activity to Google Photos. */
public final class GalleryBridge extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        KeyguardManager keyguard = (KeyguardManager) getSystemService(KEYGUARD_SERVICE);
        Intent incoming = getIntent();
        Uri media = incoming == null ? null : incoming.getData();
        // A secure Camera session must not open an unrestricted gallery behind the lock screen.
        if (keyguard == null || keyguard.isKeyguardLocked() || incoming == null
                || !Intent.ACTION_VIEW.equals(incoming.getAction()) || media == null
                || !"content".equals(media.getScheme())
                || !("media".equals(media.getAuthority()) || "secmedia".equals(media.getAuthority()))) {
            finish();
            return;
        }
        try {
            media = publicMedia(media, incoming.getStringExtra("filepath"));
            if (media == null) {
                Log.w("CameraGalleryBridge", "No public MediaStore row for Camera media");
                finish();
                return;
            }
            String type = getContentResolver().getType(media);
            if (type == null || !(type.startsWith("image/") || type.startsWith("video/"))) {
                finish();
                return;
            }
            Intent viewer = new Intent(Intent.ACTION_VIEW);
            viewer.setPackage("com.google.android.apps.photos");
            viewer.setDataAndType(media, type);
            viewer.setClipData(ClipData.newRawUri("Camera media", media));
            viewer.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(viewer);
        } catch (ActivityNotFoundException | SecurityException | IllegalArgumentException error) {
            Log.w("CameraGalleryBridge", "Unable to open Camera media in Google Photos", error);
        }
        finish();
    }

    private Uri publicMedia(Uri media, String path) {
        if ("media".equals(media.getAuthority())) {
            return media;
        }
        // Camera supplies the public file path; Samsung's private provider need not be opened.
        if (path == null || path.isEmpty()) {
            return null;
        }
        try (Cursor target = getContentResolver().query(MediaStore.Files.getContentUri("external"),
                new String[]{"_id", "mime_type"}, "_data=?", new String[]{path}, null)) {
            if (target == null || target.getCount() != 1 || !target.moveToFirst()) {
                return null;
            }
            String type = target.getString(1);
            Uri collection = type != null && type.startsWith("image/")
                    ? MediaStore.Images.Media.EXTERNAL_CONTENT_URI
                    : type != null && type.startsWith("video/") ? MediaStore.Video.Media.EXTERNAL_CONTENT_URI : null;
            return collection == null ? null : ContentUris.withAppendedId(collection, target.getLong(0));
        }
    }
}
