#!/usr/bin/env python3

import os
import pathlib
import serial
import logging
import argparse
import traceback
from typing import List
from string import printable
import tftpy
import threading
import lzma

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='Flash image files through u-boot and tftp')

    parser.add_argument(
        'image',
        type=pathlib.Path,
        help='Name of image file to flash')

    parser.add_argument(
        '-s',
        '--serial',
        help='Serial console to use')

    parser.add_argument(
        '-t',
        '--tftp',
        nargs='?',
        type=str,
        default=None,
        const="AUTO",
        help="Use external TFTP server or start our own")

    parser.add_argument(
        '--serverip',
        help='IP of the host that will be used TFTP transfer.')

    parser.add_argument(
        '--ipaddr',
        help='IP of the board that will be used TFTP transfer.')

    args = parser.parse_args()

    tftp_root = os.getcwd()

    if args.tftp == "AUTO":
        log.info(f"Starting our TFTP server...")

        tftpsrv = PYTFTPServer(tftp_root)
        TFTP_srv_thread = threading.Thread(name="TFTP Server thread", target=tftpsrv.start_tftp_server)
        TFTP_srv_thread.start()

    elif os.path.isdir(args.tftp):
        # use external path
        tftp_root = args.tftp
        log.info(f"Use external TFTP root {tftp_root}")
    else:
        raise Exception("-t parameter is not external TFTP root.")

    do_flash_image(args, tftp_root)

    if args.tftp == "AUTO":
        log.info("Stopping our TFTP server")
        tftpsrv.stop_tftp_server()
        TFTP_srv_thread.join()


class PYTFTPServer(object):
    def __init__(self, folder):
        self.tftp_server = tftpy.TftpServer(folder)

    def start_tftp_server(self):
        # listen to all interfaces and port 69
        self.tftp_server.listen()

    def stop_tftp_server(self):
        self.tftp_server.stop()


def do_flash_image(args, tftp_root):

    log.info(args.image)

    conn = open_connection(args)

    uboot_propmt = "=>"

    # Send 'CR', and check for one of the possible options:
    # - uboot_prompt appears, if u-boot console is already active
    # - u-boot is just starting, so we will get "Hit any key.."
    log.info('Waiting for u-boot prompt...')
    conn_send(conn, "\r")
    conn_wait_for_any(conn, [uboot_propmt, "Hit any key to stop autoboot:"])
    # we got "Hit any key", so let's stop the boot
    conn_send(conn, "\r")
    conn_wait_for(conn, uboot_propmt)

    image_size = os.path.getsize(args.image)

    ###########
    base_addr = 0x0
    mmc_device = 1
    mmc_part = 0
    mmc_block_size = 512
    ###########

    chunk_filename = "chunk.bin"
    chunk_size_in_bytes = 20*1024*1024

    use_lzma = False

    if str(args.image).endswith(".xz"):
        use_lzma = True
        f_lzma = lzma.open(args.image)
        image_size = 0
    else:
        f_img = open(args.image, "rb")

    bytes_sent = 0
    block_start = base_addr // mmc_block_size
    out_fullname = os.path.join(tftp_root, chunk_filename)

    if args.serverip:
        conn_send(conn, f"env set serverip {args.serverip}\r")
        conn_wait_for(conn, uboot_propmt)

    if args.ipaddr:
        conn_send(conn, f"env set ipaddr {args.ipaddr}\r")
        conn_wait_for(conn, uboot_propmt)

    # switch to the required MMC device/partition
    conn_send(conn, f"mmc dev {mmc_device} {mmc_part}\r")
    conn_wait_for(conn, uboot_propmt)

    # do in loop:
    # - read X MB chunk from image file
    # - save chunk to file in tftp root
    # - tell u-boot to 'tftp-and-emmc' chunk
    while True:
        if use_lzma:
            data = f_lzma.read(chunk_size_in_bytes)
        else:
            data = f_img.read(chunk_size_in_bytes)

        if not data:
            break

        chunk_size_in_blocks = len(data) // mmc_block_size
        if len(data) % mmc_block_size:
            chunk_size_in_blocks += 1

        buffer_is_00_only = True
        for i in range(len(data)):
            # check for zero only
            if (data[i] != 0):
                buffer_is_00_only = False

        if buffer_is_00_only:
            conn_send(conn, f"mw.b 0x48000000 0x00 0x{len(data):X}\r")
            conn_wait_for(conn, uboot_propmt)
        else:
            # create chunk
            f_out = open(out_fullname, "wb")
            f_out.write(data)
            f_out.close()

            conn_send(conn, f"tftp 0x48000000 {chunk_filename}\r")
            conn_wait_for(conn, uboot_propmt)

        conn_send(conn, f"mmc write 0x48000000 0x{block_start:X} 0x{chunk_size_in_blocks:X}\r")
        conn_wait_for(conn, uboot_propmt)

        bytes_sent += len(data)
        block_start += chunk_size_in_blocks

        if image_size:
            print(f"\nProgress: {bytes_sent:_}/{image_size:_} ({bytes_sent * 100 // image_size}%)")
        else:
            print(f"\nProgress: {bytes_sent:_}")

        print("===============================")

    # send "newline char" to start further output on the new line
    print("")

    os.remove(out_fullname)
    if use_lzma:
        f_lzma.close()
    else:
        f_img.close()
    conn.close()

    log.info("Image was flashed successfully.")


def open_connection(args):
    # Default value
    dev_name = '/dev/ttyUSB0'
    if args.serial:
        dev_name = args.serial
    baud = 115200

    log.info(f"Using serial port {dev_name} with baudrate {baud}")
    conn = serial.Serial(port=dev_name, baudrate=baud, timeout=20)
    if conn.is_open:
        conn.close()
    conn.open()

    return conn


def conn_wait_for(conn, expect: str):
    rcv_str = ""
    while expect not in rcv_str:
        data = conn.read(1)
        if not data:
            raise TimeoutError(f"Timeout waiting for `{expect}` from the device")
        rcv_char = chr(data[0])
        if rcv_char in printable or rcv_char == '\b':
            print(rcv_char, end='', flush=True)
        rcv_str += rcv_char


def conn_wait_for_any(conn, expect: List[str]):
    rcv_str = ""
    # stay in the read loop until any of expected string is received
    # in other words - all expected substrings are not in received buffer
    while all([x not in rcv_str for x in expect]):
        data = conn.read(1)
        if not data:
            raise TimeoutError(f"Timeout waiting for `{expect}` from the device")
        rcv_char = chr(data[0])
        if rcv_char in printable or rcv_char == '\b':
            print(rcv_char, end='', flush=True)
        rcv_str += rcv_char


def conn_send(conn, data):
    conn.write(data.encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.fatal(e)
        log.fatal(traceback.format_exc())
