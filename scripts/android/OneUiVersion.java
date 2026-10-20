// SPDX-License-Identifier: GPL-3.0-or-later
package com.samsung.android.camera.feature;

/** HWC1 Camera's version ABI, retaining its S10 feature contract on the pinned host. */
public enum OneUiVersion {
    V1_0(-1, 100000, 280100),
    V1_1(-1, 100100, 280100),
    V1_2(-1, 100200, 280200),
    V1_5(-1, 100500, 280300),
    V2_0(-1, 110000, 290100),
    V2_1(-1, 110100, 290200),
    V2_5(-1, 110500, 290300),
    V3_0(-1, 120000, 300100),
    V3_1(-1, 120100, 300100),
    V3_1_1(30101, 120500, 300200),
    V4_0(40000, 130000, 310100),
    V4_1(40100, 130100, 310100),
    V4_1_1(40101, 130500, 310200),
    V5_0(50000, 140000, 320100);

    private final int mOneUiVersionCode;
    private final int mSepVersionCode;
    private final int mSeApiVersionCode;

    OneUiVersion(int oneUiVersionCode, int sepVersionCode, int seApiVersionCode) {
        mOneUiVersionCode = oneUiVersionCode;
        mSepVersionCode = sepVersionCode;
        mSeApiVersionCode = seApiVersionCode;
    }

    public static OneUiVersion get(int code) {
        // Only this legacy Camera class sees the alias; OS properties are unchanged.
        if (code == 90000) {
            return V4_1;
        }
        for (OneUiVersion version : values()) {
            if (code != -1 && version.mOneUiVersionCode == code) {
                return version;
            }
        }
        throw new IllegalArgumentException("get : argument is invalid - " + code);
    }

    private int getOneUiVersionCode() {
        return mOneUiVersionCode;
    }

    public int getSepVersionCode() {
        return mSepVersionCode;
    }

    public int getSeApiVersionCode() {
        return mSeApiVersionCode;
    }

    public boolean isGreaterThanOrEqualTo(OneUiVersion other) {
        return mOneUiVersionCode >= other.mOneUiVersionCode;
    }

    public boolean isLessThanOrEqualTo(OneUiVersion other) {
        return mOneUiVersionCode <= other.mOneUiVersionCode;
    }
}
