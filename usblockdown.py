#!/usr/bin/env python3

# This tool uses the Linux kernel's USB authorization support to lock all
# USB interfaces. It then monitors for any USB device being plugged in and
# let's the user decide for every interface what to do with it.
# The tool can be interrupted at any time with CTRL + C.

import glob
import os
import sys
import pyudev
import usb

class Colors:
    reset = '\033[0m'
    red = '\033[91m'
    green = '\033[92m'
    yellow = '\033[93m'
    blue = '\033[94m'

def red(msg):
    return f"{Colors.red}{msg}{Colors.reset}"

def blue(msg):
    return f"{Colors.blue}{msg}{Colors.reset}"

def green(msg):
    return f"{Colors.green}{msg}{Colors.reset}"

def yellow(msg):
    return f"{Colors.yellow}{msg}{Colors.reset}"

def print_info(msg):
    print(f"{Colors.blue}{msg}{Colors.reset}")

def print_error(msg):
    print(f"{Colors.red}{msg}{Colors.reset}")

def get_interface_string(intf):
    '''Takes an interface and returns a colored string representation.'''
    intf_string = ""
    first_line = True
    for line in str(intf).splitlines():
        if first_line:
            line = yellow(line)
            first_line = False
        elif "bInterfaceClass" in line:
            line = red(line)
        elif "bAlternateSetting" in line or "iInterface" in line:
            line = yellow(line)
        intf_string += f"{line}\n"
    return intf_string

def get_device_string(dev):
    '''Takes a device and returns a colored string representation.'''
    dev_string = ""
    first_line = True
    for line in dev._get_full_descriptor_str().splitlines():
        if first_line:
            line = yellow(line)
            first_line = False
        elif "bDeviceClass" in line:
            line = red(line)
        elif "iProduct" in line or "iManufacturer"  in line:
            line = red(line)
        dev_string += f"{line}\n"
    return dev_string

def get_device_summary(dev):
    '''
    Takes a device and returns a string represenation of the device.
    Also adds general information on how many configurations and interfaces
    have been found.
    '''
    output = f"\n{get_device_string(dev)}\n"
    output += f"Configurations found: {yellow(str(dev.bNumConfigurations))}"
    for cfg in dev:
        output += f"\nInterfaces found for Configuration {yellow(str(cfg.index+1))}: {yellow(str(cfg.bNumInterfaces))}\n\n"
        for intf in cfg:
            output += get_interface_string(intf)
    return output

def get_device(path):
    '''
    Takes a sysfs path to a device and returns the corresponding USB device object.
    '''
    devnum_path = path + "/devnum"
    busnum_path = path + "/busnum"
    if os.path.isfile(devnum_path) and os.path.isfile(busnum_path):
        with open(devnum_path, 'r') as f:
            devnum = f.readline().rstrip()
        with open(busnum_path, 'r') as f:
            busnum = f.readline().rstrip()
        for dev in usb.core.find(find_all=True):
            if dev.bus == int(busnum) and dev.address == int(devnum):
                return dev
    return None

def lock_all_interfaces(lock):
    '''Lock all interfaces by manipulating via sysfs.'''
    listing = glob.glob('/sys/bus/usb/devices/usb*')
    for path in listing:
        path += "/interface_authorized_default"
        if os.path.isfile(path):
            with open(path, 'w') as f:
                if lock:
                    f.write("0")
                else:
                    f.write("1")

def unlock_single_interface(path, probe_driver):
    '''
    Unlocks a single interface. The interface is referenced by the sysfs path.
    The parameter probe_driver is a boolean which specifies whether the corresponding
    interface driver should be loaded or not.
    '''
    interface = path.rsplit('/', 1)[1]
    path += '/authorized'
    with open(path, 'w') as f:
        f.write("1")
    if probe_driver:
        with open('/sys/bus/usb/drivers_probe', 'w') as f:
            f.write(interface)

def handle_device(path, dev):
    '''
    Takes the sysfs path of a USB device as well as its USB oject representation.
    It then iterates over all configurations and interfaces and queries the user how
    to handle it.
    '''
    for cfg in dev:
        for intf in cfg:
            path_intf = f"{path}/{path.rsplit('/',1)[1]}:{str(cfg.index+1)}.{str(intf.index)}"
            print(f"Allow Interface {yellow(str(intf.index) + ',' + str(intf.bAlternateSetting))} "\
                  f"({red(usb.core._try_lookup(usb.core._lu.interface_classes,intf.bInterfaceClass))}) in Configuration {yellow(str(cfg.index+1))}?")
            print(f"{blue('1')} => unlock & probe driver")
            print(f"{blue('2')} => unlock only")
            print(f"{blue('Other key')} => keep locked")
            line = sys.stdin.readline().rstrip()
            if line == "1":
                unlock_single_interface(path_intf, probe_driver=True)
                print_info("Unlocked interface...")
            elif line == "2":
                unlock_single_interface(path_intf, probe_driver=False)
                print_info("Unlocked interface, didn't probe driver.")
                print("Interface: " + path_intf.rsplit('/', 1)[1])
            else:
                print_info("Keeping interface locked...")

def main():
    print_info(f"\n{10*'#'} USBlockdown {10*'#'}\n")

    if os.getuid() != 0:
        print_error("You need to have root privileges to run this script.\n")
        sys.exit(1)

    try:
        print_info("Locking USB...")
        lock_all_interfaces(True)

        print("Waiting for USB devices...")
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by('usb')
        print("Escape via CTRL+C.")

        for dev in iter(monitor.poll, None):
            path = dev.sys_path
            if dev.action == "add" and dev.get('DEVTYPE') == "usb_device":
                usb_dev = get_device(path)
                if not usb_dev:
                    print_error("Warning: A USB device was added but I couldn't find it. Possibly removed?")
                    continue
                print(get_device_summary(usb_dev))
                handle_device(path, usb_dev)

    except KeyboardInterrupt:
        while True:
            print_info("Do you want to unlock USB? [yes,no]")
            line = sys.stdin.readline().rstrip()
            if line == "yes":
                print_info("Unlocking USB...")
                lock_all_interfaces(False)
                break
            if line == "no":
                print_info("Keeping USB locked...")
                break
        print_info("Exiting.")

    except Exception as e:
        print(f"Panic:\n{str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
