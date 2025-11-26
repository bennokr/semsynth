"""SemSynth module entrypoint.

Allows ``python -m semsynth`` to dispatch to the CLI defined in
:mod:`semsynth.cli`.
"""

from .cli import main


if __name__ == "__main__":
    main()
