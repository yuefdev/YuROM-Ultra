#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Adapt the pinned Samsung storage hand-off to the donor vold's tokenless API."""
import copy
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

SERVICES_SHA256="05d52cec00855dd7e4e2d2f0c5fb4a1e3a51951736c905b22568a40aeadae37a"
VOLD_SHA256="1856ffbd5dfd3922c0987fced54031e40ebad03bc84c6b0f540995946dbc7009"
OWNER="Lcom/android/server/StorageManagerService$StorageManagerInternalImpl;"
CALL="    invoke-interface {v0, p1, p2, p3, v1}, Landroid/os/IVold;->unlockCeStorage(ILjava/lang/String;[BZ)V"
REPLACEMENT='    # This vold accepts only the empty legacy-HAT sentinel; p3 remains the derived CE secret.\n    const-string p2, "!"\n\n'+CALL
CE_TOKENLESS_EDIT={"class":OWNER,"method":"unlockCeStorage(I[B[B)V","find":CALL,"replace":REPLACEMENT}


def digest(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def patch_smali(text):
    method=re.search(r"^\.method public final unlockCeStorage\(I\[B\[B\)V\n.*?^\.end method$",text,re.M|re.S)
    if not text.startswith(".class ") or OWNER not in text.splitlines()[0] or not method or text.count(CALL)!=1 or REPLACEMENT in text:
        raise ValueError("Unexpected or already adapted CE storage method")
    if CALL not in method.group(0):raise ValueError("CE call moved outside the pinned method")
    return text.replace(CALL,REPLACEMENT)


def configure_tokenless_ce(system):
    """Apply the same single-method fix when building without optional Artisan hooks."""
    from build_artisan_control import dex_classes
    system=Path(system);services=system/"framework/services.jar"
    if digest(system/"bin/vold")!=VOLD_SHA256 or digest(services)!=SERVICES_SHA256:
        raise ValueError("Unknown vold/services pair for tokenless CE compatibility")
    with tempfile.TemporaryDirectory(prefix="s10-ce-storage-") as temporary:
        folder=Path(temporary);matches=[]
        with zipfile.ZipFile(services) as original:
            for name in original.namelist():
                if re.fullmatch(r"classes\d*\.dex",name) and OWNER in dex_classes(original.read(name)):matches.append(name)
            if len(matches)!=1:raise ValueError("CE storage owner must occur in exactly one DEX")
            entry=matches[0];smali=folder/"smali"
            subprocess.run(["baksmali","d","--debug-info","false","-l","-j","8","-o",str(smali),str(services)+"/"+entry],check=True,capture_output=True)
            source=smali/(OWNER[1:-1]+".smali");source.write_text(patch_smali(source.read_text()))
            dex=folder/"patched.dex"
            subprocess.run(["smali","a","-a","35","-j","8","-o",str(dex),str(smali)],check=True,capture_output=True)
            if set(dex_classes(dex.read_bytes()))!=set(dex_classes(original.read(entry))):raise ValueError("CE compatibility changed the class inventory")
            output=folder/"services.jar"
            with zipfile.ZipFile(output,"w") as target:
                for item in original.infolist():target.writestr(copy.copy(item),dex.read_bytes() if item.filename==entry else original.read(item.filename))
            with zipfile.ZipFile(output) as target:
                for name in original.namelist():
                    if name!=entry and target.read(name)!=original.read(name):raise ValueError("Unrelated services entry changed")
        with services.open("wb") as stream:stream.write(output.read_bytes())
    return {"vold_sha256":VOLD_SHA256,"services_sha256":digest(services),"legacy_hat_sentinel":"!","derived_ce_secret_preserved":True,"credential_verification_preserved":True}
