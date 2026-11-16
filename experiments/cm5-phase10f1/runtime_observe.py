"""Appended to existing in-RAM observer only for BOOT-selected runs."""
fdt = Path('/sys/firmware/fdt')
fdt_data = fdt.read_bytes() if fdt.exists() else None
r['boot_handoff_runtime'] = dict(
    fdt_sha256=hashlib.sha256(fdt_data).hexdigest() if fdt_data is not None else None,
    fdt_bytes=len(fdt_data) if fdt_data is not None else None,
    model=Path('/proc/device-tree/model').read_bytes().rstrip(b'\0').decode(errors='replace'),
    compatible=Path('/proc/device-tree/compatible').read_bytes().rstrip(b'\0').decode(errors='replace'),
    proc_cmdline_sha256=hashlib.sha256(Path('/proc/cmdline').read_bytes().rstrip(b'\n')).hexdigest(),
    chosen_bootargs_sha256=hashlib.sha256(Path('/proc/device-tree/chosen/bootargs').read_bytes().rstrip(b'\0')).hexdigest())
