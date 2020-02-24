# tbot, Embedded Automation Tool
# Copyright (C) 2019  Harald Seiler
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import abc
import contextlib
import typing

from . import linux_shell, path
import tbot
from tbot.machine import linux

class Toolchain(abc.ABC):
    """Generic toolchain type."""

    @abc.abstractmethod
    def enable(self, host: "Builder") -> None:
        """Enable this toolchain on the given ``host``."""
        pass


H = typing.TypeVar("H", bound="Builder")


class EnvScriptToolchain(Toolchain):
    """Toolchain that is initialized using an env script."""

    def enable(self, host: H) -> None:
        host.exec0("unset", "LD_LIBRARY_PATH")
        host.exec0("source", self.env_script)

    def __init__(self, path: path.Path[H]) -> None:
        """
        Create a new EnvScriptToolchain.

        :param linux.Path path: Path to the env script
        """
        self.env_script = path


class Builder(linux_shell.LinuxShell):
    """
    Mixin to mark a machine as a build-host.

    You need to define the ``toolchain()`` method when using this mixin.  You
    can then use the ``enable()`` method to enable a toolchain and compile
    projects with it:

    .. code-block:: python

        with MyBuildHost(lh) as bh:
            bh.exec0("uptime")

            with bh.enable("generic-armv7a-hf"):
                cc = bh.env("CC")
                bh.exec0(linux.Raw(cc), "main.c")

    .. note::

        If you look closely, I have used ``linux.Raw(cc)`` in the ``exec0()``
        call.  This is necessary because a lot of toolchains define ``$CC`` as
        something like

        .. code-block:: text

            CC=arm-poky-linux-gnueabi-gcc -march=armv7-a -mfpu=neon -mfloat-abi=hard -mcpu=cortex-a8

        where some parameters are already included.  Without the
        :py:class:`linux.Raw <tbot.machine.linux.Raw>`, tbot would run

        .. code-block:: shell-session

            $ "${CC}" main.c

        where the arguments are interpreted as part of the path to the compiler.
        This will obviously fail so instead, with the :py:class:`linux.Raw
        <tbot.machine.linux.Raw>`,
        tbot will run

        .. code-block:: shell-session

            $ ${CC} main.c

        where the shell expansion will do the right thing.
    """

    @property
    @abc.abstractmethod
    def toolchains(self) -> typing.Dict[str, Toolchain]:
        """
        Return a dictionary of all toolchains that exist on this buildhost.

        **Example**::

            @property
            def toolchains(self) -> typing.Dict[str, linux.build.Toolchain]:
                return {
                    "generic-armv7a": linux.build.EnvScriptToolchain(
                        linux.Path(
                            self,
                            "/path/to/environment-setup-armv7a-neon-poky-linux-gnueabi",
                        )
                    ),
                    "generic-armv7a-hf": linux.build.EnvScriptToolchain(
                        linux.Path(
                            self,
                            "/path/to/environment-setup-armv7ahf-neon-poky-linux-gnueabi",
                        )
                    ),
                }
        """
        pass

    @contextlib.contextmanager
    def enable(self, arch: str) -> typing.Iterator[None]:
        """
        Enable the toolchain for ``arch`` on this BuildHost instance.

        **Example**::

            with lh.build() as bh:
                # Now we are on the buildhost

                with bh.enable("generic-armv7a-hf"):
                    # Toolchain is enabled here
                    cc = bh.env("CC")
                    bh.exec0(linux.Raw(cc), "--version")
        """
        tc = self.toolchains[arch]

        with self.subshell():
            tc.enable(self)
            yield None

class EnvSetLinaroToolchain(Toolchain):
    """Toolchain from
    https://releases.linaro.org/components/toolchain/binaries/
    initialized through setting Shell Environment variables.

    example configuration:

    def toolchains(self) -> typing.Dict[str, linux.build.Toolchain]:
        return {
            "linaro-gnueabi": linux.build.EnvSetLinaroToolchain(
                host_arch = "i686",
                arch = "arm-linux-gnueabi",
                date = "2018.05",
                gcc_vers = "7.3",
                gcc_subvers = "1",
                ),
            }

    """

    def enable(self, host: H) -> None:  # noqa: D102
        td = host.workdir / "toolchain"
        if not td.exists():
            host.exec0("mkdir", "-p", td)
        host.exec0("cd", td)
        host.exec0("pwd")
        ending = ".tar.xz"
        path_name = "gcc-linaro-" + self.gcc_vers + "." + self.gcc_subvers + "-" + self.date + "-" + self.host_arch + "_" + self.arch
        link_path = self.gcc_vers + "-" + self.date + "/" + self.arch + "/" + path_name
        tooldir = td / path_name / "bin"
        ret = host.exec("test", "-d", tooldir)
        if ret[0] == 1:
            host.exec0("wget", "https://releases.linaro.org/components/toolchain/binaries/" + link_path + ending)
            host.exec0("tar", "-xJf", path_name + ending)
            host.exec0("cd", path_name)
        ret = host.exec("printenv", "PATH", tbot.machine.linux.Pipe, "grep", "--color=never", tooldir)
        if ret[0] == 1:
            host.exec0(linux.Raw("export PATH=" + str(tooldir).split(":")[1] + ":$PATH"))
        host.exec0("printenv", "PATH")
        if "arm" in self.arch:
            host.exec0("export", "ARCH=arm" )
            host.exec0("export", "CROSS_COMPILE=" + self.arch + "-")
        else:
            raise RuntimeError(self.arch + " not supported yet")

        host.exec0("printenv", "ARCH")
        host.exec0("printenv", "CROSS_COMPILE")

    def __init__(self, host_arch: str, arch: str, date: str, gcc_vers: str, gcc_subvers: str) -> None:
        """
        Create a new EnvSetLinaroToolchain.

        :param str host_arch: host architecture "i686"
        :param str arch: target architecture "arm-linux-gnueabi"
        :param str date: release date of the toolchain "2018.05"
        :param str gcc_vers: gcc version "7.3"
        :param str gcc_subvers: gcc subversion "1"
        """
        self.host_arch = host_arch
        self.arch = arch
        self.date = date
        self.gcc_vers = gcc_vers
        self.gcc_subvers = gcc_subvers

class EnvSetBootlinToolchain(Toolchain):
    """Toolchain from https://toolchains.bootlin.com/downloads/releases/toolchains
    initialized through setting Shell Environment variables.

    example configuration:

    def toolchains(self) -> typing.Dict[str, linux.build.Toolchain]:
        return {
            "bootlin-armv5-eabi": linux.build.EnvSetBootlinToolchain(
                arch = "armv5-eabi",
                libc = "glibc",
                typ = "stable",
                date = "2018.11-1",
                ),
            }
    """

    def enable(self, host: H) -> None:  # noqa: D102
        td = host.workdir / "toolchain"
        if not td.exists():
            host.exec0("mkdir", "-p", td)
        host.exec0("cd", td)
        host.exec0("pwd")
        fn = self.arch + "--" + self.libc + "--" + self.typ + "-" + self.date
        fn2 = self.arch + "/tarballs/" + fn
        ending = ".tar.bz2"
        tooldir = td / fn / "bin"
        ret = host.exec("test", "-d", tooldir)
        if ret[0] == 1:
            msg = "Get toolchain " + fn
            tbot.log.message(msg)
            host.exec0("wget", "https://toolchains.bootlin.com/downloads/releases/toolchains/" + fn2 + ending)
            host.exec0("tar", "xfj", fn + ending)
            host.exec0("cd", fn)
            host.exec0("./relocate-sdk.sh")
        ret = host.exec("printenv", "PATH", tbot.machine.linux.Pipe, "grep", "--color=never", tooldir)
        if ret[0] == 1:
            msg = "Add toolchain to PATH", str(tooldir).split(":")[1]
            tbot.log.message(msg)
            host.exec0(linux.Raw("export PATH=" + str(tooldir).split(":")[1] + ":$PATH"))
        host.exec0("printenv", "PATH")
        if "arm" in self.arch:
            host.exec0("export", "ARCH=arm" )
            host.exec0("export", "CROSS_COMPILE=arm-linux-")
        host.exec0("printenv", "ARCH")
        host.exec0("printenv", "CROSS_COMPILE")

    def __init__(self, arch: str, libc: str, typ: str, date: str) -> None:
        """
        Create a new EnvScriptToolchain.

        :param str arch: architecture.
        :param str libc: used libc.
        :param str typ: "stable" or "bleeding-edge"
        :param str date: release date of the toolchain
        """
        self.arch = arch
        self.libc = libc
        self.typ = typ
        self.date = date
