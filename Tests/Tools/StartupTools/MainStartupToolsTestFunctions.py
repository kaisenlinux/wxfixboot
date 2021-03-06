#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# MainStartupTools test functions for WxFixBoot
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

#Import modules.
import sys
import os

#Import other modules.
sys.path.append('../../..') #Need to be able to import the Tools module from here.

import Tools.coretools as CoreTools
from Tools.dictionaries import *
import Tools.StartupTools.core as CoreStartupTools
import Tests.DialogFunctionsForTests as DialogTools

WOULD_EMERGENCY_EXIT = False
WOULD_EMERGENCY_EXIT_BECAUSE = []

def emergency_exit(message):
    """
    Test suite special: sets a variable so the tests know if an Emergency Exit
    would have been triggered.
    """

    global WOULD_EMERGENCY_EXIT
    global WOULD_EMERGENCY_EXIT_BECAUSE

    WOULD_EMERGENCY_EXIT = True
    WOULD_EMERGENCY_EXIT_BECAUSE.append(message)

def check_depends():
    """
    Check dependencies, and show an error message and kill the app if the dependencies are not met.
    """

    #Create a temporary list to allow WxFixBoot to notify the user of particular unmet
    #dependencies.
    cmd_list = ("cp", "mv", "which", "uname", "fsck", "ls", "modprobe", "mount", "umount",
                "rm", "ping", "badblocks", "arch", "file", "sh", "echo", "lshw",
                "lvdisplay", "dmidecode", "chroot", "strings", "dd", "blkid")

    #Create a list to contain names of failed commands.
    failed_list = []

    for command in cmd_list:
        #Run the command with its argument and log the output (if in debug mode)
        retval = CoreTools.start_process("which "+command, return_output=True)[0]

        if retval != 0:
            failed_list.append(command)

    #Check if any commands failed.
    if failed_list != []:
        #Missing dependencies!
        emergency_exit("The following dependencies could not be found on your system: "
                       + ', '.join(failed_list)+".\n\nPlease install the missing dependencies.")

def get_oss():
    """Get the names of all OSs on the HDDs."""
    root_fs = CoreTools.get_partition_mounted_at("/")

    #Get Linux OSs.
    keys = list(DISK_INFO.keys())
    keys.sort()

    for partition in keys:
        if DISK_INFO[partition]["Type"] == "Device":
            continue

        elif DISK_INFO[partition]["FileSystem"] in ("hfsplus", "hfs", "apfs"):
            #Look for Mac OS X.
            os_name = "Mac OS X ("+partition+")"

            #Check if we need to mount the partition.
            was_mounted = False

            if CoreTools.is_mounted(partition):
                #If mounted, get the mountpoint.
                mount_point = CoreTools.get_mount_point_of(partition)

            else:
                #Mount the partition and check if anything went wrong.
                mount_point = "/mnt/wxfixboot/mountpoints"+partition

                if CoreTools.mount_partition(partition=partition, mount_point=mount_point) != 0:
                    #Ignore the partition.
                    continue

                was_mounted = True

            if os.path.exists(mount_point+"/mach_kernel") or os.path.exists(mount_point+"/System/Library/Kernels/kernel"):
                #Create OS_INFO entry for it.
                OS_INFO[os_name] = {}
                OS_INFO[os_name]["Name"] = os_name
                OS_INFO[os_name]["IsCurrentOS"] = False
                OS_INFO[os_name]["Arch"] = "Unknown"
                OS_INFO[os_name]["Partition"] = partition
                OS_INFO[os_name]["PackageManager"] = "Mac App Store"
                OS_INFO[os_name]["RawFSTabInfo"], OS_INFO[os_name]["EFIPartition"], OS_INFO[os_name]["BootPartition"] = (["Unknown"], "Unknown", "Unknown")

            #Unmount the filesystem if needed.
            if was_mounted:
                if CoreTools.unmount(mount_point) != 0:
                    break
                    #CoreTools.emergency_exit("Couldn't unmount "+partition+" after looking for"
                    #                         + "operating systems on it! Please reboot your "
                    #                         + "computer and try again.")

        elif DISK_INFO[partition]["FileSystem"] in ("vfat", "ntfs", "exfat"):
            #Look for Windows. NOTE: It seems NTFS volumes can't be mounted twice, which is why
            #we're being more careful here.
            #Check if we need to mount the partition.
            was_mounted = False

            if CoreTools.is_mounted(partition):
                #If mounted, get the mountpoint.
                mount_point = CoreTools.get_mount_point_of(partition)

            else:
                #Mount the partition and check if anything went wrong.
                mount_point = "/mnt/wxfixboot/mountpoints"+partition

                if CoreTools.mount_partition(partition=partition, mount_point=mount_point) != 0:
                    #Ignore the partition.
                    continue

                was_mounted = True

            #Check if there's a Windows/WinNT dir.
            if not (os.path.isdir(mount_point+"/WinNT") or os.path.isdir(mount_point+"/Windows") or os.path.isdir(mount_point+"/WINDOWS")):
                #Skip this partition, and unmount if needed.
                pass

            else:
                #Look for lots of different Windows editions.
                if CoreStartupTools.has_windows_9x(mount_point):
                    os_name = "Windows 95/98/ME"

                elif CoreStartupTools.has_windows_xp(mount_point):
                    os_name = "Windows XP"

                elif CoreStartupTools.has_windows_vista(mount_point):
                    os_name = "Windows Vista"

                elif CoreStartupTools.has_windows_7(mount_point):
                    os_name = "Windows 7"

                elif CoreStartupTools.has_windows_8(mount_point):
                    os_name = "Windows 8/8.1"

                elif CoreStartupTools.has_windows_10(mount_point):
                    os_name = "Windows 10"

                else:
                    #Unknown Windows.
                    os_name = "Windows"

                #Create OS_INFO entry for it.
                os_name = os_name+" ("+partition+")"
                OS_INFO[os_name] = {}
                OS_INFO[os_name]["Name"] = os_name
                OS_INFO[os_name]["IsCurrentOS"] = False
                OS_INFO[os_name]["Arch"] = "Unknown"
                OS_INFO[os_name]["Partition"] = partition
                OS_INFO[os_name]["PackageManager"] = "Windows Installer"
                OS_INFO[os_name]["RawFSTabInfo"], OS_INFO[os_name]["EFIPartition"], OS_INFO[os_name]["BootPartition"] = (["Unknown"], "Unknown", "Unknown")

            #Unmount the filesystem if needed.
            if was_mounted:
                if CoreTools.unmount(mount_point) != 0:
                    break
                    #CoreTools.emergency_exit("Couldn't unmount "+partition+" after looking for"
                    #                         + "operating systems on it! Please reboot your "
                    #                         + "computer and try again.")

        else:
            #Look for Linux.
            #The python command runs on python 2 and python 3.
            #If there are aliases for partition, check if the root FS is one of those too.
            root_fs_is_alias = False

            if "Aliases" in DISK_INFO[partition]:
                root_fs_is_alias = (root_fs in DISK_INFO[partition]["Aliases"])

            if partition == root_fs or root_fs_is_alias:
                cmd = "python -c \"from __future__ import print_function; import platform; print(' '.join(platform.linux_distribution()));\""
                apt_cmd = "which apt-get"
                dnf_cmd = "which dnf"
                chroot = False
                is_current_os = True
                mount_point = ""

            else:
                mount_point = "/mnt/wxfixboot/mountpoints"+partition
                cmd = "chroot "+mount_point+" python -c \"from __future__ import print_function; import platform; print(' '.join(platform.linux_distribution()));\""
                apt_cmd = "chroot "+mount_point+" which apt-get"
                dnf_cmd = "chroot "+mount_point+" which dnf"
                chroot = True
                is_current_os = False

                #Mount the partition and check if anything went wrong.
                if CoreTools.mount_partition(partition=partition, mount_point=mount_point) != 0:
                    #Ignore the partition.
                    continue

            #Look for Linux on this partition.
            retval, temp = CoreTools.start_process(cmd, return_output=True)
            os_name = temp.replace('\n', '')

            #Run the function to get the architechure.
            os_arch = CoreStartupTools.determine_os_architecture(mount_point=mount_point)

            #If the OS's name wasn't found, but its architecture was, there must be an OS here,
            #so try to use lsb_release if possible before asking the user. Catch if the name is
            #just whitespace too.
            if (retval != 0 or os_name == "" or os_name.isspace()) and os_arch != None:
                os_name = CoreStartupTools.get_os_name_with_lsb(partition=partition,
                                                                mount_point=mount_point,
                                                                is_current_os=is_current_os)

                #If we really have to, ask the user.
                if os_name is None:
                    os_name = CoreStartupTools.ask_for_os_name(partition=partition,
                                                               is_current_os=is_current_os)

            #Look for APT.
            package_manager = CoreStartupTools.determine_package_manager(apt_cmd=apt_cmd,
                                                                         dnf_cmd=dnf_cmd) 

            #Also check if CoreStartupTools.ask_for_os_name was used to determine the name.
            #If the user skipped naming the OS, ignore it and skip the rest of this loop iteration.
            if os_name != None and os_arch != None and package_manager != "Unknown":
                #Add this information to OS_INFO.
                OS_INFO[os_name] = {}
                OS_INFO[os_name]["Name"] = os_name
                OS_INFO[os_name]["IsCurrentOS"] = is_current_os
                OS_INFO[os_name]["Arch"] = os_arch
                OS_INFO[os_name]["Partition"] = partition
                OS_INFO[os_name]["PackageManager"] = package_manager
                OS_INFO[os_name]["RawFSTabInfo"], OS_INFO[os_name]["EFIPartition"], OS_INFO[os_name]["BootPartition"] = CoreStartupTools.get_fstab_info(mount_point, os_name)

                if chroot is False:
                    SYSTEM_INFO["CurrentOS"] = OS_INFO[os_name].copy()

            if chroot:
                #Unmount the filesystem.
                if CoreTools.unmount(mount_point) != 0: break
                    #CoreTools.emergency_exit("Couldn't unmount "+partition+" after looking for"
                    #                         + "operating systems on it! Please reboot your "
                    #                         + "computer and try again.")

                #Remove the temporary mountpoint
                os.rmdir(mount_point)

    #Check that at least one OS was detected.
    if len(OS_INFO) >= 1:
        return OS_INFO, SYSTEM_INFO

    #Otherwise...
    return (False, False)

    #Exit.
    #CoreTools.emergency_exit("You don't appear to have any Linux installations on your hard disks. If you do have Linux installations but WxFixBoot hasn't found them, please file a bug or ask a question on WxFixBoot's launchpad page. If you're using Windows or Mac OS X, then sorry as WxFixBoot has no support for these operating systems. You could instead use the tools provided by Microsoft and Apple to fix any issues with your computer.")
