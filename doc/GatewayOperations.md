# Gateway capabilities and operation ownership

`LocalClient.capabilities()` probes the gateway using the existing comms-check
request. A version 2 gateway reports its kind and supported features. Plain
replies may answer other clients' comms checks, so the probe waits until its
deadline for capabilities. It returns protocol version 1 with an empty feature
list only if the gateway sent plain replies, and raises `TimeoutError` rather
than assuming the gateway supports new messages when nothing answered.

For a sequence of device operations, acquire ownership before connecting:

```python
with client.operation(device_id):
    with client.connection(device_id, data_types, timeout_ms=30000) as mtu:
        rpc = RpcClient(client, mtu, device_id)
        # Query preconditions and execute the related operation here.
```

The gateway admits one exclusive operation at a time. An acquisition fails
immediately with `device_busy` if another operation or a legacy connection is
active, or a released connection is still closing; callers retry later. Physical
Bluetooth connection sharing remains available to ordinary clients outside an
exclusive operation. Other clients may continue receiving telemetry. Operations
require a concrete device ID: the serial gateway's own ID is accepted, the
`InfuseID.GATEWAY` alias is not.

Requests belonging to an operation carry a random operation ID. Connection
results for the owned device carry that ID while the owner has a connection
request outstanding. Connection request IDs are preserved alongside operation IDs,
so results of a link released earlier do not satisfy a later request. A foreign request cannot send packets or release the owned
connection. Operation IDs coordinate trusted local clients; they do not provide
authentication for remote access.

Ownership expires after inactivity. The default is 60 seconds, configurable
between 5 and 300 seconds. The owner's requests and connection results refresh
the deadline, as do packets from the owned device received over its connection
or answering an RPC. Renew across longer silent steps with
`control_request("renew_operation", {"owner": operation_id})`. Expiry or
explicit release sends a release for each connection the operation still holds,
and for a link it created that no request references. Cleanup releases carry each
original connection request ID so the gateway releases the correct client reference.

A released connection is closing until the gateway reports it dropped or failed.
So that a lost notification cannot block the gateway, the wait ends 15 seconds
after any pending connection setup (at most 60 seconds) could complete. Results
of a teardown that outlasts this bound may reach the next owner. The serial
gateway's own device is always connected and needs no teardown. Legacy requests
the gateway has not yet answered, such as those made while a link closes or
drops, survive its teardown. The gateway answers them over a new link, so they
still block acquisitions until released, while a failure of the link ends them,
as their clients take the failure as their own result. A released request whose
setup then fails leaves no link to tear down, so the device stops closing.

A legacy client killed while connected leaves its link open, so acquisitions
fail until that device disconnects. Legacy connections to the serial gateway's
own device never drop, and stop blocking after 60 seconds without requests.
Packets rejected for another operation are dropped without a notification, as
older clients could not recognise one; their RPCs wait for the RPC timeout.
Packets of an expired operation are also dropped without a notification, but
expiry releases its connections, so its client sees the link drop once it closes.
Rejected connection requests fail immediately with `device_busy`, or with
`operation_expired` if they carry the ID of an operation that has ended. Until
an ended operation's connections are released, legacy connection requests fail
with `device_busy`, while legacy releases still reach the gateway.

Every control request is answered. Failures raise `GatewayControlError`, a
`RuntimeError` whose string is the error `code`, with the gateway's optional
`message`. Unknown methods fail with `unsupported_capability`, malformed
parameters with `invalid_request` and unexpected handler failures with
`internal_error`. Handlers report specific failures by raising
`GatewayControlError(code, message)`.

Control responses use the existing comms-check notification type with extra
fields so older telemetry clients can ignore them. New control requests are sent
only after capability discovery. The protocol is additive and uses the same
loopback UDP transport as the existing tools. Clients skip notifications they
cannot decode and keep waiting until their own deadline, so new notification
types do not break them. No MCP dependency is required.
