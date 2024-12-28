#!/usr/bin/env python3


def humanised_seconds(seconds: int, units: int = 2) -> str:
    """Convert a seconds count to human readable units"""
    scales = [365 * 24 * 60 * 60, 7 * 24 * 60 * 60, 24 * 60 * 60, 60 * 60, 60, 1]
    postfix = ["year", "week", "day", "hour", "minute", "second"]

    vals = []
    for scale in scales:
        vals.append(seconds // scale)
        seconds -= scale * vals[-1]

    def construct(val, postfix):
        return f"{val} {postfix}{'' if val == 1 else 's'}"

    for idx, val in enumerate(vals):
        if val == 0:
            continue
        units = min(units, len(postfix) - idx)
        final = []
        while units > 0:
            final.append(construct(vals[idx], postfix[idx]))
            idx += 1
            units -= 1

        return ", ".join(final)
    return "0 seconds"
