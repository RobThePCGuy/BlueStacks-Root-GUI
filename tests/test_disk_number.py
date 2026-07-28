"""_disk_number: fast diskpart parse, with a Get-Disk fallback for localisation.

Pins the behaviour that made the fast path safe to adopt -- it must agree with
Get-Disk in BOTH states, because _detach() treats None as proof the disk is gone.
A fast path that returned None for an *attached* disk would make _detach report
success while the image stayed mounted.
"""
from unittest import mock

import ext4_symlink as es


ATTACHED = """
DiskPart successfully selected the virtual disk file.

Device type ID: 3 (Unknown)
Virtual size:  128 GB
Physical size: 3530 MB
Filename: C:\\ProgramData\\BlueStacks_nxt\\Engine\\Tiramisu64\\Data.vhdx
Is Child: No
Associated disk#: 2
"""

DETACHED = """
DiskPart successfully selected the virtual disk file.

Device type ID: 3 (Unknown)
Virtual size:  128 GB
Filename: C:\\ProgramData\\BlueStacks_nxt\\Engine\\Tiramisu64\\Data.vhdx
Is Child: No
Associated disk#:
"""

# A localised install prints the same data under translated field names.
LOCALISED = """
DiskPart hat die Datei für den virtuellen Datenträger ausgewählt.

Datenträger 2
"""


def _completed(stdout):
    return mock.Mock(stdout=stdout, stderr="", returncode=0)


def test_attached_returns_disk_number_without_calling_get_disk():
    with mock.patch.object(es, "_diskpart", return_value=_completed(ATTACHED)), \
         mock.patch.object(es, "_disk_number_via_get_disk") as slow:
        assert es._disk_number("X.vhdx") == 2
    slow.assert_not_called()


def test_detached_returns_none_without_calling_get_disk():
    # _detach() relies on this: None must mean "gone", not "couldn't tell".
    with mock.patch.object(es, "_diskpart", return_value=_completed(DETACHED)), \
         mock.patch.object(es, "_disk_number_via_get_disk") as slow:
        assert es._disk_number("X.vhdx") is None
    slow.assert_not_called()


def test_unrecognised_output_falls_back_to_get_disk():
    # Must NOT be mistaken for "detached" -- that would let _detach() claim
    # success on a still-mounted image on any non-English Windows.
    with mock.patch.object(es, "_diskpart", return_value=_completed(LOCALISED)), \
         mock.patch.object(es, "_disk_number_via_get_disk", return_value=7) as slow:
        assert es._disk_number("X.vhdx") == 7
    slow.assert_called_once()


def test_parse_flag_distinguishes_detached_from_unparseable():
    with mock.patch.object(es, "_diskpart", return_value=_completed(DETACHED)):
        assert es._disk_number_via_diskpart("X.vhdx") == (None, True)
    with mock.patch.object(es, "_diskpart", return_value=_completed(LOCALISED)):
        assert es._disk_number_via_diskpart("X.vhdx") == (None, False)


def test_case_insensitive_field_match():
    with mock.patch.object(es, "_diskpart",
                           return_value=_completed("associated DISK#:  11\n")):
        assert es._disk_number_via_diskpart("X.vhdx") == (11, True)
