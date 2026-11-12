"""OpenWrt platform adapter (skeleton).

OpenWrt runs Linux, so it shares the Linux enforcement path (tc, CAKE,
HTB+fq_codel, nftables, hostapd, dnsmasq). Detection of the OpenWrt environment
is done via /etc/openwrt_release.
"""

from __future__ import annotations

from gateway_agent.adapters.linux.adapter import LinuxAdapter


class OpenWrtAdapter(LinuxAdapter):
    name = "openwrt"
    platform = "openwrt"

    def __init__(self, config):
        super().__init__(config)

    async def detect_capabilities(self):
        report = await super().detect_capabilities()
        # On OpenWrt, UCI is used for network/AP config instead of raw files.
        return report
