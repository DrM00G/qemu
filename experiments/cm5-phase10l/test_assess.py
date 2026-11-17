"""Readiness assessment must distinguish not-yet-mounted from unsafe mounts."""
import unittest
from assess import verified_mounts


class AssessmentTests(unittest.TestCase):
    def test_early_unmounted_fsw_and_ready_verified_mount(self):
        early = dict(target='inactive', pid1='systemd',
                     lower='/dev/mapper/cm5_os_verified ext4 ro,noatime,norecovery', fsw='')
        ready = dict(early, target='active', fsw='/dev/mapper/cm5_fsw_verified ext4 ro,noatime,norecovery')
        self.assertTrue(verified_mounts([early, ready]))
        self.assertFalse(verified_mounts([early]))
        self.assertFalse(verified_mounts([dict(ready, fsw='')]))
        self.assertFalse(verified_mounts([dict(early, fsw='/dev/mmcblk0p5 ext4 ro'), ready]))
        self.assertFalse(verified_mounts([dict(ready, fsw='/dev/mapper/cm5_fsw_verified ext4 rw,noatime')]))
        self.assertFalse(verified_mounts([dict(early, lower='/dev/mmcblk0p2 ext4 ro'), ready]))


if __name__ == '__main__':
    unittest.main()
