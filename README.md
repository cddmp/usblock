# usb-lockdown-linux

A simple tool to protect against malicious USB devices.

Once the tool is started (as root), it will lock all USB devices (interfaces) by using the Linux kernel's USB authorization support. 
It will then monitor for any USB devices being plugged in. Once a USB device it detected, the tool will list all interfaces. 
The user then has 3 options for every interface:

- Unlock the interface and probe the kernel to load the corresponding driver
- Only unlock the interface but don't probe
- Keep the interface locked

If the second option is chosen, the tool will print out the interface path in sysfs. Such a path could look like that:

```
3-2:1.0
```

The user can then manually probe the driver at any point in time via:

```console
# echo 3-2:1.0 > /sys/bus/usb/drivers_probe 
```

This approach allows to unock only those interfaces, which the user considers trustworthy.

# Dependencies
- python3-pyudev
- python3-pyusb
