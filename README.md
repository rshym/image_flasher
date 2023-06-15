# image_flasher

Flash big binary files through the u-boot and TFTP server to the eMMC on the R-CAR board.

Based on https://github.com/xen-troops/rcar_flash.

### Usage:
```
image_flasher.py [-h] [-s SERIAL] [-t [TFTP]] [--serverip SERVERIP] [--ipaddr IPADDR] image
```

### Command line options:

```
-s
--serial
```
Serial device to be used for communications with the u-boot.
`/dev/ttyUSB0` is used if not provided.

```
-t
--tftp
```
Path to the root of the running TFTP server. If no path is specified,
then script runs own TFTP server.
Pay attention that root rights are required to run own server due to
need to open port 69.
Also check that your firewall allows TFTP connections
(e.g.: `sudo ufw allow tftp`).

```
--serverip
```
IP address of the host. If not provided, then u-boot will use it's
own settings from environment. If provided, then script will execute
`set serverip {SERVERIP}` before start of TFTP operations.

```
--ipaddr
```
IP address of the board. If not provided, then u-boot will use it's
own settings from environment. If provided, then script will execute
`set ipaddr {IPADDR}` before start of TFTP operations.

```
image
```
Path to the image file. Raw (.img) or .xz-packed files are acceptable.
This file will be split into chunks (`chunk.bin`),
that can be transmitted to the board by TFTP and flashed into eMMC
device 1 partition 0, starting from address 0.

### Examples of usage

Flash `full.img` using already running TFTP server with directory `/srv/tftp`
used as root of the TFTP server.
```
./image_flasher.py -t /srv/tftp ./full.img
```

Flash `full.img` using own TFTP server. `sudo` is required to open port 69
on local host.
```
sudo ./image_flasher.py -t -- ./full.img
```

Flash `full.img` using own TFTP server and work inside `10.10.1.*` network.
Pay attention that `--` is used to specify that `-t` has no parameters, and
`./full.img` is the path to the image, not to the TFTP directory.
 `sudo` is required to open port 69 on local host.
```
sudo ./image_flasher.py --serverip 10.10.1.15 --ipaddr 10.10.1.10 -t -- ./full.img
```