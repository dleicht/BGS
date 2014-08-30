#  main.py 30.08.14 - 13:03
#  
#  Copyright 2014 Ekianjo and Dominik Leicht (kickass) <domi.leicht@gmail.com>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
#  This software was designed to be freeware.

'''
BGS - Backup Game Saves v0.2.5.0
-----------------------
Initial app design by Ekianjo up until v0.2.4.2
Code refinement and additions since v0.2.5.0 by kickass
-----------------------
Version history:

v0.2.5.0 (Aug 2014):	added google drive support:
                        changed the gui design
                        introduced a backup logging file (bgs.log)
                        (backups on a per game/emulator basis)
                        (restore functionality)
-----------------------
BGS has 3 main funtions:

1. Search your handheld for games/emulators and offer to archive the corresponding gamesaves in a backup file to prevent data loss.
2. Send that backup file to the cloud automatically (google drive a.t.m.).
3. Automatically restore from an earlier backup.

BGS now uses pydrive (http://pythonhosted.org/PyDrive/) to manage google drive file access and authorization.
I had to rewrite a portion of pydrive's code to make browser based authorization work on the pandora.
So it's kind of tailored specifically for the pandora and may not work on other devices. Keep that in mind if you want to use that code.

BGS will upload/download backup files to/from a "_bgs" folder in your drive account.
The idea behind google drive support is this:
You probably play the same game on different platforms (linux, win, pandora, damn, maybe even xbox360...).
With cloud backups you take your gamesaves with you and do not depend on an individual system (as emulators run on many platforms).
Also its a reliable mechanism to prevent data loss.

Please enjoy this software as much as we do :)

ToDo List:
- add additional cloud services
- write a proper gui
'''

# Let the code begin...
import os, sys, tarfile, shutil, itertools
import PyZenity, glob
from pydrive.auth import GoogleAuth, CheckAuth
from pydrive.drive import GoogleDrive
from datetime import datetime


def add2log(lfile, logdate, archivefile, dirs):
    try:
        with open(lfile, 'a') as handle:
            handle.write(str(logdate) + ": " + archivefile + " " + str(dirs) + "\n")
        print "\nLog entry added..."
    except Exception as err:
        print err


def checkbrowsers(browserlist): # check a list of .desktop files for existance and add items to a list of existing browsers.
    availablebrowsers = []
    for val in browserlist.itervalues():
        if os.path.isfile(val[1]):
            availablebrowsers.append(val)
    return availablebrowsers


def parsedesktopfile(browserlist): # parse the existing browsers for their respective pnd_run commands.
    for item in browserlist:
        try:
            with open(item[1], "r") as handle:
                for line in handle:
                    if line.startswith("Exec"):
                        execline = line.strip("Exec=")
                        print "Exec line found - containing the following cmd path:"
                        print execline
                        l = []
                        l.append(item[0])
                        l.append(item[1])
                        l.append(execline.strip('\n\r'))
                        browsercmds.append(l)
                    else:
                        pass
        except Exception as err:
            print err
    return browsercmds # returns a list of browsername[0], path of desktopfile[1], pnd_run command[2]


def kindofbackup(): # this is kind of a main menu
    choicelist = [["Local backup only"], ["Local + cloud backup"], ["Restore from backup"]]
    a = PyZenity.List(["Your choice"],
        text="BGS - Your trusty savegame backup solution\n\nThis little tool will search your handheld for installed games/emulators\nand will then backup the corresponding savegames\nor restore savegames from an earlier backup.",
        title="BGS - Backup Game Saves", height=300, editable=False, select_col=1, window_icon=iconfile,
        data=choicelist)
    return a


def backupspecific(progname, appdatafolder, listfolders, listfiles): # crawl the list of templates for path/filenames with gamesaves and get them ready to be archived
    global directories, directorytobackup, programsfound
    for topdirectory in directories:
        workingfolder = checkprogram(progname, topdirectory)
        if workingfolder != "":
            programsfound.append(progname)
            print "working folder is " + workingfolder #confirm the top level working folder under /media/xx/pandora/PAF  - it is not used after expect for path
            if checkappdata(appdatafolder, topdirectory) == False:
                print "the program " + progname + ".pnd does not have a appdata folder so far."
            else:
                directoriesinappfolder = os.listdir(("/media/{0}/pandora/appdata/{1}".format(topdirectory, appdatafolder)))#special case of ALLFOLDER: where everything is to backup in the said folder
                if listfolders[0] == '*ALLFOLDER*':
                    directorytobackup.append(("/media/{0}/pandora/appdata/{1}").format(topdirectory, appdatafolder))
                else:
                    #marks folders to save
                    for onefolder in directoriesinappfolder:
                        for foldertobackup in listfolders:
                            if onefolder == foldertobackup:
                                print progname + ":found folder " + onefolder + " to backup"
                                directorytobackup.append(("/media/{0}/pandora/appdata/{1}/{2}").format(topdirectory, appdatafolder, onefolder)) #add the path worklist to backup where we will give the final instructions to zip in the end
                            #need to build functions for files as well
                    for filetobackup in listfiles:
                        result = []
                        result = glob.glob("/media/{0}/pandora/appdata/{1}/{2}".format(topdirectory, appdatafolder, filetobackup))
                        if result != []:
                            for resultat in result:
                                directorytobackup.append(resultat)


def makearchivefile(folders): # build the actual archive from given path/filenames
    global directorytobackup, directories, today, shutil, archivename, archivefile
    sizeofarchive = 0
    pathtoarchive = ""
    archivename = "BGSfile{0}.tar.bz2".format(today)
    pathtoarchive = PyZenity.GetDirectory(multiple=False, title="Choose a path for your backup:", window_icon=iconfile, selected="/media", sep=None)
    if pathtoarchive == None:
        print "Canceled by user..."
        sys.exit()
    else:
        #print "pathtoarchive:"
        #print pathtoarchive
        archivefile = pathtoarchive[0] + "/" + archivename # Maybe pathtoarchive is a list, maybe use [0]
        print "Chosen path for the archive: " + archivefile
        if os.path.isfile(archivefile) == True:
            print "Careful, an archive with the same name already exists."
        tar = tarfile.open(archivefile, "w:bz2")
        #define nb of directories to backup
        nbdirectoriestobackup = float(len(folders))
        print nbdirectoriestobackup
        #there will probably be bugs inside this part... need to check it out!!
        # kickass: funny, you imported PyZenity on purpose to make things easier, but decided to not use it in this case. i wonder why...
        #cmd = 'zenity --progress --text="Backing Up Games Saves..." --auto-close'
        #proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        proc = PyZenity.Progress(title="BGS - Backup Game Saves", text=folders[0], auto_close=True, no_cancel=True)
        n = 0.0
        for folder in folders:
            n += 1
            print n
            tar.add(folder)
            print "added " + folder
            progress = int(100 * (float(n / nbdirectoriestobackup)))
            print progress
            if progress < 100:
                proc(progress, folder)
            else:
                proc(progress)
        tar.close()
    sizeofarchive = int((os.path.getsize(archivefile)) / (1024 * 1024))
    a = PyZenity.Question(text="Backup has been completed as:\n" + archivefile + "\n\nThe file size is:\n" + str(sizeofarchive) + " Mb.\n\nDo you want to copy it to another location (redundancy, y'know')?\nIt makes sense to use a different disk here.", window_icon=iconfile)
    if a == True:
        pathtocopy = PyZenity.GetDirectory(multiple=False, title="Choose a path for the copy of your backup:", window_icon=iconfile, selected="/media", sep=None)
        if pathtoarchive == None:
            print "Canceled by user..."
            sys.exit()
        else:
            cfile = pathtocopy[0] + "/" + archivename
            print "pathtocopy:"
            print pathtocopy
            print "cfile: " + cfile
            try:
                shutil.copyfile(archivefile, cfile) # copy
                a = PyZenity.InfoMessage(text=archivefile + "\n was successfully copied to\n" + cfile, window_icon=iconfile)
            except Exception as err:
                a = PyZenity.Warning(text="Whoooooops, something went wrong.\nHere's an error msg for you:'\n\n" + err, title="BGS - Backup Save Games", window_icon=iconfile)
                bgs()
    else:
        pass


def checkprogram(progname, directory): #returns folder if the PND is found in one of the appsfolder directory or "" if not found
    global appsfolder
    found = 0
    for folder in appsfolder:
        if os.path.isfile("/media/{0}/pandora/{1}/{2}".format(directory, folder, progname)) == True:
            print "Found " + progname + " in " + folder + " in " + directory
            found += 1
        if found == 0:
            return ""
        else:
            return folder


def checkappdata(appdatafolder, directory): #checks if the related appfolder exists
    if os.path.isdir("/media/{0}/pandora/appdata/{1}".format(directory, appdatafolder)) == True:
        return True
    else:
        return False


def checkfolderexists(path, foldername): #checks if a certain folder exists
    if os.path.isdir(path + foldername):
        return True
    else:
        return False


def defineglobaldirectories(): #define the top levels directories in /media and writes a global variable
    global directories, debug
    directories = os.listdir("/media")
    directories.remove("hdd")
    directories.remove("ram")
    for directory in directories:
        if directory[0] == ".":
            directories.remove(directory)
    if debug == True:
        print directories


def findpreviousbgs(): #finds previous BGS files if they exist and ask to erase or not
    global directories
    result = []
    for topdirectory in directories:
        caca = glob.glob('/media/{0}/BGS*'.format(topdirectory))
        if caca != []:
            for element in caca:
                result.append(element)
    if result != []:
        print "\nFound previous bgs archives:"
        print result
        resultstring = ""
        sizetotal = 0
        for element in result:
            resultstring += element + "\n"
            sizetotal += int((os.path.getsize(element)) / (1024 * 1024))
        a = PyZenity.Question(text="I found previous BGS archives:\n{0}\nThey are taking a total of {1} Mb in size.\n\nWould you like to delete them?".format(resultstring, str(sizetotal)), title="BGS - Backup Game Saves", window_icon=iconfile)
        if a == True:
            for element in result:
                os.remove(element)
                print element + " removed."
        else:
            print "Previous archives were kept."


def displayprogstobackup(list): #displays the list of programs found to be backed up for save data
    global programsfound, proglist, backupsize
    #backupsize = evaluatebackupsizebeforearchive() The user will choose which games to backup in this dialog now. So giving an estimation of the archive size upfront doesnt make sense anymore...
    a = PyZenity.List(["#","Game"], text="Found the following games/emulators.\nPlease select which you'd like to backup:", title="BGS - Backup Save Games", boolstyle="checklist", window_icon=iconfile, height=400, editable=False, select_col=None, sep='|', data=list)
    return a


def evaluatebackupsizebeforearchive(): #will give an estimation of the size to backup before doing the actual archive
    global directorytobackup
    totalsizetop = 0
    for directory in directorytobackup:
        totalsizetop += getsize(directory)
    print totalsizetop
    totalsizetop = int(totalsizetop / 1024 / 1024)
    print totalsizetop
    return totalsizetop


def getsize(startpath): #thanks stackoverflow!
    totalsize = 0
    for dirpath, dirnames, filenames in os.walk(startpath):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            totalsize += os.path.getsize(fp)
    return totalsize


def initiategauth(): # get google authentication done properly. this, of course, does NOT need to be done with every file transaction.
    global gauth, drive
    gauth = GoogleAuth()
    print "Creating a local webserver and auto handle authentication..."
    try:
        gauth.LocalWebserverAuth(browsercmd=browsers[0][2]) # Creates local webserver and auto handles authentication
        global drive
        drive = GoogleDrive(gauth)
    except Exception as err:
        print err
        a = PyZenity.Warning(text="Whoooooops, something went wrong.\nHere's an error msg for you:'\n\n" + str(err), window_icon=iconfile)
        bgs()

def fileupload(fid, aname, afile): # upload a file to gdrive - fid is the fileID of the parent folder (_bgs), fname is the filename, of course
    global drive
    newfile = drive.CreateFile({'title': aname, "parents": [{"kind": "drive#fileLink", "id": fid}]})
    print "Now uploading: " + aname + "\nto folder: " + fid
    newfile.SetContentFile(afile)
    try:
        proc = PyZenity.Progress(text='Uploading ' + aname, title='BGS - Backup Game Saves', auto_close=True, percentage=1, pulsate=True, no_cancel=True)(0)
        newfile.Upload()
        print "upload done!"
    except Exception as err:
        print err
        a = PyZenity.Warning(text="Whoooooops, something went wrong.\nHere's an error msg for you:'\n\n" + str(err), window_icon=iconfile)
        bgs()


def checkbgsfolder(): # check for a _bgs folder in the root dir of the gdrive account. if none is found it will be created.
    global folderid
    folderthere = False
    file_list = drive.ListFile({'q': "'root' in parents and trashed=false"}).GetList()
    print "Contents of the gdrive root folder:"
    for file1 in file_list: # Auto-iterate through all files that match this query
        print 'title: %s, id: %s' % (file1['title'].encode('utf8'), file1['id'].encode('utf8'))
        if "_bgs" in file1['title'].encode('utf8'):
            folderthere = True
            folderid = str(file1['id'].encode('utf8'))
        else:
            pass
    if folderthere is True:
        print "_bgs folder already there!"
        print "_bgs folder id: " + folderid
    else:
        newdir = drive.CreateFile({'title': '_bgs', 'mimeType': 'application/vnd.google-apps.folder'}) # in the gdrive api folders are just files with a specific mime-type
        newdir.Upload()
        print "Created _bgs folder..."
        print "Re-checking for the folder to get the id..."
        checkbgsfolder()


def byebye():
    a = PyZenity.InfoMessage(text="All done!\nThanks for using BGS :)", title="BGS - Backup Game Saves",
        window_icon=iconfile)
    print "\nAll done. Thanks for using BGS!"


def internet_on():
    nstat = os.system('ping -c 1 8.8.8.8')
    return nstat

def untarbackup():
    a = PyZenity.Warning(text="You seriously should ONLY\nrestore BGS made backups with this tool.\nYou risk data loss and/or disk damage otherwise.\n\nYou've been warned.", title="BGS - Backup Save Games", window_icon=iconfile)
    if a is True:
        file2untar = PyZenity.GetFilename(multiple=False, title="Choose a BGS made backup to restore:", window_icon=iconfile)
        if file2untar:
            try:
                print "Chosen backup file: "+str(file2untar[0])
                tar = tarfile.open(file2untar[0], mode="r:bz2")
                print "\n\nTrying to extract the archive to / ...\n\n"
                for tarinfo in tar:
                    print tarinfo.name, "is", tarinfo.size, "bytes in size and is",
                    if tarinfo.isreg():
                        print "a regular file."
                    elif tarinfo.isdir():
                        print "a directory."
                    else:
                        print "something else."
                    tar.extract(path="/",member=tarinfo)
                tar.close()
            except Exception as err:
                a = PyZenity.Warning(text="Whoooooops, something went wrong.\nHere's an error msg for you:'\n\n" + err, title="BGS - Backup Save Games", window_icon=iconfile)
                bgs()
        else:
            bgs()
    else:
        bgs()


def bgs(): # main app
    # Variables galore...
    global today, uploaddone, listoftemplates, browserdict, availablebrowsers, browsercmds, browsers, appsfolder, directorytobackup, programsfound, emptylist, directories, debug, appdatapath, mypath, cfgfile, mypath, iconfile, logfile, gauth
    today = datetime.today().strftime("%Y-%m-%d_%H%M%S")
    #get media list in /media and record them in variable
    #check if they are still here at launch of the application
    #template should contain following info: name of pnd, name of appdata folder, folder with save files, file extension of save file
    listoftemplates = [
        ("gambatte.pnd", "gambatte-qt", ['saves', '.config'], [], [])
        , ('pcsx_rearmed_r19.pnd', 'pcsx_rearmed', ['.pcsx', 'screenshots'], [], [])
        , ('drastic.pnd', 'DraStic', ['.links', 'backup', 'config', 'profiles', 'savestates'], [], [])
        , ('PPSSPP.pnd', 'PPSSPP', ['*ALLFOLDER*'], [], [])
        , ('gpSP-pnd-0.9-2Xb-u8a.pnd', 'gpsp', ['', ''], [], [])
        , ('UAE4ALLv2.0.pnd', 'uae4all', ['saves', 'conf'], [], [])
        , ('snes9x4p_20120226.pnd', 'snes9x.skeezix.alpha', ['.snes96_snapshots'], [], [])
        , ('gpfce_r2.pnd', 'gpfce', ['fceultra'], [], [])
        , ('gngeo_0.8.5.pnd', 'gngeo_pepone', ['save', 'conf'], [], [])
        , ('fba.pnd', 'fba-dave18', ['savestates', 'screenshots', 'conf', 'config'], [], [])
        , ('apkenv-v42.3.17.2.pnd', 'apkenv', ['data'], [], [])
        , ('darkplaces.pnd', 'darkplaces', ['.darkplaces'], [], [])
        , ('dunedynasty.pnd', 'dunedynasty', ['dunedynasty'], [], [])
        , ('scummvm-op.pnd', 'scummvm', ['saves'], [], [])
        , ('rtcw.pnd', 'rtcw', ['home'], [], [])
        , ('PicoDrive_190.pnd', 'picodrive', ['srm', 'mds', 'cfg', 'brm'], [], [])
        , ('freespace2.pnd', 'freespace2', ['home'], [], [])
        , ('exult-1.4.pnd', 'exult', ['.exult'], [], [])
        , ('cdoom.pnd', 'doom', ['.chocolate-doom'], [], [])
        , ('solarusdx-zsdx-11201.pnd', 'solarusdx', ['.solarus'], [], [])
        , ('pewpew2.pnd', 'pewpew2', ['documents'], [], [])
        , ('duke3d.pnd', 'duke3d', ['.eduke32'], [], [])
        , ('8Blitter.pnd', '8blitter.lordus', ['data'], [], [])
        , ('pushover.pnd', 'pushover', ['.pushover'], [], [])
        , ('projectx_ptitseb.pnd', 'projectx', ['savegame'], [], [])
        , ('nubnub.pnd', 'nubnub', ['*ALLFOLDER*'], ['uploadedscore', 'settings', 'hiscore'], [])
        , ('mupen64plus2.pnd', 'mupen64plus2', ['*ALLFOLDER*'], [], [])
        , ('prequengine.pnd', 'prequengine', ['save'], [], [])
        , ('vvvvvv.pnd', 'vvvvvv', ['.vvvvvv'], [], [])
        , ('outofthisworld.pnd', 'outofthisworld', ['home'], [], [])
        , ('paperwars-v1.0.0-ekianjo.pnd', 'paperwars', ['Save'], [], [])
        , ('homeworld.pnd', 'homeworld', ['cfg'], [], [])
        , ('freeciv.pnd', 'freeciv', ['*ALLFOLDER*'], [], [])
        , ('microbes1.0rel2-1.pnd', 'microbes', ['*ALLFOLDER*'], [], [])
        , ('mooboy.mrz.pnd', 'mooboy.mrz', ['*ALLFOLDER*'], [], [])
        , ('area2048_m-ht.pnd', 'area2048', ['*ALLFOLDER*'], [], [])
        , ('bosonx.pnd', 'bosonx', ['*ALLFOLDER*'], [], [])
        , ('zdoom.pnd', 'zdoom', ['*ALLFOLDER*'], [], [])
        , ('widelands.pnd', 'widelands', ['*ALLFOLDER*'], [], [])
        , ('super_hexagon_full.pnd', 'super_hexagon', ['*ALLFOLDER*'], [], [])
        , ('snowman.pnd', 'snowman-reloaded', ['*ALLFOLDER*'], [], [])
        , ('nanolemmings.pnd', 'nanolemmings', ['*ALLFOLDER*'], [], [])
        , ('doublecross.pnd', 'doublecross', ['*ALLFOLDER*'], [], [])
        , ('dopewars.pnd', 'dopewars', ['*ALLFOLDER*'], [], [])
        , ('metroidclassic.pnd', 'metroidclassic', ['*ALLFOLDER*'], [], [])
        , ('notpacman_ptitseb.pnd', 'notpacman', ['*ALLFOLDER*'], [], [])
        , ('nottetris.pnd', 'nottetris', ['*ALLFOLDER*'], [], [])
        , ('openttd.pnd', 'openttd', ['*ALLFOLDER*'], [], [])
        , ('reicast.pnd', 'reicast', ['*ALLFOLDER*'], [], [])
        #,('starcraft.pnd','starcraft',['',''],[],[])
        #,('','',['',''],[],[])
    ]
    # browserdict is a dictionary template to look for installed javascript capable browsers (assuming there are .desktop files in /usr/share/applications) as we need one of those to do google auth. the pnd_run call will be parsed from the desktopfile.
    browserdict = {"firefox": ["firefox", "/usr/share/applications/hdonk_firefox_001#0.desktop"],
                   "qupzilla": ["qupzilla", "/usr/share/applications/qupzilla-app#0.desktop"],
                   "babypanda": ["babypanda", "/usr/share/applications/babypanda-app#0.desktop"]}
    availablebrowsers = []
    uploaddone = False
    browsercmds = []
    browsers = []
    appsfolder = ['menu', 'desktop', 'apps']
    directorytobackup = []
    programsfound = []
    emptylist = []
    directories = ""
    debug = False
    prog_folder_couple = []
    prog_folder_list = []
    cfgfile = ""
    #appdatapath = os.getenv('APPDATADIR')
    mypath = os.getenv('HOME')
    appdatapath = mypath
    logfile = appdatapath + "/bgs.log"
    iconfile = mypath + "/icon.png"
    defineglobaldirectories()
    backupchoice = kindofbackup()
    if backupchoice == None:
        print "Canceled by user..."
        sys.exit()
# Local backup routine
    elif backupchoice[0] == "Local backup only":
        findpreviousbgs()
        for programtobackup in listoftemplates:
            backupspecific(programtobackup[0], programtobackup[1], programtobackup[2], programtobackup[3])
            if directorytobackup != []: # check listoftemplates for programs, if directorytobackup is NOT empty, the program seems to be available for backup
                prog_folder_couple.append(programtobackup[0]) # add the program .pnd name to a list of program+[folders] couple list (on a per program basis - so the program name and corresponding folders will be coupled properly
                prog_folder_couple.append(directorytobackup) # add the folders to that same couple list
                directorytobackup = [] # make sure these folders will not be used for the next program
                prog_folder_list.append(prog_folder_couple) # add the couple list to a list of all couples
                prog_folder_couple = []
            else:
                pass
        #print "prog_folder_list:\n"
        #print prog_folder_list
        bgs_dict = dict(prog_folder_list) # now this is really cool: using a dictionary with prognames as keys, we can easily ask for prognames to be backuped and parse the dictionary for the corresponding values to automatically get the right folders!
        print "\nDictionary of games:folders available for backup (bgs_dict):\n"
        print bgs_dict
        gamelist = []
        glist = []
        for item in bgs_dict.keys():
            gamelist.append("")
            gamelist.append(item)
            glist.append(gamelist)
            gamelist = []
        #print glist
        progdisplay = displayprogstobackup(glist)
        if progdisplay == None:
            print "Canceled by user..."
            sys.exit()
        elif progdisplay == [""]:
            print "No choice was made."
            a = PyZenity.Warning(text="Please choose at least one game to backup!", title="BGS - Backup Save Games", window_icon=iconfile)
            bgs()
        else:
            print "\nChosen progs to backup:\n"
            print progdisplay
            chosendirstobackup_ = []
            for item in progdisplay:
                chosendirstobackup_.append(bgs_dict[item]) # parse the dictionary for values(folders) of the chosen items(prognames).
            chosendirstobackup = list(itertools.chain(*chosendirstobackup_)) # proper usage of itertools to flatten a nested list of lists :) note there's two lists here: chosendirstobackup_ and chosendirstobackup
            print "\nWill now start makearchivefile() with the following folders:"
            print chosendirstobackup
            makearchivefile(chosendirstobackup)
            add2log(logfile, today, archivefile, chosendirstobackup)
            byebye()
            bgs()
# Local + cloud backup routine
    elif backupchoice[0] == "Local + cloud backup":
        findpreviousbgs()
        for programtobackup in listoftemplates:
            backupspecific(programtobackup[0], programtobackup[1], programtobackup[2], programtobackup[3])
            if directorytobackup != []: # check listoftemplates for programs, if directorytobackup is NOT empty, the program seems to be available for backup
                prog_folder_couple.append(programtobackup[0]) # add the program .pnd name to a list of program+[folders] couple list (on a per program basis - so the program name and corresponding folders will be coupled properly
                prog_folder_couple.append(directorytobackup) # add the folders to that same couple list
                directorytobackup = [] # make sure these folders will not be used for the next program
                prog_folder_list.append(prog_folder_couple) # add the couple list to a list of all couples
                prog_folder_couple = []
            else:
                pass
        #print "prog_folder_list:\n"
        #print prog_folder_list
        bgs_dict = dict(prog_folder_list) # now this is really cool: using a dictionary with prognames as keys, we can easily ask for prognames to be backuped and parse the dictionary for the corresponding values to automatically get the right folders!
        print "\nDictionary of games:folders available for backup (bgs_dict):\n"
        print bgs_dict
        gamelist = []
        glist = []
        for item in bgs_dict.keys():
            gamelist.append("")
            gamelist.append(item)
            glist.append(gamelist)
            gamelist = []
            #print glist
        progdisplay = displayprogstobackup(glist)
        if progdisplay == None:
            print "Canceled by user..."
            sys.exit()
        elif progdisplay == [""]:
            print "No choice was made."
            a = PyZenity.Warning(text="Please choose at least one game to backup!", title="BGS - Backup Save Games", window_icon=iconfile)
            bgs()
        else:
            print "\nChosen progs to backup:\n"
            print progdisplay
            chosendirstobackup_ = []
            for item in progdisplay:
                chosendirstobackup_.append(bgs_dict[item]) # parse the dictionary for values(folders) of the chosen items(prognames).
            chosendirstobackup = list(itertools.chain(*chosendirstobackup_)) # proper usage of itertools to flatten a nested list of lists :) note there's two lists here: chosendirstobackup_ and chosendirstobackup
            print "\nWill now start makearchivefile() with the following folders:"
            print chosendirstobackup
            makearchivefile(chosendirstobackup)
            add2log(logfile, today, archivefile, chosendirstobackup)
            browsers = parsedesktopfile(checkbrowsers(browserdict))
            print "\nFound the following browsers:"
            print browsers
            for item in browsers:
                print "found: " + item[0] + " here:" + item[2]
                print
            if internet_on() != 0:
                a = PyZenity.Warning(text="Can't reach the interwebs!\nGo check your connection.", title="BGS - Backup Save Games", window_icon=iconfile)
                bgs()
            else:
                if browsers == "":
                    a = PyZenity.Warning(text="None of the required browsers [firefox,babypanda,qupzilla] seem to be installed.\nWe need one of these for Google authentication.\nPlease install at least one of them.", title="BGS - Backup Save Games", window_icon=iconfile)
                    bgs()
                else:
                    if not gauth or gauth.access_token_expired is True: # Check if GoogleAuth() has not been invoked before and if the Google Drive Access Token has expired. If so: initiate GoogleAuth()
                        print "Google Auth needed..."
                        initiategauth()
                        print "gauth.access_token_expired = " + str(gauth.access_token_expired)
                    else:
                        print "gauth.access_token_expired = " + str(gauth.access_token_expired)
                        print "Google Auth already handled..."
                    checkbgsfolder()
                    fileupload(folderid, archivename, archivefile)
                    byebye()
                    bgs()
# Restore routine
    else:
        untarbackup()
        byebye()
        bgs()
global gauth
gauth = None
bgs()