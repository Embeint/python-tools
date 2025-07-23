#!/usr/bin/env python3

import enum


class WiFiState(enum.IntEnum):
    DISCONNECTED = 0
    INTERFACE_DISABLED = 1
    INACTIVE = 2
    SCANNING = 3
    AUTHENTICATING = 4
    ASSOCIATING = 5
    ASSOCIATED = 6
    HANDSHAKE_4WAY = 7
    GROUP_HANDSHAKE = 8
    COMPLETED = 9
    UNKNOWN = 10


class InterfaceMode(enum.IntEnum):
    INFRASTRUCTURE_STATION = 0
    IBSS_STATION = 1
    AP = 2
    P2P_GO = 3
    P2P_GROUP_FORMATION = 4
    MESH = 5


class FrequencyBand(enum.IntEnum):
    BAND_2_4_GHZ = 0
    BAND_5_GHZ = 1
    BAND_6_GHZ = 2

    def __str__(self):
        pretty_names = {
            self.BAND_2_4_GHZ: "2.4 GHz",
            self.BAND_5_GHZ: "5 GHz",
            self.BAND_6_GHZ: "6 GHz",
        }
        return pretty_names[self.value]


class FrequencyChannel(enum.IntEnum):
    CHANNEL_ANY = 255


class LinkMode(enum.IntEnum):
    WIFI_802_11 = 0
    WIFI_802_11b = 1
    WIFI_802_11a = 2
    WIFI_802_11g = 3
    WIFI_802_11n = 4
    WIFI_802_11ac = 5
    WIFI_802_11ax = 6
    WIFI_802_11ax_6Ghz = 7
    WIFI_802_11be = 8

    def __str__(self):
        pretty_names = {
            self.WIFI_802_11: "802.11 (Legacy)",
            self.WIFI_802_11b: "802.11.b",
            self.WIFI_802_11a: "802.11.a",
            self.WIFI_802_11g: "802.11.g",
            self.WIFI_802_11n: "802.11.n",
            self.WIFI_802_11ac: "802.11.ac",
            self.WIFI_802_11ax: "802.11.ax",
            self.WIFI_802_11ax_6Ghz: "802.11.ax (6 GHz)",
            self.WIFI_802_11be: "802.11.be",
        }
        return pretty_names[self.value]


class SecurityType(enum.IntEnum):
    NONE = 0
    WPA2_PSK = 1
    WPA2_PSK_SHA256 = 2
    WPA3_SAE = 3
    GB_WAPI = 4
    EAP = 5
    WEP = 6
    WPA_PSK = 7

    def __str__(self):
        pretty_names = {
            self.NONE: "None",
            self.WPA2_PSK: "WPA2-PSK",
            self.WPA2_PSK_SHA256: "WPA2-PSK-SHA256",
            self.WPA3_SAE: "WPA3-SAE",
            self.GB_WAPI: "GB 15629.11-2003 WAPI",
            self.EAP: "EAP",
            self.WEP: "WEP",
            self.WPA_PSK: "WPA-PSK",
        }
        return pretty_names[self.value]
