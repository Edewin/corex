from corex.core.cpu import CpuSource, clean_cpu_name
from corex.core.engine import Engine
from corex.core.gpu import GpuSource, pci_device_name
from corex.core.hwmon import HwmonPool, read_chips
from corex.core.model import DeviceKind, Kind
from corex.core.network import NetworkSource
from corex.core.storage import StorageSource
from corex.core.units import format_value, human_bytes

STAT_1 = "cpu  100 0 100 800 0 0 0 0 0 0\ncpu0 50 0 50 400 0 0 0 0 0 0\ncpu1 50 0 50 400 0 0 0 0 0 0\nintr 1\n"
STAT_2 = "cpu  200 0 200 1400 200 0 0 0 0 0\ncpu0 150 0 150 400 0 0 0 0 0 0\ncpu1 50 0 50 1000 200 0 0 0 0 0\nintr 1\n"


def _engine(fake, **kw):
    return Engine(fake.roots, use_nvml=False,
                  storage={"statvfs": lambda m: (100 * 2**30, 25 * 2**30), "resolve_dev": lambda p: p},
                  network={"ipv4": lambda: {"eth0": "192.168.1.5"}, "ssid": lambda i: "Home"},
                  gpu={"pci_ids": ()}, **kw)


# -- units -------------------------------------------------------------------

def test_human_bytes():
    assert human_bytes(512) == "512 B"
    assert human_bytes(1536) == "1.5 KB"
    assert human_bytes(5 * 2**20, per_second=True) == "5.0 MB/s"
    assert human_bytes(400 * 2**10, per_second=True) == "400 KB/s"   # was ".400 MB/s" in v1


def test_format_value():
    assert format_value(Kind.TEMP, 45.4) == "45 °C"
    assert format_value(Kind.CLOCK, 3500) == "3.50 GHz"
    assert format_value(Kind.CLOCK, 800) == "800 MHz"
    assert format_value(Kind.LOAD, None) == "—"
    assert format_value(Kind.INFO, None, "up") == "up"


# -- CPU -----------------------------------------------------------------------

def test_cpu_name_cleanup():
    assert clean_cpu_name("Intel(R) Core(TM) i7-12700K CPU @ 3.60GHz") == "Intel Core i7-12700K"
    assert clean_cpu_name("AMD Ryzen 9 5900X 12-Core Processor") == "AMD Ryzen 9 5900X"


def test_cpu_load_counts_iowait_as_idle(fake):
    fake.write("proc/cpuinfo", "processor\t: 0\nmodel name\t: AMD Ryzen 5 5600 6-Core Processor\n"
                               "cpu MHz\t\t: 3500.0\nprocessor\t: 1\ncpu MHz\t\t: 3600.0\n")
    fake.write("proc/stat", STAT_1)
    src = CpuSource(fake.roots)
    first = src.sample(0.0, HwmonPool([]))[0]
    assert first.name == "AMD Ryzen 5 5600"
    assert first.reading("cpu/load/total").value is None        # no previous sample yet
    fake.write("proc/stat", STAT_2)
    dev = src.sample(1.0, HwmonPool([]))[0]
    # total: busy +200 of +1000 jiffies (iowait 200 counts as idle)
    assert dev.reading("cpu/load/total").value == 20.0
    assert dev.reading("cpu/load/0").value == 100.0
    assert dev.reading("cpu/load/1").value == 0.0
    # no cpufreq in sysfs -> falls back to /proc/cpuinfo
    assert dev.reading("cpu/clock/max").value == 3600.0


def test_cpu_takes_its_temperatures(fake):
    fake.write("proc/cpuinfo", "processor\t: 0\nmodel name\t: X\n")
    fake.write("proc/stat", STAT_1)
    fake.hwmon(0, "k10temp", "sys/devices/pci0000:00/0000:00:18.3",
               temp1_input="55250", temp1_label="Tctl", temp3_input="48000", temp3_label="Tccd1")
    fake.hwmon(1, "nct6798", "sys/devices/platform/nct6775.656", temp1_input="30000", fan2_input="900")
    pool = HwmonPool(read_chips(fake.roots))
    dev = CpuSource(fake.roots).sample(0.0, pool)[0]
    temps = {r.label: r.value for r in dev.groups[0].readings}
    assert temps == {"CPU (Tctl)": 55.25, "CCD 1": 48.0}
    assert [c.name for c in pool.remaining()] == ["nct6798"]


# -- hwmon ---------------------------------------------------------------------

def test_hwmon_units_labels_and_bad_values(fake):
    fake.hwmon(0, "nct6798", "sys/devices/platform/nct6775.656",
               temp1_input="34000", temp1_label="SYSTIN",
               temp2_input="-128000",                       # disconnected sensor
               fan1_input="1200", fan2_input="0",
               in0_input="1032", power1_average="25500000")
    (chip,) = read_chips(fake.roots)
    by_label = {r.label: (r.kind, r.value) for r in chip.readings()}
    assert by_label["SYSTIN"] == (Kind.TEMP, 34.0)
    assert "Temperature 2" not in by_label
    assert by_label["Fan 1"] == (Kind.FAN, 1200.0)
    assert by_label["Fan 2"] == (Kind.FAN, 0.0)
    assert by_label["Voltage 0"] == (Kind.VOLT, 1.032)
    assert by_label["Power 1"] == (Kind.POWER, 25.5)
    assert chip.id == "hwmon/nct6798@nct6775.656"          # stable, not hwmon0


# -- storage -------------------------------------------------------------------

def _disk(fake, name, dev_path, sectors="1953525168", rotational="0", model=None):
    fake.link(f"sys/block/{name}", dev_path)
    base = f"sys/block/{name}"
    fake.write(f"{base}/size", sectors)
    fake.write(f"{base}/queue/rotational", rotational)
    fake.write(f"{base}/removable", "0")
    if model:
        fake.write(f"{base}/device/model", model)


def test_storage_rates_mounts_lvm_and_nvme_temperature(fake):
    ctrl = "sys/devices/pci0000:00/0000:00:01.1/0000:01:00.0/nvme/nvme0"
    _disk(fake, "nvme0n1", f"{ctrl}/nvme0n1", model="Samsung SSD 980 PRO 1TB")
    fake.mkdir(f"{ctrl}/nvme0n1/nvme0n1p2")                 # partition
    fake.mkdir("sys/block/loop0")                           # skipped
    fake.link("sys/block/dm-0", "sys/devices/virtual/block/dm-0")
    fake.write("sys/block/dm-0/size", "100")
    fake.mkdir("sys/block/dm-0/slaves/nvme0n1p2")           # LVM on the partition
    fake.hwmon(0, "nvme", ctrl, temp1_input="41850", temp1_label="Composite")
    fake.write("proc/mounts", "/dev/dm-0 / ext4 rw 0 0\n/dev/dm-0 /var/snap ext4 rw 0 0\n"
                              "tmpfs /run tmpfs rw 0 0\n")
    fake.write("proc/diskstats", "259 0 nvme0n1 10 0 2048 0 10 0 4096 0 0 100 0 0 0 0\n")

    src = StorageSource(fake.roots, statvfs=lambda m: (100 * 2**30, 25 * 2**30), resolve_dev=lambda p: p)
    pool = HwmonPool(read_chips(fake.roots))
    (dev,) = src.sample(0.0, pool)
    assert dev.name == "Samsung SSD 980 PRO 1TB"
    assert dev.detail.startswith("NVMe SSD")
    assert dev.reading("hwmon/nvme@nvme0/temp1").value == 41.85
    assert dev.reading("disk/nvme0n1/space/").value == 75.0
    assert dev.reading("disk/nvme0n1/space/var/snap") is None   # same device, shortest mount kept

    fake.write("proc/diskstats", "259 0 nvme0n1 10 0 6144 0 10 0 4096 0 0 600 0 0 0 0\n")
    (dev,) = src.sample(2.0, HwmonPool([]))
    assert dev.reading("disk/nvme0n1/read").value == (6144 - 2048) * 512 / 2.0
    assert dev.reading("disk/nvme0n1/write").value == 0.0
    assert dev.reading("disk/nvme0n1/busy").value == 25.0       # 500 ms busy in 2 s


# -- network -------------------------------------------------------------------

NET_DEV = ("Inter-|   Receive  |  Transmit\n face |bytes packets|bytes\n"
           "    lo: 999 0 0 0 0 0 0 0 999 0 0 0 0 0 0 0\n"
           "  eth0: {rx} 0 0 0 0 0 0 0 {tx} 0 0 0 0 0 0 0\n"
           "docker0: 5 0 0 0 0 0 0 0 5 0 0 0 0 0 0 0\n")


def test_network_rate_uses_real_elapsed_time(fake):
    fake.link("sys/class/net/eth0/device", "sys/devices/pci0000:00/0000:05:00.0")
    fake.write("sys/class/net/eth0/operstate", "up")
    fake.write("sys/class/net/eth0/speed", "1000")
    fake.mkdir("sys/class/net/docker0")                    # virtual: no device link
    fake.mkdir("sys/class/net/lo")
    fake.write("proc/net/dev", NET_DEV.format(rx=1_000_000, tx=0))
    src = NetworkSource(fake.roots, ipv4=lambda: {"eth0": "10.0.0.2"}, ssid=lambda i: None)
    (dev,) = src.sample(10.0, HwmonPool([]))
    assert dev.reading("net/eth0/down").value is None
    fake.write("proc/net/dev", NET_DEV.format(rx=4_000_000, tx=300_000))
    (dev,) = src.sample(13.0, HwmonPool([]))                # a late tick: 3 s, not 1 s
    assert dev.reading("net/eth0/down").value == 1_000_000.0
    assert dev.reading("net/eth0/up").value == 100_000.0
    assert dev.reading("net/eth0/link").text == "Connected · 1 Gbit/s"
    assert dev.reading("net/eth0/ipv4").text == "10.0.0.2"
    assert dev.detail == "eth0 · 1 Gbit/s"


def test_network_counter_reset_gives_no_rate(fake):
    fake.link("sys/class/net/eth0/device", "sys/devices/pci0000:00/0000:05:00.0")
    fake.write("proc/net/dev", NET_DEV.format(rx=5000, tx=5000))
    src = NetworkSource(fake.roots, ipv4=lambda: {}, ssid=lambda i: None)
    src.sample(0.0, HwmonPool([]))
    fake.write("proc/net/dev", NET_DEV.format(rx=10, tx=10))   # interface re-created
    (dev,) = src.sample(1.0, HwmonPool([]))
    assert dev.reading("net/eth0/down").value is None


# -- GPU -----------------------------------------------------------------------

def test_amd_gpu_from_sysfs(fake, tmp_path):
    pci = "sys/devices/pci0000:00/0000:00:03.1/0000:0b:00.0"
    fake.link("sys/class/drm/card0/device", pci)
    fake.mkdir("sys/class/drm/card0-DP-1")
    dev = f"{pci}"
    fake.write(f"{dev}/vendor", "0x1002")
    fake.write(f"{dev}/device", "0x73bf")
    fake.write(f"{dev}/gpu_busy_percent", "37")
    fake.write(f"{dev}/mem_info_vram_used", str(2 * 2**30))
    fake.write(f"{dev}/mem_info_vram_total", str(16 * 2**30))
    fake.write(f"{dev}/pp_dpm_sclk", "0: 500Mhz\n1: 2321Mhz *\n")
    fake.hwmon(0, "amdgpu", pci, temp1_input="52000", temp1_label="edge", temp2_input="61000",
               temp2_label="junction", fan1_input="1100", power1_average="123000000")
    ids = tmp_path / "pci.ids"
    ids.write_text("1002  Advanced Micro Devices, Inc. [AMD/ATI]\n"
                   "\t73bf  Navi 21 [Radeon RX 6800/6800 XT / 6900 XT]\n"
                   "1022  Advanced Micro Devices, Inc. [AMD]\n")
    pool = HwmonPool(read_chips(fake.roots))
    (gpu,) = GpuSource(fake.roots, use_nvml=False, pci_ids=(str(ids),)).sample(0.0, pool)
    assert gpu.name == "Radeon RX 6800/6800 XT / 6900 XT"
    assert gpu.reading("gpu/card0/load").value == 37.0
    assert gpu.reading("gpu/card0/vram_load").value == 12.5
    assert gpu.reading("gpu/card0/clock_core").value == 2321.0
    temps = [r.label for g in gpu.groups if g.name == "Temperatures" for r in g.readings]
    assert temps == ["Edge", "Hotspot"]
    assert pool.remaining() == []


def test_pci_ids_unknown_device(tmp_path):
    ids = tmp_path / "pci.ids"
    ids.write_text("1002  AMD\n\t73bf  Navi 21\n10de  NVIDIA\n")
    assert pci_device_name("0x1002", "0x73bf", (str(ids),)) == "Navi 21"
    assert pci_device_name("0x1002", "0xffff", (str(ids),)) is None


# -- engine --------------------------------------------------------------------

def test_engine_minmax_labels_and_board_name(fake):
    fake.write("proc/cpuinfo", "processor\t: 0\nmodel name\t: X\n")
    fake.write("proc/stat", STAT_1)
    fake.write("proc/meminfo", "MemTotal: 16000000 kB\nMemAvailable: 12000000 kB\nSwapTotal: 0 kB\n")
    fake.write("sys/class/dmi/id/board_vendor", "ASUSTeK COMPUTER INC.")
    fake.write("sys/class/dmi/id/board_name", "ROG STRIX B550-F GAMING")
    fake.hwmon(0, "nct6798", "sys/devices/platform/nct6775.656", temp1_input="30000", fan1_input="800")
    fake.hwmon(1, "jc42", "sys/devices/i2c/0-0018", temp1_input="38000")
    fake.hwmon(2, "acpitz", None, temp1_input="27800")

    eng = _engine(fake, labels={"hwmon/nct6798@nct6775.656/fan1": "CPU cooler"})
    eng.sample(0.0)
    fake.write("sys/class/hwmon/hwmon0/temp1_input", "45000")
    snap = eng.sample(1.0)

    board = snap.device("hwmon/nct6798@nct6775.656")
    assert board.kind == DeviceKind.BOARD and board.name == "ASUS ROG STRIX B550-F GAMING"
    t = board.reading("hwmon/nct6798@nct6775.656/temp1")
    assert (t.value, t.min, t.max) == (45.0, 30.0, 45.0)
    assert board.reading("hwmon/nct6798@nct6775.656/fan1").label == "CPU cooler"

    mem = snap.device("memory")
    assert mem.groups[0].name == "Temperatures"                # RAM module sensor
    assert mem.reading("mem/ram/load").value == 25.0
    assert snap.device("hwmon/acpitz@hwmon2").name == "ACPI thermal zone"
    assert snap.status == {"hwmon": True, "nvml": False}

    eng.reset_minmax()
    t = eng.sample(2.0).reading("hwmon/nct6798@nct6775.656/temp1")
    assert (t.min, t.max) == (45.0, 45.0)


def test_engine_on_empty_system(fake):
    snap = _engine(fake).sample(0.0)
    assert snap.devices == ()                                  # nothing readable: no empty devices, no crash
