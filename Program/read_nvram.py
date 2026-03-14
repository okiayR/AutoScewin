from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from typing import List, Optional


# --------- Data model ---------
@dataclass
class Option:
    code: str          # like "00"
    label: str         # like "Disabled"
    selected: bool     # True if has *
    is_default: bool   # True if marked (default)


@dataclass
class Setting:
    question: str
    token: str
    help: str
    options: List[Option]
    value: str
    default_value: str
    raw_block: str


# --------- Parser ---------
RE_QUESTION = re.compile(r"^\s*Setup Question\s*=\s*(.+?)\s*$", re.MULTILINE)
RE_HELP     = re.compile(r"^\s*Help String\s*=\s*(.+?)\s*$", re.MULTILINE)
RE_TOKEN    = re.compile(r"^\s*Token\s*=\s*(.+?)\s*$", re.MULTILINE)
RE_VALUE    = re.compile(r"^\s*Value\s*=\s*(.+?)\s*$", re.MULTILINE)
RE_DEFAULT  = re.compile(r"^\s*BIOS Default\s*=\s*(.+?)\s*$", re.MULTILINE)

# Matches option entries like: *[00]Disabled or [01]Enabled (line by line).
RE_OPTION_ENTRY = re.compile(
    r"^\s*(?:Options\s*=\s*)?(?P<star>\*)?\[(?P<code>[0-9A-Fa-f]{2})\](?P<label>[^\r\n\[\]]+)",
    re.MULTILINE,
)


def split_into_blocks(text: str) -> List[str]:
    """
    Your nvram export is made of blocks separated by blank lines.
    This function creates those blocks.
    """
    blocks = []
    current = []
    for line in text.splitlines():
        if line.strip() == "":
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def parse_setting_block(block: str) -> Optional[Setting]:
    """
    Parse one block into a Setting if it looks like one.
    """
    q = RE_QUESTION.search(block)
    t = RE_TOKEN.search(block)

    if not q or not t:
        return None

    question = q.group(1).strip()
    token = t.group(1).strip()

    h = RE_HELP.search(block)
    help_str = h.group(1).strip() if h else ""

    v = RE_VALUE.search(block)
    value = v.group(1).strip() if v else ""

    d = RE_DEFAULT.search(block)
    default_value = d.group(1).strip() if d else ""

    # Collect options if present
    options: List[Option] = []
    for m in RE_OPTION_ENTRY.finditer(block):
        star = m.group("star")
        code = m.group("code").upper()
        label = m.group("label").strip()
        is_default = bool(re.search(r"\(default\)\s*$", label, flags=re.IGNORECASE))
        # Strip inline comments if present.
        label = label.split("//", 1)[0].rstrip()
        # Clean up trailing stuff like " (default)" if it exists
        label = re.sub(r"\s*\(default\)\s*$", "", label, flags=re.IGNORECASE)
        options.append(Option(code=code, label=label, selected=bool(star), is_default=is_default))

    return Setting(
        question=question,
        token=token,
        help=help_str,
        options=options,
        value=value,
        default_value=default_value,
        raw_block=block
    )


def parse_nvram_file(path: Path) -> List[Setting]:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = split_into_blocks(text)

    settings: List[Setting] = []
    for block in blocks:
        s = parse_setting_block(block)
        if s:
            settings.append(s)
    return settings


def update_setting_block(block: str, *, option_label: Optional[str] = None, value: Optional[str] = None) -> str:
    """
    Update a single setting block by selecting an option label or setting a value.
    """
    lines = block.splitlines()
    updated_lines = []
    selected_label = option_label
    value_updated = False

    option_line_re = re.compile(
        r"^(\s*(?:Options\s*=\s*)?)(\*?)(\[[0-9A-Fa-f]{2}\].*)$"
    )
    value_line_re = re.compile(r"^(\s*Value\s*=\s*)(.+?)(\s*(//.*)?)$")

    for line in lines:
        m = option_line_re.match(line)
        if m and selected_label is not None:
            entry = m.group(3)
            entry_match = RE_OPTION_ENTRY.match(entry)
            if entry_match:
                label = entry_match.group("label").strip()
                label = label.split("//", 1)[0].rstrip()
                label = re.sub(r"\s*\(default\)\s*$", "", label, flags=re.IGNORECASE)
                star = "*" if label == selected_label else ""
                line = f"{m.group(1)}{star}{entry}"
        if selected_label is None and value is not None:
            v = value_line_re.match(line)
            if v:
                prefix = v.group(1)
                suffix = v.group(3) or ""
                line = f"{prefix}{value}{suffix}"
                value_updated = True
        updated_lines.append(line)

    if selected_label is None and value is not None and not value_updated:
        updated_lines.append(f"Value\t= {value}")

    return "\n".join(updated_lines)


def update_nvram_text(text: str, updates: dict[str, dict[str, str]]) -> str:
    """
    Apply updates keyed by token to the nvram text.
    updates[token] can include keys: option_label, value.
    """
    blocks = split_into_blocks(text)
    new_blocks: List[str] = []
    for block in blocks:
        s = parse_setting_block(block)
        if s and s.token in updates:
            update = updates[s.token]
            new_block = update_setting_block(
                block,
                option_label=update.get("option_label"),
                value=update.get("value"),
            )
            new_blocks.append(new_block)
        else:
            new_blocks.append(block)
    return "\n\n".join(new_blocks) + "\n"


def update_nvram_file(path: Path, updates: dict[str, dict[str, str]]) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    new_text = update_nvram_text(text, updates)
    path.write_text(new_text, encoding="utf-8")


# BIOS Settings
# Each entry matches against the BIOS setting question.
# Strict = match full question exactly, anything without "(Strict)" finds partial matches.
QUICK_LOOKUPS = [
    "ACPI Sleep State (Strict)",
    "ACPI Standby State (Strict)",
    "ACS (Strict)",
    "ADR enable (Strict)",
    "Advanced Error Reporting (Strict)",
    "AES (Strict)",
    "AP threads Idle Manner (Strict)",
    "ARTG Object (Strict)",
    "ASPM (Strict)",
    "ASPM Support (Strict)",
    "BCLK Aware Adaptive Voltage (Strict)",
    "Bi-directional PROCHOT# (Strict)",
    "Bluetooth Controller (Strict)",
    "BME DMA Mitigation (Strict)",
    "Boot performance mode (Strict)",
    "BT Core (Strict)",
    "C-State Auto Demotion (Strict)",
    "C-state Pre-Wake (Strict)",
    "C-State Un-demotion (Strict)",
    "C6DRAM (Strict)",
    "CER (Strict)",
    "clkreq for clock",
    "clock gat",
    "CPU C-states (Strict)",
    "cpu crashlog",
    "CrashLog Feature (Strict)",
    "ddr powerdown and idle counter",
    "DeepSx Wake on WLAN and BT Enable (Strict)",
    "Disable DSX ACPRESENT PullDown (Strict)",
    "disable fast pkg c state ramp",
    "Disable PROCHOT# Output (Strict)",
    "Discrete Thunderbolt(TM) Support (Strict)",
    "DMI ASPM (Strict)",
    "DMI Gen3 ASPM (Strict)",
    "DMI Link ASPM Control (Strict)",
    "DPC (Strict)",
    "EC Low Power Mode (Strict)",
    "ECC Support (Strict)",
    "EDPC (Strict)",
    "eist",
    "Enable Hibernation (Strict)",
    "Energy Efficient P-state (Strict)",
    "Energy Efficient Turbo (Strict)",
    "Enhanced C-states (Strict)",
    "Enhanced Interleave (Strict)",
    "EPG DIMM Idd3N (Strict)",
    "EPG DIMM Idd3P (Strict)",
    "Execute Disable Bit (Strict)",
    "Extended Tag (Strict)",
    "Fast Boot (Strict)",
    "FER (Strict)",
    "GNA Device",
    "HDC Control (Strict)",
    "HDCP Support (Strict)",
    "Hot-Plug Support",
    "Hyper-Threading (Strict)",
    "iGPU Multi-Monitor",
    "Intel (VMX) Virtualization Technology (Strict)",
    "Intel Rapid Recovery Technology (Strict)",
    "Intel RMT State (Strict)",
    "Intel Trusted Execution Technology (Strict)",
    "Intel(R) Speed Shift Technology (Strict)",
    "Intel(R) Speed Shift Technology Interrupt Control (Strict)",
    "Interrupt Redirection Mode Selection (Strict)",
    "IPU Device",
    "IPv4 PXE Support (Strict)",
    "IPv6 PXE Support (Strict)",
    "JTAG C10 Power Gate (Strict)",
    "l1 low",
    "l1 substates",
    "LAN Wake From DeepSx (Strict)",
    "Legacy IO Low Latency (Strict)",
    "lpm",
    "LTR (Strict)",
    "Maximum Payload (Strict)",
    "Maximum Read Request (Strict)",
    "ME State (Strict)",
    "Memory Scrambler (Strict)",
    "MonitorMWait (Strict)",
    "MRC Fast Boot (Strict)",
    "Native ASPM",
    "Network Stack Driver Support (Strict)",
    "NFER (Strict)",
    "optane",
    "os idle mode",
    "Package C State Limit (Strict)",
    "Package C-State Demotion (Strict)",
    "Package C-State Un-demotion (Strict)",
    "PAVP Enable (Strict)",
    "PCH Cross Throttling (Strict)",
    "PCI Delay Optimization (Strict)",
    "PCI Express Native Power Management (Strict)",
    "Pcie Pll SSC (Strict)",
    "PCIE Tunneling over USB4 (Strict)",
    "PECI (Strict)",
    "PEG - ASPM (Strict)",
    "pep",
    "Perform Platform Erase Operations (Strict)",
    "PERR# Generation (Strict)",
    "PET Progress (Strict)",
    "PMAX Object (Strict)",
    "pme sci",
    "Power Down Mode (Strict)",
    "power gating",
    "PPCC Object (Strict)",
    "PS2 Devices Support (Strict)",
    "PS3 Enable (Strict)",
    "PS4 Enable (Strict)",
    "PS_ON Enable (Strict)",
    "PTID Support (Strict)",
    "PTM (Strict)",
    "PTT (Strict)",
    "RC6(Render Standby) (Strict)",
    "Ring Down Bin (Strict)",
    "Row Hammer Mode (Strict)",
    "Row Hammer Prevention (Strict)",
    "S0ix Auto Demotion (Strict)",
    "SA GV (Strict)",
    "Security Device Support (Strict)",
    "SelfRefresh Enable (Strict)",
    "SelfRefresh IdleTimer (Strict)",
    "SERR# Generation (Strict)",
    "SHA256 PCR Bank (Strict)",
    "SPD Write Disable (Strict)",
    "speedstep",
    "spread spectrum",
    "SR-IOV Support (Strict)",
    "TCM State(Strict)",
    "Thermal Throttling Level (Strict)",
    "Three Strike Counter (Strict)",
    "throttler ckemin defeature",
    "Total Memory Encryption (Strict)",
    "TPM State (Strict)",
    "TVB Ratio Clipping (Strict)",
    "TVB Voltage Optimizations (Strict)",
    "URR (Strict)",
    "USB Audio Offload (Strict)",
    "usb power delivery in soft off state",
    "VGA Palette Snoop (Strict)",
    "VT-d (Strict)",
    "vtd",
    "Wake on LAN Enable (Strict)",
    "Wake on WLAN and BT Enable (Strict)",
    "WatchDog (Strict)",
    "WDT Enable (Strict)",
    "Wi-Fi Controller (Strict)",
    "Wi-Fi Core (Strict)",
    "WWAN Device (Strict)",
]

# Alias map for GUI display. Customize values as needed.
QUICK_LOOKUP_ALIASES = {k: k.replace(" (Strict)", "") for k in QUICK_LOOKUPS}
QUICK_LOOKUP_ALIASES.update({
    "ACPI Sleep State (Strict)": "ACPI Sleep State",
    "ACPI Standby State (Strict)": "ACPI Standby State",
    "ACS (Strict)": "ACS",
    "ADR enable (Strict)": "ADR Enable",
    "Advanced Error Reporting (Strict)": "Advanced Error Reporting",
    "AES (Strict)": "AES",
    "AP threads Idle Manner (Strict)": "AP Threads Idle Manner",
    "ARTG Object (Strict)": "ARTG Object",
    "BCLK Aware Adaptive Voltage (Strict)": "BCLK Aware Adaptive Voltage",
    "Bi-directional PROCHOT# (Strict)": "Bi-directional PROCHOT#",
    "Bluetooth Controller (Strict)": "Bluetooth Controller",
    "BME DMA Mitigation (Strict)": "BME DMA Mitigation",
    "Boot performance mode (Strict)": "Boot Performance Mode",
    "BT Core (Strict)": "BT Core",
    "C-State Auto Demotion (Strict)": "C-State Auto Demotion",
    "C-state Pre-Wake (Strict)": "C-State Pre-Wake",
    "C-State Un-demotion (Strict)": "C-State Un-demotion",
    "C6DRAM (Strict)": "C6DRAM",
    "CER (Strict)": "CER",
    "clkreq for clock": "CLKREQ for Clock",
    "clock gat": "Clock Gating",
    "CPU C-states (Strict)": "CPU C-States",
    "cpu crashlog": "CPU CrashLog",
    "CrashLog Feature (Strict)": "CrashLog Feature",
    "ddr powerdown and idle counter": "DDR PowerDown and Idle Counter",
    "DeepSx Wake on WLAN and BT Enable (Strict)": "DeepSx Wake on WLAN and BT Enable",
    "Disable DSX ACPRESENT PullDown (Strict)": "Disable DSX ACPRESENT PullDown",
    "disable fast pkg c state ramp": "Disable Fast Package C-State Ramp",
    "Disable PROCHOT# Output (Strict)": "Disable PROCHOT# Output",
    "Discrete Thunderbolt(TM) Support (Strict)": "Discrete Thunderbolt(TM) Support",
    "DPC (Strict)": "DPC",
    "EC Low Power Mode (Strict)": "EC Low Power Mode",
    "ECC Support (Strict)": "ECC Support",
    "EDPC (Strict)": "EDPC",
    "eist": "EIST",
    "Enable Hibernation (Strict)": "Enable Hibernation",
    "Energy Efficient P-state (Strict)": "Energy Efficient P-State",
    "Energy Efficient Turbo (Strict)": "Energy Efficient Turbo",
    "Enhanced C-states (Strict)": "Enhanced C-States",
    "Enhanced Interleave (Strict)": "Enhanced Interleave",
    "EPG DIMM Idd3N (Strict)": "EPG DIMM Idd3N",
    "EPG DIMM Idd3P (Strict)": "EPG DIMM Idd3P",
    "Execute Disable Bit (Strict)": "Execute Disable Bit",
    "Extended Tag (Strict)": "Extended Tag",
    "FER (Strict)": "FER",
    "GNA Device": "GNA Device",
    "HDC Control (Strict)": "HDC Control",
    "HDCP Support (Strict)": "HDCP Support",
    "Hot-Plug Support": "Hot-Plug Support",
    "Hyper-Threading (Strict)": "Hyper-Threading",
    "iGPU Multi-Monitor": "iGPU Multi-Monitor",
    "Intel (VMX) Virtualization Technology (Strict)": "Intel (VMX) Virtualization Technology",
    "Intel Rapid Recovery Technology (Strict)": "Intel Rapid Recovery Technology",
    "Intel RMT State (Strict)": "Intel RMT State",
    "Intel Trusted Execution Technology (Strict)": "Intel Trusted Execution Technology",
    "Intel(R) Speed Shift Technology (Strict)": "Intel(R) Speed Shift Technology",
    "Intel(R) Speed Shift Technology Interrupt Control (Strict)": "Intel(R) Speed Shift Technology Interrupt Control",
    "Interrupt Redirection Mode Selection (Strict)": "Interrupt Redirection Mode Selection",
    "IPU Device": "IPU Device",
    "IPv4 PXE Support (Strict)": "IPv4 PXE Support",
    "IPv6 PXE Support (Strict)": "IPv6 PXE Support",
    "JTAG C10 Power Gate (Strict)": "JTAG C10 Power Gate",
    "l1 low": "L1 Low",
    "l1 substates": "L1 Substates",
    "LAN Wake From DeepSx (Strict)": "LAN Wake From DeepSx",
    "Legacy IO Low Latency (Strict)": "Legacy IO Low Latency",
    "lpm": "LPM",
    "LTR (Strict)": "LTR",
    "Maximum Payload (Strict)": "Maximum Payload",
    "Maximum Read Request (Strict)": "Maximum Read Request",
    "ME State (Strict)": "ME State",
    "Memory Scrambler (Strict)": "Memory Scrambler",
    "MonitorMWait (Strict)": "MonitorMWait",
    "Network Stack Driver Support (Strict)": "Network Stack Driver Support",
    "NFER (Strict)": "NFER",
    "optane": "Optane",
    "os idle mode": "OS Idle Mode",
    "Package C State Limit (Strict)": "Package C-State Limit",
    "Package C-State Demotion (Strict)": "Package C-State Demotion",
    "Package C-State Un-demotion (Strict)": "Package C-State Un-demotion",
    "PAVP Enable (Strict)": "PAVP Enable",
    "PCH Cross Throttling (Strict)": "PCH Cross Throttling",
    "PCI Delay Optimization (Strict)": "PCI Delay Optimization",
    "PCI Express Native Power Management (Strict)": "PCI Express Native Power Management",
    "Pcie Pll SSC (Strict)": "PCIE PLL SSC",
    "PCIE Tunneling over USB4 (Strict)": "PCIE Tunneling over USB4",
    "PECI (Strict)": "PECI",
    "pep": "PEP",
    "Perform Platform Erase Operations (Strict)": "Perform Platform Erase Operations",
    "PERR# Generation (Strict)": "PERR# Generation",
    "PET Progress (Strict)": "PET Progress",
    "PMAX Object (Strict)": "PMAX Object",
    "pme sci": "PME SCI",
    "Power Down Mode (Strict)": "Power Down Mode",
    "power gating": "Power Gating",
    "PPCC Object (Strict)": "PPCC Object",
    "PS2 Devices Support (Strict)": "PS2 Devices Support",
    "PS3 Enable (Strict)": "PS3 Enable",
    "PS4 Enable (Strict)": "PS4 Enable",
    "PS_ON Enable (Strict)": "PS_ON Enable",
    "PTID Support (Strict)": "PTID Support",
    "PTM (Strict)": "PTM",
    "PTT (Strict)": "PTT",
    "RC6(Render Standby) (Strict)": "RC6(Render Standby)",
    "Ring Down Bin (Strict)": "Ring Down Bin",
    "Row Hammer Mode (Strict)": "Row Hammer Mode",
    "Row Hammer Prevention (Strict)": "Row Hammer Prevention",
    "S0ix Auto Demotion (Strict)": "S0ix Auto Demotion",
    "SA GV (Strict)": "SA GV",
    "Security Device Support (Strict)": "Security Device Support",
    "SelfRefresh Enable (Strict)": "SelfRefresh Enable",
    "SelfRefresh IdleTimer (Strict)": "SelfRefresh IdleTimer",
    "SERR# Generation (Strict)": "SERR# Generation",
    "SHA256 PCR Bank (Strict)": "SHA256 PCR Bank",
    "SPD Write Disable (Strict)": "SPD Write Disable",
    "speedstep": "SpeedStep",
    "spread spectrum": "Spread Spectrum",
    "SR-IOV Support (Strict)": "SR-IOV Support",
    "TCM State(Strict)": "TCM State",
    "Thermal Throttling Level (Strict)": "Thermal Throttling Level",
    "Three Strike Counter (Strict)": "Three Strike Counter",
    "throttler ckemin defeature": "Throttler CKEMIN Defeature",
    "Total Memory Encryption (Strict)": "Total Memory Encryption",
    "TPM State (Strict)": "TPM State",
    "TVB Ratio Clipping (Strict)": "TVB Ratio Clipping",
    "TVB Voltage Optimizations (Strict)": "TVB Voltage Optimizations",
    "URR (Strict)": "URR",
    "USB Audio Offload (Strict)": "USB Audio Offload",
    "usb power delivery in soft off state": "USB Power Delivery in Soft Off State",
    "VGA Palette Snoop (Strict)": "VGA Palette Snoop",
    "VT-d (Strict)": "VT-d",
    "vtd": "VTD",
    "Wake on LAN Enable (Strict)": "Wake on LAN Enable",
    "Wake on WLAN and BT Enable (Strict)": "Wake on WLAN and BT Enable",
    "WatchDog (Strict)": "WatchDog",
    "WDT Enable (Strict)": "WDT Enable",
    "Wi-Fi Controller (Strict)": "Wi-Fi Controller",
    "Wi-Fi Core (Strict)": "Wi-Fi Core",
    "WWAN Device (Strict)": "WWAN Device",
})


def pick_current_label(s: Setting) -> str:
    selected = [o for o in s.options if o.selected]
    if selected:
        return selected[0].label
    # If no option is marked selected, return "not selected".
    return "(not selected)"


def pick_default_label(s: Setting) -> Optional[str]:
    defaults = [o for o in s.options if o.is_default]
    if defaults:
        return defaults[0].label
    return None


def pick_selected_option_index(s: Setting) -> Optional[int]:
    for i, o in enumerate(s.options):
        if o.selected:
            return i
    return None


def pick_default_option_index(s: Setting) -> Optional[int]:
    for i, o in enumerate(s.options):
        if o.is_default:
            return i
    code = parse_default_code(s.default_value)
    if code:
        for i, o in enumerate(s.options):
            if o.code == code:
                return i
    return None


def parse_default_code(raw: str) -> Optional[str]:
    if not raw:
        return None
    m = re.search(r"<\s*([0-9A-Fa-f]+)\s*>", raw)
    if not m:
        m = re.search(r"\[\s*([0-9A-Fa-f]+)\s*\]", raw)
    token = m.group(1) if m else raw.strip()
    if not token:
        return None
    if re.fullmatch(r"[0-9A-Fa-f]+", token):
        value = int(token, 16)
        return f"{value:02X}"
    return None


def pick_default_value(s: Setting) -> Optional[str]:
    if s.default_value:
        return s.default_value
    return None


def build_quick_default_map(settings: List[Setting]) -> dict[str, Optional[str]]:
    """
    Build a map of QUICK_LOOKUPS key -> default option label (if available).
    """
    defaults: dict[str, Optional[str]] = {}
    for key in QUICK_LOOKUPS:
        matches = [s for s in settings if match_setting_by_key(s, key)]
        if len(matches) != 1:
            defaults[key] = None
            continue
        s = matches[0]
        defaults[key] = pick_default_label(s) or pick_default_value(s)
    return defaults


def match_setting_by_key(s: Setting, key: str) -> bool:
    raw = key.strip()
    if not raw:
        return False
    is_strict = raw.endswith(" (Strict)")
    k = raw[:-9].strip() if is_strict else raw
    if not k:
        return False
    # Match only against BIOS setting name (question)
    question = s.question.strip()
    if is_strict:
        return question == k
    return k.lower() in question.lower()


def main():
    nvram_path = Path("nvram.txt")
    if not nvram_path.exists():
        raise SystemExit("ERROR: nvram.txt not found in this folder.")

    settings = parse_nvram_file(nvram_path)

    print(f"Loaded settings: {len(settings)}")
    print()

    if not QUICK_LOOKUPS:
        print("QUICK_LOOKUPS is empty.")
        print("Next step: add tokens or search substrings to QUICK_LOOKUPS.")
        print()
        print("To help you choose, here are the first 20 settings with their tokens:")
        for s in settings[:20]:
            cur = pick_current_label(s) if s.options else "(no options)"
            print(f"- Token={s.token:>6} | {s.question} | Current: {cur}")
        return

    print("Quick settings:")
    for key in QUICK_LOOKUPS:
        matches = [s for s in settings if match_setting_by_key(s, key)]
        if not matches:
            print(f"- '{key}': NOT FOUND in nvram.txt")
            continue

        if len(matches) > 1:
            print(f"- '{key}': {len(matches)} matches found:")
            for s in matches:
                cur = pick_current_label(s) if s.options else "(no options parsed)"
                print(f"    - Token={s.token:>6} | {s.question} -> {cur}")
            continue

        s = matches[0]
        if s.options:
            cur = pick_current_label(s)
            labels = {o.label.lower() for o in s.options}
            is_toggle = labels == {"enabled", "disabled"} and len(s.options) == 2
            kind = "TOGGLE" if is_toggle else "CHOICE"
            print(f"- [{kind}] {s.question} (Token={s.token}) -> {cur}")
        else:
            value = s.value or "(no value parsed)"
            print(f"- [VALUE] {s.question} (Token={s.token}) -> {value}")

    print("\nDone.")


if __name__ == "__main__":
    main()
