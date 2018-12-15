#!/usr/bin/env python
# Copyright 2018 the Deno authors. All rights reserved. MIT license.
import third_party
from util import enable_ansi_colors, root_path, run
from util import shell_quote
import os
import re
import sys
from distutils.spawn import find_executable
import prebuilt


def main():
    enable_ansi_colors()

    os.chdir(root_path)

    third_party.fix_symlinks()
    third_party.download_gn()
    third_party.download_clang_format()
    third_party.download_clang()
    prebuilt.load()
    third_party.maybe_download_sysroot()

    write_lastchange()

    # TODO allow users to specify target directory.
    target_path = "target"

    gn_gen(target_path, "release")
    gn_gen(target_path, "debug")


def write_if_not_exists(filename, contents):
    if not os.path.exists(filename):
        with open(filename, "w+") as f:
            f.write(contents)


def write_lastchange():
    write_if_not_exists(
        "build/util/LASTCHANGE",
        "LASTCHANGE=c42e4ddbb7973bfb0c57a49ab6bf6dc432baad7e-\n")
    write_if_not_exists("build/util/LASTCHANGE.committime", "1535518087")
    # TODO Properly we should call the following script, but it seems to cause
    # a rebuild on every commit.
    # run([
    #    sys.executable, "build/util/lastchange.py", "-o",
    #    "build/util/LASTCHANGE", "--source-dir", root_path, "--filter="
    # ])


# If this text is found in args.gn, we assume it hasn't been hand edited.
gn_args_header = [
    "# This file is automatically generated by tools/setup.py.",
    "# REMOVE THIS LINE to preserve any changes you make.", ""
]


def gn_string(s):
    # In gn, strings are enclosed in double-quotes and use backslash as the
    # escape character. The only escape sequences supported are:
    #   \" (for literal quote)
    #   \$ (for literal dollars sign)
    #   \\ (for literal backslash)
    # Any other use of a backslash is treated as a literal backslash.
    s = re.sub(r'("|\$|\\(?=["$\\]))', r'\\\1', s)
    s = '"' + s + '"'
    return s


def gn_args_are_generated(lines):
    for line in lines:
        if re.match("^\s*#.*REMOVE THIS LINE", line):
            return True
    return False


def read_gn_args(args_filename):
    if not os.path.exists(args_filename):
        return (None, False)  # No content, not hand edited.

    with open(args_filename) as f:
        lines = f.read().splitlines()
        args = [l.strip() for l in lines if not re.match("^\s*(#|$)", l)]
        hand_edited = not gn_args_are_generated(lines)
        return (args, hand_edited)


def write_gn_args(args_filename, args):
    assert not gn_args_are_generated(args)  # No header -> hand crafted.
    lines = gn_args_header + args
    assert gn_args_are_generated(lines)  # With header -> generated.

    # Ensure the directory where args.gn goes exists.
    d = os.path.dirname(args_filename)
    if not os.path.isdir(d):
        os.makedirs(d)

    with open(args_filename, "w") as f:
        f.write("\n".join(lines) + "\n")


def generate_gn_args(mode):
    out = []
    if mode == "release":
        out += ["is_official_build=true"]
    elif mode == "debug":
        # Enable Jumbo build by default in debug mode for faster build.
        # https://chromium.googlesource.com/chromium/src/+/master/docs/jumbo.md
        out += ["use_jumbo_build=true"]
    else:
        print "Bad mode {}. Use 'release' or 'debug' (default)" % mode
        sys.exit(1)

    if "DENO_BUILD_ARGS" in os.environ:
        out += os.environ["DENO_BUILD_ARGS"].split()

    # Check if ccache or sccache are in the path, and if so we set cc_wrapper.
    cc_wrapper = find_executable("ccache") or find_executable("sccache")
    if cc_wrapper:
        # The gn toolchain does not shell escape cc_wrapper, so do it here.
        out += ['cc_wrapper=%s' % gn_string(shell_quote(cc_wrapper))]
        if os.name == "nt":
            # Disable treat_warnings_as_errors until this sccache bug is fixed:
            # https://github.com/mozilla/sccache/issues/264
            out += ["treat_warnings_as_errors=false"]

    # Look for sccache; if found, set rustc_wrapper.
    rustc_wrapper = find_executable("sccache")
    if rustc_wrapper:
        out += ['rustc_wrapper=%s' % gn_string(rustc_wrapper)]

    return out


# gn gen.
def gn_gen(target_path, mode):
    gn_out = os.path.join(target_path, mode)

    # Rather than using gn gen --args we write directly to the args.gn file.
    # This is to avoid quoting/escaping complications when passing overrides as
    # command-line arguments.
    args_filename = os.path.join(gn_out, "args.gn")

    # Check if args.gn exists, and if it was auto-generated or handcrafted.
    existing_gn_args, hand_edited = read_gn_args(args_filename)

    # If args.gn wasn't handcrafted, regenerate it.
    if hand_edited:
        print "%s: Using gn options from hand edited '%s'." % (mode,
                                                               args_filename)
        gn_args = existing_gn_args
    else:
        print "%s: Writing gn options to '%s'." % (mode, args_filename)
        gn_args = generate_gn_args(mode)
        if gn_args != existing_gn_args:
            write_gn_args(args_filename, gn_args)

    for line in gn_args:
        print "  " + line

    run([third_party.gn_path, "gen", gn_out], env=third_party.google_env())


if __name__ == '__main__':
    sys.exit(main())
