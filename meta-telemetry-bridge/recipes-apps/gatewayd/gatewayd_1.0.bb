SUMMARY = "C++ Industrial Gateway Daemon for Heterogeneous Edge System"
SECTION = "apps"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

FILESEXTRAPATHS:prepend := "${THISDIR}/../../../gatewayd:"

SRC_URI = "file://src/ \
           file://inc/ \
           file://CMakeLists.txt \
           file://gatewayd.service"

S = "${WORKDIR}"

inherit cmake systemd

do_install:append() {
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/gatewayd.service ${D}${systemd_system_unitdir}/gatewayd.service
}

SYSTEMD_SERVICE:${PN} = "gatewayd.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

FILES:${PN} += "${bindir}/gatewayd \
                ${systemd_system_unitdir}/gatewayd.service"
