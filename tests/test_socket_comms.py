import os

import infuse_iot.socket_comms as comms

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def test_socket_comms():
    # Ensure notifications can be sent from the server to the client, and requests sent in reverse
    multicast_addr = comms.default_multicast_address()
    # Increment port by 1 so we can run the tests in parallel with a real instance
    test_addr = (multicast_addr[0], multicast_addr[1] + 1)
    server = comms.LocalServer(test_addr)
    client = comms.LocalClient(test_addr)

    # Send request to server
    request = comms.GatewayRequestCommsCheck()
    client.send(request)

    # Server receives request, responds
    recv_req = server.receive()
    assert isinstance(recv_req, comms.GatewayRequestCommsCheck)
    response = comms.ClientNotificationCommsCheck()
    server.broadcast(response)

    # Client receives the response
    recv_rsp = client.receive()
    assert isinstance(recv_rsp, comms.ClientNotificationCommsCheck)
