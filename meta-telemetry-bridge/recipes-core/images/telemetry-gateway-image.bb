SUMMARY = "Custom Production Image for STM32 Telemetry Linux Gateway"
DESCRIPTION = "Minimalist Yocto Linux image containing the telemetry gateway daemon and hardware utilities."
LICENSE = "MIT"

# Inherit standard core image functionality
inherit core-image

# Base image features
IMAGE_FEATURES += " \
    splash \
    ssh-server-dropbear \
    hwcodecs \
"

# Package selection for the Gateway OS
IMAGE_INSTALL:append = " \
    packagegroup-core-boot \
    gatewayd \
    telemetry-daemon \
    sensor-gateway-app \
    openocd \
    libgpiod \
    libgpiod-tools \
    wireless-regdb-static \
    wpa-supplicant \
    iproute2 \
    tzdata \
"

# Set image storage capacity constraints
IMAGE_LINGUAS = " "
IMAGE_ROOTFS_SIZE ?= "8192"
IMAGE_ROOTFS_EXTRA_SPACE ?= "102400"
