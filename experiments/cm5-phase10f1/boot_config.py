"""Explicit CM5/official IO headless lab policy, not firmware DT execution.

Sources: pinned raspberrypi/documentation config_txt/{boot,conditional,
what_is_config_txt}.adoc, revision c6a64966af136da21a1e55551c5a395cb6987fce.
All active operations have an outcome in the private directive ledger.
"""
import re
from block_reader import Outcome, require
from validate import dtb

PROFILE = 'cm5-headless-lab'
MODEL_FILTERS = {'pi1','pi2','pi3','pi3+','pi4','pi5','pi400','pi500',
                 'cm0','cm1','cm3','cm3+','cm4','cm4s','cm5','pi0','pi0w','pi02'}
SUBSTITUTIONS = {
    ('dtparam', 'audio=on'): 'No modeled audio; generated lab DT omits audio enablement.',
    ('camera_auto_detect', '1'): 'No attached lab cameras; no probing or automatic camera overlays.',
    ('display_auto_detect', '1'): 'No attached lab displays; no probing or automatic display overlays.',
    ('dtoverlay', 'vc4-kms-v3d'): 'Headless generated DT replaces graphics tree; KMS overlay is not applied.',
    ('dtoverlay', 'dwc2,dr_mode=host'): 'No USB workload/controller in supported lab profile; host-mode overlay not applied.',
    ('dtoverlay', 'nospi10'): 'SoC spi10 is absent from generated lab DT; no overlay is applied. Phase10E enables separate RP1 SPI0 for its synthetic workload.',
    ('max_framebuffers', '2'): 'No firmware framebuffer is provided.',
    ('disable_fw_kms_setup', '1'): 'No firmware KMS cmdline synthesis; original BOOT cmdline used plus recorded lab append.',
    ('disable_overscan', '1'): 'No framebuffer/overscan operation in headless lab.',
    ('arm_boost', '1'): 'TCG CPU and fixed lab clocks replace firmware frequency/boost policy.',
}


def select_cm5(fat, report):
    selected = {}
    stack = []
    total = 0
    auto = '0'
    ledger = report.setdefault('config_directives', [])
    report['config_profile'] = dict(name=PROFILE, board='CM5 + official CM5 IO',
        known_identity_source='explicit operator-selected lab profile; no EEPROM board detection',
        matching_model_filters=['cm5','pi5'], physical_firmware_equivalence=False)

    def parse(name, enabled=True):
        nonlocal total, auto
        require(name not in stack and len(stack) < 8, 'INVALID_CONFIG', 'cyclic/deep include')
        stack.append(name)
        data = fat.file(name); total += len(data)
        require(total <= 65536, 'UNSUPPORTED', 'config total exceeds 64KiB')
        try:
            text = data.decode('ascii')
        except UnicodeError as exc:
            raise Outcome('INVALID_CONFIG', 'non-ASCII config') from exc
        require('\0' not in text, 'INVALID_CONFIG', 'NUL config')
        for number, raw in enumerate(text.splitlines(), 1):
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            require(len(raw) <= 98, 'UNSUPPORTED', 'config line exceeds 98 characters')
            row = dict(file=name, line=number, directive=line, category='UNSUPPORTED')
            ledger.append(row)
            if line.startswith('['):
                f = line[1:-1] if line.endswith(']') else ''
                require(f in MODEL_FILTERS | {'all','none'}, 'UNSUPPORTED', 'unknown conditional '+line)
                enabled = f in ('all','cm5','pi5')
                row.update(category='INTERPRETED', active=enabled)
                continue
            row['active'] = enabled
            if not enabled:
                row['category'] = 'INACTIVE'
                continue
            if line.startswith('include '):
                enabled = parse(line[8:].strip(), enabled)
                row['category'] = 'INTERPRETED'
            elif line.startswith('initramfs '):
                fields = line.split()
                require(len(fields) == 3 and fields[2] in ('followkernel','0') and
                        re.fullmatch(r'[A-Za-z0-9_.-]+', fields[1]), 'UNSUPPORTED', 'initramfs form/address')
                selected['initramfs'] = fields[1]; row['category'] = 'INTERPRETED'
                row['placement'] = 'QEMU ARM loader placement substitutes firmware followkernel allocation'
            elif '=' in line:
                key, value = (s.strip() for s in line.split('=',1))
                if key in ('kernel','cmdline','device_tree'):
                    require(re.fullmatch(r'[A-Za-z0-9_.-]+',value), 'UNSUPPORTED', 'non-root selector')
                    selected[{'device_tree':'dtb'}.get(key,key)] = value
                    row['category'] = 'INTERPRETED'
                elif key == 'auto_initramfs':
                    require(value in ('0','1'), 'UNSUPPORTED', 'auto_initramfs value')
                    auto = value; row['category'] = 'INTERPRETED'
                elif key == 'arm_64bit':
                    require(value in ('0','1'), 'UNSUPPORTED', 'arm_64bit value')
                    row.update(category='INTERPRETED', reason='CM5 is 64-bit-only; flag has no effect')
                elif (key,value) in SUBSTITUTIONS:
                    row.update(category='LAB_SUBSTITUTION', reason=SUBSTITUTIONS[key,value])
                    if key == 'dtoverlay':
                        source = 'overlays/'+value.split(',')[0]+'.dtbo'
                        overlay = fat.file(source)
                        dtb(overlay)
                        row.update(overlay_source=source, overlay_applied=False,
                            overlay_resolution='requested source inspected only; firmware overlay_map remapping not executed')
                else:
                    raise Outcome('UNSUPPORTED', f'{name}:{number}: directive {key}={value}')
            else:
                raise Outcome('UNSUPPORTED', f'{name}:{number}: config syntax')
        stack.pop()
        return enabled

    parse('config.txt')
    names = {e['name'].casefold() for e in fat.directory()}
    if 'kernel' not in selected:
        selected['kernel'] = 'kernel_2712.img' if 'kernel_2712.img' in names else 'kernel8.img'
    selected.setdefault('dtb', 'bcm2712-rpi-cm5-cm5io.dtb')
    selected.setdefault('cmdline', 'cmdline.txt')
    if auto == '1':
        # Deliberately fail closed on ambiguous explicit/auto interactions.
        require('initramfs' not in selected, 'UNSUPPORTED', 'explicit initramfs with auto_initramfs=1')
        k = selected['kernel']
        require(k.startswith('kernel'), 'UNSUPPORTED', 'auto initramfs custom kernel naming')
        selected['initramfs'] = 'initramfs'+k[6:].rsplit('.',1)[0]
    require('initramfs' in selected, 'UNSUPPORTED', 'lab requires selected initramfs')
    report['selection_defaults'] = dict(board_dtb='CM5/official IO only; absent DTB fails closed, no Pi5 DT fallback',
        auto_initramfs_final=auto, kernel_default_fallback='kernel8.img only when no explicit kernel and default absent')
    report['selected'] = selected
    return selected
