#!/usr/bin/env bash
# Copyright (c) 2025 Salvo Giangreco
# SPDX-License-Identifier: GPL-3.0-or-later

# [
if [[ "$TARGET_CODENAME" == "beyond1lte" ]]; then
    source "$SRC_DIR/scripts/utils/s10_inputs.sh" || exit 1
    CHECK_S10_INPUTS || exit 1
fi
source "$SRC_DIR/scripts/utils/build_utils.sh" || exit 1

FORCE=false
BUILD_ROM=false
BUILD_ZIP=true
DEBUG=false

START_TIME="$(date +%s)"

SOURCE_FIRMWARE_PATH="$(cut -d "/" -f 1 -s <<< "$SOURCE_FIRMWARE")_$(cut -d "/" -f 2 -s <<< "$SOURCE_FIRMWARE")"
TARGET_FIRMWARE_PATH="$(cut -d "/" -f 1 -s <<< "$TARGET_FIRMWARE")_$(cut -d "/" -f 2 -s <<< "$TARGET_FIRMWARE")"

GET_WORK_DIR_HASH()
{
    if [[ "$TARGET_CODENAME" == "beyond1lte" ]]; then
        python3 "$SRC_DIR/scripts/utils/s10_tree_hash.py" inputs "$DEBUG" \
            "$SRC_DIR/scripts" "$SRC_DIR/buildenv.sh" "$OUT_DIR/config.sh" \
            "$SRC_DIR/unica" "$SRC_DIR/target/$TARGET_CODENAME" \
            "$SRC_DIR/platform/$TARGET_PLATFORM" "$FW_DIR" \
            "$SRC_DIR/prebuilts" "$SRC_DIR/security" "$SRC_DIR/external" "$TOOLS_DIR"
        return $?
    fi
    local HASH_PATHS=("$SRC_DIR/unica" "$SRC_DIR/target/$TARGET_CODENAME")
    if [ -d "$SRC_DIR/platform/$TARGET_PLATFORM" ]; then
        HASH_PATHS+=("$SRC_DIR/platform/$TARGET_PLATFORM")
    fi
    (
        set -o pipefail
        find "${HASH_PATHS[@]}" -type f -print0 | \
            sort -z | xargs -0 -r sha1sum | sha1sum | cut -d " " -f 1
    )
}

PREPARE_SCRIPT()
{
    while [ "$#" != 0 ]; do
        if [[ "$1" == "--force" ]] || [[ "$1" == "-f" ]]; then
            FORCE=true
        elif [[ "$1" == "--no-rom-zip" ]]; then
            BUILD_ZIP=false
        elif [[ "$1" == "--debug" ]]; then
            DEBUG=true
        else
            if [[ "$1" == "-"* ]]; then
                LOGE "Unknown option: $1"
            fi
            PRINT_USAGE
            exit 1
        fi

        shift
    done
}

PRINT_BUILD_OUTCOME()
{
    local EXIT_CODE="$?"
    local END_TIME
    local ESTIMATED

    END_TIME="$(date +%s)"
    ESTIMATED="$((END_TIME - START_TIME))"

    if [ "$EXIT_CODE" != "0" ]; then
        echo -n -e '\n\033[1;31m'"Build failed "
    else
        echo -n -e '\n\033[1;32m'"Build completed "
    fi
    echo -e "in $((ESTIMATED / 3600))hrs $(((ESTIMATED / 60) % 60))min $((ESTIMATED % 60))sec."'\033[0m\n'
}

PRINT_USAGE()
{
    echo "Usage: make_rom [options]" >&2
    echo " -f, --force : Force ROM build" >&2
    echo " --no-rom-zip : Do not build ROM zip" >&2
    echo " --debug : Create a debug build" >&2
}
# ]

PREPARE_SCRIPT "$@"

if $FORCE; then
    BUILD_ROM=true
else
    if [ -f "$WORK_DIR/.completed" ]; then
        PREVIOUS_WORK_HASH="$(cat "$WORK_DIR/.completed")" || exit 1
        CURRENT_WORK_HASH="$(GET_WORK_DIR_HASH)" || exit 1
        if [[ "$TARGET_CODENAME" == "beyond1lte" ]]; then
            WORK_OUTPUT_HASH="$(python3 "$SRC_DIR/scripts/utils/s10_tree_hash.py" work "" "$WORK_DIR")" || exit 1
            CURRENT_WORK_HASH="s10-v1:$CURRENT_WORK_HASH:$WORK_OUTPUT_HASH"
        fi
        if [[ "$PREVIOUS_WORK_HASH" == "$CURRENT_WORK_HASH" ]]; then
            LOGW "No changes have been detected in the build environment"
            BUILD_ROM=false
        else
            LOGW "Changes detected in the build environment"
            BUILD_ROM=true
        fi
    else
        BUILD_ROM=true
    fi
fi

trap 'PRINT_BUILD_OUTCOME' EXIT
trap 'echo' INT

if $BUILD_ROM; then
    [ -d "$APKTOOL_DIR" ] && rm -rf "$APKTOOL_DIR"
    [ -f "$WORK_DIR/.completed" ] && rm -f "$WORK_DIR/.completed"

    if [[ "$TARGET_FIRMWARE_OFFLINE" == "true" ]]; then
        ONLINE_INPUTS=("$SOURCE_FIRMWARE")
        IFS=':' read -r -a SOURCE_EXTRAS <<< "$SOURCE_EXTRA_FIRMWARES"
        ONLINE_INPUTS+=("${SOURCE_EXTRAS[@]}")
        for FIRMWARE_INPUT in "${ONLINE_INPUTS[@]}"; do
            [[ -n "$FIRMWARE_INPUT" ]] || continue
            IFS='/' read -r FW_MODEL FW_CSC FW_ID <<< "$FIRMWARE_INPUT"
            if [[ -z "$FW_MODEL" || -z "$FW_CSC" ]]; then
                LOGE "Malformed source firmware input"
                exit 1
            fi
            FW_CACHE_KEY="${FW_MODEL}_${FW_CSC}"
            if [[ "$TARGET_CODENAME" == "beyond1lte" && "$FW_CACHE_KEY" == "SM-S908B_EUX" ]]; then
                # The pinned local input has proof records, not an extractor marker.
                # Never replace it with a newer FUS release during this port build.
                CHECK_S10_SOURCE_INPUTS || exit 1
                continue
            fi
            if [ ! -f "$FW_DIR/$FW_CACHE_KEY/.extracted" ]; then
                if [ ! -f "$ODIN_DIR/$FW_CACHE_KEY/.downloaded" ]; then
                    "$SRC_DIR/scripts/download_fw.sh" --ignore-source --ignore-target "$FIRMWARE_INPUT" || exit 1
                fi
                "$SRC_DIR/scripts/extract_fw.sh" --ignore-source --ignore-target "$FIRMWARE_INPUT" || exit 1
            fi
        done
        unset ONLINE_INPUTS SOURCE_EXTRAS FIRMWARE_INPUT FW_MODEL FW_CSC FW_ID FW_CACHE_KEY
    elif [ ! -f "$FW_DIR/$SOURCE_FIRMWARE_PATH/.extracted" ] || [ ! -f "$FW_DIR/$TARGET_FIRMWARE_PATH/.extracted" ]; then
        if [ ! -f "$ODIN_DIR/$SOURCE_FIRMWARE_PATH/.downloaded" ] || [ ! -f "$ODIN_DIR/$TARGET_FIRMWARE_PATH/.downloaded" ]; then
            LOG_STEP_IN true "Downloading required firmwares"
            "$SRC_DIR/scripts/download_fw.sh" || exit 1
            LOG_STEP_OUT
        fi
        LOG_STEP_IN true "Extracting required firmwares"
        "$SRC_DIR/scripts/extract_fw.sh" || exit 1
        LOG_STEP_OUT
    fi

    if [[ "$TARGET_CODENAME" == "beyond1lte" ]]; then
        CHECK_S10_SOURCE_INPUTS || exit 1
    elif [[ "$TARGET_CODENAME" == "beyond2lte" ]]; then
        # Do not accidentally start an S22 donor build for the S10+.
        # The original G975F kernel and the official S26 Ultra system
        # must already exist. This is not a bootability certification.
        python3 "$SRC_DIR/scripts/utils/astropart_s26_preflight.py" \
            --firmware-dir "$FW_DIR" \
            --kernel "$SRC_DIR/target/beyond2lte/kernel" || exit 1
    fi

    # Capture after firmware/tool preparation and before modifying the work tree.
    BUILD_INPUT_HASH="$(GET_WORK_DIR_HASH)" || exit 1

    LOG_STEP_IN true "Creating work dir"
    "$SRC_DIR/scripts/internal/create_work_dir.sh" || exit 1
    LOG_STEP_OUT

    if [ -d "$SRC_DIR/platform/$TARGET_PLATFORM/patches" ]; then
        LOG_STEP_IN true "Applying platform patches"
        "$SRC_DIR/scripts/internal/apply_modules.sh" "$SRC_DIR/platform/$TARGET_PLATFORM/patches" || exit 1
        LOG_STEP_OUT
    fi
    if [ -d "$SRC_DIR/target/$TARGET_CODENAME/patches" ]; then
        LOG_STEP_IN true "Applying device patches"
        "$SRC_DIR/scripts/internal/apply_modules.sh" "$SRC_DIR/target/$TARGET_CODENAME/patches" || exit 1
        LOG_STEP_OUT
    fi
    if [ -d "$SRC_DIR/unica/patches" ]; then
        LOG_STEP_IN true "Applying ROM patches"
        "$SRC_DIR/scripts/internal/apply_modules.sh" "$SRC_DIR/unica/patches" || exit 1
        LOG_STEP_OUT
    fi

    if [ -d "$SRC_DIR/unica/mods" ]; then
        LOG_STEP_IN true "Applying ROM mods"
        "$SRC_DIR/scripts/internal/apply_modules.sh" "$SRC_DIR/unica/mods" || exit 1
        LOG_STEP_OUT
    fi

    if [ -d "$APKTOOL_DIR" ]; then
        LOG_STEP_IN true "Building APKs/JARs"

        # Capture the list before launching any job; process substitution hides find errors.
        APK_BUILD_LIST="$(mktemp "$OUT_DIR/apk-build-list.XXXXXX")" || exit 1
        if ! find "$APKTOOL_DIR" -type d \( -name "*.apk" -o -name "*.jar" \) -print0 > "$APK_BUILD_LIST"; then
            rm -f "$APK_BUILD_LIST"
            exit 1
        fi
        BUILD_PIDS=()
        while IFS= read -r -d '' f; do
            f="${f/$APKTOOL_DIR\//}"
            PARTITION="$(cut -d "/" -f 1 -s <<< "$f")"
            if [[ "$TARGET_CODENAME" == "beyond1lte" ]]; then
                # Completion removes profiles from shared partition metadata.
                # Serialize APK processes, retaining apktool's internal workers.
                if [[ "$PARTITION" == "system" ]]; then
                    "$SRC_DIR/scripts/apktool.sh" b "system" "$f" || exit 1
                else
                    "$SRC_DIR/scripts/apktool.sh" b "$PARTITION" "$(cut -d "/" -f 2- -s <<< "$f")" || exit 1
                fi
            else
                if [[ "$PARTITION" == "system" ]]; then
                    "$SRC_DIR/scripts/apktool.sh" b "system" "$f" &
                else
                    "$SRC_DIR/scripts/apktool.sh" b "$PARTITION" "$(cut -d "/" -f 2- -s <<< "$f")" &
                fi
                BUILD_PIDS+=("$!")
            fi
        done < "$APK_BUILD_LIST"
        BUILD_FAILED=0
        for BUILD_PID in "${BUILD_PIDS[@]}"; do
            if wait "$BUILD_PID"; then
                :
            else
                LOGE "APK/JAR task failed: pid=$BUILD_PID"
                BUILD_FAILED=1
            fi
        done
        rm -f "$APK_BUILD_LIST" || exit 1
        [[ "$BUILD_FAILED" -eq 0 ]] || exit 1
        unset APK_BUILD_LIST BUILD_PIDS BUILD_PID BUILD_FAILED

        LOG_STEP_OUT
    fi

    if [[ "$TARGET_CODENAME" == "beyond1lte" ]]; then
        # Apply after all modules: QHD product features replace SurfaceFlinger.
        LOG_STEP_IN true "Fixing legacy composer display port validation"
        python3 "$SRC_DIR/scripts/utils/s10_display_port.py" \
            "$WORK_DIR/system/system/bin/surfaceflinger" || exit 1
        LOG_STEP_OUT
        LOG_STEP_IN true "Fixing legacy HDMI audio output flag"
        python3 "$SRC_DIR/scripts/utils/s10_hdmi_audio.py" \
            "$WORK_DIR/vendor/lib/hw/audio.primary.exynos9820.so" || exit 1
        LOG_STEP_OUT
        python3 -B "$SRC_DIR/scripts/utils/s10_final_metadata.py" "$WORK_DIR" || exit 1
    fi

    FINAL_INPUT_HASH="$(GET_WORK_DIR_HASH)" || exit 1
    if [[ "$BUILD_INPUT_HASH" != "$FINAL_INPUT_HASH" ]]; then
        LOGE "Build inputs covered by the cache key changed during work generation"
        exit 1
    fi
    if [[ "$TARGET_CODENAME" == "beyond1lte" ]]; then
        CHECK_S10_KERNEL_SET "$WORK_DIR/kernel" || exit 1
        WORK_OUTPUT_HASH="$(python3 "$SRC_DIR/scripts/utils/s10_tree_hash.py" work "" "$WORK_DIR")" || exit 1
        FINAL_INPUT_HASH="s10-v1:$FINAL_INPUT_HASH:$WORK_OUTPUT_HASH"
    fi
    # Readers must not observe an empty or partially written completion record.
    COMPLETION_TMP="$(mktemp "$WORK_DIR/.completed.XXXXXX")" || exit 1
    if ! printf '%s' "$FINAL_INPUT_HASH" > "$COMPLETION_TMP" ||
            ! mv -f "$COMPLETION_TMP" "$WORK_DIR/.completed"; then
        rm -f "$COMPLETION_TMP"
        exit 1
    fi
    unset BUILD_INPUT_HASH FINAL_INPUT_HASH COMPLETION_TMP
fi

if $BUILD_ZIP; then
    LOG_STEP_IN true "Creating zip"
    "$SRC_DIR/scripts/internal/build_flashable_zip.sh" || exit 1
    LOG_STEP_OUT
fi

exit 0
