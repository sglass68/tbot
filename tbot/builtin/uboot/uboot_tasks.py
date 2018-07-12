"""
Collection of U-Boot tasks
--------------------------
"""
import pathlib
import typing
import tbot
from tbot import tc


@tbot.testcase
def check_uboot_version(tb: tbot.TBot, *, uboot_binary: pathlib.PurePosixPath) -> None:
    """
    Check whether the version of U-Boot running on the board is the same
    as the one supplied as a binary file in uboot_bin.

    :param pathlib.PurePosixPath uboot_binary: Path to the U-Boot binary
    """
    with tb.with_board_uboot() as tb:
        strings = tb.shell.exec0(
            f"strings {uboot_binary} | grep U-Boot", log_show=False
        )
        version = tb.boardshell.exec0("version").split("\n")[0]
        tbot.log.debug(f"U-Boot Version (on the board) is '{version}'")
        assert version in strings, "U-Boot version does not seem to match"


@tbot.testcase
def uboot_checkout(
    tb: tbot.TBot,
    *,
    clean: bool = True,
    buildhost: typing.Optional[str] = None,
    builddir: typing.Optional[pathlib.PurePosixPath] = None,
    patchdir: typing.Optional[pathlib.PurePosixPath] = None,
    repo: typing.Optional[str] = None,
    rev: typing.Optional[str] = None,
) -> tc.UBootRepository:
    """
    Create a checkout of U-Boot **on the buildhost**

    :param bool clean: Whether an existing repository should be cleaned
    :param str buildhost: Which buildhost should U-Boot be built on?
    :param pathlib.PurePosixPath builddir: Where to checkout U-Boot to, defaults to ``tb.config["uboot.builddir"]``
    :param pathlib.PurePosixPath patchdir: Optional U-Boot patches to be applied
        ontop of the tree, defaults to ``tb.config["uboot.patchdir"]``, supply a
        nonexistent path to force ignoring the patches
    :param str repo: Where to get U-Boot from, defaults to ``tb.config["uboot.repository"]``
    :param str rev: Revision from the repo to be checked out, defaults to
                    ``tb.config["uboot.revision", None]``
    :returns: The U-Boot checkout as a meta object for other testcases
    :rtype: UBootRepository
    """

    with tb.machine(tbot.machine.MachineBuild(name=buildhost)) as tb:
        builddir = builddir or tb.shell.workdir / tb.config["uboot.builddir"]
        patchdir = patchdir or tb.config["uboot.patchdir", None]
        repo = repo or tb.config["uboot.repository"]
        rev = rev or tb.config["uboot.revision", None]

        docstr = f"""In this document, we assume the following file locations:

* The build directory is `{builddir}`
* The U-Boot repository is `{repo}`
"""
        docstr += (
            "(For you it will most likely be `git://git.denx.de/u-boot.git`)\n"
            if repo != "git://git.denx.de/u-boot.git"
            else ""
        )
        docstr += (
            f"* Board specific patches can be found in `{patchdir}`\n"
            if patchdir is not None
            else ""
        )

        tbot.log.doc(docstr + "\n")

        git_testcase = "git_clean_checkout" if clean else "git_dirty_checkout"

        gitdir = tb.call(git_testcase, repo=repo, target=builddir, rev=rev)
        if patchdir is not None and clean is True:
            tb.call("git_apply_patches", gitdir=gitdir, patchdir=patchdir)
        return tc.UBootRepository(gitdir)


@tbot.testcase
def uboot_checkout_and_build(
    tb: tbot.TBot,
    *,
    builddir: typing.Optional[pathlib.PurePosixPath] = None,
    patchdir: typing.Optional[pathlib.PurePosixPath] = None,
    repo: typing.Optional[str] = None,
    rev: typing.Optional[str] = None,
    toolchain: typing.Optional[tc.Toolchain] = None,
    defconfig: typing.Optional[str] = None,
) -> tc.UBootRepository:
    """
    Checkout U-Boot and build it

    :param pathlib.PurePosixPath builddir: Where to checkout U-Boot to, defaults to ``tb.config["uboot.builddir"]``
    :param pathlib.PurePosixPath patchdir: Optional U-Boot patches to be applied
        ontop of the tree, defaults to ``tb.config["uboot.patchdir"]``, supply a
        nonexistent path to force building without patches
    :param str repo: Where to get U-Boot from, defaults to ``tb.config["uboot.repository"]``
    :param str rev: Revision from the repo to be checked out, defaults to
                    ``tb.config["uboot.revision", None]``
    :param Toolchain toolchain: What toolchain to use, defaults to ``tb.config["board.toolchain"]``
    :param str defconfig: What U-Boot defconfig to use, defaults to ``tb.config["uboot.defconfig"]``
    :returns: The U-Boot checkout as a meta object for other testcases
    :rtype: UBootRepository
    """

    tbot.log.doc(
        """
## U-Boot Checkout ##
"""
    )

    ubootdir = tb.call(
        "uboot_checkout", builddir=builddir, patchdir=patchdir, repo=repo, rev=rev
    )
    assert isinstance(ubootdir, tc.UBootRepository)

    toolchain = toolchain or tb.call("toolchain_get")

    tbot.log.doc(
        """
## U-Boot Build ##
"""
    )

    tb.call("uboot_build", builddir=ubootdir, toolchain=toolchain, defconfig=defconfig)

    return ubootdir


@tbot.testcase
def uboot_checkout_and_prepare(
    tb: tbot.TBot,
    *,
    builddir: typing.Optional[pathlib.PurePosixPath] = None,
    patchdir: typing.Optional[pathlib.PurePosixPath] = None,
    repo: typing.Optional[str] = None,
    toolchain: typing.Optional[tc.Toolchain] = None,
    defconfig: typing.Optional[str] = None,
) -> tc.UBootRepository:
    """
    Checkout U-Boot and prepare for building it (ie in an interactive session
    using ``interactive_build``)

    :param pathlib.PurePosixPath builddir: Where to checkout U-Boot to, defaults to ``tb.config["uboot.builddir"]``
    :param pathlib.PurePosixPath patchdir: Optional U-Boot patches to be applied
        ontop of the tree, defaults to ``tb.config["uboot.patchdir"]``, supply a
        nonexistent path to force building without patches
    :param str repo: Where to get U-Boot from, defaults to ``tb.config["uboot.repository"]``
    :param Toolchain toolchain: What toolchain to use, defaults to ``tb.config["board.toolchain"]``
    :param str defconfig: What U-Boot defconfig to use, defaults to ``tb.config["uboot.defconfig"]``
    :returns: The U-Boot checkout as a meta object for other testcases
    :rtype: UBootRepository
    """

    tbot.log.doc(
        """
## U-Boot Checkout ##
"""
    )

    ubootdir = tb.call(
        "uboot_checkout", builddir=builddir, patchdir=patchdir, repo=repo
    )
    assert isinstance(ubootdir, tc.UBootRepository)

    toolchain = toolchain or tb.call("toolchain_get")

    tbot.log.doc(
        """
## U-Boot Build ##
"""
    )

    tb.call(
        "uboot_build",
        builddir=ubootdir,
        toolchain=toolchain,
        defconfig=defconfig,
        do_compile=False,
    )

    return ubootdir
