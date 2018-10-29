import copy as cpy
import typing
import tbot
from tbot.machine import linux
from tbot.machine.linux import auth

H1 = typing.TypeVar("H1", bound=linux.LinuxMachine)
H2 = typing.TypeVar("H2", bound=linux.LinuxMachine)


@tbot.testcase
def copy(p1: linux.Path[H1], p2: linux.Path[H2]) -> None:
    """
    Copy a file, possibly from one host to another.

    If one of the paths is associated with an SSHMachine,
    ``scp`` will be used to do the transfer.

    :param linux.Path p1: Exisiting path to be copied
    :param linux.Path p2: Target where ``p1`` should be copied
    """
    if isinstance(p1.host, p2.host.__class__) or isinstance(p2.host, p1.host.__class__):
        # Both paths are on the same host
        p2_w1 = linux.Path(p1.host, p2)
        p1.host.exec0("cp", p1, p2_w1)
        return
    elif isinstance(p1.host, linux.SSHMachine) and p1.host.labhost is p2.host:
        # Copy from an SSH machine
        copy_to = False
        local_path = typing.cast(linux.Path[linux.LinuxMachine], p2)
        remote_path = typing.cast(linux.Path[linux.SSHMachine], p1)
    elif isinstance(p2.host, linux.SSHMachine) and p2.host.labhost is p1.host:
        # Copy to an SSH machine
        copy_to = True
        local_path = typing.cast(linux.Path[linux.LinuxMachine], p1)
        remote_path = typing.cast(linux.Path[linux.SSHMachine], p2)
    elif isinstance(p1.host, linux.lab.LocalLabHost) and isinstance(
        p2.host, linux.lab.SSHLabHost
    ):
        # Copy from local to ssh labhost
        copy_to = True
        local_path = typing.cast(linux.Path[linux.LinuxMachine], p1)
        # Create a fake SSH machine path
        fake_machine = cpy.copy(p2.host)
        setattr(fake_machine, "ignore_hostkey", False)
        remote_path = typing.cast(
            linux.Path[linux.SSHMachine], linux.Path(fake_machine, p2)
        )
    elif isinstance(p2.host, linux.lab.LocalLabHost) and isinstance(
        p1.host, linux.lab.SSHLabHost
    ):
        # Copy to local from ssh labhost
        copy_to = False
        local_path = typing.cast(linux.Path[linux.LinuxMachine], p2)
        # Create a fake SSH machine path
        fake_machine = cpy.copy(p1.host)
        setattr(fake_machine, "ignore_hostkey", False)
        remote_path = typing.cast(
            linux.Path[linux.SSHMachine], linux.Path(fake_machine, p1)
        )
    else:
        raise NotImplementedError(f"Can't copy from {p1.host} to {p2.host}!")

    # Copy from/to an SSH host
    local_host = local_path.host
    ssh_host: linux.SSHMachine = remote_path.host

    hk_disable = ["-o", "StrictHostKeyChecking=no"] if ssh_host.ignore_hostkey else []

    scp_command = ["scp", "-P", str(ssh_host.port), *hk_disable]

    authenticator = ssh_host.authenticator
    if isinstance(authenticator, auth.PrivateKeyAuthenticator):
        scp_command += ["-o", "BatchMode=yes", "-i", str(authenticator.key)]
    elif isinstance(authenticator, auth.PasswordAuthenticator):
        scp_command = ["sshpass", "-p", authenticator.password] + scp_command

    if copy_to:
        local_host.exec0(
            *scp_command,
            local_path,
            f"{ssh_host.username}@{ssh_host.hostname}:{remote_path._local_str()}",
        )
    else:
        local_host.exec0(
            *scp_command,
            f"{ssh_host.username}@{ssh_host.hostname}:{remote_path._local_str()}",
            local_path,
        )