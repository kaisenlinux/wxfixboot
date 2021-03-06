#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Helper Backend Tools in the BackendTools Package for WxFixBoot
# This file is part of WxFixBoot.
# Copyright (C) 2013-2020 Hamish McIntyre-Bhatty
# WxFixBoot is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3 or,
# at your option, any later version.
#
# WxFixBoot is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with WxFixBoot.  If not, see <http://www.gnu.org/licenses/>.

# pylint: disable=logging-not-lazy
#
# Reason (logging-not-lazy): This is a more readable way of logging.

"""
This module contains the helper backend tools (functions) used when performing
more complex operations with WxFixBoot. These are included here to reduce code
duplication and attempt to keep everything more organised.
"""

#Import modules
import os
import sys
import time
import logging

#Import other modules.
sys.path.append('../..') #Need to be able to import the Tools module from here.
import Tools.coretools as CoreTools #pylint: disable=wrong-import-position
import Tools.dialogtools as DialogTools #pylint: disable=wrong-import-position
from Tools.dictionaries import * #pylint: disable=wrong-import-position

#Set up logging.
logger = logging.getLogger(__name__)
logger.setLevel(logging.getLogger("WxFixBoot").getEffectiveLevel())

def partition_matches_os(partition, _os):
    """
    Matches the given boot device to an OS, using the info we gathered at startup
    using the function above
    """

    #Try to match it by UUID or by name, looking for the same type of match we got before,
    #to avoid false positives.
    logger.debug("partition_matches_os(): Partition To Match: "+partition+"...")
    logger.debug("partition_matches_os(): OS to match with: "+_os+"...")
    logger.debug("partition_matches_os(): Trying to match (1st) with: "
                 + OS_INFO[_os]["Partition"]+"...")

    logger.debug("partition_matches_os(): Trying to match (2nd) with: "
                 + OS_INFO[_os]["BootPartition"]+"...")

    logger.debug("partition_matches_os(): Trying to match (3rd) with: "
                 + OS_INFO[_os]["EFIPartition"]+"...")

    #If partition is unknown ignore it.
    if partition == "Unknown":
        return False

    #If the eg EFI partition isn't known, don't do the rest of the test in the if statement to
    #avoid erors (short-circuit logic).
    if OS_INFO[_os]["Partition"] != "Unknown" \
        and partition in (OS_INFO[_os]["Partition"], DISK_INFO[OS_INFO[_os]["Partition"]]["UUID"]):
        return True

    elif OS_INFO[_os]["BootPartition"] != "Unknown" \
        and partition in (OS_INFO[_os]["BootPartition"],
                          DISK_INFO[OS_INFO[_os]["BootPartition"]]["UUID"]):

        return True

    elif OS_INFO[_os]["EFIPartition"] != "Unknown" \
        and partition in (OS_INFO[_os]["EFIPartition"],
                          DISK_INFO[OS_INFO[_os]["EFIPartition"]]["UUID"]):

        return True


    #Otherwise return false.
    return False

def wait_until_packagemanager_free(mount_point, package_manager):
    """
    Check if the package manager is in use, and if so, wait until it is no longer in use.
    """

    if package_manager == "apt-get":
        cmd = "apt-get check"
        success_retvals = (0, 0) #100 omitted - indicates apt is in use.

    elif package_manager == "dnf":
        cmd = "dnf -C check-update"
        success_retvals = (0, 100) #100 - updates available.

    if mount_point != "":
        cmd = "chroot "+mount_point+" "+cmd

    retval = 1

    #Trap in while loop until package manager is free.
    #FIXME: Doesn't work with DNF, but doesn't strictly matter because it will just wait
    #FIXME: Handle return code 100 when updates are available.
    #until the lock is free, rather than exiting.
    while retval not in success_retvals:
        retval = CoreTools.start_process(cmd, show_output=False, privileged=True)

        #Get the package cache if there is none. 200 - locking failure.
        if package_manager == "dnf" and retval not in (0, 200):
            CoreTools.start_process("sh -c 'echo No cache available, "
                                    + "downloading package information...'")

            if mount_point != "":
                cmd2 = "chroot "+mount_point+" dnf check-update"

            else:
                cmd2 = "dnf check-update"

            CoreTools.start_process(cmd2, show_output=False, privileged=True)

        time.sleep(5)

def find_missing_fsck_modules():
    """Check for and return all missing fsck modules (fsck.vfat, fsck.minix, etc)."""
    logger.info("find_missing_fsck_modules(): Looking for missing FSCK modules to ignore...")
    failed_list = []

    keys = list(DISK_INFO.keys())
    keys.sort()

    for disk in keys:
        #Check the FSType is known and isn't swap.
        if DISK_INFO[disk]["FileSystem"] not in ("Unknown", "N/A"):
            #Check if this module is present.
            if CoreTools.start_process("which fsck."+DISK_INFO[disk]["FileSystem"],
                                       show_output=False) != 0:
                #Couldn't find it, add it to the failed list.
                logger.warning("FSCKModules(): Couldn't find FSCK module fsck."
                               + DISK_INFO[disk]["FileSystem"]
                               + "! Adding it to the list of missing modules...")

                failed_list.append("fsck."+DISK_INFO[disk]["FileSystem"])

            else:
                logger.debug("FSCKModules(): Found fsck."+DISK_INFO[disk]["FileSystem"]+"...")

    #Return the list, so FSCheck functions know which FSes to ignore.
    logger.info("find_missing_fsck_modules(): Done! Missing FSCK modules: "+', '.join(failed_list))
    return failed_list

def find_checkable_file_systems():
    """
    Find all checkable filesystems, and then return them to
    EssentialBackendTools().filesystem_check()
    """

    logger.info("find_checkable_file_systems(): Finding and returning all filesystems/partitions "
                + "that can be checked...")

    #Do setup.
    do_not_check_list = []
    filesystems_to_check = {}
    root_fs = CoreTools.get_partition_mounted_at("/")

    #Get a list of missing fsck modules (if any) based on the existing filesystems.
    missing_fsck_modules = find_missing_fsck_modules()

    keys = list(DISK_INFO.keys())
    keys.sort()

    #Determine checkable partitions.
    for disk in keys:
        #Ignore all devices.
        if DISK_INFO[disk]["Type"] == "Device":
            continue

        #Check if the required fsck module is present, and that the partition isn't root_fs
        if "fsck."+DISK_INFO[disk]["FileSystem"] in missing_fsck_modules:
            mount_point = "None"
            check_this_fs = False
            remount_fs_after = False
            reason = "filesystem checker was not found."

        elif SYSTEM_INFO["IsLiveDisk"] is False and disk == root_fs:
            #If we're not running on a live disk, skip the filesystem if it's the same as root_fs
            #(in which case checking it may corrupt data).
            mount_point = "/"
            check_this_fs = False
            remount_fs_after = False
            reason = "disk is busy."

        #Extra check for LVM disks using aliases.
        elif DISK_INFO[disk]["Product"] == "LVM Partition" and root_fs in DISK_INFO[disk]["Aliases"]:
            mount_point = "/"
            check_this_fs = False
            remount_fs_after = False
            reason = "disk is busy."

        else:
            #If filesystem is unknown, or not applicable (extended partitions), don't check it.
            if DISK_INFO[disk]["FileSystem"] in ("Unknown", "N/A"):
                mount_point = "None"
                check_this_fs = False
                remount_fs_after = False
                reason = "filesystem was not recognised."

            else:
                #Check if the partition is mounted.
                if CoreTools.is_mounted(disk) is False:
                    mount_point = "None"
                    check_this_fs = True
                    remount_fs_after = False

                #Extra check for LVM disks using aliases.
                elif DISK_INFO[disk]["Product"] == "LVM Partition" and \
                     CoreTools.any_mounted(DISK_INFO[disk]["Aliases"]) is False:

                    mount_point = "None"
                    check_this_fs = True
                    remount_fs_after = False

                else:
                    #Unmount the FS temporarily, to avoid data corruption.
                    mount_point = CoreTools.get_mount_point_of(disk)

                    if CoreTools.unmount(disk) != 0:
                        logger.warning("find_checkable_file_systems(): Failed to unmount "+disk
                                       +", which is necessary for safe disk checking! Ignoring it.")

                        check_this_fs = False
                        remount_fs_after = False
                        reason = "disk is busy."

                    else:
                        check_this_fs = True
                        remount_fs_after = True

        if check_this_fs:
            #Add it to the dictionary for checking.
            filesystems_to_check[disk] = {}
            filesystems_to_check[disk]["Remount"] = remount_fs_after
            filesystems_to_check[disk]["MountPoint"] = mount_point

        else:
            #Add it to the non-checkable list
            do_not_check_list.append(disk+", because the "+reason)

    #Report uncheckable partitions.
    if do_not_check_list != []:
        #Some filesystems will not be checked. Tell the user.
        DialogTools.show_msg_dlg(kind="info",
                                 message="The following filesystems will not be checked:\n\n"
                                 + '\n'.join(do_not_check_list)+"\n\nThe most likely reason for "
                                 + "this is that some of the filesystems are in use, or that the "
                                 + "required filesystem checkers weren't found. WxFixBoot will "
                                 + "now continue to check the remaining filesystems.")

    logger.info("find_checkable_file_systems(): Done! Filesystems that won't be checked: "
                + '\n'.join(do_not_check_list)+"...")

    return filesystems_to_check

def write_fstab_entry_for_uefi_partition(_os, mount_point):
    """
    Write an /etc/fstab entry for the UEFI System Partition, if there isn't already one.
    DISABLED***
    """
    #FIXME Disabled cos breaks things.
    #TODO When I try to fix this, use the new config file readers/writers.
    return True

    logger.info("write_fstab_entry_for_uefi_partition(): Preparing to write an fstab entry for "
                + "the UEFI partition ("+OS_INFO[_os]["EFIPartition"]+")...")

    write_entry = True

    #Make the directory mount_point/boot/efi if it doesn't already exist.
    if os.path.isdir(mount_point+"/boot/efi") is False:
        CoreTools.start_process("mkdir -p "+mount_point+"/boot/efi", show_output=False,
                                privileged=True)

    #Open the mount_point/etc/fstab file for reading. If we aren't using chroot, this'll just be
    #/etc/fstab, otherwise, /mnt/wxfixboot/mountpoints/dev/sdxy/etc/fstab. Also, save its contents
    #in a variable.
    fstab = open(mount_point+"/etc/fstab", "r")
    new_file_contents = []

    for line in fstab:
        if OS_INFO[_os]["EFIPartition"] in line \
            or "UUID="+DISK_INFO[OS_INFO[_os]["EFIPartition"]]["UUID"] in line:

            #This fstab already has an entry for the UEFI System Partition!
            write_entry = False

        new_file_contents.append(line)

    #Check if we need to write the entry.
    if write_entry is False:
        #We don't!
        logger.info("write_fstab_entry_for_uefi_partition(): fstab entry already present! "
                    + "Skipping...")

        fstab.close()

    else:
        #We do. If we can use the UUID, then we will, but otherwise we'll use the standard
        #device name.
        logger.info("write_fstab_entry_for_uefi_partition(): Writing fstab entry...")
        new_file_contents.append("\n#fstab entry for UEFI System Partition ("
                                 + OS_INFO[_os]["EFIPartition"]+"), written by WxFixBoot.\n")

        if DISK_INFO[OS_INFO[_os]["EFIPartition"]]["UUID"] != "Unknown":
            logger.info("write_fstab_entry_for_uefi_partition(): Using UUID to prevent problems "
                        + "down the line...")

            new_file_contents.append("UUID="+DISK_INFO[OS_INFO[_os]["EFIPartition"]]["UUID"]
                                     + " /boot/efi vfat defaults 0 2\n")

        else:
            logger.warning("write_fstab_entry_for_uefi_partition(): We have no UUID for the "
                           + "UEFI Partition: "+OS_INFO[_os]["EFIPartition"]+"! This isn't good, "
                           + "and may cause problems down the line. Continuing anyway, using "
                           + "device name instead...")

            new_file_contents.append(OS_INFO[_os]["EFIPartition"]+" /boot/efi vfat defaults 0 2\n")

        #Write the finished lines to the file.
        fstab.close()
        fstab = open(mount_point+"/etc/fstab", 'w')
        fstab.write(''.join(new_file_contents))
        fstab.close()

        logger.info("write_fstab_entry_for_uefi_partition(): Done!")

def backup_uefi_files(mount_point):
    """Backup some .efi files, just in case something goes wrong."""
    #TODO: Make this smarter when we detect Windows.
    logger.info("backup_uefi_files(): Backing up UEFI Files...")

    #We'll backup /EFI/boot/bootx64.efi if it exists, and we'll also backup Windows's uefi files,
    #if they exist. First do /EFI/boot/bootx64.efi. Fortunately, the UEFI partition is always a
    #fat32/fat16 filesystem, so case doesn't matter.
    logger.info("backup_uefi_files(): Backing up "+mount_point+"/boot/efi/boot/boot*.efi...")

    if os.path.isfile(mount_point+"/boot/efi/EFI/boot/boot*.efi"):
        if CoreTools.start_process("cp -v "+mount_point+"/boot/efi/EFI/boot/boot*.efi "
                                   + mount_point+"/boot/efi/EFI/boot/bkpbootx64.efi",
                                   show_output=False, privileged=True) != 0:
            #Log and warn user if this went wrong.
            logger.error("backup_uefi_files(): Failed to backup failsafe UEFI boot file! "
                         + "Warning user and continuing...")

            DialogTools.show_msg_dlg(kind="warning", message="WxFixBoot failed to save "
                                     + "your UEFI boot files to the backup directory! Click okay to continue.")

    #Now do Windows's files, if they exist.
    logger.info("backup_uefi_files(): Backing up Windows's boot files if they exist...")

    if os.path.isfile(mount_point+"/boot/efi/EFI/Microsoft/boot/bootmgfw.efi"):
        if CoreTools.start_process("cp -v "+mount_point+"/boot/efi/EFI/Microsoft/boot/bootmgfw.efi "
                                   + mount_point+"/boot/efi/EFI/Microsoft/boot/bkpbootmgfw.efi",
                                   show_output=False, privileged=True) != 0:
            #Log and warn user if this went wrong.
            logger.error("backup_uefi_files(): Failed to backup Windows's UEFI boot files! "
                         + "Warning user and continuing...")

            DialogTools.show_msg_dlg(kind="warning", message="WxFixBoot failed to "
                                     + "backup Windows's UEFI boot files! Click okay to continue.")

    logger.info("backup_uefi_files(): Done!")

def manage_uefi_files(_os, mount_point):
    """Manage UEFI bootloader files."""
    logger.info("manage_uefi_files(): Copying UEFI Files to uefi_boot_dir...")

    #First, let's check if EFI/boot already exists. This is a fat32/fat16 filesystem,
    #so case doesn't matter.
    if os.path.isdir(mount_point+"/boot/efi/EFI/boot"):
        uefi_boot_dir = mount_point+"/boot/efi/EFI/boot"

    else:
        #It doesn't, so we'll create it.
        uefi_boot_dir = mount_point+"/boot/efi/EFI/boot"
        CoreTools.start_process("mkdir "+uefi_boot_dir, show_output=False, privileged=True)

    #Do this different depending on whether the OS is ubuntu or fedora-based.
    if OS_INFO[_os]["PackageManager"] == "apt-get":
        source_dir = mount_point+"/boot/efi/EFI/ubuntu"

    elif OS_INFO[_os]["PackageManager"] == "dnf":
        source_dir = mount_point+"/boot/efi/EFI/fedora"

    if BOOTLOADER_INFO[_os]["Settings"]["NewBootloader"] == "GRUB-UEFI":
        #We need to copy grubx64.efi to uefi_boot_dir.
        logger.info("manage_uefi_files(): Copying grubx64.efi to "+uefi_boot_dir+"...")

        if CoreTools.start_process("cp -v "+source_dir+"/grubx64.efi "+uefi_boot_dir+"/bootx64.efi",
                                   show_output=False, privileged=True) != 0:
            logger.error("manage_uefi_files(): Failed to copy "+source_dir+"/grub*.efi to "
                         + uefi_boot_dir+"/bootx64.efi! Attempting to continue anyway...")

    logger.info("manage_uefi_files(): Done!")
