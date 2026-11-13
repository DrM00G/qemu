#!/usr/bin/env bash
# Local research only; public pinned source lives outside the QEMU checkout.
set -euo pipefail
task_root=${PHASE3_KERNEL_ROOT:-$HOME/cm5-phase3-kernel}
repo=$(cd -- "$(dirname -- "$0")/../.." && pwd)
task_root=$(realpath -m "$task_root")
case "$task_root" in "$repo"|"$repo"/*) echo 'Kernel workspace must be outside the QEMU checkout'; exit 1;; esac
mkdir -p "$task_root"
available_bytes=$(df -PB1 "$task_root" | awk 'NR==2 {print $4}')
if (( available_bytes < 8 * 1024 * 1024 * 1024 )); then
    echo 'Kernel workspace needs at least 8 GiB free persistent storage; avoid RAM-backed /tmp'
    exit 1
fi
free -h
df -h "$task_root"
revision=62a56e350fcfd1c5e204c62dac4ea4ee205eb24e
source_dir="$task_root/linux-$revision"
build_dir="$task_root/build"
mkdir -p "$task_root" "$build_dir"
if [[ ! -f "$source_dir/Makefile" ]]; then
    archive="$task_root/linux-$revision.tar.gz"
    curl -fL --retry 3 "https://codeload.github.com/raspberrypi/linux/tar.gz/$revision" -o "$archive"
    tar -xzf "$archive" -C "$task_root"
fi
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
make -C "$source_dir" O="$build_dir" defconfig
cfg=("$source_dir/scripts/config" --file "$build_dir/.config")
# Keep the generic virt platform; remove unrelated physical-board selections.
while read -r board; do
    [[ "$board" == ARCH_VIRT ]] || "${cfg[@]}" --disable "$board"
done < <(sed -n 's/^config \(ARCH_[A-Z0-9_]*\)$/\1/p' "$source_dir/arch/arm64/Kconfig.platforms")
for option in ARM64_4K_PAGES ARM64_64K_PAGES DEBUG_INFO DEBUG_INFO_BTF KVM \
    SOUND MEDIA_SUPPORT USB_SUPPORT WLAN WIRELESS BT MTD NFC INFINIBAND \
    DRM_NOUVEAU DRM_AMDGPU DRM_RADEON BTRFS_FS; do
    "${cfg[@]}" --disable "$option"
done
for option in ARM64_16K_PAGES ARCH_VIRT PCI PCI_HOST_GENERIC VIRTIO VIRTIO_PCI \
    VIRTIO_MMIO VIRTIO_BLK VIRTIO_NET VIRTIO_CONSOLE HW_RANDOM_VIRTIO \
    EXT4_FS OVERLAY_FS TMPFS TMPFS_XATTR BLK_DEV_INITRD RD_GZIP RD_ZSTD \
    DEVTMPFS DEVTMPFS_MOUNT BLK_DEV_DM DM_VERITY DM_VERITY_FEC \
    CRYPTO_SHA256 REED_SOLOMON REED_SOLOMON_DEC8 SERIAL_AMBA_PL011 \
    SERIAL_AMBA_PL011_CONSOLE DRM DRM_VIRTIO_GPU CGROUPS NAMESPACES \
    ISO9660_FS JOLIET SQUASHFS_XZ SQUASHFS_ZSTD SQUASHFS_LZ4 SQUASHFS_LZO DM_MULTIPATH \
    SECCOMP SECCOMP_FILTER FHANDLE INOTIFY_USER FANOTIFY AUTOFS_FS \
    UNIX INET IPV6 PACKET NETFILTER SECURITY SECURITY_APPARMOR; do
    "${cfg[@]}" --enable "$option"
done
"${cfg[@]}" --set-str LOCALVERSION '-cm5-surrogate-16k'
"${cfg[@]}" --disable LOCALVERSION_AUTO
"${cfg[@]}" --set-str SYSTEM_TRUSTED_KEYS '' --set-str SYSTEM_REVOCATION_KEYS ''
"${cfg[@]}" --set-val NR_CPUS 8
make -C "$source_dir" O="$build_dir" olddefconfig
for option in ARM64_16K_PAGES VIRTIO_BLK VIRTIO_NET PCI_HOST_GENERIC EXT4_FS \
    OVERLAY_FS BLK_DEV_DM DM_VERITY DM_VERITY_FEC CRYPTO_SHA256 REED_SOLOMON_DEC8 REED_SOLOMON_ENC8 \
    ISO9660_FS DM_MULTIPATH SQUASHFS_XZ; do
    grep -qx "CONFIG_$option=y" "$build_dir/.config" || { echo "Required option absent: $option"; exit 1; }
done
printf '%s\n' "$revision" > "$build_dir/source-commit.txt"
aarch64-linux-gnu-gcc --version > "$build_dir/compiler-version.txt"
make -C "$source_dir" O="$build_dir" -j "${JOBS:-4}" Image modules
make -C "$source_dir" O="$build_dir" INSTALL_MOD_PATH="$task_root/modules" modules_install
sha256sum "$build_dir/arch/arm64/boot/Image" "$build_dir/.config" > "$build_dir/SHA256SUMS"
make -s -C "$source_dir" O="$build_dir" kernelrelease > "$build_dir/kernelrelease.txt"
echo "Kernel built in $build_dir"
