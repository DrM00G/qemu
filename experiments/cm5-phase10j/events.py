"""Private local FSW observations; no upstream use or physical parity claim."""
import re


PATTERNS = {
    'version': r'-- Program Version: .+ --',
    'topology': r'TopologyBase: initializing\.\.\.',
    'initializations': r'\w+: successfully initialized!',
    'components': r'\w+Component: successfully initialized!',
    'tasks_created': r'\w+ created!',
    'tasks_started': r'\w+Task: starting\.\.\.',
    'topology_started': r'TopologyBase: starting\.\.\.',
    'housekeeping': r': Sampling\.\.\.',
    'packet_receipts': r'PacketForwarderComponent: Received packet with APID: from \d+ for \d+',
    'packet_routes': r'OutboundVirtualChannelTasksHandler: Routing packet with precedence class \d+ to virtual channel \d+',
    'outbound_sends': r'OutboundVirtualChannelTask: Sending to SatnogsComms',
    'queue_items': r'SatnogsCommsTask: Got queue item',
    'tx_dumps': r'TX: (?:[0-9A-F]{2} )*[0-9A-F]{2}',
    'watchdog_unimplemented': r'WatchdogTask: run called but not yet implemented',
    'spi_failures': r'SatnogsCommsTask: Failed to send SPI_IOC_MESSAGE',
    'spi_open_failures': r'Failed to open /dev/spidev0\.0',
    'serial_init_failures': r'PobcCommTask: Error initializing serial class: .+',
    'stack_rounding': r'\[WARNING\] \w+ stack size is not multiple of page size \d+, rounding',
    'stack_clamps': r'\w+ stack size is too small, clamping to \d+',
    'crashes': r'.*(?:segmentation fault|core dumped|illegal instruction|error while loading shared libraries|cannot execute binary).*',
}


def summarize(text):
    """Normalize CR/LF framing only; retain full lines and original line order.

    Categories can overlap (components are a subset of initializations). No
    sorting, deduplication, inferred timestamps, or repair of interleaved lines.
    Unknown lines remain available for review, including unexpected errors.
    """
    patterns = {k: re.compile(v, re.I) for k, v in PATTERNS.items()}
    events = {k: [] for k in patterns}
    ordered, unmatched = [], []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        kinds = [k for k, p in patterns.items() if p.fullmatch(line)]
        item = dict(line=number, text=line, categories=kinds)
        ordered.append(item)
        if not kinds:
            unmatched.append(item)
        for kind in kinds:
            events[kind].append(line)
    # Preserve the old API's packets key, now with full, explicit observations.
    events['packets'] = [x['text'] for x in ordered if
                         set(x['categories']) & {'packet_receipts', 'packet_routes'}]
    return dict(counts={k: len(v) for k, v in events.items()}, events=events,
                ordered=ordered, unmatched=unmatched)
