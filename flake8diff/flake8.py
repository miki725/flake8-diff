"""
Run flake8 across a set of changed files and filter out violations occurring
only on the lines that were changed.

By default it's configured for "git diff master" which is useful for
buildmasters looking at a checked out PR.

To use, dump this in a file somewhere...

$ pip install flake8-diff
$ git checkout pr/NNN
$ git merge origin/master
$ flake8-diff

"""
from __future__ import unicode_literals, print_function
import logging
import re
import subprocess
from blessings import Terminal

from .exceptions import NotLocatableVCSError, UnsupportedVCSError
from .utils import _execute
from .vcs import SUPPORTED_VCS


terminal = Terminal()
identity = lambda x: x

# Setup logging
logger = logging.getLogger(__name__)
FORMAT = "%(asctime)-15s %(name)s %(levelname)s %(message)s"
logging.basicConfig(format=FORMAT)
logger.setLevel(logging.ERROR)


# TODO: Handle these not being found in a better way
FLAKE8 = subprocess.check_output(["which", "flake8"]).strip()

# Constants
FLAKE8_OUTPUT = '{filename}:{line}:{char}: {code} {description}'
HEADER_STRING = 'Found violations'
HEADER_OUTPUT = '{header}: {filename}'
SIMPLE_OUTPUT = '\t{code} @ {line}:{char} - {description}'

# Regexes
FLAKE8_LINE = re.compile(
    r'^(?P<filename>[^\s]+)'
    r':'
    r'(?P<line_number>[\d]+)'
    r':'
    r'(?P<char_number>[\d]+)'
    r': '
    r'(?P<error_code>[\w\d]*) '
    r'(?P<description>.*)',
)

# Color themes
COLORS = {
    'off': dict(
        header=identity,
        filename=identity,
        code=identity,
        line=identity,
        char=identity,
        description=identity,
    ),
    'nocolor': dict(
        header=terminal.bold_underline,
        filename=terminal.standout,
        code=terminal.bold,
        line=identity,
        char=identity,
        description=identity,
    ),
    'dark': dict(
        header=terminal.bold,
        filename=identity,
        code=terminal.bold_red,
        line=terminal.magenta,
        char=terminal.magenta,
        description=terminal.yellow,
    ),
    'light': dict(
        header=terminal.bold,
        filename=identity,
        code=terminal.bold_red,
        line=terminal.magenta,
        char=terminal.magenta,
        description=terminal.blue,
    ),
}


class Flake8Diff(object):
    """
    Main class implementing flake8-diff functionality
    """

    def __init__(self, commits, options=None):
        self.commits = commits
        self.options = options

        if self.options.get('verbose'):
            logger.setLevel(logging.INFO)
        if self.options.get('debug'):
            logger.setLevel(logging.DEBUG)

    def get_vcs(self):
        """
        Get appropriate VCS engine
        """
        if self.options.get('vcs'):
            vcs = self.options.get('vcs')
            if vcs not in SUPPORTED_VCS:
                raise UnsupportedVCSError(vcs)
            return SUPPORTED_VCS.get(vcs)(self.commits, self.options, logger)

        for vcs in SUPPORTED_VCS.values():
            vcs = vcs(self.commits, self.options, logger)
            if vcs.is_used():
                return vcs

        raise NotLocatableVCSError

    def flake8(self, filename):
        """
        Run flake8 on a file
        """
        command = filter(
            None,
            [FLAKE8]
            + (self.options.get('flake8_options', '') or '').split()
            + [filename]
        )
        return _execute(command, logger)

    def color_getter(self, component):
        """
        Get color formatting function for selected theme via options.
        If function is not present in the themes,
        identity function is returned.
        """
        theme = COLORS.get(self.options.get('color_theme'), {})
        return theme.get(component, identity)

    def get_color_kwargs(self, details):
        """
        Get string formatting kwargs from violation details
        """
        get = lambda i: details.get(i, '')
        return dict(
            line=self.color_getter('line')(get('line_number')),
            char=self.color_getter('char')(get('char_number')),
            code=self.color_getter('code')(get('error_code')),
            description=self.color_getter('description')(get('description')),
            filename=self.color_getter('filename')(get('filename')),
            header=self.color_getter('header')(get('header')),
        )

    def process(self):
        """
        Perform the magic
        """
        overall_violations = 0
        vcs = self.get_vcs()

        for filename in vcs.changed_files():
            violated_lines = vcs.changed_lines(filename)

            logger.info("checking {} lines {}".format(
                filename,
                ', '.join(violated_lines)),
            )

            violations = []
            for violation in self.flake8(filename).splitlines():
                matches = FLAKE8_LINE.match(violation)
                if matches:
                    violation_details = matches.groupdict()
                    if violation_details['line_number'] in violated_lines:
                        violations.append(violation_details)
                        if self.options.get('standard_flake8_output'):
                            print(FLAKE8_OUTPUT.format(
                                **self.get_color_kwargs(violation_details)
                            ))

            overall_violations += len(violations)

            if violations and not self.options.get('standard_flake8_output'):
                print(HEADER_OUTPUT.format(
                    **self.get_color_kwargs(dict(
                        filename=filename,
                        header=HEADER_STRING
                    ))
                ))

                for line in violations:
                    print(SIMPLE_OUTPUT.format(
                        **self.get_color_kwargs(line)
                    ))

        return overall_violations == 0