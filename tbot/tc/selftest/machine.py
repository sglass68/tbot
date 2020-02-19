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

import typing
import time
import re
import tbot
from tbot.machine import channel
from tbot.machine import linux
from tbot.machine import board

__all__ = (
    "selftest_machine_reentrant",
    "selftest_machine_labhost_shell",
    "selftest_machine_ssh_shell",
    "selftest_machine_sshlab_shell",
)


@tbot.testcase
def selftest_machine_reentrant(lab: typing.Optional[linux.Lab] = None,) -> None:
    """Test if a machine can be entered multiple times."""
    with lab or tbot.acquire_lab() as lh:
        with lh as h1:
            assert h1.exec0("echo", "FooBar") == "FooBar\n"

        with lh as h2:
            assert h2.exec0("echo", "FooBar2") == "FooBar2\n"


@tbot.testcase
def selftest_machine_labhost_shell(lab: typing.Optional[linux.Lab] = None,) -> None:
    """Test the LabHost's shell."""
    with lab or tbot.acquire_lab() as lh:
        selftest_machine_shell(lh)

        with lh.clone() as l2:
            selftest_machine_channel(l2.ch, False)

        with lh.clone() as l2:
            selftest_machine_channel(l2.ch, True)


@tbot.testcase
def selftest_machine_ssh_shell(lab: typing.Optional[linux.Lab] = None,) -> None:
    """Test an SSH shell."""
    from tbot.tc.selftest import minisshd

    with lab or tbot.acquire_lab() as lh:
        if not minisshd.check_minisshd(lh):
            tbot.skip("dropbear is not installed so ssh can't be tested")

        with minisshd.minisshd(lh) as ssh:
            selftest_machine_shell(ssh)

            selftest_machine_channel(ssh.ch, True)


@tbot.testcase
def selftest_machine_sshlab_shell(lab: typing.Optional[linux.Lab] = None,) -> None:
    """Test an SSH LabHost shell."""
    from tbot.tc.selftest import minisshd

    with lab or tbot.acquire_lab() as lh:
        if not minisshd.check_minisshd(lh):
            tbot.skip("dropbear is not installed so ssh can't be tested")

        with minisshd.minisshd(lh) as ssh:
            ssh.exec0("true")

            tbot.log.message(tbot.log.c("Testing with paramiko ...").bold)
            with minisshd.MiniSSHLabHostParamiko(ssh.port) as slp:
                selftest_machine_shell(slp)

            tbot.log.message(tbot.log.c("Testing with plain ssh ...").bold)
            with minisshd.MiniSSHLabHostSSH(ssh.port) as sls:
                selftest_machine_shell(sls)


@tbot.testcase
def selftest_machine_shell(m: typing.Union[linux.LinuxShell, board.UBootShell]) -> None:
    # Capabilities
    cap = []
    if isinstance(m, linux.LinuxShell):
        if isinstance(m, linux.Bash):
            cap.extend(["printf", "jobs", "control", "run"])
        # TODO: Re-add when Ash is implemented
        # if m.shell == linux.Ash:
        #     cap.extend(["printf", "control"])

    tbot.log.message("Testing command output ...")
    out = m.exec0("echo", "Hello World")
    assert out == "Hello World\n", repr(out)

    out = m.exec0("echo", "$?", "!#")
    assert out == "$? !#\n", repr(out)

    if "printf" in cap:
        out = m.exec0("printf", "Hello World")
        assert out == "Hello World", repr(out)

        out = m.exec0("printf", "Hello\\nWorld")
        assert out == "Hello\nWorld", repr(out)

        out = m.exec0("printf", "Hello\nWorld")
        assert out == "Hello\nWorld", repr(out)

    s = "_".join(map(lambda i: f"{i:02}", range(80)))
    out = m.exec0("echo", s)
    assert out == f"{s}\n", repr(out)

    tbot.log.message("Testing return codes ...")
    assert m.test("true")
    assert not m.test("false")

    if isinstance(m, linux.LinuxShell):
        tbot.log.message("Testing env vars ...")
        value = "12\nfoo !? # true; exit\n"
        m.env("TBOT_TEST_ENV_VAR", value)
        out = m.env("TBOT_TEST_ENV_VAR")
        assert out == value, repr(out)

        tbot.log.message("Testing redirection (and weird paths) ...")
        f = m.workdir / ".redir test.txt"
        if f.exists():
            m.exec0("rm", f)

        assert (
            m.fsroot / "proc" / "version"
        ).exists(), "/proc/version is missing for some reason ..."

        m.exec0("echo", "Some data - And some more", linux.RedirStdout(f))

        out = m.exec0("cat", f)
        # TODO: Newline
        assert out == "Some data - And some more\n", repr(out)

        # TODO: Evaluate what to do with this
        # tbot.log.message("Testing formatting ...")
        # tmp = linux.Path(m, "/tmp/f o/bar")
        # out = m.exec0("echo", linux.F("{}:{}:{}", tmp, linux.Pipe, "foo"))
        # assert out == "/tmp/f o/bar:|:foo\n", repr(out)

        # TODO: Hm?
        # m.exec0("export", linux.F("NEWPATH={}:{}", tmp, linux.Env("PATH"), quote=False))
        # out = m.env("NEWPATH")
        # assert out != "/tmp/f o/bar:${PATH}", repr(out)

        if "jobs" in cap:
            t1 = time.monotonic()
            out = m.exec0(
                "sleep", "10", linux.Background, "echo", "Hello World"
            ).strip()
            t2 = time.monotonic()

            assert re.match(r"\[\d+\] \d+\nHello World", out), repr(out)
            assert (
                t2 - t1
            ) < 9.0, (
                f"Command took {t2 - t1}s (max 9s). Sleep was not sent to background"
            )

            # Kill the sleep process.  In some circumstances, tbot does not
            # seem to be able to kill all child processes of a subprocess
            # channel.  To prevent this from leading to issues, kill the sleep
            # right here instead of relying on tbot to do so correctly at the
            # very end.      Tracking-Issue: Rahix/tbot#13
            m.exec("kill", linux.Raw("%%"), linux.Then, "wait", linux.Raw("%%"))

        if "control" in cap:
            out = m.exec0(
                "false", linux.AndThen, "echo", "FOO", linux.OrElse, "echo", "BAR"
            ).strip()
            assert out == "BAR", repr(out)

            out = m.exec0(
                "true", linux.AndThen, "echo", "FOO", linux.OrElse, "echo", "BAR"
            ).strip()
            assert out == "FOO", repr(out)

        tbot.log.message("Testing subshell ...")
        out = m.env("SUBSHELL_TEST_VAR")
        assert out == "", repr(out)

        with m.subshell():
            out_b = m.env("SUBSHELL_TEST_VAR", "123")
            out = m.env("SUBSHELL_TEST_VAR")
            assert out == "123", repr(out)
            assert out_b == "123", repr(out_b)

        out = m.env("SUBSHELL_TEST_VAR")
        assert out == "", repr(out)

        if "run" in cap:
            tbot.log.message("Testing mach.run() ...")

            # Test simple uses where everything works as expected
            f = m.workdir / "test_run.txt"
            with m.run("cat", linux.RedirStdout(f)) as cat:
                cat.sendline("Hello World")
                cat.sendline("Lorem ipsum")

                cat.sendcontrol("D")
                cat.terminate0()

            with m.run("cat", f) as cat:
                content = cat.terminate0()

            assert content == "Hello World\nLorem ipsum\n", repr(content)

            with m.run("bash", "--norc", "--noprofile") as bs:
                bs.sendline("exit")
                bs.terminate0()

            # Test failing cases (unexpected abort, return code, missig terminate)
            raised = False
            try:
                with m.run("echo", "Hello World") as echo:
                    echo.read_until_prompt("Lorem Ipsum")
                    echo.terminate0()
            except channel.channel.DeathStringException:
                raised = True

            assert raised, "Early abort of interactive command was not detected!"

            raised = False
            try:
                with m.run("false") as false:
                    false.terminate0()
            except Exception:
                raised = True

            assert raised, "Failing command was not detected properly!"

            with m.run("sh", "-c", "exit 123") as sh:
                rc = sh.terminate()[0]
                assert rc == 123, f"Expected return code 123, got {rc!r}"

            raised = False
            try:
                with m.run("echo", "Hello World"):
                    pass
            except RuntimeError:
                raised = True
                # Necessary to bring machine back into good state
                m.ch.read_until_prompt()

            assert raised, "Missing terminate did not lead to error"

            m.exec0("true")

    if isinstance(m, board.UBootShell):
        tbot.log.message("Testing env vars ...")

        m.exec0("setenv", "TBOT_TEST", "Lorem ipsum dolor sit amet")
        out = m.exec0("printenv", "TBOT_TEST")
        assert out == "TBOT_TEST=Lorem ipsum dolor sit amet\n", repr(out)

        out = m.env("TBOT_TEST")
        assert out == "Lorem ipsum dolor sit amet", repr(out)


@tbot.testcase
def selftest_machine_channel(ch: channel.Channel, remote_close: bool) -> None:
    tbot.skip("Channel tests need to be reimplemented for machine-v2")

    out = ch.raw_command("echo Hello World", timeout=1)
    assert out == "Hello World\n", repr(out)

    # Check recv_n
    ch.send("echo Foo Bar\n")
    out2 = ch.recv_n(8, timeout=1.0)
    assert out2 == b"echo Foo", repr(out)
    ch.read_until_prompt(channel.TBOT_PROMPT)

    # Check timeout
    raised = False
    try:
        ch.send("echo Foo Bar")
        ch.read_until_prompt(channel.TBOT_PROMPT, timeout=0)
    except TimeoutError:
        raised = True
    assert raised
    ch.send("\n")
    ch.read_until_prompt(channel.TBOT_PROMPT)

    assert ch.isopen()

    if remote_close:
        ch.send("exit\n")
        time.sleep(0.1)
        ch.recv(timeout=1)

        raised = False
        try:
            ch.recv(timeout=1)
        except channel.ChannelClosedException:
            raised = True
        assert raised
    else:
        ch.close()

    assert not ch.isopen()

    raised = False
    try:
        ch.send("\n")
    except channel.ChannelClosedException:
        raised = True
    assert raised

    raised = False
    try:
        ch.recv(timeout=1)
    except channel.ChannelClosedException:
        raised = True
    assert raised
