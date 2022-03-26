#!/usr/bin/env bash

set -euox pipefail

starttime="$(date +%s)"
midtime=""


cd_script_dir() {
    DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" > /dev/null && pwd )"
    cd "$DIR" || exit 1
}

take_time() {
    echo "===================="
    endtime=$(bc <<<"($starttime - $(date +%s)) /60")
    [ ! "x${midtime}" = "x" ] && echo $(bc <<<"($midtime - $(date +%s)) /60")m elapsed in between.
    midtime="$(date +%s)"
    echo $(bc <<<"($midtime - $(date +%s)) /60") elapsed total.
    echo "===================="
    echo ""
}

set_up_apt() {
    sudo apt-get install --no-install-recommends -y \
    sudo make gcc-arm-none-eabi gcc g++ libc6-dev \
    device-tree-compiler bison flex python3 python3-dev \
    swig cpio lzma bc kmod libgmp-dev libssl-dev \
    ca-certificates vim git gdb-arm-none-eabi \
    libglib2.0-dev libpixman-1-dev libmpc-dev abootimg wget
}


set_up() {
    [ ! -d "linux" ] && git clone --depth 1 "${REPO_PATH}" -b "${BRANCH}"
    cd linux || { echo "Cloning failed"; exit 1; }
    cd .. || echo "this wont fail."

    if [ "${MAKECROSSCOMPILATION}" = "y" ]; then
        export CROSS_COMPILE="arm-none-eabi-";
        { [ -d "gcc-arm-none-eabi-10.3-2021.10" ] && export PATH="/home/user/gcc-arm-none-eabi-10.3-2021.10/bin:$PATH"; } || \
            { wget "https://developer.arm.com/-/media/Files/downloads/gnu-rm/10.3-2021.10/gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2" && tar -xvf gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2; }
        { [ -d "gcc-arm-none-eabi-10.3-2021.10" ] && export PATH="/home/user/gcc-arm-none-eabi-10.3-2021.10/bin:$PATH"; } || \
            { echo GCC not found. Exit. && exit 1; }
    fi
}

compile() {
    [ "$(pwd | rev | cut -d'/' -f1 | rev)" = "linux" ] || { cd linux || { echo "Linux not found. exit"; exit 1; }; };

    export ARCH="arm"
    make "$CONFIG" && make -j$(nproc) && make INSTALL_MOD_PATH=mod_path modules_install && make zImage

    [ "x$?" = "x0" ] || { echo "Compilation failed. Exit"; exit 1; };

}


build_bootimg() {
    echo build succeeded
    # cd arch/arm/boot || echo no dir
    KVERS="$(ls mod_path/lib/modules)"
    echo "Kernel built: ${KVERS}"
    mkdir "../${KVERS}";
    echo "appending zImage"

    DTB_KERNEL="zImage_dtb"

    cat arch/arm/boot/zImage arch/arm/boot/dts/tegra20-asus-sl101.dtb > "../${KVERS}/${DTB_KERNEL}"
    cp -rv arch/arm/boot "../${KVERS}"
    cp -rv mod_path/lib "../${KVERS}"

    cd "../${KVERS}" || echo "cd fail!"


    LNXBLOBFN="blob.LNX"
    BOOTIMGFN="${KVERS}.bootimg"
    empty_initrd "initrd.img"
    boot_cfg > "bootimg.cfg"

    abootimg --create "${LNXBLOBFN}" \
        -f bootimg.cfg \
        -r initrd.img \
        -k "${DTB_KERNEL}" || { echo "abootimg failed."; exit 1; };
    echo "boot image created.";
    [ -d "../android-tf101-tools" ] || { echo "TF101 Tools not found. Exit"; exit 1; }

    ../android-tf101-tools/blobpack -s "${LNXBLOBFN}" LNX "${BOOTIMGFN}" || { echo "blobpacking failed."; exit 1; };
    echo "${BOOTIMGFN} build succeeded.";
    cd ".." || echo "this won't fail."
    sudo copy -vr "${KVERS}" /data
}

empty_initrd() {
    { [ "$1" = "x" ] && INITRD_FN="empty_initrd.img"; } || INITRD_FN="$1"
    echo "
00000000: 504b 0506 0000 0000 0000 0000 0000 0000  PK..............
00000010: 0000 0000 0000                           ......
" | xxd -r > "${INITRD_FN}"
    echo "Empty initrd created as '${INITRD_FN}'"
}

boot_cfg() {
    echo "bootsize = 0x788000
pagesize = 0x800
kerneladdr = 0x10008000
ramdiskaddr = 0x11000000
secondaddr = 0x10f00000
tagsaddr = 0x10000100
name =
cmdline = nvmem=128M@384M mem=1024M@0M vmalloc=256M root=/dev/mmcblk1 rw video=tegrafb console=tty0 usbcore.old_scheme_first=1 tegraboot=sdmmc"
}


# REPO_PATH="https://github.com/grate-driver/linux"
REPO_PATH="https://github.com/clamor-s/linux"
# CONFIG="tegra_defconfig"
CONFIG="transformer_defconfig"
BRANCH="sl101"
MAKECROSSCOMPILATION="y"

# echo [ "x$1" = "x" ] || { CUSTOM_T="" }
# go to script directory
cd_script_dir
# set_up_apt not needed
set_up # clone kernel & gcc arm binaries if necessary
take_time
compile # kernel
take_time
build_bootimg
take_time
echo "TOOK $endtime min"
