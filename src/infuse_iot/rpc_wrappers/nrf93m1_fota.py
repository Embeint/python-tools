#!/usr/bin/env python3

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand

FOTA_ERROR_CAUSES = {
    1: "HTTP error",
    2: "Transport error",
    3: "Socket error",
    4: "Flash error",
    5: "Verification error",
    6: "TLS error",
    7: "Package size error",
}

FOTA_ERROR_DETAILS = {
    2: {
        8: "No such file",
        9: "Out of memory",
        10: "SSL configuration error",
        11: "URL parse error",
        12: "DNS resolution failed",
        13: "Protocol error",
        14: "Socket error",
        15: "Bind failed",
        16: "Connection timeout",
        17: "Connection error",
        18: "Server closed the connection",
        20: "Request timeout",
        21: "Internal error",
        23: "TLS is not supported",
    },
    3: {
        34: "I/O error",
        103: "Connection aborted locally",
        104: "Connection reset by peer",
        107: "Not connected",
    },
    4: {
        -2: "Offset past the end of the delta partition",
        -8: "Flash write failed",
        -17: "No delta partition registered",
        -19: "Writing the delta partition is not permitted",
    },
    5: {
        1: "Delta package was not found",
        2: "Delta is incomplete",
        3: "Delta is invalid",
        4: "Wrong base image",
        5: "Unmatched new image",
        6: "Patching failed",
        7: "Signature check failed",
        8: "Delta state is unavailable",
    },
}

TLS_VERIFICATION_FLAGS = {
    1: "Certificate is expired",
    2: "Certificate is revoked",
    4: "CN mismatch",
    8: "Untrusted CA",
    16: "CRL is not trusted",
    32: "CRL is expired",
    64: "Certificate is missing",
    128: "Verification was skipped",
    256: "Other reason",
    512: "Certificate is not yet valid",
    1024: "CRL is from the future",
    2048: "keyUsage mismatch",
    4096: "extendedKeyUsage mismatch",
    8192: "nsCertType mismatch",
    16384: "Unacceptable certificate signature hash",
    32768: "Unacceptable certificate signature algorithm",
    65536: "Unacceptable certificate key",
    131072: "Unacceptable CRL signature hash",
    262144: "Unacceptable CRL signature algorithm",
    524288: "Unacceptable CRL key",
}

# The modem reports Mbed TLS errors as decimal values. -0x7780 is the error
# emitted in the observed failure case.
MBEDTLS_ERROR_DETAILS = {
    -0x7780: "Fatal alert message received from peer",
}


def decode_fota_error(cause: int, detail: int) -> tuple[str, str]:
    """Return human-readable descriptions for %HTTPFOTADL FOTA error fields."""
    cause_description = FOTA_ERROR_CAUSES.get(cause, "Unknown error cause")

    if detail == 0:
        return cause_description, "No further information"

    if cause == 1:
        return cause_description, f"HTTP status {detail}"

    if cause == 6:
        if -32767 <= detail < 0:
            description = MBEDTLS_ERROR_DETAILS.get(detail, "Mbed TLS error")
            return cause_description, f"{description} ({detail}, {detail:#x})"
        if detail == -65537:
            return cause_description, "Peer closed the TLS record layer during a read"
        if detail == -65538:
            return cause_description, "Configured PSK key could not be decoded from hexadecimal"
        if detail > 0:
            flags = [description for flag, description in TLS_VERIFICATION_FLAGS.items() if detail & flag]
            if flags:
                return cause_description, "; ".join(flags)
            return cause_description, f"Unknown X.509 verification flags ({detail})"

    detail_description = FOTA_ERROR_DETAILS.get(cause, {}).get(detail)
    if detail_description is not None:
        return cause_description, detail_description
    if cause == 7:
        return cause_description, f"Attempted package size: {detail} bytes"
    return cause_description, f"Unknown detail ({detail})"


class nrf93m1_fota(InfuseRpcCommand, defs.nrf93m1_fota):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("url", type=str, help="HTTP/HTTPS URL of the nRF93M1 FOTA package")

    def __init__(self, args):
        self.url = args.url

    def command_timeout_ms(self) -> int:
        return 31 * 60 * 1000

    def request_struct(self):
        return self.url.encode("utf-8") + b"\x00"

    def request_json(self):
        return {"url": self.url}

    def handle_response(self, return_code, response):
        if return_code == 0:
            print("nRF93M1 FOTA package verified; modem is rebooting")
            return

        if response and response.cause:
            cause, detail = decode_fota_error(response.cause, response.detail)
            print(
                f"nRF93M1 FOTA failed ({self.return_code_str(return_code)}): "
                f"cause={response.cause} ({cause}), detail={response.detail} ({detail})"
            )
        else:
            print(f"nRF93M1 FOTA failed ({self.return_code_str(return_code)})")
