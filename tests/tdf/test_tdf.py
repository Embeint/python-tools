import os

from infuse_iot.tdf import TDF

# assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"

TESTDATA_FILENAME = os.path.join(os.path.dirname(__file__), "tdf_example.bin")


def test_tdf():
    with open(TESTDATA_FILENAME, "rb") as f:
        test_data = f.read(-1)

    test_blocks = [test_data[i : (i + 512)] for i in range(0, len(test_data), 512)]

    decoder = TDF()
    total_tdfs = 0

    # Iterate over each block
    for block in test_blocks:
        assert len(block) % 512 == 0
        # Iterate over each TDF in the block
        for tdf in decoder.decode(block):
            assert isinstance(tdf, TDF.Reading)
            total_tdfs += 1

    # Number of TDFs on the example block should never change
    assert total_tdfs == 53
