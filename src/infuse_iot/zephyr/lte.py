#!/usr/bin/env python3

import enum


class RegistrationState(enum.IntEnum):
    NOT_REGISTERED = 0
    REGISTERED_HOME = 1
    SEARCHING = 2
    REGISTRATION_DENIED = 3
    REGISTRATION_UNKNOWN = 4
    REGISTERED_ROAMING = 5
    UICC_FAIL = 90

    def __str__(self):
        pretty_names = {
            self.NOT_REGISTERED: "Not registered",
            self.REGISTERED_HOME: "Registered (Home Network)",
            self.SEARCHING: "Searching",
            self.REGISTRATION_DENIED: "Registration denied",
            self.REGISTRATION_UNKNOWN: "Unknown",
            self.REGISTERED_ROAMING: "Registered (Roaming)",
            self.UICC_FAIL: "SIM card failure",
        }
        return pretty_names[self.value]


class AccessTechnology(enum.IntEnum):
    NONE = 0
    LTE_M = 7
    NB_IOT = 9

    def __str__(self):
        pretty_names = {
            self.NONE: "None",
            self.LTE_M: "LTE-M",
            self.NB_IOT: "NB-IoT",
        }
        return pretty_names[self.value]


class LteSystemMode(enum.IntEnum):
    LTE_M = 1
    NB_IOT = 2
    GNSS = 3
    LTE_M_GNSS = 4
    NB_IOT_GNSS = 5
    LTE_M_NB_IOT = 6
    LTE_M_NB_IOT_GNSS = 7
    DEFAULT = 0xFF

    def __str__(self):
        pretty_names = {
            self.LTE_M: "LTE-M",
            self.NB_IOT: "NB-IoT",
            self.GNSS: "GNSS",
            self.LTE_M_GNSS: "LTE-M + GNSS",
            self.NB_IOT_GNSS: "NB-IoT + GNSS",
            self.LTE_M_NB_IOT: "LTE-M + NB-IoT",
            self.LTE_M_NB_IOT_GNSS: "LTE-M + NB-IoT + GNSS",
            self.DEFAULT: "Modem default",
        }
        return pretty_names[self.value]


class LteSystemPreference(enum.IntEnum):
    AUTO = 0
    LTE_M = 1
    NB_IOT = 2
    PLMN_LTE_M = 3
    PLMN_NB_IOT = 4

    def __str__(self):
        pretty_names = {
            self.AUTO: "No preference",
            self.LTE_M: "LTE-M",
            self.NB_IOT: "NB-IoT",
            self.PLMN_LTE_M: "PLMN > LTE-M",
            self.PLMN_NB_IOT: "PLMN > NB-IoT",
        }
        return pretty_names[self.value]


class LteBand:
    def __init__(self, band, freq_dl_low, offset_dl, freq_ul_low, offset_ul):
        self.band = band
        self.fdl_low = freq_dl_low
        self.ndl = offset_dl
        self.ful_low = freq_ul_low
        self.nul = offset_ul


class LteBands:
    bands = {
        1: LteBand(1, 2110, 0, 1920, 18000),
        2: LteBand(2, 1930, 600, 1850, 18600),
        3: LteBand(3, 1805, 1200, 1710, 19200),
        4: LteBand(4, 2110, 1950, 1710, 19950),
        5: LteBand(5, 869, 2400, 824, 20400),
        6: LteBand(6, 875, 2650, 830, 20650),
        7: LteBand(7, 2620, 2750, 2500, 20750),
        8: LteBand(8, 925, 3450, 880, 21450),
        9: LteBand(9, 1844.9, 3800, 1749.9, 21800),
        10: LteBand(10, 2110, 4150, 1710, 22150),
        11: LteBand(11, 1475.9, 4750, 1427.9, 22750),
        12: LteBand(12, 729, 5010, 699, 23010),
        13: LteBand(13, 746, 5180, 777, 23180),
        14: LteBand(14, 758, 5280, 788, 23280),
        17: LteBand(17, 734, 5730, 704, 23730),
        18: LteBand(18, 860, 5850, 815, 23850),
        19: LteBand(19, 875, 6000, 830, 24000),
        20: LteBand(20, 791, 6150, 832, 24150),
        21: LteBand(21, 1495.9, 6450, 1447.9, 24450),
        22: LteBand(22, 3510, 6600, 3410, 24600),
        23: LteBand(23, 2180, 7500, 2000, 25500),
        24: LteBand(24, 1525, 7700, 1626.5, 25700),
        25: LteBand(25, 1930, 8040, 1850, 26040),
        26: LteBand(26, 859, 8690, 814, 26690),
        27: LteBand(27, 852, 9040, 807, 27040),
        28: LteBand(28, 758, 9210, 703, 27210),
        31: LteBand(31, 462.5, 9870, 452.5, 27760),
        33: LteBand(33, 1900, 36000, 1900, 36000),
        34: LteBand(34, 2010, 36200, 2010, 36200),
        35: LteBand(35, 1850, 36350, 1850, 36350),
        36: LteBand(36, 1930, 36950, 1930, 36950),
        37: LteBand(37, 1910, 37550, 1910, 37550),
        38: LteBand(38, 2570, 37750, 2570, 37750),
        39: LteBand(39, 1880, 38250, 1880, 38250),
        40: LteBand(40, 2300, 38650, 2300, 38650),
        41: LteBand(41, 2496, 39650, 2496, 39650),
        42: LteBand(42, 3400, 41590, 3400, 41590),
        43: LteBand(43, 3600, 43590, 3600, 43590),
        44: LteBand(44, 703, 45590, 703, 45590),
    }

    @classmethod
    def earfcn_to_freq(cls, earfcn_dl):
        prev = None
        for b in cls.bands.values():
            if prev is None:
                prev = b
                continue
            if earfcn_dl >= prev.ndl and earfcn_dl < b.ndl:
                info = prev

                ul_offset = info.nul - info.ndl
                earfcn_ul = earfcn_dl + ul_offset

                freq_dl = info.fdl_low + 0.1 * (earfcn_dl - info.ndl)
                freq_ul = info.ful_low + 0.1 * (earfcn_ul - info.nul)
                return (freq_dl, freq_ul)

            prev = b
        raise ValueError(f"EARFCN {earfcn_dl} is invalid")


class MobileCountryCodes:
    _names = {
        289: "Abkhazia",
        412: "Afghanistan",
        276: "Albania",
        603: "Algeria",
        544: "American Samoa (United States of America)",
        213: "Andorra",
        631: "Angola",
        365: "Anguilla (United Kingdom)",
        344: "Antigua and Barbuda",
        722: "Argentina",
        283: "Armenia",
        363: "Aruba",
        505: "Australia",
        232: "Austria",
        400: "Azerbaijan",
        364: "Bahamas",
        426: "Bahrain",
        470: "Bangladesh",
        342: "Barbados",
        257: "Belarus",
        206: "Belgium",
        702: "Belize",
        616: "Benin",
        350: "Bermuda",
        402: "Bhutan",
        736: "Bolivia",
        362: "Bonaire, Sint Eustatius and Saba, Curaçao, Saint Maarten",
        218: "Bosnia and Herzegovina",
        652: "Botswana",
        724: "Brazil",
        995: "British Indian Ocean Territory (United Kingdom)",
        348: "British Virgin Islands (United Kingdom)",
        528: "Brunei",
        284: "Bulgaria",
        613: "Burkina Faso",
        642: "Burundi",
        456: "Cambodia",
        624: "Cameroon",
        302: "Canada",
        625: "Cape Verde",
        346: "Cayman Islands (United Kingdom)",
        623: "Central African Republic",
        622: "Chad",
        730: "Chile",
        460: "China",
        461: "China",
        732: "Colombia",
        654: "Comoros",
        629: "Congo",
        548: "Cook Islands (Pacific Ocean)",
        712: "Costa Rica",
        219: "Croatia",
        368: "Cuba",
        280: "Cyprus",
        230: "Czech Republic",
        630: "Democratic Republic of the Congo",
        238: "Denmark (Kingdom of Denmark)",
        638: "Djibouti",
        366: "Dominica",
        370: "Dominican Republic",
        514: "East Timor",
        740: "Ecuador",
        602: "Egypt",
        706: "El Salvador",
        627: "Equatorial Guinea",
        657: "Eritrea",
        248: "Estonia",
        636: "Ethiopia",
        750: "Falkland Islands (United Kingdom)",
        288: "Faroe Islands (Kingdom of Denmark)",
        542: "Fiji",
        244: "Finland",
        208: "France",
        742: "French Guiana (France)",
        647: "French Indian Ocean Territories (France)",
        547: "French Polynesia (France)",
        628: "Gabon",
        607: "Gambia",
        282: "Georgia",
        262: "Germany",
        620: "Ghana",
        266: "Gibraltar (United Kingdom)",
        202: "Greece",
        290: "Greenland (Kingdom of Denmark)",
        352: "Grenada",
        340: "Guadeloupe, Martinique, Saint Barthélemy, Saint Martin (France)",
        704: "Guatemala",
        611: "Guinea",
        632: "Guinea-Bissau",
        738: "Guyana",
        372: "Haiti",
        708: "Honduras",
        454: "Hong Kong",
        216: "Hungary",
        274: "Iceland",
        404: "India",
        405: "India",
        406: "India",
        510: "Indonesia",
        432: "Iran",
        418: "Iraq",
        272: "Ireland",
        425: "Israel, Palestine",
        222: "Italy",
        612: "Ivory Coast",
        338: "Jamaica",
        440: "Japan",
        441: "Japan",
        416: "Jordan",
        401: "Kazakhstan",
        639: "Kenya",
        545: "Kiribati",
        467: "rea",
        450: "rea",
        221: "Kosovo",
        419: "Kuwait",
        437: "Kyrgyzstan",
        457: "Laos",
        247: "Latvia",
        415: "Lebanon",
        651: "Lesotho",
        618: "Liberia",
        606: "Libya",
        295: "Liechtenstein",
        246: "Lithuania",
        270: "Luxembourg",
        455: "Macau",
        294: "North Macedonia",
        646: "Madagascar",
        650: "Malawi",
        502: "Malaysia",
        472: "Maldives",
        610: "Mali",
        278: "Malta",
        551: "Marshall Islands",
        609: "Mauritania",
        617: "Mauritius",
        334: "Mexico",
        550: "cronesia",
        259: "Moldova",
        212: "Monaco",
        428: "Mongolia",
        297: "Montenegro",
        354: "Montserrat (United Kingdom)",
        604: "Morocco",
        643: "Mozambique",
        414: "Myanmar",
        649: "Namibia",
        536: "Nauru",
        429: "Nepal",
        204: "Netherlands (Kingdom of the Netherlands)",
        546: "New Caledonia",
        530: "New Zealand",
        710: "Nicaragua",
        614: "Niger",
        621: "Nigeria",
        555: "Niue",
        242: "Norway",
        422: "Oman",
        410: "Pakistan",
        552: "Palau",
        714: "Panama",
        537: "Papua New Guinea",
        744: "Paraguay",
        716: "Peru",
        515: "Philippines",
        260: "Poland",
        268: "Portugal",
        330: "Puerto Rico (United States of America)",
        427: "Qatar",
        226: "Romania",
        250: "Russian Federation",
        635: "Rwanda",
        658: "int Helena",
        356: "Saint Kitts and Nevis",
        358: "Saint Lucia",
        308: "Saint Pierre and Miquelon",
        360: "Saint Vincent and the Grenadines",
        549: "Samoa",
        292: "San Marino",
        626: "São Tomé and Príncipe",
        420: "Saudi Arabia",
        608: "Senegal",
        220: "Serbia",
        633: "Seychelles",
        619: "Sierra Leone",
        525: "Singapore",
        231: "Slovakia",
        293: "Slovenia",
        540: "Solomon Islands",
        637: "Somalia",
        655: "South Africa",
        659: "South Sudan",
        214: "Spain",
        413: "Sri Lanka",
        634: "Sudan",
        746: "Suriname",
        653: "Swaziland",
        240: "Sweden",
        228: "Switzerland",
        417: "Syria",
        466: "Taiwan",
        436: "Tajikistan",
        640: "Tanzania",
        520: "Thailand",
        615: "Togo",
        554: "Tokelau",
        539: "Tonga",
        374: "Trinidad and Tobago",
        605: "Tunisia",
        286: "Turkey",
        438: "Turkmenistan",
        376: "Turks and Caicos Islands",
        553: "Tuvalu",
        641: "Uganda",
        255: "Ukraine",
        424: "United Arab Emirates",
        430: "United Arab Emirates (Abu Dhabi)",
        431: "United Arab Emirates (Dubai)",
        234: "United Kingdom",
        235: "United Kingdom",
        310: "United States of America",
        311: "United States of America",
        312: "United States of America",
        313: "United States of America",
        314: "United States of America",
        315: "United States of America",
        316: "United States of America",
        332: "United States Virgin Islands",
        748: "Uruguay",
        434: "Uzbekistan",
        541: "Vanuatu",
        734: "Venezuela",
        452: "Vietnam",
        543: "Wallis and Futuna",
        421: "Yemen",
        645: "Zambia",
        648: "Zimbabwe",
    }

    @classmethod
    def name_from_mcc(cls, mcc):
        return cls._names.get(mcc, "Unknown")
