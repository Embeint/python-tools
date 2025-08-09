#!/usr/bin/env python3

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class gravity_reference_update(InfuseRpcCommand, defs.gravity_reference_update):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--variance", type=int, default=0, help="Maximum axis variance to accept")

    def __init__(self, args):
        self._max_variance = args.variance

    def request_struct(self):
        return self.request(self._max_variance)

    def request_json(self):
        return {"max_variance": str(self._max_variance)}

    def handle_response(self, return_code, response):
        r = response

        if return_code == -errno.EIO:
            print(f"IMU variance too large: {r.variance.x:6d} {r.variance.y:6d} {r.variance.z:6d}")
            return
        elif return_code < 0:
            print(f"Failed to update gravity reference vector ({errno.strerror(-return_code)})")
            return

        print(f"\t  Gravity: {r.reference.x:6d} {r.reference.y:6d} {r.reference.z:6d}")
        print(f"\t Variance: {r.variance.x:6d} {r.variance.y:6d} {r.variance.z:6d}")
        print(f"\t  Samples: {r.num_samples:d}")
        print(f"\t   Period: {r.sample_period_us:d} us")
