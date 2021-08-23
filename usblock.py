#!/usr/bin/env python3

# This tool uses the Linux kernel's USB authorization support to lock all
# USB interfaces. It then monitors for any USB device being plugged in and
# let's the user decide for every interface what to do with it.
# The tool can be interrupted at any time with CTRL + C.

import glob
import os
import sys
import time
import pyudev
import usb

RESET = '\033[0m'
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'

def red(msg):
    return f"{RED}{msg}{RESET}"

def blue(msg):
    return f"{BLUE}{msg}{RESET}"

def green(msg):
    return f"{GREEN}{msg}{RESET}"

def yellow(msg):
    return f"{YELLOW}{msg}{RESET}"

def print_info(msg):
    print(f"{BLUE}{msg}{RESET}")

def print_error(msg):
    print(f"{RED}{msg}{RESET}")

def to_int(input_string):
    num = None
    try:
        num = int(input_string)
    except:
        pass
    return num

def get_interface_string(self):
    '''
    Takes an interface and returns a colored string representation.
    '''
    intf_string = ""
    first_line = True
    for line in str(self).splitlines():
        if first_line:
            line = yellow(line)
            first_line = False
        elif "bInterfaceClass" in line:
            line = red(line)
        elif "bAlternateSetting" in line or "iInterface" in line:
            line = yellow(line)
        intf_string += f"{line}\n"
    return intf_string

def get_interface_class_string(self):
    '''
    Takes an interface and returns the device class as string.
    '''
    intf_class_string = ""
    for line in str(self).splitlines():
        if "bInterfaceClass" in line:
            try:
                #Example: bInterfaceClass    :    0x1 Audio
                intf_class_string = line.split(":")[1].lstrip().rstrip().split(" ", 1)[1]
            except Exception:
                intf_class_string = "n/a"
            break
    return intf_class_string

class UsbDevice:
    '''
    UsbDevice is a wrapper around the PyUSB device object. It allows to create a USB device object
    from a given sysfs path.
    '''
    def __init__(self, path):
        self.__path = path
        self.__cfgs_map = {}
        self.__cfgs = []

        devnum_path = path + "/devnum"
        busnum_path = path + "/busnum"
        if os.path.isfile(devnum_path) and os.path.isfile(busnum_path):
            with open(devnum_path, 'r') as f:
                devnum = f.readline().rstrip()
            with open(busnum_path, 'r') as f:
                busnum = f.readline().rstrip()
            for dev in usb.core.find(find_all=True):
                if dev.bus == int(busnum) and dev.address == int(devnum):
                    self.__dev = dev
                    for cfg in self.__dev:
                        # Every USB configuration has a configuration value. Unfortunately, this value is not simply
                        # a counter. If a device has only one configuration, one could expect that the configuration value
                        # is 0 or 1, but it can also be 2 or 5 or whatever. This is a bit annoying, when iterating over
                        # configurations. Therefore, we introduce a configuration map here which allows to get the configuration
                        # value from the list index and vice versa.
                        self.__cfgs.append(cfg)
                        self.__cfgs_map[cfg.bConfigurationValue] = cfg.index

        else:
            raise Exception

    def __get_device_string(self):
        '''
        Takes a device and returns a colored string representation.
        '''
        dev_string = ""
        first_line = True
        for line in self.__dev._get_full_descriptor_str().splitlines():
            if first_line:
                line = yellow(line)
                first_line = False
            elif "bDeviceClass" in line:
                line = red(line)
            elif "iProduct" in line or "iManufacturer"  in line:
                line = red(line)
            dev_string += f"{line}\n"
        return dev_string

    def get_device_summary(self):
        '''
        Returns a string represenation of the device including general information and how many
        configurations and interfaces were found.
        '''
        output = f"\n{self.__get_device_string()}\n"
        output += f"Configurations found: {yellow(str(self.__dev.bNumConfigurations))}"
        for cfg in self.__cfgs:
            output += f"\nInterfaces found for Configuration {yellow(str(cfg.index+1))}: {yellow(str(cfg.bNumInterfaces))}\n\n"
            for intf in cfg:
                output += intf.get_interface_string()
        return output

    def get_active_configuration(self):
        '''
        Returns the current configuration by reading the necessary information via sysfs.
        '''
        try:
            with open(f"{self.__path}/bConfigurationValue","r") as f:
                value = f.read()
            value = to_int(value)
            return self.__cfg_value_to_index(value)
        except:
            return -1

    def get_sysfs_path(self):
        '''
        Returns the sysfs path for the USB device.
        '''
        return self.__path

    def get_num_configurations(self):
        '''
        Returns the total number of configurations.
        '''
        return self.__dev.bNumConfigurations

    def set_configuration(self, num):
        '''
        Allows to set a confguration by confguration value.
        '''
        num = self.__cfg_index_to_value(num-1)
        self.__dev.set_configuration(num)

    def get_configuration(self, num):
        '''
        Returns a list containing all configurations.
        '''
        return self.__cfgs[num-1]

    def __cfg_value_to_index(self, num):
        '''
        Maps from configuration value the actual configuration list index.
        '''
        return self.__cfgs_map[num] + 1

    def __cfg_index_to_value(self, num):
        '''
        Maps from the configuration list index to the configuration value.
        '''
        return list(self.__cfgs_map.keys())[list(self.__cfgs_map.values()).index(num)]

class UsbLock:
    ERR_SUCCESS = 0
    ERR_USB_DEV_REMOVED = 1
    ERR_USB_CFG_DISAPPEARED = 2

    def enable(self):
        '''
        Enables the USB locking for all USB devices.
        '''
        print_info("Locking USB...")
        self.__lock(True)
        self.__monitor()

    def disable(self):
        '''
        Disables the USB locking for all USB devices.
        '''
        print_info("Unlocking USB...")
        self.__lock(False)

    def __lock(self, lock):
        '''
        Allows to lock (lock == True) or unlock (lock == False) all USB devices.
        '''
        listing = glob.glob('/sys/bus/usb/devices/usb*')
        for path in listing:
            path += "/interface_authorized_default"
            if os.path.isfile(path):
                with open(path, 'w') as f:
                    if lock:
                        f.write("0")
                    else:
                        f.write("1")

    def __monitor(self):
        '''
        Main USB device monitoring loop. Will watch for any new USB devices via udev.
        '''
        print("Waiting for USB devices...")
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by('usb')

        for dev in iter(monitor.poll, None):
            path = dev.sys_path
            if dev.action == "add" and dev.get('DEVTYPE') == "usb_device":
                try:
                    self.__dev = UsbDevice(path)
                except Exception as e:
                    print_error("Error: A USB device was added but I couldn't find it. Possibly removed already?")
                    continue
                self.__handle_device()

    def __handle_device(self):
        '''
        Main function for handling of plugged-in USB devices.
        '''
        print(self.__dev.get_device_summary())

        # A USB device can have multiple configurations, but only one configuration with one interface can be
        # used at the same time. Let the user decide which configuration should be handled.
        num_configurations = self.__dev.get_num_configurations()
        choice = 1
        if num_configurations > 1:
            print(f"Which configuration would you like to examine ({yellow('1-'+str(num_configurations))})?")
            print(f"{blue('1-'+str(num_configurations))} => select configuration")
            print(f"{blue('Other key')} => keep all interfaces in all configurations locked")
            choice = to_int(sys.stdin.readline().rstrip())
            if choice is not None and choice > 0 and choice <= num_configurations:
                self.__dev.set_configuration(choice)
            else:
                print_info("Keeping all interfaces in all configurations locked...\n")
                return

        self.__handle_configuration(choice)

    def __handle_configuration(self, choice):
        '''
        Takes a configuration and processes it.
        '''
        # Get sysfs path of USB device for later processing
        path = self.__dev.get_sysfs_path()

        print(f"Examining configuration {yellow(choice)}:")

        # Set configuration as requested
        self.__dev.set_configuration(choice)

        # Load configuration as object
        cfg= self.__dev.get_configuration(choice)

        for intf in cfg:
            path_intf = f"{path}/{path.rsplit('/',1)[1]}:{str(cfg.bConfigurationValue)}.{str(intf.index)}"
            print(f"Allow Interface {yellow(str(intf.index) + ',' + str(intf.bAlternateSetting))} "\
                    f"({red(intf.get_interface_class_string())}) in Configuration {yellow(str(choice))}?")
            print(f"{blue('1')} => unlock & probe driver")
            print(f"{blue('2')} => unlock only")
            print(f"{blue('Other key')} => keep locked")
            line = sys.stdin.readline().rstrip()

            if line == "1":
                retval = self.__unlock_single_interface(path_intf, probe_driver=True)
                if retval == self.ERR_SUCCESS:
                    print_info("Unlocked interface...\n")
                    continue
            elif line == "2":
                retval = self.__unlock_single_interface(path_intf, probe_driver=False)
                if retval == self.ERR_SUCCESS:
                    print_info("Unlocked interface, didn't probe driver.")
                    print(f"Manually unlock via: 'echo {blue(path_intf.rsplit('/', 1)[1])} > /sys/bus/usb/drivers_probe' \n")
                    continue
            else:
                print_info("Keeping interface locked...\n")
                continue

            # If one of the unlock calls above fails, we will end up here. This could happen if the USB disappeared for some reason
            # (e.g. unplugged) or the selected configuration suddenly disappeared from sysfs. This seems to happen, if the kernel has
            # no appropriate driver for the selected configuration and interface. The kernel then falls back to the first (?) configuration.
            result = self.__handle_configuration_error(retval, choice)
            if result >= 0:
                self.__handle_configuration(result)
            return

    def __handle_configuration_error(self, retval, choice):
        '''
        Takes the requested USB configuration as well as the return value of the __unlock_single_interface()
        function and processes it.
        '''
        if retval == self.ERR_USB_DEV_REMOVED:
            print(red("It seems that the device disappeared. Was it removed? Skipping device."))
            return -1

        if retval == self.ERR_USB_CFG_DISAPPEARED:
            result = self.__dev.get_active_configuration()

            if result > 0:
                print(f"{red('Unlock failed, the kernel switched automatically from configuration')} {yellow(choice)} {red('to')} {yellow(result)}{red('!')}\n"\
                        f"{red('So configuration')} {yellow(choice)} {red('is no longer available and will be skipped.')}")
                print(f"Continue with configuration {yellow(result)}? [y/n]")

                while True:
                    line = sys.stdin.readline().rstrip()
                    if line == "y":
                        return result
                    if line == "n":
                        print_info("\nIgnoring interface...")
                        return -1

    def __unlock_single_interface(self, path, probe_driver):
        '''
        Unlocks a single interface. The interface is referenced by the sysfs path.
        The parameter probe_driver is a boolean which specifies whether the corresponding
        interface driver should be loaded or not.
        '''
        interface = path.rsplit('/', 1)[1]
        path += '/authorized'

        try:
            with open(path, 'w') as f:
                f.write("1")
        except FileNotFoundError:
            return self.ERR_USB_DEV_REMOVED

        if probe_driver:
            with open('/sys/bus/usb/drivers_probe', 'w') as f:
                f.write(interface)

        if not self.__sysfs_path_exists(path):
            return self.ERR_USB_CFG_DISAPPEARED

        return self.ERR_SUCCESS

    def __sysfs_path_exists(self, path):
        '''
        Checks whether a given sysfs path (still) exists or not.
        '''
        # FIXME: Currently the sleep is needed as a hacky workaround for a race condition.
        # If we probe the driver, it can happen that the kernel does not have the correct driver.
        # In this case, the configuration will be removed from sysfs - the sysfs path just disappears.
        # Therefore, we need to wait a bit and check, if the sysfs path is still there.
        # A much better solution (aka correct solution) would be, to somehow test whether the driver probe
        # failed or not.
        time.sleep(0.5)
        if os.path.exists(path):
            return True
        return False

def main():
    # Some monkey patching: We need these functions to extend the Interface class at runtime
    # for simplicity reasons.
    usb.core.Interface.get_interface_string = get_interface_string
    usb.core.Interface.get_interface_class_string = get_interface_class_string

    print_info(f"\n{10*'#'} USBlock {10*'#'}\n")

    if os.getuid() != 0:
        print_error("You need to have root privileges to run this script.\n")
        sys.exit(1)

    lock = UsbLock()
    try:
        print("Escape via CTRL+C.")
        lock.enable()
    except KeyboardInterrupt:
        while True:
            print_info("Do you want to unlock USB? [yes/no]")
            line = sys.stdin.readline().rstrip()
            if line == "yes":
                lock.disable()
                break
            if line == "no":
                print_info("Keeping USB locked...")
                break
        print("Exiting.")
    except Exception as e:
        print_error(f"Panic:\n{str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
