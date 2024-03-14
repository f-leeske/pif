#!/usr/bin/python
import argparse
import os
import signal
import subprocess
import sys
import warnings
from pathlib import Path
from shutil import get_terminal_size
from typing import Iterator

import pexpect
from contextlib import contextmanager

# the pipenv env is inside the project, not the central env location
if os.getenv("PIPENV_VENV_IN_PROJECT"):
    print(
        "You have set the PIPENV_VENV_IN_PROJECT variable, so pipf can't find the environment locations. This is currently not supported"
    )
    exit()


# taken straight from vistir's implementation. Restores all env vars after the context manager is closed
@contextmanager
def temp_environ():
    # type: () -> Iterator[None]
    """Allow the ability to set os.environ temporarily"""
    environ = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(environ)


def get_env_dir(envname: str = ""):
    """
    find and return the absolute path of the virtualenv location matching the given envname (.local/share/virtualenvs/...)
    """
    if not envname:
        env_path = os.getenv("VIRTUAL_ENV")
    else:
        environments_root = os.getenv("WORKON_HOME")
        if not environments_root:
            environments_root = "~/.local/share/virtualenvs"

        root_path = Path(environments_root).expanduser()
        env_path = list(root_path.glob(envname + "*"))
        if len(env_path) > 1:
            # TODO implement for different envs with same name. This can happen with default pipenv
            print("More than one Env of the same name. Not currently supported.")
            exit()
        env_path = env_path[0]

    return env_path


def get_working_dir(envname: str = ""):
    """
    find and return the absolute path of the working directory matching the given envname. TODO: select between multiple with same name
    """
    env_path = get_env_dir(envname)

    # TODO ensure this file exists. MAybe pipenv has some weird cases
    with open(env_path / ".project") as projfile:
        working_dir = projfile.readline()
    return working_dir


def is_pipenv_venv_active():
    """
    Return whether a pipenv environment is currently active. Basically just returns the PIPENV_ACTIVE environment variable
    """
    return os.getenv("PIPENV_ACTIVE") == 1


def cd_to_env_dir(envname: str = ""):
    if is_pipenv_venv_active():
        # we're in a pipenv environment, so we don't need the envname. #TODO warn if the given envname input differs from the active environment
        env_dir = get_working_dir()
    else:
        env_dir = get_working_dir(envname)
    os.chdir(env_dir)


parser = argparse.ArgumentParser(
    description="Wrapper around pipenv that allows for conda-like activation and management of envs from anywhere, not just the env of the current directory."
)
parser.add_argument(
    "--name",
    "-n",
    help="which env to use. The names of the envs must be unique!",
    required=False,
)  # TODO Currently still unique
# TODO rework this dirty hack with nargs='+'
parser.add_argument(
    "command",
    help="command to forward to pipenv. See pipenv --help for options.",
    nargs="+",
)

args = parser.parse_args()


in_correct_dir = False
if not is_pipenv_venv_active() and not args.name:
    cwd = Path(".").absolute()
    if (cwd / "Pipfile").exists():
        warnings.warn(
            "Not in a venv and no name supplied. Found a Pipfile in current dir, using this environment"
        )
        in_correct_dir = True
    else:
        raise EnvironmentError(
            "Not in a venv and no name supplied. Found no Pipfile in current dir, cannot identify which venv to use"
        )


# pipenv cds into the environment's working directory, so we overwrite the shell command
if args.command[0] == "shell" and args.name:
    os.environ["PIPENV_ACTIVE"] = "1"
    os.environ.pop(
        "PIP_SHIMS_BASE_MODULE", None
    )  # straight from pipenv code, no idea what this does

    # this code to launch the subshell is taken directly from pipenv's fork_compat
    dims = get_terminal_size()

    with temp_environ():
        envshell = pexpect.spawn(os.getenv("SHELL"), ["-i"])
        envshell.sendline("source " + str(get_env_dir(args.name)) + "/bin/activate")
        # Handler for terminal resizing events
        # Must be defined here to have the shell process in its context, since
        # we can't pass it as an argument

        def sigwinch_passthrough(sig, data):
            dims = get_terminal_size()
            envshell.setwinsize(dims.lines, dims.columns)

        signal.signal(signal.SIGWINCH, sigwinch_passthrough)
        # Interact with the new shell.
        envshell.interact(escape_character=None)
        envshell.close()
        sys.exit(envshell.exitstatus)

else:
    cmd = ["pipenv"]
    cmd.extend(args.command)

if not in_correct_dir:
    subprocess.run(cmd, cwd=get_working_dir(args.name))
else:
    subprocess.run(cmd)

# TODO: PR to pipenv with correct link in environment variables setting (pipenv --env)
