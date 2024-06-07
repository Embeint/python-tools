#!/usr/bin/env python3

import logging

# https://docs.python.org/3/howto/logging.html#configuring-logging-for-a-library
logging.getLogger("infuse").addHandler(logging.NullHandler())
