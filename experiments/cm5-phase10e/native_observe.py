# Appended to the public observer in guest RAM.
import mmap
r['native_rp1'] = {}
n = r['native_rp1']
pci = Path('/sys/bus/pci/devices/0002:01:00.0')
try:
    n['vendor'] = (pci/'vendor').read_text().strip()
    n['device'] = (pci/'device').read_text().strip()
    n['driver'] = os.readlink(pci/'driver')
    n['resources'] = (pci/'resource').read_text().splitlines()[:3]
    n['msi_irqs'] = sorted(x.name for x in (pci/'msi_irqs').iterdir())
    fd = os.open(pci/'resource1', os.O_RDONLY)
    try:
        with mmap.mmap(fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ) as mem:
            n['chip_id'] = int.from_bytes(mem[:4],'little')
    finally:
        os.close(fd)
    fd = os.open(pci/'resource2', os.O_RDWR)
    try:
        with mmap.mmap(fd,65536) as mem:
            old_first,old_last = mem[:4],mem[-4:]
            mem[:4] = b'P10E';mem[-4:] = b'BAR2'
            n['bar2_scratch'] = mem[:4]==b'P10E' and mem[-4:]==b'BAR2'
            mem[:4],mem[-4:] = old_first,old_last
    finally:
        os.close(fd)
    result = subprocess.run(['python3','-c',SPI_CODE],capture_output=True,text=True,timeout=20)
    n['spi'] = json.loads(result.stdout) if result.returncode==0 else {'status':'ERROR','returncode':result.returncode,'error':result.stderr[-1000:]}
    n['target_after_spi'] = cmd('systemctl', 'is-active', 'multi-user.target')
    n['spi_finish_uptime'] = float(Path('/proc/uptime').read_text().split()[0])
    summary = Path('/sys/kernel/debug/clk/clk_summary')
    n['sys_clock_summary'] = [x for x in summary.read_text().splitlines() if 'clk_sys' in x] if summary.exists() else []
except Exception as error:
    n['error'] = str(error)
