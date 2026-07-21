#!/bin/python
# PYTHON_ARGCOMPLETE_OK
"""Main python obf interface.
"""
import os
import argparse
from pathlib import Path
from datetime import datetime
import logging
from logging.handlers import TimedRotatingFileHandler

from obf_modules.logginghelper import ColorFormatter
try:
    import argcomplete
except ModuleNotFoundError:
    argcomplete = None
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from obf_modules.checkmodule import Checkmodule
from obf_modules.buildmodule import Buildmodule
from obf_modules.compilemodule import Compilemodule


class Main():
    """Main function.
        Parses arguments and calls the action selected by the user.
    """
    __version__: str = "V20251111"

    def __init__(self):
        with open("config.toml", "rb") as f:
            self.config = tomllib.load(f)
            self.config["obf"]["directory"] = Path(os.getcwd())

            # Creating logger
            logger = logging.getLogger()
            logger.setLevel(logging.DEBUG)
            # File logging
            log_file_path = self.config["obf"]["directory"].joinpath(self.config["obf"]["log"])
            file_handler = TimedRotatingFileHandler(log_file_path, when='midnight', backupCount=30)
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s: %(message)s')
            file_handler.setFormatter(file_formatter)

            # Console logging
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = ColorFormatter('%(levelname)s: %(message)s')
            console_handler.setFormatter(console_formatter)

            # Adding handlers to logger
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)

    def main(self):
        """ Main function.
        Checks the arguments using argparse, and calls the individual action functions.
        """
        self.config["obf"]["run_timestamp"] = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        # Define the arguments;
        aparser = argparse.ArgumentParser(
            description="Main interface of obf."
        )
        aparser.add_argument("-V", "--version", action="version", version="Version: " + self.__version__, help="Print the version.")
        aparser.add_argument(
            "action",
            choices=[
                "build",
                "buildcompile",
                "rebuild",
                "rebuildcompile",
                "remove",
                "check",
                "config",
                "compile",
                "cleanup",
            ],
            help="Action to perform"
        )
        if argcomplete is None:
            print("WARNING: Python package 'argcomplete' is not installed. Tab completion will not work. Install with 'pip3 install argcomplete' and then activate it via 'activate-global-python-argcomplete' for best experience.")
        else:
            argcomplete.autocomplete(aparser)
        # Parse the arguments;
        args = aparser.parse_args()
        match args.action:
            case "build":
                self.build_dockerimages()
            case "check":
                self.perform_checks()
            case "config":
                self.list_config()
            case "compile":
                self.start_compilation()
            case "buildcompile":
                self.build_dockerimages()
                self.start_compilation()
            case "remove":
                self.remove_dockerimages()
            case "rebuild":
                self.remove_dockerimages()
                self.build_dockerimages()
            case "rebuildcompile":
                self.remove_dockerimages()
                self.build_dockerimages()
                self.start_compilation()
            case "cleanup":
                self.cleanup_exited_containers()

    def build_dockerimages(self):
        """Build the docker images of the enabled compilers, analyzers, transformers.
        """
        checker = Checkmodule(self.config)
        checker.check_docker_running_windows()
        checker = Buildmodule(self.config)
        checker.build_compilers(only_enabled=self.config["compiler"]["only_enabled"])

    def remove_dockerimages(self):
        """Remove the docker images of the enabled compilers, analyzers, transformers.
        """
        checker = Buildmodule(self.config)
        checker.remove_compilers(only_enabled=self.config["compiler"]["only_enabled"])

    def perform_checks(self):
        """Check the structure of the obf project and the sample sources.
        """
        checker = Checkmodule(self.config)
        checker.check_config()
        checker.check_sources("src", only_enabled=self.config["src"]["only_enabled"])

    def list_config(self):
        """List the current config (enabled sample sources, compilers, transformers, analyzers).
        """
        checker = Checkmodule(self.config)
        checker.list_config()

    def start_compilation(self):
        """Compile each sample source with each enabled compiler.
        """
        checker = Compilemodule(self.config)
        checker.compile()
        if self.config["compiler"]["cleanup-failed-containers"]:
            checkmod = Checkmodule(self.config)
            checkmod.cleanup_compiler_containers()

    def cleanup_exited_containers(self):
        """Cleanup all exited docker containers.
        """
        checker = Checkmodule(self.config)
        checker.cleanup_exited_containers(cleanup_all=True)

    def _get_last_run(self, out_dir: Path, for_analyze: bool = False) -> Path | None:
        run_dirs = []
        # Go through all subdirs/files in the out_dir
        for entry in out_dir.iterdir():
            # Only add directories starting with "run_" to the list
            if entry.is_dir() and entry.name.startswith("run_"):
                if for_analyze and "analyze" in entry.name:
                    continue
                run_dirs.append(entry)
        # Check if we get directories and return the (alphabetically) latest one
        if len(run_dirs) > 0:
            return sorted(run_dirs)[-1]
        return None


if __name__ == "__main__":
    main = Main()
    main.main()
