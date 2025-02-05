#!/usr/bin/env python3

import enum


class errno(enum.IntEnum):
    """Error codes exported from Zephyr `errno.h`"""

    EPERM = (1, "Not owner")
    ENOENT = (2, "No such file or directory")
    ESRCH = (3, "No such context")
    EINTR = (4, "Interrupted system call")
    EIO = (5, "I/O error")
    ENXIO = (6, "No such device or address")
    E2BIG = (7, "Arg list too long")
    ENOEXEC = (8, "Exec format error")
    EBADF = (9, "Bad file number")
    ECHILD = (10, "No children")
    EAGAIN = (11, "No more contexts")
    ENOMEM = (12, "Not enough core")
    EACCES = (13, "Permission denied")
    EFAULT = (14, "Bad address")
    ENOTBLK = (15, "Block device required")
    EBUSY = (16, "Mount device busy")
    EEXIST = (17, "File exists")
    EXDEV = (18, "Cross-device link")
    ENODEV = (19, "No such device")
    ENOTDIR = (20, "Not a directory")
    EISDIR = (21, "Is a directory")
    EINVAL = (22, "Invalid argument")
    ENFILE = (23, "File table overflow")
    EMFILE = (24, "Too many open files")
    ENOTTY = (25, "Not a typewriter")
    ETXTBSY = (26, "Text file busy")
    EFBIG = (27, "File too large")
    ENOSPC = (28, "No space left on device")
    ESPIPE = (29, "Illegal seek")
    EROFS = (30, "Read-only file system")
    EMLINK = (31, "Too many links")
    EPIPE = (32, "Broken pipe")
    EDOM = (33, "Argument too large")
    ERANGE = (34, "Result too large")
    ENOMSG = (35, "Unexpected message type")
    EDEADLK = (45, "Resource deadlock avoided")
    ENOLCK = (46, "No locks available")
    ENOSTR = (60, "STREAMS device required")
    ENODATA = (61, "Missing expected message data")
    ETIME = (62, "STREAMS timeout occurred")
    ENOSR = (63, "Insufficient memory")
    EPROTO = (71, "Generic STREAMS error")
    EBADMSG = (77, "Invalid STREAMS message")
    ENOSYS = (88, "Function not implemented")
    ENOTEMPTY = (90, "Directory not empty")
    ENAMETOOLONG = (91, "File name too long")
    ELOOP = (92, "Too many levels of symbolic links")
    EOPNOTSUPP = (95, "Operation not supported on socket")
    EPFNOSUPPORT = (96, "Protocol family not supported")
    ECONNRESET = (104, "Connection reset by peer")
    ENOBUFS = (105, "No buffer space available")
    EAFNOSUPPORT = (106, "Addr family not supported")
    EPROTOTYPE = (107, "Protocol wrong type for socket")
    ENOTSOCK = (108, "Socket operation on non-socket")
    ENOPROTOOPT = (109, "Protocol not available")
    ESHUTDOWN = (110, "Can't send after socket shutdown")
    ECONNREFUSED = (111, "Connection refused")
    EADDRINUSE = (112, "Address already in use")
    ECONNABORTED = (113, "Software caused connection abort")
    ENETUNREACH = (114, "Network is unreachable")
    ENETDOWN = (115, "Network is down")
    ETIMEDOUT = (116, "Connection timed out")
    EHOSTDOWN = (117, "Host is down")
    EHOSTUNREACH = (118, "No route to host")
    EINPROGRESS = (119, "Operation now in progress")
    EALREADY = (120, "Operation already in progress")
    EDESTADDRREQ = (121, "Destination address required")
    EMSGSIZE = (122, "Message size")
    EPROTONOSUPPORT = (123, "Protocol not supported")
    ESOCKTNOSUPPORT = (124, "Socket type not supported")
    EADDRNOTAVAIL = (125, "Can't assign requested address")
    ENETRESET = (126, "Network dropped connection on reset")
    EISCONN = (127, "Socket is already connected")
    ENOTCONN = (128, "Socket is not connected")
    ETOOMANYREFS = (129, "Too many references: can't splice")
    ENOTSUP = (134, "Unsupported value/command")
    EILSEQ = (138, "Illegal byte sequence")
    EOVERFLOW = (139, "Value overflow")
    ECANCELED = (140, "Operation canceled")

    description: str

    def __new__(cls, value: int, description: str = ""):
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.description = description
        return obj

    @classmethod
    def strerror(cls, int) -> str:
        return cls(int).description
