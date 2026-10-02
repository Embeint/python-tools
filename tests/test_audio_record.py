import wave
from types import SimpleNamespace
from unittest.mock import Mock

from infuse_iot.common import InfuseType
from infuse_iot.definitions import tdf as tdf_defs
from infuse_iot.epacket import interface
from infuse_iot.socket_comms import ClientNotificationConnectionDropped, ClientNotificationEpacketReceived
from infuse_iot.tools.audio_record import SubCommand


def test_recording_survives_idle_and_unrelated_disconnect(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = Mock()
    monkeypatch.setattr("infuse_iot.tools.audio_record.LocalClient", lambda *_: client)
    command = SubCommand(SimpleNamespace(server_sock=None, gateway=False, id=123, name="test", conn_timeout=1000))
    command._freq = 8000
    command._decoder = Mock()
    command._decoder.decode.return_value = [Mock(id=tdf_defs.readings.pcm_16bit_chan_left.ID, data=[Mock(val=7)])]
    packet = Mock(route=[Mock(infuse_id=123, interface=interface.ID.BT_CENTRAL)], ptype=InfuseType.TDF, payload=b"")
    client.receive.side_effect = [
        None,
        ClientNotificationConnectionDropped(999),
        ClientNotificationEpacketReceived(packet),
        ClientNotificationConnectionDropped(123),
    ]
    command.handle_connection()
    files = list(tmp_path.glob("*.wav"))
    assert len(files) == 1
    with wave.open(str(files[0]), "rb") as recording:
        assert recording.getframerate() == 8000
        assert recording.readframes(1) == b"\x07\x00"
