#!/usr/bin/env python3

import os
import serial
import logging
import argparse
import traceback
from typing import List
import tftpy
import threading

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(
        description='Flash image files through u-boot and tftp', )
    parser.add_argument(
        '-i',
        '--image',
        help='Path to the image file')

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
        help="Start our own TFTP server to feed files to u-boot")

    args = parser.parse_args()

    tftp_root = os.getcwd()

    if args.tftp == "AUTO":
        tftp_ip = "127.0.0.1"
        tftp_port = 69
        log.info(f"Starting our TFTP server {tftp_ip}:{tftp_port}")

        tftpsrv = PYTFTPServer(tftp_ip, tftp_port, tftp_root)
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
    def __init__(self, ip, port, folder):
        self.ip = ip
        self.port = port
        self.tftp_server = tftpy.TftpServer(folder)

    def start_tftp_server(self):
        self.tftp_server.listen(self.ip, self.port)

    def stop_tftp_server(self):
        self.tftp_server.stop()


def do_flash_image(args, tftp_root):

    conn = open_connection(args)

    uboot_propmt = "=>"
    # wait for interruption prompt
    try:
        log.info('Waiting for "Hit any key to stop autoboot"...')
        conn_wait_for(conn, "Hit any key to stop autoboot:")
        conn_send(conn, "\r")
    except:
        # if prompt 'timeout-ed' send CR to check maybe u-boot is active already
        conn_send(conn, "\r")
        conn_wait_for(conn, uboot_propmt)

    log.info(args.image)
    # do in loop:
    # - read X MB chunk from image file
    # - save chunk to file in tftp root
    # - tell u-boot to 'tftp-and-emmc' chunk
    image_size = os.path.getsize(args.image)

    ###########
    base_addr = 0x0
    mmc_device = 1
    mmc_part = 0
    mmc_block_size = 512
    ###########

    chunk_filename = "chunk.bin"
    chunk_size_in_bytes = 20*1024*1024

    f_img = open(args.image, "rb")
    bytes_sent = 0
    block_start = base_addr // mmc_block_size
    out_fullname = os.path.join(tftp_root, chunk_filename)

    # switch to required MMC device/partition
    conn_send(conn, f"mmc dev {mmc_device} {mmc_part}\r")
    conn_wait_for(conn, uboot_propmt)

    while bytes_sent < image_size:
        # create chunk
        data = f_img.read(chunk_size_in_bytes)
        f_out = open(out_fullname, "wb")
        f_out.write(data)
        f_out.close()

        chunk_size_in_blocks = len(data) // mmc_block_size
        if len(data) % mmc_block_size:
            chunk_size_in_blocks += 1

        # instruct u-boot to tftp-and-emmc file
        conn_send(conn, f"tftp 0x48000000 {chunk_filename}\r")
        conn_wait_for(conn, uboot_propmt)

        conn_send(conn, f"mmc write 0x48000000 0x{block_start:X} 0x{chunk_size_in_blocks:X}\r")
        conn_wait_for(conn, uboot_propmt)

        bytes_sent += len(data)
        block_start += chunk_size_in_blocks

        print(f"{bytes_sent:_}/{image_size:_} ({bytes_sent * 100 // image_size}%)", end="\r")

    # send "newline char" to start further output on the new line
    print("")

    os.remove(out_fullname)

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
    data = conn.read_until(expect.encode('ascii')).decode('ascii')
    print(data)
    if expect not in data:
        raise Exception(f"Timeout waiting for `{expect}` from the device")


def conn_send(conn, data):
    conn.write(data.encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.fatal(e)
        log.fatal(traceback.format_exc())
