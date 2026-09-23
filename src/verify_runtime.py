"""Setup import check, compatible with native argument passing in PowerShell 5.1."""
from .utils import local_environment


def main() -> None:
    local_environment()
    import numpy
    import scipy
    import librosa
    import soundfile
    import matplotlib

    print("Core imports OK")


if __name__ == "__main__":
    main()
