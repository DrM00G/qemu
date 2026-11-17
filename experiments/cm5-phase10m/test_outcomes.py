"""Failure dimensions must not collapse a booted, degraded workload into one bit."""
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).with_name('assess.py')
spec=importlib.util.spec_from_file_location('phase10m_assessment',path)
assessment=importlib.util.module_from_spec(spec);spec.loader.exec_module(assessment)


class OutcomeTests(unittest.TestCase):
    def test_degraded_packets_keep_boot_and_other_functions_separate(self):
        boot=dict(kernel_entry=True,os_mount=True,normal_poweroff=True)
        users=[dict(target='active',pid1='systemd',fsw='/dev/mapper/cm5_fsw_verified ext4 ro,norecovery',libc_call=True)]*2
        fsw=dict(execution_evidence={'exe':'/opt/fsw/RpiDeployment.elf'},exit_status=124)
        counts=dict(initializations=20,tasks_created=11,tasks_started=10,housekeeping=2)
        result=assessment.function_outcomes(boot,users,fsw,counts)
        self.assertEqual(result['kernel'],'PASS');self.assertEqual(result['userspace'],'PASS')
        self.assertEqual(result['initialization'],'PASS');self.assertEqual(result['housekeeping'],'PASS')
        self.assertEqual(result['internal_packet_path'],'FAIL');self.assertEqual(result['shutdown'],'PASS')
        self.assertEqual(result['fec_correction'],'NOT_EXERCISED_CLEAN_BASELINE')

    def test_mount_loader_and_boot_failures_are_distinct(self):
        boot=dict(kernel_entry=True,os_mount=True)
        users=[dict(target='active',pid1='systemd',fsw='/dev/mapper/cm5_fsw_verified ext4 ro,norecovery',libc_call=True)]*2
        result=assessment.function_outcomes(boot,users,dict(failure_stage='executable-metadata'),{})
        self.assertEqual(result['fsw_filesystem'],'PASS');self.assertEqual(result['executable_launch'],'FAIL')
        self.assertEqual(result['dynamic_loading'],'NOT_REACHED')
        result=assessment.function_outcomes(boot,users,dict(failure_stage='dynamic-loading'),{})
        self.assertEqual(result['dynamic_loading'],'FAIL')
        result=assessment.function_outcomes(dict(kernel_entry=True,os_mount=False),[],{}, {})
        self.assertEqual(result['verified_root'],'FAIL');self.assertEqual(result['housekeeping'],'NOT_REACHED')
        self.assertEqual(assessment.function_outcomes({},[],{}, {})['kernel'],'NOT_REACHED')

    def test_execution_proof_cannot_be_replaced_with_ram_or_an_asserted_hash(self):
        fsw=dict(execution_mode='verified-fsw-partition',generation_id='one',executable='/opt/fsw/RpiDeployment.elf',
            uid=0,executable_prehash=False,elf_uploaded=False,ram_fallback=False,
            execution_evidence=dict(exe='/opt/fsw/RpiDeployment.elf',command_line='/opt/fsw/RpiDeployment.elf',executable_map_present=True))
        self.assertTrue(assessment.execution_proven(fsw,'one'))
        self.assertFalse(assessment.execution_proven(fsw,'different-generation'))
        self.assertFalse(assessment.execution_proven(dict(fsw,ram_fallback=True),'one'))
        self.assertFalse(assessment.execution_proven(dict(fsw,execution_evidence=dict(exe='/run/RpiDeployment.elf')),'one'))


if __name__=='__main__':unittest.main()
