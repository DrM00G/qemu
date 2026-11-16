"""Install only public in-RAM observers, preserving original OS/FSW assets."""
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


def wrap(code):
    extra = (HERE/'linux_census.py').read_text()
    source = (HERE/'guest_gpio.py').read_text()
    # A canonical tty truncates lines near4096 bytes, even with echo disabled.
    extra += "\nGPIO_CODE = (\n" + ''.join(
        '    '+json.dumps(source[i:i+512])+'\n' for i in range(0,len(source),512)) + ")\n"
    extra += "\ntry:\n    gpio_child = subprocess.run(['python3','-c',GPIO_CODE], capture_output=True, text=True, timeout=15)\n    r['phase10i_gpio'] = json.loads(gpio_child.stdout)\nexcept Exception as gpio_error:\n    r['phase10i_gpio'] = dict(status='ERROR',error=str(gpio_error))\n"
    return code.replace("print('P10C_USER_JSON='", extra+"\nprint('P10C_USER_JSON='")


def capture_machine(qmp, out):
    raw = {}
    for name, command in [('qtree','info qtree'),('mtree','info mtree -f')]:
        raw[name] = qmp.command('human-monitor-command',{'command-line':command})
    for path in ['/machine/native-rp1','/machine/native-rp1/rp1',
                 '/machine/native-rp1/rp1/gpio','/machine/native-rp1/rp1/spi0']:
        raw[path] = qmp.command('qom-list',dict(path=path))
        raw[path+'/realized'] = qmp.command('qom-get',dict(path=path,property='realized'))
    (out/'phase10i-qom.json').write_text(json.dumps(raw,indent=2))
