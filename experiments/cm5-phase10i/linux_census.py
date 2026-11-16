# Appended public observer fragment; data remains in private run evidence.
r['phase10i_linux'] = dict(schema=1,environment='qemu',drivers=[])
for bus in ('platform','pci','spi','i2c'):
    root = Path('/sys/bus')/bus/'devices'
    if not root.exists():
        continue
    for device in sorted(root.iterdir()):
        node = device/'of_node'
        record = dict(bus=bus,name=device.name,
                      driver=(device/'driver').resolve().name if (device/'driver').exists() else None)
        if node.exists():
            record['dt_path'] = '/'+str(node.resolve()).split('/devicetree/base/',1)[-1]
            compatible = node/'compatible'
            record['compatible'] = compatible.read_bytes().rstrip(b'\0').decode(errors='replace').split('\0') if compatible.exists() else []
        r['phase10i_linux']['drivers'].append(record)
r['phase10i_linux']['buses'] = {}
for bus, directory in [('gpio','/sys/bus/gpio/devices'),('i2c','/sys/class/i2c-adapter'),
                       ('spi','/sys/class/spi_master'),('mmc','/sys/class/mmc_host')]:
    path = Path(directory)
    r['phase10i_linux']['buses'][bus] = sorted(p.name for p in path.iterdir()) if path.exists() else []
r['phase10i_linux']['interrupts'] = Path('/proc/interrupts').read_text()
r['phase10i_linux']['online_cpus'] = Path('/sys/devices/system/cpu/online').read_text().strip()

r['phase10i_linux']['gpio_chips'] = {}
for gpio_chip in Path('/sys/bus/gpio/devices').glob('gpiochip*'):
    r['phase10i_linux']['gpio_chips'][gpio_chip.name] = {k:(gpio_chip/k).read_text().strip() for k in ('label','dev','ngpio') if (gpio_chip/k).exists()}
