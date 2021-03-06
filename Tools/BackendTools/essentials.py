#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Essential Backend Tools in the BackendTools Package for WxFixBoot
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
This contains the essential backend tools operations.
(internet connection test, file system checks).

These are called the essential tools because a failure here may cancel all other
operations. For example, if a filesystem check fails, it's a bad idea to write to
the disk by doing bootloader operations. Likewise, a new bootloader cannot be
installed without an internet connection.
"""

#Import modules.
import logging
import sys
import wx

#Import other modules.
sys.path.append('../..') #Need to be able to import the Tools module from here.

import Tools.coretools as CoreTools #pylint: disable=wrong-import-position
import Tools.dialogtools as DialogTools #pylint: disable=wrong-import-position
from Tools.dictionaries import SYSTEM_INFO, DISK_INFO #pylint: disable=wrong-import-position
from . import helpers as HelperBackendTools #pylint: disable=wrong-import-position

#Set up logging.
logger = logging.getLogger(__name__)
logger.setLevel(logging.getLogger("WxFixBoot").getEffectiveLevel())

#Silence other errors.
OPERATIONS = []

def check_internet_connection():
    """Check the internet connection."""
    logger.info("check_internet_connection(): Checking the Internet Connection w/ OpenDNS...")

    while True:
        #Test the internet connection by pinging an OpenDNS DNS server.
        packet_loss = "100%"

        logger.debug("check_internet_connection(): Running 'ping -c 5 -i 0.5 208.67.222.222'...")
        retval, output = CoreTools.start_process("ping -c 5 -i 0.5 208.67.222.222",
                                                 show_output=False, return_output=True)

        if retval != 0:
            #This errored for some reason. Probably no internet connection.
            logger.error("check_internet_connection(): Command errored!")
            packet_loss = "100%"

        else:
            #Get the % packet loss.
            for line in output.split("\n"):
                if 'packet loss' in line:
                    packet_loss = line.split()[-5]

        if packet_loss == "0%":
            #Good! We have a reliable internet connection.
            logger.info("check_internet_connection(): Internet Connection Test Succeeded!")
            break

        else:
            #Uh oh! We DON'T have a reliable internet connection! Ask the user to either try again,
            #or skip Bootloader operations.
            logger.error("check_internet_connection(): Internet Connection test failed! Asking "
                         + "user to try again or disable bootloader operations...")

            result = DialogTools.show_yes_no_dlg(message="Your Internet Connection failed the "
                                                 + "test! Without a working internet connection, "
                                                 + "you cannot perform bootloader operations. "
                                                 + "Click yes to try again, and click no to give "
                                                 + "up and skip bootloader operations.",
                                                 title="WxFixBoot - Disable Bootloader "
                                                 + "Operations?",
                                                 buttons=("Try again",
                                                          "Cancel Bootloader Operations"))

            if result is False:
                logger.warning("check_internet_connection(): Disabling bootloader operations "
                               + "due to bad internet connection...")

                SYSTEM_INFO["DisableBootloaderOperations"] = True
                SYSTEM_INFO["DisableBootloaderOperationsBecause"] \
                .append("Internet Connection test failed.")

                break

            else:
                #We'll just run the loop again
                logger.info("check_internet_connection(): Testing the internet connection "
                            + "again...")

def filesystem_check(_type, manage_bootloader_function):
    """Quickly check all filesystems."""
    logger.debug("filesystem_check(): Starting...")

    #Update Current Operation Text.
    wx.CallAfter(wx.GetApp().TopWindow.update_current_operation_text,
                 message="Preparing for Filesystem Check...")

    wx.CallAfter(wx.GetApp().TopWindow.update_current_progress, 10)
    wx.CallAfter(wx.GetApp().TopWindow.update_output_box,
                 "\n###Preparing to do the Filesystem Check...###\n")

    #Determine which Disks are to be checked.
    filesystems_to_check = HelperBackendTools.find_checkable_file_systems()
    wx.CallAfter(wx.GetApp().TopWindow.update_current_progress, 30)

    #Find the length of the list (this is needed to update the progressbars).
    filesystems_to_check_length = len(filesystems_to_check)
    checked = 0

    DialogTools.show_msg_dlg(kind="info", message="WxFixBoot will now perform the disk checks. "
                             + "You may wish to open the terminal output box to view the "
                             + "progress information.")

    #Run the check on the checkable Disks
    for disk in filesystems_to_check:
        #Gather info.
        logger.info("filesystem_check():: Checking "+disk+"...")
        wx.CallAfter(wx.GetApp().TopWindow.update_output_box, "\n###Checking Disk: "+disk+"###\n")
        wx.CallAfter(wx.GetApp().TopWindow.update_current_operation_text,
                     message="Checking Disk: "+disk)
        wx.CallAfter(wx.GetApp().TopWindow.update_current_progress,
                     30+((50//filesystems_to_check_length)*(checked+1)))

        run_badblocks = False

        #Create a command list that will work based on the fstype of this Disk and the type of
        #check we're performing. If there aren't any use cases for the fstype, display a message
        #to the user and skip it.
        if _type == "Quick":
            if DISK_INFO[disk]["FileSystem"] == "jfs":
                exec_cmds = "fsck.jfs -vf "+disk

            elif DISK_INFO[disk]["FileSystem"] == "minix":
                exec_cmds = "fsck.minix -avf "+disk

            elif DISK_INFO[disk]["FileSystem"] == "reiserfs":
                exec_cmds = "fsck.reiserfs -apf "+disk

            elif DISK_INFO[disk]["FileSystem"] == "xfs":
                exec_cmds = "xfs_repair -Pvd "+disk

            elif DISK_INFO[disk]["FileSystem"] in ("hfs", "hfsplus"):
                exec_cmds = "fsck.hfsplus -fy "+disk

            elif DISK_INFO[disk]["FileSystem"] == "vfat":
                exec_cmds = "fsck.vfat -yv "+disk

            elif DISK_INFO[disk]["FileSystem"] in ('ext2', 'ext3', 'ext4', 'ext4dev'):
                exec_cmds = "fsck."+DISK_INFO[disk]["FileSystem"]+" -yvf "+disk

            else:
                exec_cmds = ""
                logger.warning("filesystem_check(): Skipping Disk: "+disk
                               + ", as WxFixBoot doesn't support checking it yet...")

                DialogTools.show_msg_dlg(kind="error", message="The filesystem on Disk: "+disk
                                         + " could not be checked, as WxFixBoot doesn't support "
                                         + "checking it yet. "+disk+" will now be skipped.")

        else:
            #For disks that doesn't do bad sector checks with the normal FS checker,
            #run badblocks manually on them.
            if DISK_INFO[disk]["FileSystem"] == "jfs":
                exec_cmds = "fsck.jfs -vf "+disk
                run_badblocks = True

            elif DISK_INFO[disk]["FileSystem"] == "minix":
                exec_cmds = "fsck.minix -avf "+disk
                run_badblocks = True

            elif DISK_INFO[disk]["FileSystem"] == "reiserfs":
                exec_cmds = "fsck.reiserfs -apf "+disk
                run_badblocks = True

            elif DISK_INFO[disk]["FileSystem"] == "xfs":
                exec_cmds = "xfs_repair -Pvd "+disk
                run_badblocks = True

            elif DISK_INFO[disk]["FileSystem"] in ("hfs", "hfsplus"):
                exec_cmds = "fsck.hfsplus -fy "+disk
                run_badblocks = True

            elif DISK_INFO[disk]["FileSystem"] == "vfat":
                exec_cmds = "fsck.vfat -yvt "+disk

            elif DISK_INFO[disk]["FileSystem"] in ('ext2', 'ext3', 'ext4', 'ext4dev'):
                exec_cmds = "fsck."+DISK_INFO[disk]["FileSystem"]+" -yvcf "+disk

            else:
                exec_cmds = ""
                DialogTools.show_msg_dlg(kind="info", message="The filesystem on Disk: "+disk
                                         + " could not be checked, as WxFixBoot doesn't support "
                                         + "checking it yet. "+disk+" will now be skipped.")

        #Run the command, and remount the Disk if needed.
        if exec_cmds != "":
            retval = CoreTools.start_process(exec_cmds, privileged=True)

            #Check the return values, and run the handler if needed.
            if retval == 0:
                #Success.
                logger.info("filesystem_check(): Checked Disk: "+disk+". No Errors Found!")

            else:
                handle_filesystem_check_return_values(exec_cmds=exec_cmds, retval=retval,
                                                      partition=disk,
                                                      manage_bootloader_function=manage_bootloader_function)

        #Run bad blocks if requested.
        if run_badblocks:
            retval = CoreTools.start_process("badblocks -sv "+disk, privileged=True)

            #Check the return values, and run the handler if needed.
            if retval == 0:
                #Success.
                logger.info("filesystem_check(): Checked Disk: "+disk+" for bad sectors. "
                            + "No Errors Found!")

            else:
                handle_filesystem_check_return_values(exec_cmds="badblocks -sv "+disk,
                                                      retval=retval, partition=disk,
                                                      manage_bootloader_function=manage_bootloader_function)

        if filesystems_to_check[disk]["Remount"]:
            logger.debug("filesystem_check(): Remounting Disk: "+disk+" Read-Write...")
            retval = CoreTools.mount_partition(partition=disk,
                                               mount_point=filesystems_to_check[disk]["MountPoint"])

            if retval != 0:
                logger.warning("filesystem_check(): Failed to remount "+disk
                               + " after check. We probably need to reboot first. Never mind...")

        checked += 1

    #Update Current Operation Text.
    wx.CallAfter(wx.GetApp().TopWindow.update_current_operation_text,
                 message="Finished Filesystem Check!")
    wx.CallAfter(wx.GetApp().TopWindow.update_current_progress, 100)
    wx.CallAfter(wx.GetApp().TopWindow.update_output_box, "\n###Finished Filesystem Check!###\n")

def handle_filesystem_check_return_values(exec_cmds, retval, partition, manage_bootloader_function):
    """Handle Filesystem Checker return codes."""
    exec_list = exec_cmds.split()

    #Return values of 1,2 or 3 happen if errors were corrected.
    if retval in (1, 2, 3) and exec_list[0] != "badblocks":
        if exec_list[0] == "xfs_repair":
            #Fs Corruption Detected.
            logger.warning("handle_filesystem_check_return_values(): xfs_repair detected "
                           + "filesystem corruption on FileSystem: "+partition
                           + ". It's probably (and hopefully) been fixed, but we're logging "
                           + "this anyway.")

            DialogTools.show_msg_dlg(kind="warning",
                                     message="Corruption was found on the filesystem: "+partition
                                     + "! Fortunately, it looks like the checker utility has "
                                     + "fixed the corruption. Click okay to continue.")

        elif exec_list[0] in ('fsck.jfs', 'fsck.minix', 'fsck.reiserfs',
                              'fsck.vfat', 'fsck.ext2', 'fsck.ex3',
                              'fsck.ext4', 'fsck.ext4dev'):

            #Fixed Errors.
            logger.info("handle_filesystem_check_return_values(): "+exec_list[0]
                        + " successfully fixed errors on the partition: "+partition
                        + ". Continuing...")

            DialogTools.show_msg_dlg(kind="warning", message="The filesystem checker found and "
                                     + "successfully fixed errors on partition: "+partition
                                     + ". Click okay to continue.")

    else:
        #Something bad happened!
        #If we're doing bootloader operations, prompt the user to disable them.
        doing_bootloader_operations = False

        for function in OPERATIONS:
            if isinstance(function, tuple):
                if manage_bootloader_function == function[0]:
                    doing_bootloader_operations = True
                    break

        logger.error("handle_filesystem_check_return_values(): "+exec_list[0]
                     +" Errored with exit value "+str(retval)
                     +"! This could indicate filesystem corruption or bad sectors!")

        if doing_bootloader_operations:
            logger.error("handle_filesystem_check_return_values(): Asking the user whether to "
                         + "skip bootloader operations...")

            result = DialogTools.show_yes_no_dlg(message="Error! The filesystem checker gave "
                                                 + "exit value: "+str(retval)+"! This could "
                                                 + "indicate filesystem corruption, a problem "
                                                 + "with the filesystem checker, or bad sectors "
                                                 + "on partition: "+partition+". If you perform "
                                                 + "bootloader operations on this partition, your "
                                                 + "system could become unstable or unbootable. "
                                                 + "Do you want to disable bootloader operations, "
                                                 + "as is strongly recommended?",
                                                 title="WxFixBoot - Disable Bootloader "
                                                 + "Operations?",
                                                 buttons=("Disable Bootloader Operations",
                                                          "Ignore and Continue Anyway"))

            if result:
                #A good choice. WxFixBoot will now disable any bootloader operations.
                logger.warning("handle_filesystem_check_return_values(): User disabled bootloader "
                               + "operations as recommended, due to bad sectors/HDD problems/FS "
                               + "Checker problems...")

                SYSTEM_INFO["DisableBootloaderOperations"] = True
                SYSTEM_INFO["DisableBootloaderOperationsBecause"] \
                .append("Filesystem corruption was detected on "+partition)

            else:
                #Seriously? Well, okay, we'll do it anyway... This is probably a very bad idea...
                logger.warning("handle_filesystem_check_return_values(): User ignored the warning "
                               + "and went ahead with bootloader modifications (if any) anyway, "
                               + "even with possible HDD problems/Bad sectors! This is a REALLY "
                               + "bad idea, but we'll do it anyway, as requested...")
