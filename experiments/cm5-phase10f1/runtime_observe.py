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
# Property hashes provide an exact structural comparison without exporting the
# private raw DT. Semantic values below are limited to hardware declarations.
dt_root = Path('/proc/device-tree')
dt_nodes = {}
for directory in [dt_root, *sorted(p for p in dt_root.rglob('*') if p.is_dir())]:
    node = '/' + str(directory.relative_to(dt_root))
    if node == '/.':
        node = '/'
    props = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    dt_nodes[node] = dict(properties={k: hashlib.sha256(v).hexdigest() for k, v in props.items()},
        compatible=props.get('compatible', b'').rstrip(b'\0').decode(errors='replace').split('\0'),
        status=props.get('status', b'okay\0').rstrip(b'\0').decode(errors='replace'))
r['boot_handoff_runtime']['nodes'] = dt_nodes
