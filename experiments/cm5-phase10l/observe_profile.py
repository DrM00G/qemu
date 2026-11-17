"""Read-only initramfs assurance evidence, evaluated inside the guest only."""
r['phase10l_boot'] = dict(
    cmdline=Path('/proc/cmdline').read_text().strip(),
    profile_marker=(Path('/run/cm5-phase10l-profile').read_text().strip()
                    if Path('/run/cm5-phase10l-profile').exists() else None),
    os_log=(Path('/run/cm5-os-verified.log').read_text()
            if Path('/run/cm5-os-verified.log').exists() else None),
    fsw_log=(Path('/run/cm5-fsw-verity.log').read_text()
             if Path('/run/cm5-fsw-verity.log').exists() else None),
    scan_dd_log_exists=Path('/run/cm5-os-verified-dd.log').exists())
