#!/usr/bin/env python

import glob
import os
import pyudev
import sys
import usb

def lock_all_interfaces(lock):
    listing = glob.glob('/sys/bus/usb/devices/usb*')
    for path in listing:
        path += "/interface_authorized_default"
        if os.path.isfile(path):
            with open(path,'w') as f:
                if lock: f.write("0")
                else: f.write("1")

def unlock_single_interface(path,probe_driver):
    interface=path.rsplit('/',1)[1]
    path += '/authorized'
    with open(path,'w') as f:
        f.write("1")

    if probe_driver:
        with open('/sys/bus/usb/drivers_probe','w') as f:
            f.write(interface)

def get_device_summary(dev):
    output = "\n{0}\n\n".format(dev._get_full_descriptor_str())
    output += "Configurations found: {0}".format(str(dev.bNumConfigurations))
    for cfg in dev:
        output += "\nInterfaces found for Configuration {0}: {1}\n\n".format(
                str(cfg.index+1),str(cfg.bNumInterfaces)
                )
        for intf in cfg:
            output += "{0}\n".format(str(intf))
    return output

def get_device(path):
    devnum_path = path + "/devnum"
    busnum_path = path + "/busnum"
    if os.path.isfile(devnum_path) and os.path.isfile(busnum_path):
        with open(devnum_path, 'r') as f:
            devnum = f.readline().rstrip()
        with open(busnum_path, 'r') as f:
            busnum = f.readline().rstrip()
        for dev in usb.core.find(find_all=True):
            if dev.bus == int(busnum) and dev.address==int(devnum):
                return dev
    return None

def handle_device(path,dev):
    for cfg in dev:
        for intf in cfg:
            path_intf = "{0}/{1}:{2}.{3}".format(
                path,
                path.rsplit('/',1)[1],
                str(cfg.index+1),
                str(intf.index)
                )
            print("Allow Interface {0} in Configuration {1}?".format(
                str(intf.index),
                str(cfg.index+1)
                ))
            print("1 => Unlock & probe driver")
            print("2 => Unlock only")
            print("Other key => keep locked")
            line = sys.stdin.readline().rstrip()
            if line == "1":
                unlock_single_interface(path_intf,probe_driver=True)
                print("Unlocked interface...")
            elif line == "2":
                unlock_single_interface(path_intf,probe_driver=False)
                print("Unlocked interface, didn't probe driver.")
                print("Interface: " + path_intf.rsplit('/',1)[1])
            else:
                print("Keeping interface locked...")

def main():
    print("\n{0} USBlockdown {0}\n".format(10*"#"))

    if os.getuid() != 0:
        print("You need to have root privileges to run this script.\n")
        sys.exit(1)

    try:
        print("Locking USB...")
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
                    print("Warning: A USB device was added but I couldn't " +
                          "find it. Possibly removed?")
                    continue
                print(get_device_summary(usb_dev))
                handle_device(path,usb_dev)

    except KeyboardInterrupt:
        while True:
            print("Do you want to unlock USB? [yes,no]")
            line = sys.stdin.readline().rstrip()
            if line == "yes":
                print("Unlocking USB...")
                lock_all_interfaces(False)
                break
            elif line == "no":
                print("Keeping USB locked...")
                break
        print("Exiting.")

    except Exception as e:
        print("Panic:\n{0}".format(str(e)))
        sys.exit(1)

if __name__ == "__main__":
    main()
